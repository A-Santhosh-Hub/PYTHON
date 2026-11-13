"""
SanGameLauncher - a tiny game library for Windows.
Keep all your game shortcuts inside ONE app, so your desktop stays clean.

- Add games (.lnk / .exe / .url) from Settings
- Import & MOVE shortcuts straight off your Desktop
- Double-click a tile to play
- Right-click a tile: Play / Rename / Open location / Remove
"""
import os, sys, json, shutil, subprocess, hashlib, glob
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

APP = "SanGameLauncher"
DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP)
ICON_DIR = os.path.join(DATA_DIR, "icons")
LINK_DIR = os.path.join(DATA_DIR, "shortcuts")      # moved desktop shortcuts live here
DB_FILE = os.path.join(DATA_DIR, "games.json")
for d in (DATA_DIR, ICON_DIR, LINK_DIR):
    os.makedirs(d, exist_ok=True)

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except Exception:
    HAS_PIL = False

BG, PANEL, TILE, TILE_HOVER, ACCENT, FG, MUTED = (
    "#0f1117", "#171a23", "#1d212d", "#2a3046", "#7c5cff", "#e8eaf2", "#8b90a3")
TILE_W, TILE_H, ICON = 130, 130, 64
NOWIN = 0x08000000  # CREATE_NO_WINDOW


# ---------------------------------------------------------------- data
def load_db():
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"games": [], "minimize_on_launch": True}


def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def icon_path_for(target):
    h = hashlib.md5(target.lower().encode("utf-8")).hexdigest()
    return os.path.join(ICON_DIR, h + ".png")


def extract_icon(target):
    """Extract the Windows icon of a .lnk/.exe/.url into a cached PNG."""
    out = icon_path_for(target)
    if os.path.exists(out):
        return out
    ps = ("Add-Type -AssemblyName System.Drawing;"
          "$i=[System.Drawing.Icon]::ExtractAssociatedIcon('%s');"
          "$i.ToBitmap().Save('%s',[System.Drawing.Imaging.ImageFormat]::Png)"
          % (target.replace("'", "''"), out.replace("'", "''")))
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       creationflags=NOWIN, timeout=20,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    return out if os.path.exists(out) else None


def nice_name(path):
    n = os.path.splitext(os.path.basename(path))[0]
    for junk in (" - Shortcut", " - shortcut", ".exe"):
        n = n.replace(junk, "")
    return n.strip() or "Game"


