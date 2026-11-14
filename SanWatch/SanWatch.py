"""
SanWatch - ad-free YouTube library for slow internet.

LIBRARY : paste YouTube links -> thumbnail cards. Watch (download once) / Stream / Brave.
DISCOVER: search YouTube by keyword inside the app, with "Load more".
MY FEED : latest videos from topics + channels you choose (cached for offline viewing).
AUTO-PLAY: plays the next video in the list automatically (mpv / VLC).
"""
import os, re, json, glob, shutil, threading, subprocess, urllib.request, webbrowser, zipfile, traceback
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    import yt_dlp
except Exception:
    yt_dlp = None
try:
    from PIL import Image, ImageTk
except Exception:
    Image = ImageTk = None

APP = "SanWatch"
DATA = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP)
THUMBS = os.path.join(DATA, "thumbs")
DB_FILE = os.path.join(DATA, "library.json")
DEFAULT_DL = os.path.join(os.path.expanduser("~"), "Videos", APP)
os.makedirs(THUMBS, exist_ok=True)

BG, PANEL, CARD, HOVER, RED, FG, MUTED, GREEN = (
    "#0f0f0f", "#181818", "#212121", "#2d2d2d", "#ff0033", "#f1f1f1", "#aaaaaa", "#2ecc71")
CW, TW, TH = 280, 260, 146
QUALITIES = ["144p", "240p", "360p", "480p", "720p", "1080p", "1440p", "2160p (4K)", "Best (original)"]
BEST = "Best (original)"
URL_RE = re.compile(r"(https?://(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)/[^\s]+)", re.I)


def load_db():
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            d.setdefault("items", [])
            if not d.get("v2"):
                d["quality"] = BEST
                d["v2"] = True
            d.setdefault("quality", BEST)
            d.setdefault("folder", DEFAULT_DL)
            return d
    except Exception:
        return {"items": [], "quality": BEST, "folder": DEFAULT_DL, "v2": True}


