# DropStream — High-Speed File Upload Server

Upload massive files (6.8 GB+) with **pause/resume**, **live progress**, and 
a **Cloudflare tunnel** so anyone on the internet can send you files — no port 
forwarding, no accounts, completely free.

---

## Files in this folder

```
server.py            ← Python FastAPI backend
index.html           ← Beautiful upload frontend (auto-served by server)
requirements.txt     ← Python dependencies
start_windows.bat    ← One-click start for Windows
start_linux_mac.sh   ← One-click start for Linux / macOS
uploads/             ← Finished files land here (auto-created)
temp_chunks/         ← Temporary chunk storage (auto-cleaned)
```

---

## Quick Start

### Step 1 — Install Python (once)
Download from https://python.org (Python 3.10+)

### Step 2 — Install dependencies
```bash
pip install -r requirements.txt
```

### Step 3 — Start the server

**Windows:**
```
Double-click start_windows.bat
```

**Linux / macOS:**
```bash
chmod +x start_linux_mac.sh
./start_linux_mac.sh
```

**Manual:**
```bash
python server.py
```

Server starts at `http://localhost:8000`

---

## Share with Anyone (Free via Cloudflare Tunnel)

### Install cloudflared (one-time)

**Windows** — download the .exe:  
https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

**macOS:**
```bash
brew install cloudflared
```

**Linux:**
```bash
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod +x cloudflared-linux-amd64
sudo mv cloudflared-linux-amd64 /usr/local/bin/cloudflared
```

### Start tunnel (after server is running)
```bash
cloudflared tunnel --url http://localhost:8000
```

You'll see a line like:
```
https://fancy-words-random.trycloudflare.com
```

**Share that URL** — anyone in the world can now upload files directly to your PC.

> The tunnel is **free** and **requires no account** using `trycloudflare.com`.

---

## Features

| Feature | Detail |
|---|---|
| **Max file size** | 50 GB (configurable in server.py) |
| **Chunk size** | 5 MB per chunk |
| **Parallel chunks** | 3 simultaneous (configurable in index.html) |
| **Pause / Resume** | Yes — mid-upload pause with full state preserved |
| **Auto retry** | 4 retries per failed chunk with exponential backoff |
| **Refresh lock** | Browser warns before closing tab during upload |
| **Progress bar** | Live % + speed (MB/s) + ETA |
| **Chunk visualizer** | Mini dots showing per-chunk status |
| **Activity log** | Real-time timestamped log |
| **Session resume** | GET /upload/status/{id} returns received chunks |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serves the upload UI |
| `POST` | `/upload/init` | Start new upload session |
| `POST` | `/upload/chunk/{id}/{index}` | Upload one chunk |
| `GET` | `/upload/status/{id}` | Check session progress |
| `POST` | `/upload/complete/{id}` | Merge all chunks |
| `DELETE` | `/upload/cancel/{id}` | Cancel & cleanup |
| `GET` | `/files` | List completed uploads |
| `GET` | `/health` | Server health check |

---

## Configuration

Edit these values at the top of each file:

**server.py:**
```python
CHUNK_SIZE    = 5 * 1024 * 1024    # 5 MB per chunk
MAX_FILE_SIZE = 50 * 1024 * 1024 * 1024  # 50 GB max
SESSION_TTL   = 24 * 3600          # Session expiry
```

**index.html (top of <script>):**
```javascript
const CHUNK_SIZE   = 5 * 1024 * 1024;  // Match server
const MAX_PARALLEL = 3;                 // Concurrent chunks (raise for faster uploads)
const MAX_RETRIES  = 4;                 // Retries per chunk
const RETRY_DELAY  = 2000;             // ms between retries
```

---

## Tips for Faster Uploads

1. **Increase `MAX_PARALLEL`** in index.html to 5 or 6 on fast connections
2. **Increase `CHUNK_SIZE`** to 10 MB for very fast connections  
3. The server uses async FastAPI — it handles multiple uploaders simultaneously
4. Cloudflare's free tunnel has no bandwidth limit, just a 100 MB/request limit  
   (chunking keeps each request at 5 MB, so this is never an issue)

---

## Where do uploaded files go?

All completed files land in the `uploads/` folder, next to `server.py`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| Port 8000 in use | Change port in server.py: `port=8001` |
| Upload stops/hangs | Check server console for errors; use Resume |
| Cloudflare URL not working | Restart cloudflared; the URL changes each time |
| Large files fail | Check disk space in the uploads/ folder |