# ---------------------------------------------------------------- app
class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("San Game Launcher")
        self.geometry("980x640")
        self.minsize(560, 400)
        self.configure(bg=BG)
        self.db = load_db()
        self.imgs = {}
        self.tiles = []
        self.cols = 0
        self._build_ui()
        self.refresh()
        self.bind("<Configure>", self._on_resize)

    # ---------- UI
    def _build_ui(self):
        top = tk.Frame(self, bg=PANEL, height=56)
        top.pack(fill="x")
        tk.Label(top, text="🎮  San Game Launcher", bg=PANEL, fg=FG,
                 font=("Segoe UI", 15, "bold")).pack(side="left", padx=16, pady=10)

        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.refresh())
        e = tk.Entry(top, textvariable=self.search, bg=TILE, fg=FG, insertbackground=FG,
                     relief="flat", font=("Segoe UI", 11), width=22)
        e.pack(side="right", padx=(6, 16), ipady=6)
        tk.Label(top, text="🔍", bg=PANEL, fg=MUTED).pack(side="right")

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=16, pady=(10, 0))
        self._btn(bar, "＋ Add Games", self.add_games, ACCENT).pack(side="left")
        self._btn(bar, "📥 Import from Desktop", self.import_desktop, TILE).pack(side="left", padx=8)
        self._btn(bar, "📁 Add Folder", self.add_folder, TILE).pack(side="left")

        self.min_var = tk.BooleanVar(value=self.db.get("minimize_on_launch", True))
        tk.Checkbutton(bar, text="Minimize launcher when game starts", variable=self.min_var,
                       command=self._save_opts, bg=BG, fg=MUTED, selectcolor=TILE,
                       activebackground=BG, activeforeground=FG, bd=0,
                       font=("Segoe UI", 9)).pack(side="right")

        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        self.canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.grid_frame = tk.Frame(self.canvas, bg=BG)
        self.win = self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.grid_frame.bind("<Configure>",
                             lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(int(-e.delta / 120), "units"))

        self.status = tk.Label(self, text="", bg=PANEL, fg=MUTED, anchor="w",
                               font=("Segoe UI", 9))
        self.status.pack(fill="x", side="bottom", ipady=4, padx=0)

        self.menu = tk.Menu(self, tearoff=0, bg=PANEL, fg=FG, activebackground=ACCENT)

    def _btn(self, parent, text, cmd, color):
        b = tk.Button(parent, text=text, command=cmd, bg=color, fg="white", relief="flat",
                      activebackground=TILE_HOVER, activeforeground="white", bd=0,
                      font=("Segoe UI", 10, "bold"), padx=14, pady=6, cursor="hand2")
        return b

    def _save_opts(self):
        self.db["minimize_on_launch"] = self.min_var.get()
        save_db(self.db)

    # ---------- tiles
    def _get_image(self, g):
        key = g["path"]
        if key in self.imgs:
            return self.imgs[key]
        p = extract_icon(g["path"])
        img = None
        try:
            if p:
                if HAS_PIL:
                    im = Image.open(p).convert("RGBA").resize((ICON, ICON), Image.LANCZOS)
                    img = ImageTk.PhotoImage(im)
                else:
                    img = tk.PhotoImage(file=p).zoom(2)
        except Exception:
            img = None
        self.imgs[key] = img
        return img

    def refresh(self):
        for t in self.tiles:
            t.destroy()
        self.tiles = []
        q = self.search.get().strip().lower()
        games = [g for g in self.db["games"] if q in g["name"].lower()]
        games.sort(key=lambda g: g["name"].lower())
        self.visible = games
        for g in games:
            self.tiles.append(self._make_tile(g))
        self._layout()
        self.status.config(text=f"  {len(self.db['games'])} games  •  double-click to play  •  right-click for options")
        if not self.db["games"]:
            self.status.config(text="  No games yet — click ＋ Add Games or 📥 Import from Desktop")

    def _make_tile(self, g):
        f = tk.Frame(self.grid_frame, bg=TILE, width=TILE_W, height=TILE_H, cursor="hand2")
        f.pack_propagate(False)
        img = self._get_image(g)
        il = tk.Label(f, image=img, bg=TILE) if img else tk.Label(f, text="🎮", bg=TILE, fg=FG, font=("Segoe UI", 30))
        il.pack(pady=(14, 6))
        nl = tk.Label(f, text=g["name"], bg=TILE, fg=FG, font=("Segoe UI", 9),
                      wraplength=TILE_W - 12, justify="center")
        nl.pack(padx=4)
        for w in (f, il, nl):
            w.bind("<Double-Button-1>", lambda e, g=g: self.play(g))
            w.bind("<Button-3>", lambda e, g=g: self.popup(e, g))
            w.bind("<Enter>", lambda e, f=f, il=il, nl=nl: [x.config(bg=TILE_HOVER) for x in (f, il, nl)])
            w.bind("<Leave>", lambda e, f=f, il=il, nl=nl: [x.config(bg=TILE) for x in (f, il, nl)])
        return f

    def _layout(self):
        w = max(self.canvas.winfo_width(), TILE_W + 20)
        cols = max(1, w // (TILE_W + 14))
        self.cols = cols
        for i, t in enumerate(self.tiles):
            t.grid(row=i // cols, column=i % cols, padx=7, pady=7)

    def _on_resize(self, e):
        if e.widget is self:
            cols = max(1, max(self.canvas.winfo_width(), TILE_W + 20) // (TILE_W + 14))
            if cols != self.cols:
                self._layout()

    # ---------- actions
    def play(self, g):
        if not os.path.exists(g["path"]):
            messagebox.showerror("Missing", f"File not found:\n{g['path']}")
            return
        try:
            os.startfile(g["path"])
            self.status.config(text=f"  ▶ Launching {g['name']}…")
            if self.min_var.get():
                self.iconify()
        except Exception as ex:
            messagebox.showerror("Could not launch", str(ex))

    def popup(self, e, g):
        m = self.menu
        m.delete(0, "end")
        m.add_command(label="▶  Play", command=lambda: self.play(g))
        m.add_command(label="✏️  Rename", command=lambda: self.rename(g))
        m.add_command(label="📂  Open file location", command=lambda: subprocess.Popen(
            ["explorer", "/select,", os.path.normpath(g["path"])]))
        m.add_separator()
        m.add_command(label="🗑  Remove from launcher", command=lambda: self.remove(g))
        m.tk_popup(e.x_root, e.y_root)

    def rename(self, g):
        n = simpledialog.askstring("Rename", "New name:", initialvalue=g["name"], parent=self)
        if n and n.strip():
            g["name"] = n.strip()
            save_db(self.db)
            self.refresh()

    def remove(self, g):
        if messagebox.askyesno("Remove", f"Remove '{g['name']}' from the launcher?\n(The game itself is not deleted.)"):
            self.db["games"] = [x for x in self.db["games"] if x is not g]
            if os.path.dirname(g["path"]) == LINK_DIR:
                try:
                    os.remove(g["path"])
                except Exception:
                    pass
            save_db(self.db)
            self.refresh()

    def _add_paths(self, paths):
        have = {x["path"].lower() for x in self.db["games"]}
        n = 0
        for p in paths:
            if p.lower() in have:
                continue
            self.db["games"].append({"name": nice_name(p), "path": p})
            have.add(p.lower())
            n += 1
        save_db(self.db)
        self.refresh()
        return n

    def add_games(self):
        files = filedialog.askopenfilenames(
            title="Select game shortcuts or .exe files",
            filetypes=[("Shortcuts / Games", "*.lnk *.exe *.url *.bat"), ("All files", "*.*")])
        if files:
            n = self._add_paths(list(files))
            self.status.config(text=f"  Added {n} game(s)")

    def add_folder(self):
        d = filedialog.askdirectory(title="Pick a folder containing game shortcuts")
        if d:
            files = [f for ext in ("*.lnk", "*.url", "*.exe") for f in glob.glob(os.path.join(d, ext))]
            n = self._add_paths(files)
            self.status.config(text=f"  Added {n} game(s) from folder")

    def import_desktop(self):
        desks = [os.path.join(os.path.expanduser("~"), "Desktop"),
                 os.path.join(os.environ.get("USERPROFILE", ""), "OneDrive", "Desktop"),
                 os.path.join(os.environ.get("PUBLIC", "C:\\Users\\Public"), "Desktop")]
        files = []
        for d in desks:
            if os.path.isdir(d):
                for ext in ("*.lnk", "*.url"):
                    files += glob.glob(os.path.join(d, ext))
        files = sorted(set(files), key=lambda p: os.path.basename(p).lower())
        if not files:
            messagebox.showinfo("Desktop", "No shortcuts found on the Desktop.")
            return
        DesktopImport(self, files)


class DesktopImport(tk.Toplevel):
    def __init__(self, app, files):
        super().__init__(app)
        self.app, self.files = app, files
        self.title("Import shortcuts from Desktop")
        self.geometry("460x560")
        self.configure(bg=BG)
        self.transient(app)
        self.grab_set()
        tk.Label(self, text="Tick the games to import", bg=BG, fg=FG,
                 font=("Segoe UI", 12, "bold")).pack(pady=(12, 4))
        self.move = tk.BooleanVar(value=True)
        tk.Checkbutton(self, text="Move them off the Desktop (cleans the desktop)",
                       variable=self.move, bg=BG, fg=FG, selectcolor=TILE,
                       activebackground=BG, activeforeground=FG).pack()
        box = tk.Frame(self, bg=PANEL)
        box.pack(fill="both", expand=True, padx=12, pady=8)
        cv = tk.Canvas(box, bg=PANEL, highlightthickness=0)
        sb = ttk.Scrollbar(box, command=cv.yview)
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(cv, bg=PANEL)
        cv.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        self.vars = []
        for p in files:
            v = tk.BooleanVar(value=False)
            tk.Checkbutton(inner, text=nice_name(p), variable=v, bg=PANEL, fg=FG,
                           selectcolor=TILE, activebackground=PANEL, activeforeground=FG,
                           anchor="w", font=("Segoe UI", 10)).pack(fill="x", padx=8)
            self.vars.append(v)
        row = tk.Frame(self, bg=BG)
        row.pack(pady=(0, 12))
        for t, c in (("Select all", lambda: [v.set(True) for v in self.vars]),
                     ("Clear", lambda: [v.set(False) for v in self.vars])):
            tk.Button(row, text=t, command=c, bg=TILE, fg=FG, relief="flat", padx=10).pack(side="left", padx=4)
        tk.Button(row, text="Import", command=self.do_import, bg=ACCENT, fg="white",
                  relief="flat", padx=18, font=("Segoe UI", 10, "bold")).pack(side="left", padx=4)

    def do_import(self):
        chosen = [p for p, v in zip(self.files, self.vars) if v.get()]
        if not chosen:
            return
        final = []
        for p in chosen:
            if self.move.get():
                dest = os.path.join(LINK_DIR, os.path.basename(p))
                try:
                    shutil.move(p, dest)
                    final.append(dest)
                except Exception:
                    final.append(p)   # e.g. public desktop needs admin: keep in place
            else:
                final.append(p)
        n = self.app._add_paths(final)
        self.app.status.config(text=f"  Imported {n} game(s)")
        self.destroy()


if __name__ == "__main__":
    Launcher().mainloop()
