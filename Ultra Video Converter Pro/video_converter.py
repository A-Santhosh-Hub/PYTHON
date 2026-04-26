"""
╔══════════════════════════════════════════════════════════════════════╗
║         🎬 ULTRA VIDEO CONVERTER PRO — by Python Developer          ║
║         Any Format → MP4 | GPU Acceleration | Batch Convert         ║
╚══════════════════════════════════════════════════════════════════════╝

Requirements:
    pip install tkinterdnd2 pillow ffmpeg-python psutil

Also requires FFmpeg installed on your system:
    Windows : https://ffmpeg.org/download.html  (add to PATH)
    Linux   : sudo apt install ffmpeg
    macOS   : brew install ffmpeg
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import threading
import os
import sys
import time
import json
import re
import shutil
import queue
from pathlib import Path
from datetime import datetime, timedelta

# ─── Optional imports ────────────────────────────────────────────────────────
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# ─── Constants ────────────────────────────────────────────────────────────────
APP_NAME    = "🎬 Ultra Video Converter Pro"
APP_VERSION = "v2.0"
DARK_BG     = "#0f0f13"
PANEL_BG    = "#1a1a24"
CARD_BG     = "#22223a"
ACCENT      = "#7c5cbf"
ACCENT2     = "#00d4aa"
TEXT_PRI    = "#e8e8f0"
TEXT_SEC    = "#8888aa"
SUCCESS     = "#00d4aa"
WARNING     = "#f5a623"
ERROR       = "#ff4757"
BORDER      = "#33334a"

SUPPORTED_FORMATS = [
    "*.avi","*.mkv","*.mov","*.wmv","*.flv","*.webm","*.m4v","*.ts","*.mts",
    "*.m2ts","*.vob","*.ogv","*.3gp","*.3g2","*.f4v","*.asf","*.rm","*.rmvb",
    "*.divx","*.xvid","*.mpg","*.mpeg","*.mp2","*.mpe","*.mpv","*.m2v","*.svi",
    "*.mxf","*.roq","*.nsv","*.amv","*.yuv","*.drc","*.gifv","*.mng"
]

GPU_ENCODERS = {
    "🖥️ CPU (x264)":         {"vcodec": "libx264",    "hwaccel": None},
    "🖥️ CPU (x265/HEVC)":    {"vcodec": "libx265",    "hwaccel": None},
    "⚡ NVIDIA NVENC (H.264)":{"vcodec": "h264_nvenc", "hwaccel": "cuda"},
    "⚡ NVIDIA NVENC (HEVC)": {"vcodec": "hevc_nvenc", "hwaccel": "cuda"},
    "🔴 AMD AMF (H.264)":     {"vcodec": "h264_amf",  "hwaccel": "dxva2"},
    "🔴 AMD AMF (HEVC)":      {"vcodec": "hevc_amf",  "hwaccel": "dxva2"},
    "🔵 Intel QSV (H.264)":   {"vcodec": "h264_qsv",  "hwaccel": "qsv"},
    "🔵 Intel QSV (HEVC)":    {"vcodec": "hevc_qsv",  "hwaccel": "qsv"},
    "🍎 Apple VideoToolbox":  {"vcodec": "h264_videotoolbox","hwaccel": "videotoolbox"},
}

QUALITY_PRESETS = {
    "🏆 Ultra (CRF 16)":   {"crf": "16", "preset": "slow"},
    "⭐ High  (CRF 20)":   {"crf": "20", "preset": "medium"},
    "✅ Medium (CRF 23)":  {"crf": "23", "preset": "medium"},
    "⚡ Fast  (CRF 26)":   {"crf": "26", "preset": "fast"},
    "💾 Small (CRF 30)":   {"crf": "30", "preset": "veryfast"},
}

RESOLUTION_OPTIONS = {
    "🔒 Keep Original":  None,
    "4K  (3840×2160)": "3840:2160",
    "2K  (2560×1440)": "2560:1440",
    "FHD (1920×1080)": "1920:1080",
    "HD  (1280×720)":  "1280:720",
    "SD  (854×480)":   "854:480",
    "360p (640×360)":  "640:360",
}

AUDIO_PRESETS = {
    "🔒 Keep Original": None,
    "AAC 320k":  {"acodec": "aac",  "abitrate": "320k"},
    "AAC 192k":  {"acodec": "aac",  "abitrate": "192k"},
    "AAC 128k":  {"acodec": "aac",  "abitrate": "128k"},
    "MP3 320k":  {"acodec": "libmp3lame", "abitrate": "320k"},
    "MP3 192k":  {"acodec": "libmp3lame", "abitrate": "192k"},
    "Mute 🔇":   {"acodec": "none", "abitrate": None},
}

FPS_OPTIONS = ["🔒 Keep Original", "60", "30", "25", "24", "23.976", "15"]

# ─── Utility: probe video info via ffprobe ────────────────────────────────────
def ffprobe(path: str) -> dict:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        str(path)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return json.loads(result.stdout)
    except Exception:
        return {}


def human_size(nbytes: int) -> str:
    for unit in ("B","KB","MB","GB","TB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"


def human_duration(secs: float) -> str:
    secs = int(secs)
    h, r = divmod(secs, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def get_video_info(path: str) -> dict:
    data = ffprobe(path)
    info = {
        "duration": 0, "width": 0, "height": 0,
        "vcodec": "?", "acodec": "?", "fps": "?",
        "size": os.path.getsize(path) if os.path.exists(path) else 0,
        "bitrate": 0,
    }
    fmt = data.get("format", {})
    info["duration"] = float(fmt.get("duration", 0))
    info["bitrate"]  = int(fmt.get("bit_rate", 0))

    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            info["vcodec"] = s.get("codec_name", "?")
            info["width"]  = s.get("width", 0)
            info["height"] = s.get("height", 0)
            num, den = s.get("r_frame_rate","0/1").split("/")
            info["fps"] = f"{int(num)/max(int(den),1):.2f}"
        elif s.get("codec_type") == "audio":
            info["acodec"] = s.get("codec_name", "?")
    return info


def check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None

# ─── File entry dataclass replacement ────────────────────────────────────────
class VideoFile:
    def __init__(self, path: str):
        self.path     = path
        self.name     = os.path.basename(path)
        self.info     = {}
        self.status   = "Queued"
        self.progress = 0
        self.eta      = ""
        self.speed    = ""
        self.error    = ""

# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════
class VideoConverterApp:
    def __init__(self, root: tk.Tk):
        self.root       = root
        self.files      : list[VideoFile] = []
        self.q          = queue.Queue()
        self.converting = False
        self.stop_flag  = threading.Event()
        self.current_proc: subprocess.Popen | None = None

        self._setup_window()
        self._setup_styles()
        self._build_ui()
        self._check_ffmpeg_startup()
        self._poll_queue()

    # ── Window setup ──────────────────────────────────────────────────────────
    def _setup_window(self):
        self.root.title(f"{APP_NAME}  {APP_VERSION}")
        self.root.geometry("1100x780")
        self.root.minsize(900, 650)
        self.root.configure(bg=DARK_BG)
        try:
            self.root.tk.call("tk", "scaling", 1.1)
        except Exception:
            pass

    def _setup_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure(".",
            background=DARK_BG, foreground=TEXT_PRI,
            fieldbackground=CARD_BG, troughcolor=PANEL_BG,
            bordercolor=BORDER, darkcolor=PANEL_BG, lightcolor=PANEL_BG,
            insertcolor=TEXT_PRI, selectbackground=ACCENT,
            selectforeground=TEXT_PRI, font=("Segoe UI", 10))

        style.configure("TFrame",    background=DARK_BG)
        style.configure("Card.TFrame", background=CARD_BG)
        style.configure("Panel.TFrame", background=PANEL_BG)

        style.configure("TLabel",    background=DARK_BG,  foreground=TEXT_PRI)
        style.configure("Card.TLabel",  background=CARD_BG,  foreground=TEXT_PRI)
        style.configure("Panel.TLabel", background=PANEL_BG, foreground=TEXT_PRI)
        style.configure("Dim.TLabel",   background=CARD_BG,  foreground=TEXT_SEC,
                         font=("Segoe UI", 9))

        style.configure("Accent.TButton",
            background=ACCENT, foreground="#ffffff",
            borderwidth=0, focusthickness=0, padding=(14, 8),
            font=("Segoe UI Semibold", 10))
        style.map("Accent.TButton",
            background=[("active", "#9b73e0"), ("pressed", "#5c3fa0")])

        style.configure("Success.TButton",
            background=ACCENT2, foreground="#000000",
            borderwidth=0, focusthickness=0, padding=(14, 8),
            font=("Segoe UI Semibold", 10))
        style.map("Success.TButton",
            background=[("active", "#00f0c0")])

        style.configure("Danger.TButton",
            background=ERROR, foreground="#ffffff",
            borderwidth=0, padding=(10, 7))
        style.map("Danger.TButton",
            background=[("active", "#ff6b7a")])

        style.configure("Ghost.TButton",
            background=PANEL_BG, foreground=TEXT_SEC,
            borderwidth=1, relief="flat", padding=(10, 7))
        style.map("Ghost.TButton",
            background=[("active", CARD_BG)], foreground=[("active", TEXT_PRI)])

        style.configure("TCombobox",
            fieldbackground=CARD_BG, background=CARD_BG,
            foreground=TEXT_PRI, arrowcolor=ACCENT,
            bordercolor=BORDER, padding=6)
        style.map("TCombobox",
            fieldbackground=[("readonly", CARD_BG)],
            selectbackground=[("readonly", CARD_BG)],
            selectforeground=[("readonly", TEXT_PRI)])

        style.configure("TProgressbar",
            troughcolor=PANEL_BG, background=ACCENT,
            bordercolor=BORDER, thickness=8)
        style.configure("Green.TProgressbar",
            troughcolor=PANEL_BG, background=SUCCESS, thickness=8)
        style.configure("Red.TProgressbar",
            troughcolor=PANEL_BG, background=ERROR, thickness=8)

        style.configure("Treeview",
            background=PANEL_BG, foreground=TEXT_PRI,
            fieldbackground=PANEL_BG, rowheight=36,
            borderwidth=0, font=("Segoe UI", 9))
        style.configure("Treeview.Heading",
            background=CARD_BG, foreground=TEXT_SEC,
            borderwidth=0, font=("Segoe UI Semibold", 9))
        style.map("Treeview",
            background=[("selected", ACCENT)],
            foreground=[("selected", "#ffffff")])

        style.configure("TSeparator", background=BORDER)
        style.configure("TNotebook", background=DARK_BG, borderwidth=0)
        style.configure("TNotebook.Tab",
            background=PANEL_BG, foreground=TEXT_SEC,
            padding=(14, 6), borderwidth=0)
        style.map("TNotebook.Tab",
            background=[("selected", CARD_BG)],
            foreground=[("selected", ACCENT)])

        style.configure("TCheckbutton",
            background=CARD_BG, foreground=TEXT_PRI,
            focusthickness=0)
        style.map("TCheckbutton",
            background=[("active", CARD_BG)])

        style.configure("TScale",
            background=CARD_BG, troughcolor=PANEL_BG,
            sliderlength=18, sliderrelief="flat")

    # ── Build UI ───────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── Top bar
        topbar = tk.Frame(self.root, bg=PANEL_BG, height=56)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        tk.Label(topbar, text="🎬", bg=PANEL_BG, fg=ACCENT,
                 font=("Segoe UI", 22)).pack(side="left", padx=(16,4), pady=8)
        tk.Label(topbar, text="Ultra Video Converter Pro",
                 bg=PANEL_BG, fg=TEXT_PRI,
                 font=("Segoe UI Semibold", 14)).pack(side="left")
        tk.Label(topbar, text=APP_VERSION,
                 bg=PANEL_BG, fg=TEXT_SEC,
                 font=("Segoe UI", 9)).pack(side="left", padx=6, pady=18)

        # FFmpeg status badge
        self.ffmpeg_badge = tk.Label(topbar, text="  Checking FFmpeg…  ",
            bg=PANEL_BG, fg=WARNING, font=("Segoe UI", 9))
        self.ffmpeg_badge.pack(side="right", padx=16)

        # GPU label
        self.gpu_badge = tk.Label(topbar, text="GPU: —",
            bg=PANEL_BG, fg=TEXT_SEC, font=("Segoe UI", 9))
        self.gpu_badge.pack(side="right", padx=(0, 12))

        # ── Main layout: left panel + right panel
        main = tk.Frame(self.root, bg=DARK_BG)
        main.pack(fill="both", expand=True, padx=10, pady=(8,4))

        # Left: file list + drop zone
        left = tk.Frame(main, bg=DARK_BG)
        left.pack(side="left", fill="both", expand=True)

        self._build_file_panel(left)

        # Right: settings
        right = tk.Frame(main, bg=DARK_BG, width=320)
        right.pack(side="right", fill="y", padx=(10,0))
        right.pack_propagate(False)
        self._build_settings_panel(right)

        # ── Bottom status bar
        self._build_status_bar()

    def _build_file_panel(self, parent):
        # Drop zone / header row
        head = tk.Frame(parent, bg=DARK_BG)
        head.pack(fill="x", pady=(0, 6))

        tk.Label(head, text="📁  Video Queue",
                 bg=DARK_BG, fg=TEXT_PRI,
                 font=("Segoe UI Semibold", 11)).pack(side="left")

        btn_row = tk.Frame(head, bg=DARK_BG)
        btn_row.pack(side="right")

        ttk.Button(btn_row, text="➕ Add Files",
                   style="Accent.TButton",
                   command=self._add_files).pack(side="left", padx=(0,4))
        ttk.Button(btn_row, text="📂 Add Folder",
                   style="Ghost.TButton",
                   command=self._add_folder).pack(side="left", padx=(0,4))
        ttk.Button(btn_row, text="🗑 Clear All",
                   style="Danger.TButton",
                   command=self._clear_files).pack(side="left")

        # Drop zone frame
        drop_outer = tk.Frame(parent, bg=BORDER, bd=0)
        drop_outer.pack(fill="both", expand=True)

        drop_inner = tk.Frame(drop_outer, bg=PANEL_BG)
        drop_inner.pack(fill="both", expand=True, padx=1, pady=1)

        # Treeview
        cols = ("name","format","resolution","duration","size","status","progress")
        self.tree = ttk.Treeview(drop_inner, columns=cols,
                                  show="headings", selectmode="extended")
        headers = {
            "name":       ("Filename",      260, "w"),
            "format":     ("Format",         60, "center"),
            "resolution": ("Resolution",    100, "center"),
            "duration":   ("Duration",       72, "center"),
            "size":       ("Size",           70, "center"),
            "status":     ("Status",        100, "center"),
            "progress":   ("Progress",       72, "center"),
        }
        for col, (txt, w, anchor) in headers.items():
            self.tree.heading(col, text=txt)
            self.tree.column(col, width=w, anchor=anchor, minwidth=40)

        # Tags for row coloring
        self.tree.tag_configure("queued",   foreground=TEXT_SEC)
        self.tree.tag_configure("done",     foreground=SUCCESS)
        self.tree.tag_configure("error",    foreground=ERROR)
        self.tree.tag_configure("active",   foreground=WARNING)
        self.tree.tag_configure("skipped",  foreground=TEXT_SEC)

        vsb = ttk.Scrollbar(drop_inner, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(drop_inner, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        drop_inner.rowconfigure(0, weight=1)
        drop_inner.columnconfigure(0, weight=1)

        # Context menu
        self.ctx_menu = tk.Menu(self.root, tearoff=0, bg=CARD_BG,
                                fg=TEXT_PRI, activebackground=ACCENT,
                                activeforeground="#fff")
        self.ctx_menu.add_command(label="ℹ  Show Info",   command=self._show_info)
        self.ctx_menu.add_command(label="📂 Open Folder", command=self._open_folder)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="🗑 Remove",      command=self._remove_selected)
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Double-1>", lambda e: self._show_info())

        # Drag-and-drop
        if DND_AVAILABLE:
            self.tree.drop_target_register(DND_FILES)
            self.tree.dnd_bind("<<Drop>>", self._on_drop)
            drop_inner.drop_target_register(DND_FILES)
            drop_inner.dnd_bind("<<Drop>>", self._on_drop)

        # Empty-state overlay label
        self.empty_label = tk.Label(drop_inner,
            text="✨  Drop video files here or click  ➕ Add Files",
            bg=PANEL_BG, fg=TEXT_SEC, font=("Segoe UI", 11))
        self.empty_label.place(relx=0.5, rely=0.5, anchor="center")

        # Info bar below treeview
        info_bar = tk.Frame(parent, bg=CARD_BG, height=28)
        info_bar.pack(fill="x", pady=(4,0))
        info_bar.pack_propagate(False)

        self.queue_info = tk.Label(info_bar, text="No files in queue",
            bg=CARD_BG, fg=TEXT_SEC, font=("Segoe UI", 9))
        self.queue_info.pack(side="left", padx=10, pady=4)

        ttk.Button(info_bar, text="🗑 Remove Selected",
                   style="Ghost.TButton",
                   command=self._remove_selected).pack(side="right", padx=4, pady=2)

    def _build_settings_panel(self, parent):
        nb = ttk.Notebook(parent)
        nb.pack(fill="both", expand=True)

        # ── Tab: Encoding ──────────────────────────────────────────────────
        enc_frame = ttk.Frame(nb, style="Panel.TFrame")
        nb.add(enc_frame, text=" ⚙ Encoding ")

        def section(p, title):
            tk.Label(p, text=title, bg=PANEL_BG, fg=TEXT_SEC,
                     font=("Segoe UI Semibold", 9)).pack(anchor="w", pady=(10,2), padx=4)

        section(enc_frame, "GPU / Encoder")
        self.gpu_var = tk.StringVar(value=list(GPU_ENCODERS.keys())[0])
        gpu_cb = ttk.Combobox(enc_frame, textvariable=self.gpu_var,
                              values=list(GPU_ENCODERS.keys()),
                              state="readonly", width=30)
        gpu_cb.pack(fill="x", padx=4)
        gpu_cb.bind("<<ComboboxSelected>>", self._on_gpu_change)

        section(enc_frame, "Quality Preset")
        self.quality_var = tk.StringVar(value=list(QUALITY_PRESETS.keys())[1])
        ttk.Combobox(enc_frame, textvariable=self.quality_var,
                     values=list(QUALITY_PRESETS.keys()),
                     state="readonly", width=30).pack(fill="x", padx=4)

        section(enc_frame, "Output Resolution")
        self.res_var = tk.StringVar(value=list(RESOLUTION_OPTIONS.keys())[0])
        ttk.Combobox(enc_frame, textvariable=self.res_var,
                     values=list(RESOLUTION_OPTIONS.keys()),
                     state="readonly", width=30).pack(fill="x", padx=4)

        section(enc_frame, "Frame Rate")
        self.fps_var = tk.StringVar(value=FPS_OPTIONS[0])
        ttk.Combobox(enc_frame, textvariable=self.fps_var,
                     values=FPS_OPTIONS,
                     state="readonly", width=30).pack(fill="x", padx=4)

        section(enc_frame, "Audio")
        self.audio_var = tk.StringVar(value=list(AUDIO_PRESETS.keys())[0])
        ttk.Combobox(enc_frame, textvariable=self.audio_var,
                     values=list(AUDIO_PRESETS.keys()),
                     state="readonly", width=30).pack(fill="x", padx=4)

        # ── Tab: Output ────────────────────────────────────────────────────
        out_frame = ttk.Frame(nb, style="Panel.TFrame")
        nb.add(out_frame, text=" 📂 Output ")

        section(out_frame, "Output Folder")
        out_path_row = tk.Frame(out_frame, bg=PANEL_BG)
        out_path_row.pack(fill="x", padx=4)

        self.out_path_var = tk.StringVar(value="Same as source")
        tk.Entry(out_path_row, textvariable=self.out_path_var,
                 bg=CARD_BG, fg=TEXT_PRI, bd=0,
                 insertbackground=TEXT_PRI, relief="flat",
                 font=("Segoe UI", 9)).pack(side="left", fill="x", expand=True, ipady=5)
        ttk.Button(out_path_row, text="…",
                   style="Ghost.TButton",
                   command=self._pick_output).pack(side="right", padx=(4,0))

        section(out_frame, "Filename")
        self.suffix_var = tk.StringVar(value="_converted")
        tk.Frame(out_frame, bg=PANEL_BG, height=1).pack()
        row = tk.Frame(out_frame, bg=PANEL_BG)
        row.pack(fill="x", padx=4)
        tk.Label(row, text="Suffix:", bg=PANEL_BG, fg=TEXT_SEC,
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Entry(row, textvariable=self.suffix_var,
                 bg=CARD_BG, fg=TEXT_PRI, bd=0, relief="flat",
                 insertbackground=TEXT_PRI, width=14,
                 font=("Segoe UI", 9)).pack(side="left", padx=(6,0), ipady=4)

        section(out_frame, "Options")
        self.overwrite_var = tk.BooleanVar(value=False)
        self.open_after_var = tk.BooleanVar(value=False)
        self.del_source_var = tk.BooleanVar(value=False)

        for label, var in [
            ("Overwrite existing files", self.overwrite_var),
            ("Open output folder when done", self.open_after_var),
            ("Delete source after conversion", self.del_source_var),
        ]:
            ttk.Checkbutton(out_frame, text=label, variable=var,
                            style="TCheckbutton").pack(anchor="w", padx=6, pady=2)

        # ── Tab: Advanced ──────────────────────────────────────────────────
        adv_frame = ttk.Frame(nb, style="Panel.TFrame")
        nb.add(adv_frame, text=" 🔧 Advanced ")

        section(adv_frame, "Extra FFmpeg Arguments")
        self.extra_args_var = tk.StringVar(value="")
        tk.Entry(adv_frame, textvariable=self.extra_args_var,
                 bg=CARD_BG, fg=TEXT_PRI, bd=0, relief="flat",
                 insertbackground=TEXT_PRI, font=("Segoe UI", 9)
                 ).pack(fill="x", padx=4, ipady=5)
        tk.Label(adv_frame, text="e.g.  -threads 4  -movflags +faststart",
                 bg=PANEL_BG, fg=TEXT_SEC,
                 font=("Segoe UI", 8)).pack(anchor="w", padx=4)

        section(adv_frame, "Thread Count")
        self.threads_var = tk.IntVar(value=0)
        thread_row = tk.Frame(adv_frame, bg=PANEL_BG)
        thread_row.pack(fill="x", padx=4)
        self.thread_label = tk.Label(thread_row, text="Auto",
            bg=PANEL_BG, fg=ACCENT, font=("Segoe UI Semibold", 10))
        self.thread_label.pack(side="right")
        ttk.Scale(thread_row, from_=0, to=32,
                  variable=self.threads_var,
                  command=self._update_thread_label,
                  orient="horizontal").pack(fill="x", expand=True, side="left")

        section(adv_frame, "Concurrent Jobs")
        self.jobs_var = tk.IntVar(value=1)
        jobs_row = tk.Frame(adv_frame, bg=PANEL_BG)
        jobs_row.pack(fill="x", padx=4)
        self.jobs_label = tk.Label(jobs_row, text="1",
            bg=PANEL_BG, fg=ACCENT, font=("Segoe UI Semibold", 10))
        self.jobs_label.pack(side="right")
        ttk.Scale(jobs_row, from_=1, to=8,
                  variable=self.jobs_var,
                  command=self._update_jobs_label,
                  orient="horizontal").pack(fill="x", expand=True, side="left")

        section(adv_frame, "Trim (seconds)")
        trim_row = tk.Frame(adv_frame, bg=PANEL_BG)
        trim_row.pack(fill="x", padx=4)
        tk.Label(trim_row, text="Start:", bg=PANEL_BG, fg=TEXT_SEC,
                 font=("Segoe UI", 9)).pack(side="left")
        self.trim_start_var = tk.StringVar(value="")
        tk.Entry(trim_row, textvariable=self.trim_start_var,
                 bg=CARD_BG, fg=TEXT_PRI, bd=0, width=8,
                 relief="flat", insertbackground=TEXT_PRI,
                 font=("Segoe UI", 9)).pack(side="left", padx=4, ipady=4)
        tk.Label(trim_row, text="End:", bg=PANEL_BG, fg=TEXT_SEC,
                 font=("Segoe UI", 9)).pack(side="left")
        self.trim_end_var = tk.StringVar(value="")
        tk.Entry(trim_row, textvariable=self.trim_end_var,
                 bg=CARD_BG, fg=TEXT_PRI, bd=0, width=8,
                 relief="flat", insertbackground=TEXT_PRI,
                 font=("Segoe UI", 9)).pack(side="left", padx=4, ipady=4)

        # ── Convert / Stop buttons at bottom ──────────────────────────────
        btn_frame = tk.Frame(parent, bg=DARK_BG)
        btn_frame.pack(fill="x", pady=(8,0))

        self.convert_btn = ttk.Button(btn_frame, text="▶  Start Conversion",
                                      style="Success.TButton",
                                      command=self._start_conversion)
        self.convert_btn.pack(fill="x", pady=(0,4))

        self.stop_btn = ttk.Button(btn_frame, text="⏹  Stop",
                                   style="Danger.TButton",
                                   command=self._stop_conversion,
                                   state="disabled")
        self.stop_btn.pack(fill="x")

    def _build_status_bar(self):
        bar = tk.Frame(self.root, bg=CARD_BG, height=88)
        bar.pack(fill="x", padx=10, pady=(4,8))
        bar.pack_propagate(False)

        # Progress section
        prog_col = tk.Frame(bar, bg=CARD_BG)
        prog_col.pack(fill="x", padx=12, pady=(8,4))

        row1 = tk.Frame(prog_col, bg=CARD_BG)
        row1.pack(fill="x")
        self.status_label = tk.Label(row1, text="Ready",
            bg=CARD_BG, fg=TEXT_PRI, font=("Segoe UI Semibold", 10))
        self.status_label.pack(side="left")

        self.pct_label = tk.Label(row1, text="",
            bg=CARD_BG, fg=ACCENT, font=("Segoe UI Semibold", 10))
        self.pct_label.pack(side="right")

        self.file_progress = ttk.Progressbar(prog_col, style="TProgressbar",
                                              maximum=100)
        self.file_progress.pack(fill="x", pady=(2,4))

        row2 = tk.Frame(prog_col, bg=CARD_BG)
        row2.pack(fill="x")

        self.overall_label = tk.Label(row2, text="Overall",
            bg=CARD_BG, fg=TEXT_SEC, font=("Segoe UI", 8))
        self.overall_label.pack(side="left")

        self.overall_progress = ttk.Progressbar(row2, style="TProgressbar",
                                                  maximum=100, length=200)
        self.overall_progress.pack(side="left", padx=8, fill="x", expand=True)

        # Stats row
        stats_row = tk.Frame(bar, bg=CARD_BG)
        stats_row.pack(fill="x", padx=12, pady=(0,6))

        self.speed_label   = tk.Label(stats_row, text="Speed: —",
            bg=CARD_BG, fg=TEXT_SEC, font=("Segoe UI", 9))
        self.speed_label.pack(side="left", padx=(0,16))

        self.eta_label     = tk.Label(stats_row, text="ETA: —",
            bg=CARD_BG, fg=TEXT_SEC, font=("Segoe UI", 9))
        self.eta_label.pack(side="left", padx=(0,16))

        self.size_label    = tk.Label(stats_row, text="Output: —",
            bg=CARD_BG, fg=TEXT_SEC, font=("Segoe UI", 9))
        self.size_label.pack(side="left")

        self.done_label    = tk.Label(stats_row, text="",
            bg=CARD_BG, fg=SUCCESS, font=("Segoe UI Semibold", 9))
        self.done_label.pack(side="right")

    # ─── Event handlers ───────────────────────────────────────────────────────
    def _check_ffmpeg_startup(self):
        if check_ffmpeg():
            self.ffmpeg_badge.config(text="  ✅ FFmpeg Ready  ", fg=SUCCESS)
        else:
            self.ffmpeg_badge.config(text="  ❌ FFmpeg Missing  ", fg=ERROR)
            messagebox.showerror(
                "FFmpeg Not Found",
                "FFmpeg was not found on your system PATH.\n\n"
                "Please install FFmpeg:\n"
                "  Windows: https://ffmpeg.org/download.html\n"
                "  Linux  : sudo apt install ffmpeg\n"
                "  macOS  : brew install ffmpeg\n\n"
                "Then restart this application."
            )

    def _on_gpu_change(self, event=None):
        enc = GPU_ENCODERS[self.gpu_var.get()]
        self.gpu_badge.config(
            text=f"GPU: {'Hardware' if enc['hwaccel'] else 'CPU'}",
            fg=ACCENT if enc["hwaccel"] else TEXT_SEC
        )

    def _update_thread_label(self, val):
        v = int(float(val))
        self.thread_label.config(text="Auto" if v == 0 else str(v))

    def _update_jobs_label(self, val):
        self.jobs_label.config(text=str(int(float(val))))

    def _add_files(self):
        types = [("Video Files", " ".join(SUPPORTED_FORMATS)), ("All Files", "*.*")]
        paths = filedialog.askopenfilenames(title="Select Video Files",
                                            filetypes=types)
        for p in paths:
            self._add_file(p)

    def _add_folder(self):
        folder = filedialog.askdirectory(title="Select Folder")
        if not folder:
            return
        count = 0
        exts = {f[1:].lower() for f in SUPPORTED_FORMATS}
        for root, _, files in os.walk(folder):
            for f in files:
                if f.rsplit(".", 1)[-1].lower() in exts:
                    self._add_file(os.path.join(root, f))
                    count += 1
        self._update_queue_info()

    def _add_file(self, path: str):
        path = path.strip().strip("{}")
        if not os.path.isfile(path):
            return
        existing = [f.path for f in self.files]
        if path in existing:
            return
        vf = VideoFile(path)
        self.files.append(vf)
        # Probe info in background
        threading.Thread(target=self._probe_file, args=(vf,), daemon=True).start()
        self._refresh_tree()

    def _probe_file(self, vf: VideoFile):
        vf.info = get_video_info(vf.path)
        self.q.put(("refresh", None))

    def _on_drop(self, event):
        raw = event.data
        # Handle multiple paths
        paths = re.findall(r'\{([^}]+)\}|(\S+)', raw)
        for p1, p2 in paths:
            self._add_file(p1 or p2)

    def _remove_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        iids = set(sel)
        self.files = [f for f in self.files
                      if str(id(f)) not in iids]
        self._refresh_tree()

    def _clear_files(self):
        if self.converting:
            messagebox.showwarning("Converting", "Stop conversion first.")
            return
        self.files.clear()
        self._refresh_tree()

    def _pick_output(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.out_path_var.set(folder)

    def _show_context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self.ctx_menu.tk_popup(event.x_root, event.y_root)

    def _show_info(self):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        vf = self._vf_by_iid(iid)
        if not vf:
            return
        info = vf.info
        msg = (
            f"📄  {vf.name}\n\n"
            f"📁  Path: {vf.path}\n\n"
            f"🎥  Video Codec : {info.get('vcodec','?')}\n"
            f"🔊  Audio Codec : {info.get('acodec','?')}\n"
            f"📐  Resolution  : {info.get('width','?')}×{info.get('height','?')}\n"
            f"🎞  Frame Rate  : {info.get('fps','?')} fps\n"
            f"⏱  Duration    : {human_duration(info.get('duration',0))}\n"
            f"💾  File Size   : {human_size(info.get('size',0))}\n"
            f"📶  Bit Rate    : {int(info.get('bitrate',0)//1000)} kbps\n\n"
            f"⚡  Status: {vf.status}\n"
            f"   Error : {vf.error or 'None'}"
        )
        messagebox.showinfo("Video Info", msg)

    def _open_folder(self):
        sel = self.tree.selection()
        if not sel:
            return
        vf = self._vf_by_iid(sel[0])
        if not vf:
            return
        folder = os.path.dirname(vf.path)
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])

    def _vf_by_iid(self, iid: str) -> VideoFile | None:
        for f in self.files:
            if str(id(f)) == iid:
                return f
        return None

    # ─── Treeview refresh ─────────────────────────────────────────────────────
    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for vf in self.files:
            info = vf.info
            res  = f"{info.get('width','?')}×{info.get('height','?')}" if info else "—"
            dur  = human_duration(info.get("duration",0)) if info else "—"
            sz   = human_size(info.get("size",0)) if info else "—"
            ext  = vf.name.rsplit(".",1)[-1].upper() if "." in vf.name else "?"
            pct  = f"{vf.progress:.0f}%" if vf.progress > 0 else ""

            tag = {
                "Done":       "done",
                "Error":      "error",
                "Converting": "active",
                "Skipped":    "skipped",
            }.get(vf.status, "queued")

            self.tree.insert("", "end", iid=str(id(vf)),
                values=(vf.name, ext, res, dur, sz, vf.status, pct),
                tags=(tag,))

        self._update_queue_info()
        show = len(self.files) == 0
        if show:
            self.empty_label.place(relx=0.5, rely=0.5, anchor="center")
        else:
            self.empty_label.place_forget()

    def _update_queue_info(self):
        total  = len(self.files)
        done   = sum(1 for f in self.files if f.status == "Done")
        errors = sum(1 for f in self.files if f.status == "Error")
        self.queue_info.config(
            text=f"{total} file{'s' if total!=1 else ''} │ {done} done │ {errors} errors"
        )

    # ─── Conversion logic ─────────────────────────────────────────────────────
    def _start_conversion(self):
        if not check_ffmpeg():
            messagebox.showerror("FFmpeg Missing", "Please install FFmpeg first.")
            return
        pending = [f for f in self.files if f.status in ("Queued", "Error")]
        if not pending:
            messagebox.showinfo("No Files", "No files queued for conversion.\nAdd files or clear errors.")
            return

        self.converting = True
        self.stop_flag.clear()
        self.convert_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self._reset_stats()

        threading.Thread(target=self._conversion_worker,
                         args=(pending,), daemon=True).start()

    def _stop_conversion(self):
        self.stop_flag.set()
        if self.current_proc:
            try:
                self.current_proc.terminate()
            except Exception:
                pass
        self.q.put(("status", "⏹  Stopped by user."))

    def _reset_stats(self):
        self.file_progress["value"] = 0
        self.overall_progress["value"] = 0
        self.pct_label.config(text="")
        self.speed_label.config(text="Speed: —")
        self.eta_label.config(text="ETA: —")
        self.size_label.config(text="Output: —")
        self.done_label.config(text="")

    def _conversion_worker(self, files: list[VideoFile]):
        total   = len(files)
        success = 0
        failed  = 0

        enc_key  = self.gpu_var.get()
        enc_cfg  = GPU_ENCODERS[enc_key]
        qual_key = self.quality_var.get()
        qual_cfg = QUALITY_PRESETS[qual_key]
        res_key  = self.res_var.get()
        res_val  = RESOLUTION_OPTIONS[res_key]
        fps_val  = self.fps_var.get()
        aud_key  = self.audio_var.get()
        aud_cfg  = AUDIO_PRESETS[aud_key]
        out_dir  = self.out_path_var.get()
        suffix   = self.suffix_var.get()
        overwrite= self.overwrite_var.get()
        threads  = int(self.threads_var.get())
        extra    = self.extra_args_var.get().strip()
        trim_s   = self.trim_start_var.get().strip()
        trim_e   = self.trim_end_var.get().strip()

        for idx, vf in enumerate(files):
            if self.stop_flag.is_set():
                break

            vf.status   = "Converting"
            vf.progress = 0
            self.q.put(("refresh", None))
            self.q.put(("status", f"🔄  [{idx+1}/{total}]  {vf.name}"))
            self.q.put(("overall", int(idx / total * 100)))

            # Determine output path
            src_dir = os.path.dirname(vf.path)
            base    = os.path.splitext(vf.name)[0]
            dst_dir = src_dir if out_dir == "Same as source" else out_dir
            os.makedirs(dst_dir, exist_ok=True)
            out_path = os.path.join(dst_dir, f"{base}{suffix}.mp4")

            if os.path.exists(out_path) and not overwrite:
                vf.status = "Skipped"
                self.q.put(("refresh", None))
                continue

            # Build ffmpeg command
            cmd = ["ffmpeg", "-y"]

            if enc_cfg["hwaccel"]:
                cmd += ["-hwaccel", enc_cfg["hwaccel"]]

            if trim_s:
                cmd += ["-ss", trim_s]
            cmd += ["-i", vf.path]
            if trim_e:
                cmd += ["-to", trim_e]

            # Video codec
            vcodec = enc_cfg["vcodec"]
            cmd += ["-vcodec", vcodec]

            # Quality
            if vcodec in ("libx264", "libx265"):
                cmd += ["-crf", qual_cfg["crf"], "-preset", qual_cfg["preset"]]
            else:
                # For HW encoders use b:v (quality via bitrate)
                cmd += ["-b:v", "4M"]

            # Resolution
            if res_val:
                cmd += ["-vf", f"scale={res_val}:force_original_aspect_ratio=decrease"]

            # FPS
            if fps_val != "🔒 Keep Original":
                cmd += ["-r", fps_val]

            # Audio
            if aud_cfg is None:
                cmd += ["-acodec", "copy"]
            elif aud_cfg.get("acodec") == "none":
                cmd += ["-an"]
            else:
                cmd += ["-acodec", aud_cfg["acodec"]]
                if aud_cfg.get("abitrate"):
                    cmd += ["-b:a", aud_cfg["abitrate"]]

            # Threads
            if threads > 0:
                cmd += ["-threads", str(threads)]

            # Fast start (streaming friendly)
            cmd += ["-movflags", "+faststart"]

            # Extra args
            if extra:
                cmd += extra.split()

            cmd.append(out_path)

            # Run
            duration = vf.info.get("duration", 0) or 0
            start_t  = time.time()

            try:
                proc = subprocess.Popen(
                    cmd,
                    stderr=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    universal_newlines=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self.current_proc = proc

                for line in proc.stderr:
                    if self.stop_flag.is_set():
                        proc.terminate()
                        break

                    # Parse time= from ffmpeg output
                    tm = re.search(r"time=(\d+):(\d+):(\d+)\.(\d+)", line)
                    if tm and duration > 0:
                        h,m,s,cs = map(int, tm.groups())
                        elapsed_enc = h*3600 + m*60 + s + cs/100
                        pct = min(elapsed_enc / duration * 100, 99)
                        vf.progress = pct

                        # Speed
                        sp = re.search(r"speed=\s*([\d.]+)x", line)
                        speed_str = f"{sp.group(1)}x" if sp else "—"
                        vf.speed  = speed_str

                        # ETA
                        elapsed_real = time.time() - start_t
                        if pct > 0:
                            total_est = elapsed_real / (pct/100)
                            eta_secs  = max(0, total_est - elapsed_real)
                            vf.eta = human_duration(eta_secs)
                        else:
                            vf.eta = "—"

                        self.q.put(("progress", (pct, speed_str, vf.eta, out_path)))
                        self.q.put(("refresh", None))

                proc.wait()
                self.current_proc = None

                if proc.returncode == 0 and not self.stop_flag.is_set():
                    vf.status   = "Done"
                    vf.progress = 100
                    success    += 1
                    self.q.put(("progress", (100, "", "", out_path)))
                    # Delete source?
                    if self.del_source_var.get():
                        try:
                            os.remove(vf.path)
                        except Exception:
                            pass
                else:
                    if not self.stop_flag.is_set():
                        vf.status = "Error"
                        vf.error  = f"FFmpeg exited with code {proc.returncode}"
                        failed += 1

            except FileNotFoundError:
                vf.status = "Error"
                vf.error  = "FFmpeg not found"
                failed += 1
            except Exception as e:
                vf.status = "Error"
                vf.error  = str(e)
                failed += 1

            self.q.put(("refresh", None))

        # Done
        self.converting = False
        self.q.put(("overall", 100))
        self.q.put(("done", (success, failed, total)))

        if self.open_after_var.get() and not self.stop_flag.is_set():
            out = self.out_path_var.get()
            if out != "Same as source" and os.path.isdir(out):
                if sys.platform == "win32":
                    os.startfile(out)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", out])
                else:
                    subprocess.Popen(["xdg-open", out])

    # ─── Queue polling ────────────────────────────────────────────────────────
    def _poll_queue(self):
        try:
            while True:
                msg, data = self.q.get_nowait()

                if msg == "refresh":
                    self._refresh_tree()

                elif msg == "status":
                    self.status_label.config(text=data)

                elif msg == "progress":
                    pct, speed, eta, out = data
                    self.file_progress["value"] = pct
                    self.pct_label.config(text=f"{pct:.1f}%")
                    if speed:
                        self.speed_label.config(text=f"Speed: {speed}")
                    if eta:
                        self.eta_label.config(text=f"ETA: {eta}")
                    if out and os.path.exists(out):
                        self.size_label.config(
                            text=f"Output: {human_size(os.path.getsize(out))}")

                elif msg == "overall":
                    self.overall_progress["value"] = data

                elif msg == "done":
                    success, failed, total = data
                    self.convert_btn.config(state="normal")
                    self.stop_btn.config(state="disabled")
                    self.status_label.config(
                        text=f"✅  Finished: {success}/{total} converted")
                    self.done_label.config(
                        text=f"✔ {success} OK   ✖ {failed} failed")
                    if failed == 0:
                        messagebox.showinfo(
                            "Conversion Complete",
                            f"🎉  All {success} file(s) converted successfully!")
                    else:
                        messagebox.showwarning(
                            "Conversion Finished",
                            f"✅ {success} succeeded\n❌ {failed} failed\n\n"
                            "Right-click a file and choose 'Show Info' to see errors.")
        except queue.Empty:
            pass

        self.root.after(80, self._poll_queue)


# ═══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()

    app = VideoConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
