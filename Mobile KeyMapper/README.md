# Mobile Key One

Play your **real Android phone** on a big PC screen with your **keyboard and mouse**, over a USB cable.

Mobile Key One is **not an emulator**. The game keeps running on your phone. The app mirrors the phone's screen to your
PC (using the open-source [scrcpy](https://github.com/Genymobile/scrcpy) server) and turns your keys and mouse into
touches on the phone, like the key-mapping tools of Android emulators (BlueStacks, GameLoop, TC Games), but for the phone
you already own.

> **Status:** works, actively developed, built and tested on Windows 11 with an Android 16 phone over USB.
> Windows only (it uses Windows Raw Input and OpenGL).

## What it does

- **Phone picture on the PC**: low delay, up to the phone's full resolution and 120 fps, picture quality presets from
  *Light* to *Max*, adjustable brightness / contrast / colour / sharpness, fullscreen.
- **Keyboard and mouse to touches**: tap, hold, toggle, auto-repeat, double tap, swipe, drag, pinch zoom, multi-tap
  sequences, key combinations such as `Shift+W`, and one key touching several spots at once.
- **WASD movement stick** with sprint, walk and auto-run keys.
- **Mouse aiming**: real mouse movement turns the camera (Windows Raw Input, mouse confinement, endless turning),
  separate sensitivity while scoped in, hold a key or press `~` / `F8` to free the mouse.
- **Drag-and-drop layout editor**: drop markers on the game's buttons, double-click to change a key, right-click for
  options, Save / Undo / Reset restore points, ready-made templates (standard shooter, battle royale).
- **Per-game profiles** that load by themselves when that game opens on the phone.
- **Smart mode (optional)**: the app learns what a game's controls look like and tells the game from its menus. In a
  match your mouse aims; in a menu the keys pause and the mouse works like a finger.
- **Key markers can fade out** (`F2` / `F3` / `F4`) for a clean view while playing.

## Requirements

- Windows 10 or 11
- Python 3.11 or newer
- An Android phone with **USB debugging** turned on (Settings > Developer options), and a USB cable that carries data
- A GPU / driver with OpenGL 3.0 or newer (any normal Windows PC)

## Install and run

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
run.bat
```

`run.bat` starts `python -m app`. The `vendor` folder already contains `adb` and the scrcpy server (see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)); nothing else needs to be installed on the phone.

## Quick start

1. Plug in the phone, allow USB debugging when it asks, press **Connect**.
2. Open your game on the phone. Press **+ New** to make controls for it (or pick a template), then **Edit controls**
   and drag each marker onto the matching button of the game. The mouse-look area belongs on an empty part of the view.
3. Press **Start playing** (`F9`). `Esc` stops.

| Key | Does |
|---|---|
| `F9` | Key mapping on / off |
| `F8` or `~` | Lock / free the mouse |
| hold `Alt` | Free the mouse while held |
| `F11` | Fullscreen |
| `F2` / `F3` / `F4` | Key markers more transparent / more visible / hide |
| `Esc` | Stop playing and release everything |

All of these can be changed in Settings > Shortcuts. Profiles are plain JSON files in
`%LOCALAPPDATA%\MobileKeyOne\profiles`.

## Tests

```bat
.venv\Scripts\python.exe -m pytest tests -q
```

The GUI tests in `tools/` run **without a phone**: `tools/fake_phone.py` attaches a simulated one, and every touch is
intercepted.

```bat
.venv\Scripts\python.exe tools\smart_ui_test.py      smart mode, hold-to-free key, duplicate keys
.venv\Scripts\python.exe tools\picture_ui_test.py    quality presets, picture look, colour check
.venv\Scripts\python.exe tools\look_gl_test.py       the GPU picture controls, measured on real pixels
.venv\Scripts\python.exe tools\editor_test.py        drag-and-drop editor
.venv\Scripts\python.exe tools\profile_ui_test.py    profiles, Save / Undo / Reset, hotkeys
.venv\Scripts\python.exe tools\intercept_test.py     whole pipeline (keys, stick, aiming, wheel, auto-load)
```

Other scripts in `tools/` talk to a real phone (for example `stream_test.py`, `control_test.py`, `game_*`, `pubg_*`,
`cod_*`). Read a script before running it: some press keys on the phone or touch a running game.

## Responsible use

- This is an **input tool**, not a cheat. It does not read or change game memory, does not modify game files, and does
  not try to hide from anti-cheat. Features that exist only to avoid detection (input randomisation, recoil
  compensation macros) are deliberately **not** included.
- Many online games forbid external input tools, and a ban is possible. The *repeat tap* mode is an auto-clicker and may
  count as cheating online. Use the app where it is allowed, and test on a spare account first. You use it at your own
  risk. More in [docs/RESEARCH.md](docs/RESEARCH.md).

## Project layout

```
app/device    adb wrapper, hot-plug tracker, foreground-app watcher
app/stream    scrcpy protocol, session, worker thread
app/video     decoder, YUV frame, OpenGL widget, picture look, colour check
app/input     touch injector, input engine, Qt event router, Raw Input
app/mapping   profiles (JSON), templates, layout-editor logic
app/ui        main window, sidebar, settings, overlay, theme
app/scene.py  smart mode: game screen vs menu
vendor/       adb and the scrcpy server v5.0.1 (client and server versions must match exactly)
tests/        unit tests
tools/        GUI tests, helper and device scripts
docs/         research notes with sources
```

## Credits and licence

Built on [scrcpy](https://github.com/Genymobile/scrcpy) (Apache-2.0) by Genymobile, Android's `adb`, Qt for Python
(PySide6), PyAV / FFmpeg and NumPy. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Licence: *to be chosen by the author* (add a `LICENSE` file before accepting contributions).
