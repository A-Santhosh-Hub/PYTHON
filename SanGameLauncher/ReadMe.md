# 🎮 San Game Launcher

A tiny, lightweight **game library for Windows**. Keep all your game shortcuts inside **one app** instead of covering your whole desktop with icons. Add your games once, then double-click a tile to play.

Built with **Python + Tkinter**, and can be packaged into a single `.exe`.

---

## ✨ Features

- 🗂️ **One window for all your games**: icons and names shown as a clean tile grid
- ▶️ **Double-click to play**: launches the game instantly
- ➕ **Add Games**: pick `.lnk`, `.exe`, `.url` or `.bat` files (multi-select supported)
- 📥 **Import from Desktop**: tick your game shortcuts and **move them off the desktop** in one click
- 📁 **Add Folder**: bulk-add every shortcut in a folder
- 🖱️ **Right-click menu**: Play, Rename, Open file location, Remove
- 🔍 **Search**: filter your library by name
- 🖼️ **Real icons**: extracted automatically from each shortcut or game and cached
- 💾 **Auto-save**: your library is remembered between sessions
- 🌙 **Dark theme** with a responsive grid that adapts to the window size
- 🔽 **Minimize on launch** (optional) to keep your screen free while gaming

---

## 📸 Screenshots

> Add your screenshots here, for example:
>
> `![Main window](screenshots/main.png)`

---

## 🚀 Getting Started

### Requirements

- Windows 10 / 11
- [Python 3.8+](https://www.python.org/downloads/) (tick **"Add Python to PATH"** during install)

### Option 1: Run from source

```bat
pip install pillow
python SanGameLauncher.py
```

Or simply double-click **`run.bat`**.

### Option 2: Build a standalone `.exe`

Double-click **`build_exe.bat`**, or run:

```bat
pip install pyinstaller pillow
pyinstaller --noconsole --onefile --name SanGameLauncher SanGameLauncher.py
```

Your app will be at:

```
dist\SanGameLauncher.exe
```

You can pin it to the taskbar or Start menu.

---

## 🕹️ How to Use

1. Open **San Game Launcher**.
2. Click **＋ Add Games** and select your game shortcuts or `.exe` files, **or** click **📥 Import from Desktop**, tick your games and press **Import**.
   - Leave *"Move them off the Desktop"* ticked to clean your desktop automatically.
3. **Double-click** any tile to launch the game.
4. **Right-click** a tile to rename it, open its location or remove it from the launcher.

> Removing a game only removes it from the launcher. The game itself is **never deleted**.

---

## 📁 Where Is My Data Stored?

Everything is saved in your user profile:

```
%APPDATA%\SanGameLauncher\
├── games.json     # your game library and settings
├── icons\         # cached game icons
└── shortcuts\     # shortcuts moved from the desktop
```

To reset the launcher, close it and delete that folder.

---

## 🗂️ Project Structure

```
SanGameLauncher/
├── SanGameLauncher.py   # main application
├── build_exe.bat        # one-click .exe builder (PyInstaller)
├── run.bat              # quick run script
└── README.md
```

---

## ❓ Troubleshooting

| Problem | Fix |
|---|---|
| Icons look blurry or are missing | Run `pip install pillow`, then restart the app |
| A desktop shortcut wasn't moved | Shortcuts on the *Public* desktop need admin rights. Run the launcher as administrator, or add it without moving |
| A game says "File not found" | The game was moved or uninstalled. Remove it and add it again |
| Antivirus flags the `.exe` | Common false positive with PyInstaller builds. Build it yourself from source |

---

## 🛣️ Roadmap

- [ ] Drag & drop to add games
- [ ] Categories and favorites
- [ ] Play-time tracking
- [ ] Custom cover art per game
- [ ] Light / dark theme toggle

---

## 🤝 Contributing

Pull requests and ideas are welcome. Fork the repo, create a branch, and open a PR.

## 📄 License

Released under the [MIT License](LICENSE). Add a `LICENSE` file to your repo to enable this.

---

## 👨‍💻 Author

**Santhosh A** (SanStudio)
Portfolio: [a-santhosh-hub.github.io/in](https://a-santhosh-hub.github.io/in/)

⭐ If you like this project, give it a star on GitHub!
