"""
DropStream - High-Speed Chunked File Upload Server
Supports: Pause/Resume, Large Files (6.8GB+), Multi-chunk parallel uploads
"""

import os
import json
import uuid
import time
import shutil
import hashlib
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ─── Config ────────────────────────────────────────────────────────────────────
UPLOAD_DIR = Path("uploads")
TEMP_DIR   = Path("temp_chunks")
UPLOAD_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

CHUNK_SIZE   = 5 * 1024 * 1024   # 5 MB per chunk
MAX_FILE_SIZE = 50 * 1024 * 1024 * 1024  # 50 GB max
SESSION_TTL   = 24 * 3600         # 24 hours

app = FastAPI(title="DropStream Upload Server", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── In-memory session store ───────────────────────────────────────────────────
sessions: dict[str, dict] = {}

def get_session(upload_id: str) -> dict:
    s = sessions.get(upload_id)
    if not s:
        raise HTTPException(404, "Upload session not found. It may have expired.")
    return s

def session_chunk_dir(upload_id: str) -> Path:
    d = TEMP_DIR / upload_id
    d.mkdir(exist_ok=True)
    return d

# ─── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """Serve the upload frontend."""
    html_path = Path("index.html")
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>index.html not found — place it next to server.py</h1>", 404)


@app.post("/upload/init")
async def init_upload(
    filename:    str = Form(...),
    total_size:  int = Form(...),
    total_chunks: int = Form(...),
    mime_type:   str = Form(default="application/octet-stream"),
):
    """Initialize a new upload session. Returns upload_id."""
    if total_size > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large. Max {MAX_FILE_SIZE // (1024**3)} GB.")

    upload_id = str(uuid.uuid4())
    safe_name  = "".join(c for c in filename if c.isalnum() or c in "._- ")[:200]
    
    sessions[upload_id] = {
        "upload_id":    upload_id,
        "filename":     safe_name,
        "mime_type":    mime_type,
        "total_size":   total_size,
        "total_chunks": total_chunks,
        "received":     set(),       # set of chunk indices received
        "started_at":   time.time(),
        "updated_at":   time.time(),
        "status":       "active",    # active | paused | complete | error
        "bytes_received": 0,
    }
    session_chunk_dir(upload_id)   # create temp dir

    print(f"[INIT] {upload_id} | {safe_name} | {total_size/1024/1024:.1f} MB | {total_chunks} chunks")
    return {"upload_id": upload_id, "chunk_size": CHUNK_SIZE}


@app.post("/upload/chunk/{upload_id}/{chunk_index}")
async def upload_chunk(upload_id: str, chunk_index: int, request: Request):
    """Receive a single chunk. Idempotent — re-sending a chunk is safe."""
    session = get_session(upload_id)

    if chunk_index < 0 or chunk_index >= session["total_chunks"]:
        raise HTTPException(400, f"Invalid chunk index {chunk_index}")

    # Read raw body (the chunk bytes)
    body = await request.body()
    if not body:
        raise HTTPException(400, "Empty chunk body")

    # Save chunk to disk
    chunk_path = session_chunk_dir(upload_id) / f"chunk_{chunk_index:06d}"
    chunk_path.write_bytes(body)

    session["received"].add(chunk_index)
    session["bytes_received"] += len(body)
    session["updated_at"] = time.time()

    received_count = len(session["received"])
    total          = session["total_chunks"]
    pct            = (received_count / total) * 100

    print(f"[CHUNK] {upload_id[:8]} | {chunk_index+1}/{total} | {pct:.1f}%")
    return {
        "chunk_index":   chunk_index,
        "received":      received_count,
        "total_chunks":  total,
        "percent":       round(pct, 2),
        "complete":      received_count == total,
    }


@app.get("/upload/status/{upload_id}")
async def upload_status(upload_id: str):
    """Return current upload progress — used by client to resume after disconnect."""
    session = get_session(upload_id)
    received = sorted(session["received"])
    return {
        "upload_id":      upload_id,
        "filename":       session["filename"],
        "total_chunks":   session["total_chunks"],
        "received_chunks": received,
        "bytes_received": session["bytes_received"],
        "total_size":     session["total_size"],
        "percent":        round(len(received) / session["total_chunks"] * 100, 2),
        "status":         session["status"],
    }


@app.post("/upload/complete/{upload_id}")
async def complete_upload(upload_id: str):
    """Merge all chunks into the final file."""
    session = get_session(upload_id)
    received = session["received"]
    total    = session["total_chunks"]

    # Verify all chunks present
    missing = [i for i in range(total) if i not in received]
    if missing:
        raise HTTPException(400, f"Missing {len(missing)} chunks: {missing[:10]}{'...' if len(missing)>10 else ''}")

    # Build output path (avoid collision)
    out_name = session["filename"]
    out_path = UPLOAD_DIR / out_name
    if out_path.exists():
        stem = out_path.stem
        suffix = out_path.suffix
        out_path = UPLOAD_DIR / f"{stem}_{upload_id[:8]}{suffix}"

    chunk_dir = session_chunk_dir(upload_id)

    print(f"[MERGE] Assembling {total} chunks → {out_path}")
    t0 = time.time()

    with open(out_path, "wb") as final:
        for i in range(total):
            chunk_path = chunk_dir / f"chunk_{i:06d}"
            with open(chunk_path, "rb") as cf:
                shutil.copyfileobj(cf, final, 1024 * 1024)

    elapsed = time.time() - t0
    size_mb = out_path.stat().st_size / 1024 / 1024

    # Cleanup temp chunks
    shutil.rmtree(chunk_dir, ignore_errors=True)
    session["status"] = "complete"

    print(f"[DONE] {out_path.name} | {size_mb:.1f} MB | merged in {elapsed:.1f}s")
    return {
        "success":   True,
        "filename":  out_path.name,
        "size_mb":   round(size_mb, 2),
        "elapsed_s": round(elapsed, 2),
        "path":      str(out_path),
    }


@app.delete("/upload/cancel/{upload_id}")
async def cancel_upload(upload_id: str):
    """Cancel and clean up a session."""
    session = sessions.pop(upload_id, None)
    if session:
        shutil.rmtree(session_chunk_dir(upload_id), ignore_errors=True)
    return {"cancelled": True}


@app.get("/files")
async def list_files():
    """List completed uploads."""
    files = []
    for f in UPLOAD_DIR.iterdir():
        if f.is_file():
            stat = f.stat()
            files.append({
                "name":     f.name,
                "size_mb":  round(stat.st_size / 1024 / 1024, 2),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
    return sorted(files, key=lambda x: x["modified"], reverse=True)


@app.get("/health")
async def health():
    return {"status": "ok", "sessions": len(sessions), "time": datetime.utcnow().isoformat()}


# ─── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  DropStream Upload Server")
    print("  http://localhost:8000")
    print("  Ctrl+C to stop")
    print("=" * 60)
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        workers=1,
        # Large body limit for direct upload fallback
        limit_max_requests=None,
    )
