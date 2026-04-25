# SanStudio File Server

A fast, beautiful file server — stream 6.8 GB videos, browse images, play audio, and download anything. Expose your PC to the internet for free with **Cloudflare Tunnel**.

---

## 📁 Folder Structure

```
san_server/
├── server.py          ← Backend (Flask)
├── requirements.txt
├── start.bat          ← Windows launcher
├── start.sh           ← Linux/Mac launcher
├── templates/
│   └── index.html     ← Frontend UI
└── uploads/           ← ← ← PUT YOUR FILES HERE
```

---

## ⚡ Quick Start

### 1. Install Python (3.9+)
Download from https://python.org

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Add your files
Put all your videos, audio, images, etc. inside the **`uploads/`** folder.
You can create subfolders too — they'll appear as clickable folders in the UI.

### 4. Start the server
**Windows:**
```
Double-click start.bat
```

**Mac/Linux:**
```bash
bash start.sh
```

Local URL: **http://localhost:5000**

---

## 🌐 Expose to Internet Free with Cloudflare Tunnel

### Step 1 — Install cloudflared

**Windows:**
```
winget install --id Cloudflare.cloudflared
```
Or download from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

**Mac:**
```
brew install cloudflared
```

**Linux (Debian/Ubuntu):**
```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb
```

### Step 2 — Run the tunnel (No account needed!)
With your server already running on port 5000, open a **new terminal** and run:

```bash
cloudflared tunnel --url http://localhost:5000
```

You'll see output like:
```
Your quick Tunnel has been created! Visit it at:
https://random-name-abc123.trycloudflare.com
```

✅ **Share that link with anyone!** They can stream and download your files from anywhere in the world.

> **Note:** The free quick tunnel URL changes every time you restart cloudflared.  
> For a permanent URL, create a free Cloudflare account and set up a named tunnel.

---

## 🎬 Features

| Feature | Details |
|---|---|
| **Video Streaming** | HTTP Range requests — streams 6.8 GB videos without buffering issues |
| **Audio Player** | In-browser playback for MP3, FLAC, AAC, WAV, OGG, M4A |
| **Image Viewer** | JPG, PNG, GIF, WEBP, AVIF, SVG |
| **Fast Download** | Direct chunked transfer — full speed downloads |
| **File Browser** | Grid & list view, search, sort, type filters |
| **Folder Support** | Navigate into subfolders |
| **All File Types** | ZIP, PDF, DOCX, code files — all downloadable |
| **Secure** | Path traversal protection — users can't escape `uploads/` |

---

## 🔧 Configuration

Edit the top of `server.py` to change settings:

```python
UPLOAD_FOLDER = "uploads"   # Change to any folder path
CHUNK_SIZE    = 1024*1024   # 1MB chunks (increase for faster LAN transfers)
```

To run on a different port:
```python
app.run(host="0.0.0.0", port=8080)   # Change 5000 → 8080
```

---

## 🛡️ Security Notes

- The server **only serves files inside `uploads/`** — path traversal is blocked
- For public internet use, consider adding basic auth (ask SanStudio!)
- Don't share the Cloudflare link publicly if files are private

---

*Developed by [SanStudio](https://a-santhosh-hub.github.io/in/)*