def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def fmt_dur(s):
    if not s:
        return ""
    s = int(s)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def find_vlc():
    for p in (r"C:\Program Files\VideoLAN\VLC\vlc.exe", r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"):
        if os.path.exists(p):
            return p
    return shutil.which("vlc")


FFDIR = os.path.join(DATA, "ffmpeg")
FF_URL = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"


def _add_ff_path():
    for root, dirs, files in os.walk(FFDIR):
        if "ffmpeg.exe" in files:
            os.environ["PATH"] = root + os.pathsep + os.environ.get("PATH", "")
            return


_add_ff_path()


def has_ffmpeg():
    return shutil.which("ffmpeg") is not None


def qh(q):
    m = re.match(r"(\d+)p", q or "")
    return int(m.group(1)) if m else None


def fmt_string(q):
    h = qh(q)
    cap = f"[height<={h}]" if h else ""
    if has_ffmpeg():
        return f"bestvideo{cap}+bestaudio/best{cap}/best"
    return f"best{cap}[ext=mp4]/best{cap}/best"


def fmt_string_stream(q):
    h = qh(q)
    cap = f"[height<={h}]" if h else ""
    return f"bestvideo{cap}+bestaudio/best{cap}/best"


def find_brave():
    la = os.environ.get("LOCALAPPDATA", "")
    for p in (r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
              r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
              os.path.join(la, r"BraveSoftware\Brave-Browser\Application\brave.exe")):
        if os.path.exists(p):
            return p
    return None


def log_error(ex):
    try:
        with open(os.path.join(DATA, "error.log"), "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
    except Exception:
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SanWatch  •  Ad-free YouTube")
        self.geometry("1100x700")
        self.minsize(640, 420)
        self.configure(bg=BG)
        self.db = load_db()
        self.imgs, self.cards, self.status_lbl = {}, [], {}
        self.busy = set()
        self.cols = 0
        self.mode = "library"
        self.results, self.search_q, self.search_n, self.more_available = [], "", 0, False
        self.db.setdefault("topics", [])
        self.db.setdefault("channels", [])
        self.feed_items = list(self.db.get("feed_cache", []))
        self.view_items = []
        self.loading = False
        self.qgen, self.cur_proc = 0, None
        self.thumb_sem = threading.Semaphore(4)
        self.more_btn = None
        self._ui()
        self.refresh()
        self.bind("<Control-v>", lambda e: self.paste_add() if self.focus_get() is not self.entry else None)
        self.bind("<Configure>", self._resize)
        if yt_dlp is None:
            messagebox.showerror("Missing", "yt-dlp is not installed.\nRun:  pip install yt-dlp pillow")

    # ---------------- UI
    def _ui(self):
        top = tk.Frame(self, bg=PANEL)
        top.pack(fill="x")
        tk.Label(top, text="▶ San", bg=PANEL, fg=RED, font=("Segoe UI", 17, "bold")).pack(side="left", padx=(16, 0), pady=10)
        tk.Label(top, text="Watch", bg=PANEL, fg=FG, font=("Segoe UI", 17, "bold")).pack(side="left", pady=10)

        self.url = tk.StringVar()
        self.entry = tk.Entry(top, textvariable=self.url, bg=CARD, fg=FG, insertbackground=FG, relief="flat",
                              font=("Segoe UI", 11))
        self.entry.pack(side="left", fill="x", expand=True, padx=14, ipady=7)
        self.entry.bind("<Return>", lambda e: self.add_from_entry())
        self._b(top, "＋ Add", self.add_from_entry, RED).pack(side="left")
        self._b(top, "📋 Paste & Add", self.paste_add, HOVER).pack(side="left", padx=8)

        tabrow = tk.Frame(self, bg=BG)
        tabrow.pack(fill="x", padx=16, pady=(10, 0))
        self.tab_btns = {}
        for key, label in (("library", "📚 Library"), ("discover", "🔍 Discover"), ("feed", "📰 My Feed")):
            b = tk.Button(tabrow, text=label, command=lambda k=key: self.switch_mode(k), relief="flat", bd=0,
                          padx=14, pady=6, cursor="hand2", font=("Segoe UI", 10, "bold"))
            b.pack(side="left", padx=(0, 6))
            self.tab_btns[key] = b
        self.autoplay = tk.BooleanVar(value=self.db.get("autoplay", True))
        tk.Checkbutton(tabrow, text="Auto-play next", variable=self.autoplay, command=self._save_autoplay,
                       bg=BG, fg=MUTED, selectcolor=CARD, activebackground=BG, activeforeground=FG,
                       bd=0).pack(side="left", padx=(10, 0))
        self._b(tabrow, "▶ Play all", self.play_all, HOVER).pack(side="left", padx=6)
        self._b(tabrow, "⏹ Stop", self.stop_queue, HOVER).pack(side="left")
        self.feedbar = tk.Frame(tabrow, bg=BG)
        self._b(self.feedbar, "🔄 Refresh feed", self.load_feed, CARD).pack(side="left", padx=(10, 4))
        self._b(self.feedbar, "⚙ Manage feed", self.manage_feed, CARD).pack(side="left")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.refresh() if self.mode == "library" else None)
        self._b(tabrow, "Search YouTube", self.yt_search_btn, RED).pack(side="right")
        self.search_entry = tk.Entry(tabrow, textvariable=self.search, bg=CARD, fg=FG, insertbackground=FG,
                                     relief="flat", width=28, font=("Segoe UI", 11))
        self.search_entry.pack(side="right", padx=8, ipady=5)
        self.search_entry.bind("<Return>", lambda e: self.on_search_enter())
        self.hint = tk.Label(tabrow, text="filter library:", bg=BG, fg=MUTED, font=("Segoe UI", 8))
        self.hint.pack(side="right")

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=16, pady=(10, 0))
        tk.Label(bar, text="Quality:", bg=BG, fg=MUTED).pack(side="left")
        self.q = tk.StringVar(value=self.db["quality"])
        cb = ttk.Combobox(bar, textvariable=self.q, values=QUALITIES, width=16, state="readonly")
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self._opt())
        tk.Label(bar, text="(lower = less data)", bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(side="left")
        self._b(bar, "📂 Videos folder", self.open_folder, CARD).pack(side="right")
        self._b(bar, "🎞 Get ffmpeg (4K)", self.get_ffmpeg, CARD).pack(side="right", padx=6)
        self._b(bar, "🎬 Set player", self.set_player, CARD).pack(side="right")
        self._b(bar, "⚙ Change folder", self.change_folder, CARD).pack(side="right", padx=6)

        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        self.cv = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, command=self.cv.yview)
        self.cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.cv.pack(side="left", fill="both", expand=True)
        self.gf = tk.Frame(self.cv, bg=BG)
        self.cv.create_window((0, 0), window=self.gf, anchor="nw")
        self.gf.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.cv.bind_all("<MouseWheel>", lambda e: self.cv.yview_scroll(int(-e.delta / 120), "units"))

        self.msg = tk.Label(self, text="", bg=PANEL, fg=MUTED, anchor="w", font=("Segoe UI", 9))
        self.msg.pack(fill="x", side="bottom", ipady=4)
        self.menu = tk.Menu(self, tearoff=0, bg=PANEL, fg=FG, activebackground=RED)
        self._style_tabs()

    def _b(self, p, t, c, col):
        return tk.Button(p, text=t, command=c, bg=col, fg="white", relief="flat", bd=0, padx=12, pady=6,
                         activebackground=HOVER, activeforeground="white", cursor="hand2",
                         font=("Segoe UI", 10, "bold"))

    def _opt(self):
        self.db["quality"] = self.q.get()
        save_db(self.db)

    def say(self, t):
        self.after(0, lambda: self.msg.config(text="  " + t))

    # ---------------- library
    def local_file(self, it):
        f = it.get("file")
        return f if f and os.path.exists(f) else None

    def thumb_img(self, it):
        vid = it["id"]
        if vid in self.imgs:
            return self.imgs[vid]
        img = None
        p = os.path.join(THUMBS, vid + ".img")
        try:
            if Image and os.path.exists(p):
                im = Image.open(p).convert("RGB").resize((TW, TH), Image.LANCZOS)
                img = ImageTk.PhotoImage(im)
        except Exception:
            img = None
        if img:
            self.imgs[vid] = img
        return img

    def lib_item(self, vid):
        for i in self.db["items"]:
            if i["id"] == vid:
                return i
        return None

    def ensure_in_library(self, it):
        lib = self.lib_item(it["id"])
        if lib:
            return lib
        it.setdefault("file", None)
        self.db["items"].insert(0, it)
        save_db(self.db)
        return it

    def current_items(self):
        if self.mode == "library":
            q = self.search.get().strip().lower()
            return [i for i in self.db["items"] if q in i["title"].lower() or q in i.get("channel", "").lower()]
        raw = self.results if self.mode == "discover" else self.feed_items
        return [self.lib_item(i["id"]) or i for i in raw]

    def refresh(self):
        for c in self.cards:
            c.destroy()
        self.cards, self.status_lbl = [], {}
        self.more_btn = None
        items = self.current_items()
        self.view_items = items
        for it in items:
            self.cards.append(self._card(it))
        if self.mode == "discover" and items and self.more_available:
            self.more_btn = self._b(self.gf, "⬇ Load more results", self.load_more, HOVER)
            self.cards.append(self.more_btn)
        if not items:
            if self.mode == "library":
                hint = "Your library is empty.\nPaste a YouTube link above, or use 🔍 Discover to search YouTube."
            elif self.mode == "discover":
                hint = (f"No results for '{self.search_q}'." if self.search_q else
                        "Type a topic in the search box (for example: car) and press Enter.")
            else:
                hint = "Your feed is empty.\nClick ⚙ Manage feed to add topics or channels."
            self.cards.append(tk.Label(self.gf, text=hint, bg=BG, fg=MUTED, font=("Segoe UI", 12),
                                       justify="center", pady=60))
        self._layout()
        n = len(items)
        if self.mode == "library":
            self.msg.config(text=f"  {len(self.db['items'])} video(s)  •  ✔ = saved offline (no data needed)")
        elif self.mode == "discover":
            self.msg.config(text=f"  Search: '{self.search_q}'  •  {n} result(s)" if self.search_q else
                            "  Discover: search YouTube by keyword")
        else:
            self.msg.config(text=f"  My Feed  •  {n} video(s)  •  stored on your PC, refresh when you have data")

    def _card(self, it):
        f = tk.Frame(self.gf, bg=CARD, width=CW)
        img = self.thumb_img(it)
        if img:
            tl = tk.Label(f, image=img, bg="black", cursor="hand2")
        else:
            tl = tk.Label(f, text="▶", bg="black", fg=FG, width=36, height=8, cursor="hand2")
            self._async_thumb(it, tl)
        tl.pack(padx=10, pady=(10, 6))
        tl.bind("<Button-1>", lambda e, it=it: self.watch(it))
        tk.Label(f, text=it["title"], bg=CARD, fg=FG, font=("Segoe UI", 10, "bold"), wraplength=TW,
                 justify="left", anchor="w").pack(fill="x", padx=12)
        info = f"{it.get('channel','')}  •  {fmt_dur(it.get('duration'))}"
        tk.Label(f, text=info, bg=CARD, fg=MUTED, font=("Segoe UI", 8), anchor="w").pack(fill="x", padx=12)
        saved = self.local_file(it)
        st = tk.Label(f, text=("✔ Saved offline" if saved else "☁ Online only"), bg=CARD,
                      fg=(GREEN if saved else MUTED), font=("Segoe UI", 8, "bold"), anchor="w")
        st.pack(fill="x", padx=12, pady=(2, 4))
        self.status_lbl[it["id"]] = st
        row = tk.Frame(f, bg=CARD)
        row.pack(fill="x", padx=10, pady=(0, 4))
        tk.Button(row, text="▶ Watch", command=lambda: self.watch(it), bg=RED, fg="white", relief="flat",
                  bd=0, padx=10, pady=3, cursor="hand2").pack(side="left")
        tk.Button(row, text="⬇ Save", command=lambda: self.download(it), bg=HOVER, fg=FG, relief="flat",
                  bd=0, padx=10, pady=3, cursor="hand2").pack(side="left", padx=6)
        tk.Button(row, text="📡 Stream", command=lambda: self.stream(it), bg=HOVER, fg=FG, relief="flat",
                  bd=0, padx=10, pady=3, cursor="hand2").pack(side="left")
        row2 = tk.Frame(f, bg=CARD)
        row2.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(row2, text="🦁 Brave", command=lambda: self.open_brave(it), bg=HOVER, fg=FG,
                  relief="flat", bd=0, padx=10, pady=3, cursor="hand2").pack(side="left")
        if self.lib_item(it["id"]) is None:
            lb = tk.Button(row2, text="＋ Library", bg=HOVER, fg=FG, relief="flat", bd=0, padx=10, pady=3,
                           cursor="hand2")
            lb.config(command=lambda it=it, lb=lb: (self.ensure_in_library(it),
                                                    lb.config(text="✔ In library", state="disabled")))
            lb.pack(side="left", padx=6)
        for w in (f, tl):
            w.bind("<Button-3>", lambda e, it=it: self.popup(e, it))
        return f

    def _layout(self):
        cols = max(1, max(self.cv.winfo_width(), CW) // (CW + 14))
        self.cols = cols
        n = 0
        for c in self.cards:
            if isinstance(c, tk.Frame):
                c.grid(row=n // cols, column=n % cols, padx=7, pady=7, sticky="n")
                n += 1
            else:
                c.grid(row=(n + cols - 1) // cols + 1, column=0, columnspan=cols, pady=14)

    def _resize(self, e):
        if e.widget is self:
            cols = max(1, max(self.cv.winfo_width(), CW) // (CW + 14))
            if cols != self.cols:
                self._layout()

    def popup(self, e, it):
        m = self.menu
        m.delete(0, "end")
        m.add_command(label="▶ Watch", command=lambda: self.watch(it))
        m.add_command(label="⬇ Save offline", command=lambda: self.download(it))
        m.add_command(label="📡 Stream (mpv / VLC)", command=lambda: self.stream(it))
        m.add_command(label="🦁 Open in Brave", command=lambda: self.open_brave(it))
        m.add_command(label="📋 Copy link", command=lambda: (self.clipboard_clear(), self.clipboard_append(it["url"])))
        if self.lib_item(it["id"]) is None:
            m.add_command(label="➕ Add to library", command=lambda: (self.ensure_in_library(it), self.say("Added to library.")))
        m.add_separator()
        m.add_command(label="🗑 Delete downloaded file", command=lambda: self.del_file(it))
        m.add_command(label="❌ Remove from list", command=lambda: self.remove(it))
        m.tk_popup(e.x_root, e.y_root)

    # ---------------- discover / feed
    def _style_tabs(self):
        for k, b in self.tab_btns.items():
            on = (k == self.mode)
            b.config(bg=RED if on else CARD, fg="white" if on else MUTED,
                     activebackground=HOVER, activeforeground="white")

    def switch_mode(self, mode):
        self.mode = mode
        self._style_tabs()
        self.hint.config(text={"library": "filter library:", "discover": "search YouTube (Enter):",
                               "feed": "search YouTube:"}[mode])
        if mode == "feed":
            self.feedbar.pack(side="left")
            if not self.feed_items and (self.db["topics"] or self.db["channels"]):
                self.load_feed()
        else:
            self.feedbar.pack_forget()
        self.refresh()

    def _save_autoplay(self):
        self.db["autoplay"] = self.autoplay.get()
        save_db(self.db)

    def on_search_enter(self):
        if self.mode != "library":
            self.yt_search_btn()

    def yt_search_btn(self):
        q = self.search.get().strip()
        if not q:
            self.say("Type something to search, for example: car")
            return
        if self.mode != "discover":
            self.switch_mode("discover")
        self.run_search(q)

    def run_search(self, q, more=False):
        if yt_dlp is None:
            return
        if self.loading:
            self.say("Still loading… please wait.")
            return
        self.loading = True
        if not more:
            self.search_q = q
            n = 20
        else:
            n = self.search_n + 20
        threading.Thread(target=self._search, args=(self.search_q, n, more), daemon=True).start()

    def load_more(self):
        self.run_search(self.search_q, more=True)

    def _flat(self, spec, limit=None):
        opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True,
                "socket_timeout": 30, "retries": 5}
        if limit:
            opts["playlistend"] = limit
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(spec, download=False)
        out, seen = [], set()
        for e in (info.get("entries") or []):
            if not e:
                continue
            vid = e.get("id")
            if not vid or len(vid) != 11 or vid in seen:
                continue
            seen.add(vid)
            out.append({"id": vid, "url": f"https://www.youtube.com/watch?v={vid}",
                        "title": e.get("title") or vid,
                        "channel": e.get("channel") or e.get("uploader") or "",
                        "duration": e.get("duration"), "file": None})
        return out

    def _search(self, q, n, more):
        self.say(f"Searching YouTube for '{q}'…  (a few seconds on slow internet)")
        try:
            items = self._flat(f"ytsearch{n}:{q}")

            def done():
                y = self.cv.yview()[0]
                self.results = items
                self.search_n = n
                self.more_available = len(items) >= n - 3
                self.loading = False
                if self.mode == "discover":
                    self.refresh()
                    if more:
                        self.update_idletasks()
                        self.cv.yview_moveto(y)
                self.say(f"Found {len(items)} video(s) for '{q}'. Click Stream / Watch to play.")
            self.after(0, done)
        except Exception as ex:
            log_error(ex)
            self.loading = False
            self.say("Search failed.")
            msg = str(ex)[:350]
            self.after(0, lambda: messagebox.showerror(
                "Search failed", msg + "\n\nCheck internet, or update: pip install -U yt-dlp"))

    @staticmethod
    def is_channel(v):
        v = v.strip()
        return v.startswith("@") or ("youtube.com/" in v and any(k in v for k in ("/@", "/channel/", "/c/", "/user/")))

    @staticmethod
    def channel_url(v):
        v = v.strip()
        if v.startswith("@"):
            v = "https://www.youtube.com/" + v
        v = v.split("?")[0].rstrip("/")
        for tail in ("/videos", "/featured", "/streams", "/shorts", "/playlists"):
            if v.endswith(tail):
                v = v[: -len(tail)]
        return v + "/videos"

    def load_feed(self):
        if self.loading:
            self.say("Still loading… please wait.")
            return
        if not (self.db["topics"] or self.db["channels"]):
            self.manage_feed()
            return
        self.loading = True
        threading.Thread(target=self._feed, daemon=True).start()

    def _feed(self):
        self.say("Refreshing your feed…  (small data: titles + thumbnails only)")
        lists, fails = [], 0
        for t in list(self.db["topics"]):
            try:
                lists.append(self._flat(f"ytsearchdate8:{t}"))
            except Exception as ex:
                log_error(ex)
                fails += 1
        for c in list(self.db["channels"]):
            try:
                es = self._flat(self.channel_url(c["url"]), limit=8)[:8]
                for e in es:
                    e["channel"] = e["channel"] or c["name"]
                lists.append(es)
            except Exception as ex:
                log_error(ex)
                fails += 1
        merged, seen = [], set()
        for i in range(8):
            for l in lists:
                if i < len(l) and l[i]["id"] not in seen:
                    seen.add(l[i]["id"])
                    merged.append(l[i])

        def done():
            self.loading = False
            if merged or not fails:
                self.feed_items = merged
                self.db["feed_cache"] = [dict(x, file=None) for x in merged]
                save_db(self.db)
            if self.mode == "feed":
                self.refresh()
            self.say(f"Feed updated: {len(merged)} video(s)" + (f"  ({fails} source(s) failed)" if fails else ""))
        self.after(0, done)

    def manage_feed(self):
        w = tk.Toplevel(self)
        w.title("Manage feed")
        w.configure(bg=BG)
        w.geometry("470x470")
        w.transient(self)
        tk.Label(w, text="Add a topic (example: python tutorial) or a channel (@handle or channel link).",
                 bg=BG, fg=FG, wraplength=430, justify="left").pack(padx=14, pady=(14, 6), anchor="w")
        row = tk.Frame(w, bg=BG)
        row.pack(fill="x", padx=14)
        ev = tk.StringVar()
        e = tk.Entry(row, textvariable=ev, bg=CARD, fg=FG, insertbackground=FG, relief="flat",
                     font=("Segoe UI", 11))
        e.pack(side="left", fill="x", expand=True, ipady=6)
        lb = tk.Listbox(w, bg=CARD, fg=FG, selectbackground=RED, relief="flat", height=14,
                        font=("Segoe UI", 10), activestyle="none")
        lb.pack(fill="both", expand=True, padx=14, pady=10)

        def fill():
            lb.delete(0, "end")
            for t in self.db["topics"]:
                lb.insert("end", "🔎  " + t)
            for c in self.db["channels"]:
                lb.insert("end", "📺  " + c["name"])

        def add(_=None):
            v = ev.get().strip()
            if not v:
                return
            if self.is_channel(v):
                m = re.search(r"(@[\w.\-]+)", v)
                name = m.group(1) if m else v.rstrip("/").split("/")[-1]
                if not any(c["url"] == v for c in self.db["channels"]):
                    self.db["channels"].append({"name": name, "url": v})
            elif v not in self.db["topics"]:
                self.db["topics"].append(v)
            save_db(self.db)
            ev.set("")
            fill()

        def remove():
            sel = lb.curselection()
            if not sel:
                return
            i, nt = sel[0], len(self.db["topics"])
            if i < nt:
                del self.db["topics"][i]
            else:
                del self.db["channels"][i - nt]
            save_db(self.db)
            fill()

        def done():
            w.destroy()
            self.switch_mode("feed")
            if self.db["topics"] or self.db["channels"]:
                self.load_feed()

        e.bind("<Return>", add)
        self._b(row, "Add", add, RED).pack(side="left", padx=(8, 0))
        btns = tk.Frame(w, bg=BG)
        btns.pack(pady=(0, 14))
        self._b(btns, "Remove selected", remove, CARD).pack(side="left", padx=6)
        self._b(btns, "Done & refresh feed", done, RED).pack(side="left", padx=6)
        fill()
        e.focus_set()

    def _async_thumb(self, it, label):
        vid = it["id"]

        def run():
            p = os.path.join(THUMBS, vid + ".img")
            with self.thumb_sem:
                if not os.path.exists(p):
                    try:
                        data = urllib.request.urlopen(f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                                                      timeout=30).read()
                        with open(p, "wb") as fh:
                            fh.write(data)
                    except Exception:
                        return

            def setit():
                try:
                    img = self.thumb_img(it)
                    if img:
                        label.config(image=img, text="", width=0, height=0)
                except tk.TclError:
                    pass
            self.after(0, setit)
        threading.Thread(target=run, daemon=True).start()

    # ---------------- add
    def paste_add(self):
        try:
            txt = self.clipboard_get()
        except Exception:
            txt = ""
        self._add_text(txt)

    def add_from_entry(self):
        self._add_text(self.url.get())
        self.url.set("")

    def _add_text(self, txt):
        urls = URL_RE.findall(txt or "")
        if not urls:
            messagebox.showinfo("No link", "Copy a YouTube video link first, then click Paste & Add.")
            return
        for u in urls:
            threading.Thread(target=self._fetch, args=(u.strip(),), daemon=True).start()

    def _fetch(self, url):
        if yt_dlp is None:
            return
        self.say("Fetching video info…")
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True,
                                   "skip_download": True, "socket_timeout": 30, "retries": 10}) as y:
                info = y.extract_info(url, download=False)
            vid = info["id"]
            if any(i["id"] == vid for i in self.db["items"]):
                self.say("Already in your list.")
                return
            th = info.get("thumbnail")
            if th:
                try:
                    data = urllib.request.urlopen(th, timeout=30).read()
                    with open(os.path.join(THUMBS, vid + ".img"), "wb") as f:
                        f.write(data)
                except Exception:
                    pass
            it = {"id": vid, "url": f"https://www.youtube.com/watch?v={vid}",
                  "title": info.get("title", vid), "channel": info.get("uploader", ""),
                  "duration": info.get("duration"), "file": None}
            self.db["items"].insert(0, it)
            save_db(self.db)
            self.after(0, self.refresh)
            self.say(f"Added: {it['title']}")
        except Exception as ex:
            log_error(ex)
            self.say("Could not add link (check internet / link).")
            msg = str(ex)[:400]
            self.after(0, lambda: messagebox.showerror("Add failed", msg))

    # ---------------- actions
    def set_status(self, vid, text, color=MUTED):
        def f():
            l = self.status_lbl.get(vid)
            if l:
                try:
                    l.config(text=text, fg=color)
                except Exception:
                    pass
        self.after(0, f)

    def watch(self, it):
        it = self.lib_item(it["id"]) or it
        fp = self.local_file(it)
        if fp:
            if self.autoplay.get() and self.find_player():
                self.stream(it)
            else:
                os.startfile(fp)
                self.say(f"Playing: {it['title']}")
        else:
            self.download(it, play_after=True)

    def download(self, it, play_after=False):
        it = self.ensure_in_library(it)
        vid = it["id"]
        if self.local_file(it):
            self.say("Already saved offline.")
            if play_after:
                os.startfile(it["file"])
            return
        if vid in self.busy:
            self.say("Already downloading…")
            return
        h = qh(self.db["quality"])
        if not has_ffmpeg() and (h is None or h > 720) and not getattr(self, "_ff_warned", False):
            self._ff_warned = True
            messagebox.showinfo("ffmpeg needed for full quality",
                                "1080p / 4K / original quality needs ffmpeg to join video + audio.\n\n"
                                "Click '🎞 Get ffmpeg (4K)' once (about 100 MB), then download again.\n\n"
                                "For now it will download the best single-file quality.")
        self.busy.add(vid)
        threading.Thread(target=self._dl, args=(it, play_after), daemon=True).start()

    def _dl(self, it, play_after):
        vid = it["id"]
        folder = self.db["folder"]
        os.makedirs(folder, exist_ok=True)

        def hook(d):
            if d["status"] == "downloading":
                tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes", 0)
                pct = f"{done * 100 / tot:.0f}%" if tot else ""
                spd = d.get("_speed_str", "").strip()
                self.set_status(vid, f"⬇ Downloading {pct}  {spd}", "#f1c40f")
            elif d["status"] == "finished":
                self.set_status(vid, "Finishing…", "#f1c40f")

        opts = {"format": fmt_string(self.db["quality"]),
                "outtmpl": os.path.join(folder, "%(title).80s [%(id)s].%(ext)s"),
                "noplaylist": True, "quiet": True, "no_warnings": True,
                "retries": 30, "fragment_retries": 30, "continuedl": True,
                "socket_timeout": 30, "progress_hooks": [hook], "windowsfilenames": True}
        if has_ffmpeg():
            h = qh(self.db["quality"])
            opts["merge_output_format"] = "mkv" if (h is None or h > 1080) else "mp4"
        try:
            with yt_dlp.YoutubeDL(opts) as y:
                info = y.extract_info(it["url"], download=True)
                fp = y.prepare_filename(info)
            if not os.path.exists(fp):
                c = [p for p in glob.glob(os.path.join(folder, f"*[[]{vid}[]].*")) if not p.endswith((".part", ".ytdl"))]
                fp = c[0] if c else None
            if not fp:
                raise RuntimeError("Downloaded file not found")
            it["file"] = fp
            save_db(self.db)
            self.set_status(vid, "✔ Saved offline", GREEN)
            self.say(f"Saved: {it['title']}")
            if play_after:
                os.startfile(fp)
        except Exception as ex:
            log_error(ex)
            self.set_status(vid, "⚠ Failed - click Save to resume", "#e74c3c")
            self.say("Download interrupted. Click Save again to RESUME.")
            msg = str(ex)[:350]
            self.after(0, lambda: messagebox.showerror("Download problem", msg))
        finally:
            self.busy.discard(vid)

    def find_player(self):
        p = self.db.get("player")
        if p and os.path.exists(p):
            return p
        for c in (shutil.which("mpv"), os.path.join(DATA, "mpv", "mpv.exe"),
                  r"C:\Program Files\mpv\mpv.exe", r"C:\Program Files (x86)\mpv\mpv.exe"):
            if c and os.path.exists(c):
                return c
        return find_vlc()

    def set_player(self):
        p = filedialog.askopenfilename(title="Select mpv.exe or vlc.exe",
                                       filetypes=[("Player", "*.exe")])
        if p:
            self.db["player"] = p
            save_db(self.db)
            self.say("Player set: " + p)

    def _no_player_msg(self):
        if messagebox.askyesno("Player needed",
                               "Online streaming needs a free player: VLC or mpv.\n\n"
                               "Open the VLC download page now?\n\n"
                               "(After installing it is detected automatically.\n"
                               "You can also use the '🦁 Brave' button instead.)"):
            webbrowser.open("https://www.videolan.org/vlc/")

    def stream(self, it):
        it = self.lib_item(it["id"]) or it
        player = self.find_player()
        fp = self.local_file(it)
        if not player:
            if fp:
                os.startfile(fp)
            else:
                self._no_player_msg()
            return
        if self.autoplay.get():
            items = self.view_items
            idx = next((k for k, x in enumerate(items) if x["id"] == it["id"]), None)
            if idx is None:
                items, idx = [it], 0
            self.start_queue(items, idx)
            return
        self.say("Getting ad-free stream… (takes a few seconds)")
        threading.Thread(target=self._stream, args=(it, player), daemon=True).start()

    def _cmd_for(self, it, player):
        vlc = "vlc" in os.path.basename(player).lower()
        extra = ["--play-and-exit", "--no-one-instance"] if vlc else []
        fp = self.local_file(it)
        if fp:
            return [player, fp] + extra
        fmt = fmt_string_stream(self.db["quality"])
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True,
                               "format": fmt, "socket_timeout": 30, "retries": 10}) as y:
            info = y.extract_info(it["url"], download=False)
        rf = info.get("requested_formats") or [info]
        vurl = rf[0].get("url")
        aurl = rf[1].get("url") if len(rf) > 1 else None
        if not vurl:
            raise RuntimeError("No playable stream URL returned for this video.")
        hdr = rf[0].get("http_headers") or info.get("http_headers") or {}
        ua = hdr.get("User-Agent", "Mozilla/5.0")
        if not vlc:
            cmd = [player, vurl, "--user-agent=" + ua, "--force-media-title=" + it["title"],
                   "--cache=yes", "--demuxer-max-bytes=300MiB"]
            if aurl:
                cmd.insert(2, "--audio-file=" + aurl)
        else:
            cmd = [player, vurl, "--http-user-agent=" + ua, "--meta-title=" + it["title"]] + extra
            if aurl:
                cmd.insert(2, "--input-slave=" + aurl)
        return cmd

    def _stream(self, it, player):
        try:
            cmd = self._cmd_for(it, player)
            self.cur_proc = subprocess.Popen(cmd)
            self.say(f"Streaming (no ads): {it['title']}")
        except Exception as ex:
            log_error(ex)
            self.say("Stream failed - see message.")
            msg = str(ex)[:400]
            self.after(0, lambda: messagebox.showerror(
                "Stream failed",
                msg + "\n\nTry: pip install -U yt-dlp , or use Watch (download), or 🦁 Brave."))

    # ---- auto-play queue
    def play_all(self):
        items = list(self.view_items)
        if not items:
            self.say("Nothing to play in this list.")
            return
        player = self.find_player()
        if not player:
            self._no_player_msg()
            return
        self.start_queue(items, 0)

    def start_queue(self, items, idx):
        player = self.find_player()
        if not player:
            self._no_player_msg()
            return
        self.stop_queue(silent=True)
        gen = self.qgen
        self.say("Starting…  (auto-play is ON: next video plays automatically)")
        threading.Thread(target=self._run_queue, args=(list(items[idx:]), player, gen), daemon=True).start()

    def stop_queue(self, silent=False):
        self.qgen += 1
        p = self.cur_proc
        if p is not None and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass
        if not silent:
            self.say("Stopped.")

    def _run_queue(self, items, player, gen):
        i = 0
        while i < len(items) and gen == self.qgen:
            it = items[i]
            try:
                cmd = self._cmd_for(it, player)
            except Exception as ex:
                log_error(ex)
                self.say("Could not get that video - see message.")
                msg = f"{it['title']}\n\n{str(ex)[:300]}"
                self.after(0, lambda m=msg: messagebox.showerror("Stream failed", m))
                break
            if gen != self.qgen:
                break
            proc = subprocess.Popen(cmd)
            self.cur_proc = proc
            self.say(f"▶ Playing ({i + 1}/{len(items)}): {it['title']}")
            proc.wait()
            if gen != self.qgen:
                break
            i += 1
            if i >= len(items):
                self.say("Queue finished.")
                break
            ev, res = threading.Event(), {"go": True}
            self.after(0, lambda n=items[i], ev=ev, res=res: self._upnext(n, ev, res))
            while not ev.wait(0.5):
                if gen != self.qgen:
                    break
            if not res["go"] or gen != self.qgen:
                break

    def _upnext(self, nxt, ev, res):
        w = tk.Toplevel(self)
        w.title("Up next")
        w.configure(bg=PANEL)
        w.attributes("-topmost", True)
        w.geometry("+%d+%d" % (self.winfo_x() + 80, self.winfo_y() + 80))
        tk.Label(w, text="Up next:", bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(padx=16, pady=(14, 0), anchor="w")
        tk.Label(w, text=nxt["title"], bg=PANEL, fg=FG, font=("Segoe UI", 11, "bold"),
                 wraplength=380, justify="left").pack(padx=16, pady=4, anchor="w")
        cd = tk.Label(w, text="", bg=PANEL, fg=RED, font=("Segoe UI", 10, "bold"))
        cd.pack(padx=16, anchor="w")
        st = {"n": 6, "done": False}

        def finish(go):
            if st["done"]:
                return
            st["done"] = True
            res["go"] = go
            ev.set()
            w.destroy()

        def tick():
            if st["done"]:
                return
            if st["n"] <= 0:
                finish(True)
                return
            cd.config(text=f"Playing in {st['n']}s")
            st["n"] -= 1
            w.after(1000, tick)

        row = tk.Frame(w, bg=PANEL)
        row.pack(pady=12)
        self._b(row, "▶ Play now", lambda: finish(True), RED).pack(side="left", padx=6)
        self._b(row, "⏹ Stop", lambda: finish(False), HOVER).pack(side="left", padx=6)
        w.protocol("WM_DELETE_WINDOW", lambda: finish(False))
        tick()

    def open_brave(self, it):
        b = find_brave()
        if b:
            subprocess.Popen([b, it["url"]])
            self.say("Opened in Brave (Shields blocks YouTube ads).")
        else:
            webbrowser.open(it["url"])
            self.say("Brave not found - opened in default browser.")

    def get_ffmpeg(self):
        if has_ffmpeg():
            messagebox.showinfo("ffmpeg", "ffmpeg is already available.")
            return
        if not messagebox.askyesno("Get ffmpeg",
                                   "Download ffmpeg once (about 100-130 MB) from GitHub?\n\n"
                                   "Needed for 1080p / 4K / original quality downloads. "
                                   "Do this on a good connection."):
            return
        threading.Thread(target=self._get_ff, daemon=True).start()

    def _get_ff(self):
        try:
            os.makedirs(FFDIR, exist_ok=True)
            zp = os.path.join(FFDIR, "ffmpeg.zip")
            with urllib.request.urlopen(FF_URL, timeout=60) as r, open(zp, "wb") as f:
                tot = int(r.headers.get("Content-Length", 0))
                done = 0
                while True:
                    chunk = r.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if tot:
                        self.say(f"Downloading ffmpeg… {done * 100 // tot}%")
            self.say("Extracting ffmpeg…")
            with zipfile.ZipFile(zp) as z:
                z.extractall(FFDIR)
            os.remove(zp)
            _add_ff_path()
            self.say("ffmpeg ready! 1080p / 4K downloads enabled.")
            self.after(0, lambda: messagebox.showinfo("ffmpeg", "ffmpeg installed. You can now download 4K."))
        except Exception as ex:
            log_error(ex)
            self.say("ffmpeg download failed.")
            msg = str(ex)[:300]
            self.after(0, lambda: messagebox.showerror("ffmpeg failed", msg))

    def del_file(self, it):
        fp = self.local_file(it)
        if fp and messagebox.askyesno("Delete", "Delete the downloaded video file from your PC?"):
            try:
                os.remove(fp)
            except Exception:
                pass
            it["file"] = None
            save_db(self.db)
            self.refresh()

    def remove(self, it):
        if messagebox.askyesno("Remove", f"Remove from list?\n{it['title']}\n(Downloaded file is kept.)"):
            self.db["items"] = [i for i in self.db["items"] if i is not it]
            save_db(self.db)
            self.refresh()

    def open_folder(self):
        os.makedirs(self.db["folder"], exist_ok=True)
        os.startfile(self.db["folder"])

    def change_folder(self):
        d = filedialog.askdirectory(title="Where should videos be saved?")
        if d:
            self.db["folder"] = d
            save_db(self.db)
            self.say("Videos will be saved to: " + d)


if __name__ == "__main__":
    App().mainloop()
