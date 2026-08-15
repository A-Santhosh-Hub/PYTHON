#!/usr/bin/env python3
"""
SanShare — share a whole folder over your local network and let someone
else browse and download it from a normal web browser. No pen drive, no
copying files twice.

One person (the "host") runs this on the machine that has the files:

    python server.py --folder "D:\\Games" --password 1234

Everyone else on the same Wi-Fi / LAN just opens a browser and goes to
the address this prints on startup. No install needed on their side.

Core pieces:
  - Directory browser (breadcrumbs, folders + files, sizes)          -> /  and /browse/<path>
  - Single file download, resumable if the connection drops          -> /download/<path>
  - Multi-select "download as one .zip" (streamed, not pre-built)    -> /download-zip
  - Optional password gate, since this may run on a shared office Wi-Fi
"""

from __future__ import annotations

import argparse
import os
import socket
from functools import wraps
from pathlib import Path

from flask import (
    Flask, Response, abort, redirect, render_template, request,
    session, stream_with_context, url_for,
)
from flask.helpers import send_from_directory
from zipstream import ZipStream

# ---------------------------------------------------------------------------
# Config (filled in by main() from the command line)
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = os.urandom(24)

ROOT_DIR: Path | None = None      # the folder being shared
ACCESS_PASSWORD: str | None = None  # optional shared password


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def human_size(num_bytes: float) -> str:
    """757 -> '757 B', 1536 -> '1.5 KB', etc."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024 or unit == "TB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.2f} PB"


def safe_join(base: Path, rel_path: str) -> Path:
    """
    Resolve rel_path underneath base and refuse anything that tries to
    escape it (../../, absolute paths, symlink tricks, etc). This is the
    one function every route relies on to keep browsing inside ROOT_DIR.
    """
    rel_path = (rel_path or "").strip().lstrip("/\\")
    candidate = (base / rel_path).resolve()
    base_resolved = base.resolve()
    if candidate != base_resolved and base_resolved not in candidate.parents:
        abort(403, description="That path is outside the shared folder.")
    return candidate


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if ACCESS_PASSWORD and not session.get("authed"):
            return redirect(url_for("login", next=request.full_path))
        return view(*args, **kwargs)
    return wrapped


# ---------------------------------------------------------------------------
# Auth (only active if --password was passed)
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if not ACCESS_PASSWORD:
        return redirect(url_for("browse"))

    error = None
    if request.method == "POST":
        if request.form.get("password", "") == ACCESS_PASSWORD:
            session["authed"] = True
            dest = request.args.get("next") or url_for("browse")
            return redirect(dest)
        error = "Wrong password — try again."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.pop("authed", None)
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Browsing
# ---------------------------------------------------------------------------

@app.route("/", defaults={"subpath": ""})
@app.route("/browse/<path:subpath>")
@login_required
def browse(subpath):
    current_dir = safe_join(ROOT_DIR, subpath)
    if not current_dir.is_dir():
        abort(404)

    folders, files = [], []
    try:
        with os.scandir(current_dir) as it:
            for entry in it:
                try:
                    rel = os.path.relpath(entry.path, ROOT_DIR).replace(os.sep, "/")
                    if entry.is_dir(follow_symlinks=False):
                        child_count = sum(1 for _ in os.scandir(entry.path))
                        folders.append({"name": entry.name, "rel_path": rel, "child_count": child_count})
                    else:
                        size = entry.stat().st_size
                        files.append({
                            "name": entry.name, "rel_path": rel,
                            "size": size, "size_h": human_size(size),
                        })
                except OSError:
                    continue  # unreadable entry (permissions, broken link) — skip it, don't crash the listing
    except PermissionError:
        abort(403)

    folders.sort(key=lambda e: e["name"].lower())
    files.sort(key=lambda e: e["name"].lower())

    rel_current = os.path.relpath(current_dir, ROOT_DIR).replace(os.sep, "/")
    if rel_current == ".":
        rel_current = ""

    crumbs = []
    if rel_current:
        parts = rel_current.split("/")
        for i, part in enumerate(parts):
            crumbs.append({"name": part, "rel_path": "/".join(parts[: i + 1])})

    return render_template(
        "index.html",
        folders=folders,
        files=files,
        crumbs=crumbs,
        current_path=rel_current,
        root_name=ROOT_DIR.name,
        has_password=bool(ACCESS_PASSWORD),
        is_root=(rel_current == ""),
    )


# ---------------------------------------------------------------------------
# Single-file download — resumable (Flask/Werkzeug handle Range headers
# automatically here via conditional=True, which is the default), so a
# dropped Wi-Fi connection on a 1GB file can pick back up instead of
# restarting from zero.
# ---------------------------------------------------------------------------

@app.route("/download/<path:filepath>")
@login_required
def download_file(filepath):
    target = safe_join(ROOT_DIR, filepath)
    if not target.is_file():
        abort(404)
    return send_from_directory(target.parent, target.name, as_attachment=True, conditional=True)


# ---------------------------------------------------------------------------
# Multi-select "download as .zip" — streamed on the fly, nothing written
# to disk on the host. Uses ZIP_STORED (no compression): game files are
# already compressed, so re-compressing just burns CPU for no size win —
# stored mode is faster and lets zipstream precompute the exact final
# size up front, so the browser still gets a real Content-Length and a
# real progress bar.
# ---------------------------------------------------------------------------

@app.route("/download-zip")
@login_required
def download_zip():
    raw_paths = request.args.getlist("paths")
    if not raw_paths:
        abort(400, description="No files or folders were selected.")

    resolved = []
    for rel in raw_paths:
        abs_path = safe_join(ROOT_DIR, rel)
        if not abs_path.exists():
            abort(404, description=f"Not found: {rel}")
        resolved.append(abs_path)

    if len(resolved) == 1:
        zip_name = f"{resolved[0].name}.zip"
    else:
        zip_name = f"{ROOT_DIR.name or 'files'}-selection.zip"

    zs = ZipStream(sized=True)  # compress_type defaults to ZIP_STORED
    for abs_path in resolved:
        zs.add_path(str(abs_path))

    resp = Response(stream_with_context(iter(zs)), mimetype="application/zip")
    resp.headers["Content-Disposition"] = f'attachment; filename="{zip_name}"'
    resp.headers["Content-Length"] = str(len(zs))
    return resp


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def get_local_ip() -> str:
    """Best-effort LAN IP — doesn't actually send any traffic, just asks
    the OS which local interface it would use to reach the internet."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    global ROOT_DIR, ACCESS_PASSWORD

    parser = argparse.ArgumentParser(description="Share a folder over your LAN via a web browser.")
    parser.add_argument("--folder", required=True, help="Full path to the folder you want to share")
    parser.add_argument("--port", type=int, default=5000, help="Port to run on (default: 5000)")
    parser.add_argument("--password", default=None, help="Optional password — recommended on shared/office Wi-Fi")
    args = parser.parse_args()

    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        raise SystemExit(f"Not a folder: {folder}")

    ROOT_DIR = folder
    ACCESS_PASSWORD = args.password
    ip = get_local_ip()

    print("=" * 64)
    print(f" Sharing:  {ROOT_DIR}")
    print(f" Open on any device on this Wi-Fi:   http://{ip}:{args.port}")
    print(f" Password protected: {'yes' if ACCESS_PASSWORD else 'no'}")
    print(" Press CTRL+C to stop sharing.")
    print("=" * 64)

    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=args.port, threads=8)
    except ImportError:
        print("(waitress not installed — using Flask's dev server instead. "
              "Run: pip install waitress   for a steadier server under big transfers.)")
        app.run(host="0.0.0.0", port=args.port, threaded=True)


if __name__ == "__main__":
    main()
