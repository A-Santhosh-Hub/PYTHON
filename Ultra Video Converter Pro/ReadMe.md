<div align="center">

# 🎬 Ultra Video Converter Pro

### Convert **Any Video Format → MP4** with GPU Acceleration, Batch Processing & a Beautiful Dark GUI

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-Required-green?style=for-the-badge&logo=ffmpeg&logoColor=white)](https://ffmpeg.org)
[![License](https://img.shields.io/badge/License-MIT-purple?style=for-the-badge)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=for-the-badge)](https://github.com)
[![Maintained](https://img.shields.io/badge/Maintained-Yes-brightgreen?style=for-the-badge)](https://github.com)

<br/>

> A professional-grade desktop video converter built entirely in Python.  
> Powered by FFmpeg under the hood with a sleek, modern dark GUI.

<br/>

```
 ╔══════════════════════════════════════════════════════╗
 ║   Any Format  →  MP4  │  GPU Accelerated  │  Fast   ║
 ║   NVIDIA • AMD • Intel • Apple • CPU x264/x265      ║
 ╚══════════════════════════════════════════════════════╝
```

</div>

---

## ✨ Features

### 🖥️ Beautiful Dark GUI
- Fully themed, professional dark interface built with `tkinter`
- Color-coded file queue (Queued / Converting / Done / Error / Skipped)
- Tabbed settings panel: **Encoding**, **Output**, **Advanced**
- Right-click context menu with video info, folder navigation, and removal

### ⚡ GPU Acceleration
| Encoder | Hardware |
|---|---|
| `libx264` / `libx265` | CPU (software) |
| `h264_nvenc` / `hevc_nvenc` | NVIDIA CUDA |
| `h264_amf` / `hevc_amf` | AMD AMF |
| `h264_qsv` / `hevc_qsv` | Intel Quick Sync |
| `h264_videotoolbox` | Apple Silicon / macOS |

### 📂 Batch Conversion
- Add individual files or **entire folders** at once
- Drag & Drop files directly into the queue
- Process multiple files sequentially with a single click

### 📊 Live Status Bar
- Per-file progress percentage and progress bar
- Overall queue progress bar
- Real-time **encoding speed** (e.g. `3.2x`), **ETA**, and **output file size**
- Done/Failed counter summary

### 🎛️ Encoding Options
- **5 Quality Presets** — Ultra (CRF 16) → Small (CRF 30)
- **7 Resolution Options** — 4K, 2K, FHD, HD, SD, 360p, or keep original
- **Custom FPS** — 60, 30, 25, 24, 23.976, 15, or keep original
- **Audio Presets** — AAC / MP3 at various bitrates, copy original, or mute

### 🔧 Advanced Controls
- Custom raw FFmpeg arguments field
- CPU thread count slider (Auto or 1–32)
- Trim by start/end time (in seconds)
- Concurrent jobs slider (1–8)

### 📁 Output Options
- Output to the same folder as source, or choose a custom directory
- Custom filename suffix (default: `_converted`)
- Overwrite existing files toggle
- Auto-open output folder when done
- Auto-delete source file after successful conversion

---

## 🚀 Quick Start

### 1. Install FFmpeg

FFmpeg must be installed and available in your system `PATH`.

**Windows**
```bash
# Using winget
winget install Gyan.FFmpeg

# Or download manually from:
# https://ffmpeg.org/download.html  →  add bin/ folder to PATH
```

**macOS**
```bash
brew install ffmpeg
```

**Linux (Debian/Ubuntu)**
```bash
sudo apt update && sudo apt install ffmpeg
```

Verify installation:
```bash
ffmpeg -version
```

---

### 2. Install Python Dependencies

```bash
pip install tkinterdnd2 pillow psutil
```

| Package | Purpose | Required? |
|---|---|---|
| `tkinterdnd2` | Drag & Drop support | Optional (recommended) |
| `pillow` | Image processing | Optional |
| `psutil` | System/GPU info | Optional |

> All packages are optional — the app runs without them, but with reduced features.

---

### 3. Run the App

```bash
python video_converter.py
```

---

## 📋 Supported Input Formats

```
.avi  .mkv  .mov  .wmv  .flv  .webm  .m4v  .ts   .mts  .m2ts
.vob  .ogv  .3gp  .3g2  .f4v  .asf   .rm   .rmvb .divx .xvid
.mpg  .mpeg .mp2  .mpe  .mpv  .m2v   .svi  .mxf  .roq  .nsv
.amv  .yuv  .drc  .gifv .mng  ...and more
```

---

## 🎮 Usage Guide

### Basic Workflow

```
1. Launch the app      →   python video_converter.py
2. Add files           →   Click ➕ Add Files  or  drag & drop videos
3. Choose GPU/Encoder  →   Settings tab → GPU / Encoder dropdown
4. Set quality         →   Quality Preset dropdown
5. Pick output folder  →   Output tab → choose directory
6. Start              →   Click ▶ Start Conversion
7. Monitor            →   Watch the live status bar at the bottom
```

### Keyboard Shortcuts (Treeview)

| Action | Shortcut |
|---|---|
| Show video info | `Double-click` on a row |
| Context menu | `Right-click` on a row |

---

## 🏗️ Project Structure

```
video_converter.py          ← Main application (single file, no split needed)
README.md                   ← You are here
LICENSE                     ← MIT License
requirements.txt            ← Optional Python dependencies
```

---

## ⚙️ How It Works

```
User selects files
       ↓
VideoFile objects created
       ↓
ffprobe probes each file (background thread)
       ↓
User configures encoder / quality / resolution / audio
       ↓
Conversion thread spawns ffmpeg subprocess per file
       ↓
stderr parsed in real-time → progress %, speed, ETA sent to queue
       ↓
Main thread polls queue every 80ms → updates GUI safely
       ↓
Output .mp4 written with -movflags +faststart (streaming-friendly)
```

---

## 🛠️ Advanced FFmpeg Arguments

The **Advanced** tab exposes a free-text field for raw FFmpeg flags.

**Examples:**

```bash
# Force stereo audio
-ac 2

# Add metadata title
-metadata title="My Video"

# Hardware decode + encode (NVIDIA)
-hwaccel cuda -hwaccel_output_format cuda

# Rotate video 90° clockwise
-vf "transpose=1"

# Denoise + sharpen
-vf "hqdn3d,unsharp"

# Burn in subtitles
-vf "subtitles=subs.srt"
```

---

## 🐛 Troubleshooting

### FFmpeg not found
Make sure FFmpeg is on your system PATH:
```bash
# Check
ffmpeg -version

# Windows: add C:\ffmpeg\bin to environment PATH
# macOS/Linux: should work after brew/apt install
```

### GPU encoder fails (e.g. NVENC)
Not all systems have GPU encoders. If `h264_nvenc` fails:
- Switch to `CPU (x264)` in the GPU dropdown
- Make sure your NVIDIA drivers are up to date
- Run `ffmpeg -encoders | grep nvenc` to verify availability

### Drag & Drop not working
Install `tkinterdnd2`:
```bash
pip install tkinterdnd2
```

### App crashes on launch (macOS)
On macOS, use the system Python or a venv. If tkinter is missing:
```bash
brew install python-tk
```

### Output file is huge
Use a higher CRF number (e.g. CRF 28–30) or switch to HEVC (x265) which compresses better at the same quality.

---

## 📦 Requirements Summary

```
Python         3.10+
FFmpeg         Any recent version (5.x or 6.x recommended)
tkinter        Included with standard Python
tkinterdnd2    pip install tkinterdnd2   (optional, for drag & drop)
pillow         pip install pillow        (optional)
psutil         pip install psutil        (optional)
```

A `requirements.txt` for the optional packages:
```
tkinterdnd2
pillow
psutil
```

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!

1. Fork the repo
2. Create your feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

**Ideas for contributions:**
- [ ] Subtitle burn-in UI option
- [ ] Video preview thumbnail
- [ ] Drag-and-drop reorder in queue
- [ ] Preset save/load system
- [ ] Notification when conversion finishes
- [ ] Progress saved to log file

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgements

- [FFmpeg](https://ffmpeg.org/) — The backbone of all video processing
- [tkinter](https://docs.python.org/3/library/tkinter.html) — Python's standard GUI library
- [tkinterdnd2](https://github.com/pmgagne/tkinterdnd2) — Drag & Drop support

---

<div align="center">

Made with ❤️ in Python

**[⬆ Back to Top](#-ultra-video-converter-pro)**

</div>
