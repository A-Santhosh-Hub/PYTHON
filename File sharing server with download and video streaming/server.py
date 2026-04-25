import os
import re
import mimetypes
import hashlib
from pathlib import Path
from flask import (
    Flask, render_template, request, Response,
    abort, jsonify, send_file
)
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ─── Config ──────────────────────────────────────────────────────────────────
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

CHUNK_SIZE = 1024 * 1024  # 1 MB chunks for streaming

ICONS = {
    "video":  ["mp4","mkv","webm","avi","mov","flv","wmv","m4v","ts","3gp"],
    "audio":  ["mp3","flac","wav","aac","ogg","m4a","opus","wma"],
    "image":  ["jpg","jpeg","png","gif","webp","bmp","svg","ico","tiff","avif"],
    "pdf":    ["pdf"],
    "zip":    ["zip","rar","7z","tar","gz","bz2","xz"],
    "code":   ["py","js","ts","html","css","json","xml","yaml","yml","sh","bat","c","cpp","java","go","rs"],
    "text":   ["txt","md","log","csv","ini","cfg","conf"],
    "doc":    ["doc","docx","xls","xlsx","ppt","pptx","odt","ods","odp"],
}

def get_file_type(ext):
    ext = ext.lower().lstrip(".")
    for ftype, exts in ICONS.items():
        if ext in exts:
            return ftype
    return "file"

def human_size(size):
    for unit in ["B","KB","MB","GB","TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"

def list_dir(rel_path=""):
    base = Path(UPLOAD_FOLDER)
    target = (base / rel_path).resolve()
    if not str(target).startswith(str(base)):
        abort(403)
    if not target.exists():
        abort(404)

    items = []
    try:
        entries = sorted(target.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        abort(403)

    for entry in entries:
        if entry.name.startswith("."):
            continue
        is_dir = entry.is_dir()
        size = 0
        if not is_dir:
            try:
                size = entry.stat().st_size
            except:
                pass
        ext = entry.suffix if not is_dir else ""
        ftype = "folder" if is_dir else get_file_type(ext)
        items.append({
            "name":    entry.name,
            "type":    ftype,
            "ext":     ext.lstrip(".").lower(),
            "size":    human_size(size) if not is_dir else "",
            "size_raw": size,
            "is_dir":  is_dir,
            "path":    str(Path(rel_path) / entry.name).replace("\\", "/"),
        })
    return items

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/files")
def api_files():
    rel = request.args.get("path", "").strip("/")
    try:
        items = list_dir(rel)
        return jsonify({"ok": True, "path": rel, "items": items})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/stream/<path:filepath>")
def stream_file(filepath):
    """Stream file with Range request support — handles 6.8 GB videos."""
    base = Path(UPLOAD_FOLDER)
    target = (base / filepath).resolve()
    if not str(target).startswith(str(base)):
        abort(403)
    if not target.exists():
        abort(404)

    file_size = target.stat().st_size
    mime, _ = mimetypes.guess_type(str(target))
    mime = mime or "application/octet-stream"

    range_header = request.headers.get("Range")
    if range_header:
        # Parse bytes=start-end
        match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if not match:
            abort(416)
        start = int(match.group(1))
        end   = int(match.group(2)) if match.group(2) else file_size - 1
        end   = min(end, file_size - 1)
        length = end - start + 1

        def generate():
            with open(target, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    yield chunk
                    remaining -= len(chunk)

        headers = {
            "Content-Range":  f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges":  "bytes",
            "Content-Length": str(length),
            "Content-Type":   mime,
        }
        return Response(generate(), 206, headers=headers)
    else:
        # Full file stream
        def generate_full():
            with open(target, "rb") as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk

        headers = {
            "Accept-Ranges":  "bytes",
            "Content-Length": str(file_size),
            "Content-Type":   mime,
        }
        return Response(generate_full(), 200, headers=headers)

@app.route("/download/<path:filepath>")
def download_file(filepath):
    """Force-download with Content-Disposition: attachment."""
    base = Path(UPLOAD_FOLDER)
    target = (base / filepath).resolve()
    if not str(target).startswith(str(base)):
        abort(403)
    if not target.exists():
        abort(404)
    return send_file(target, as_attachment=True)

if __name__ == "__main__":
    print("=" * 55)
    print("  SanStudio File Server  —  http://localhost:5000")
    print("  Upload folder:", UPLOAD_FOLDER)
    print("=" * 55)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
