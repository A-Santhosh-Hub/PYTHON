"""Live in-game test of real mouse aiming (Battle Prime, landscape).

Moves the real Windows mouse (SendInput -> Raw Input -> app -> phone) and measures how far the game camera
turns. Uses only the camera zone, the WASD stick and the fire button. Refuses to run unless the game is in the
foreground with the match HUD showing (joystick knob at rest), and stops at once if that stops being true.

Usage:  .venv\\Scripts\\python.exe tools\\game_looktest.py <sheet.png> --in-match
Do not touch the mouse while it runs.
"""
from __future__ import annotations

import argparse
import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.logging_setup import setup_logging  # noqa: E402
from app.mapping.profile import Binding, Look, Profile, Stick  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

PROFILE = "zz-aim-test"
GAME_PACKAGE = "com.blitzteam.battleprime"
STICK = Stick(0.1265, 0.814, radius=0.10, ramp_ms=50)
LOOK = Look(0.42, 0.22, 0.74, 0.56, sens_x=1.0, sens_y=1.0)          # empty view area, clear of every button
FIRE = Binding("LMB", 0.856, 0.700, "hold", "Fire")
user32 = ctypes.windll.user32
user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def send_mouse(dx: int, dy: int) -> None:
    user32.SendInput(1, ctypes.byref(INPUT(0, INPUT._U(MOUSEINPUT(dx, dy, 0, 0x0001, 0, 0)))), ctypes.sizeof(INPUT))


def knob_fraction(img: QImage) -> float:
    gray = img.convertToFormat(QImage.Format.Format_Grayscale8)
    buf = np.frombuffer(gray.constBits(), np.uint8).reshape(gray.height(), gray.bytesPerLine())[:, : gray.width()]
    h, w = buf.shape
    yy, xx = np.ogrid[:h, :w]
    mask = (xx - STICK.x * w) ** 2 + (yy - STICK.y * h) ** 2 <= (0.028 * h) ** 2
    return float((buf[mask] > 215).mean())


def scene_diff(a: QImage, b: QImage) -> float:
    def arr(img):
        g = img.convertToFormat(QImage.Format.Format_Grayscale8)
        return np.frombuffer(g.constBits(), np.uint8).reshape(g.height(), g.bytesPerLine())[:, : g.width()].astype(np.int16)
    x, y = arr(a), arr(b)
    h, w = x.shape
    box = (slice(int(h * 0.20), int(h * 0.75)), slice(int(w * 0.30), int(w * 0.75)))
    return float(np.abs(x[box] - y[box]).mean())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("--in-match", action="store_true")
    args = ap.parse_args()
    if not args.in_match:
        print("Refusing to run: pass --in-match once the game is in a match (not on a menu).")
        return 2

    setup_logging()
    app = QApplication([])
    app.setStyleSheet(theme.STYLE_SHEET)
    window = MainWindow()
    window.show()
    window.raise_()
    window.activateWindow()

    def pump(seconds: float) -> None:
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            app.processEvents()
            time.sleep(0.003)

    def cleanup(code: int) -> int:
        window._set_mapping(False)
        window.store.delete(PROFILE)
        window._refresh_profile_list(previous_profile)
        window.close()
        return code

    previous_profile = str(window.settings.value("profile", "Default"))
    end = time.time() + 15
    while not any(d.usable for d in window.devices) and time.time() < end:
        pump(0.2)
    serial = next(d.serial for d in window.devices if d.usable)
    window._toggle_connection()
    end = time.time() + 15
    while window.video.frame_size() == (0, 0) and time.time() < end:
        pump(0.1)
    size = window.video.frame_size()
    print("video size:", size, flush=True)
    pump(1.0)

    video, engine = window.video, window.engine

    def frame() -> QImage:
        return video.grabFramebuffer().copy(video.target_rect().toRect())

    def foreground_is_game() -> bool:
        out = window.adb.run("shell", "dumpsys", "activity", "activities", serial=serial, check=False).stdout
        return any(GAME_PACKAGE in l for l in out.splitlines() if "topResumedActivity" in l)

    knob = knob_fraction(frame()) if size[0] > size[1] else 0.0
    print(f"match check (joystick knob at rest): {knob:.2f}", flush=True)
    if size[0] <= size[1] or knob < 0.8 or not foreground_is_game():
        print("The match HUD is not on screen (menu / other app / not landscape) - sending no input. Aborting.")
        return cleanup(3)
    if not window.isActiveWindow():
        print("SKIP: the app window has no focus, so Raw Input would not arrive. Click it and rerun.")
        return cleanup(2)

    profile = Profile(PROFILE, "landscape", [FIRE])
    profile.set_stick(STICK)
    profile.looks.append(LOOK)
    window.store.save(profile)
    window._refresh_profile_list(PROFILE)
    window._set_mapping(True)
    print("mapping:", engine.mapping_active, "| mouse captured:", engine.look_captured, flush=True)
    if not engine.look_captured:
        return cleanup(2)

    shots: list[tuple[str, QImage]] = []
    results: dict[str, float] = {}
    max_fingers = 0
    abort = ""

    def snap(caption: str) -> QImage:
        img = frame()
        shots.append((caption, img))
        return img

    def sweep(dx: int, dy: int, steps: int, step_ms: float) -> None:
        nonlocal max_fingers
        for _ in range(steps):
            send_mouse(dx, dy)
            max_fingers = max(max_fingers, engine.injector.active_count)
            pump(step_ms / 1000)

    def check_still_in_match() -> bool:
        nonlocal abort
        pump(0.35)                                       # let the camera finger lift so the knob is at rest
        if knob_fraction(frame()) < 0.5:
            pump(0.5)
            if knob_fraction(frame()) < 0.5 or not foreground_is_game():
                abort = "the match HUD is no longer on screen"
                return False
        return True

    def trial(label: str, dx: int, dy: int, steps: int, step_ms: float = 10) -> None:
        if abort or not check_still_in_match():
            return
        start = snap(f"{label} - before")
        sweep(dx, dy, steps, step_ms)
        pump(0.35)
        results[label] = scene_diff(start, snap(f"{label} - after"))

    idle_a = snap("idle")
    pump(1.0)
    results["idle (no mouse movement)"] = scene_diff(idle_a, snap("idle +1 s"))
    trial("mouse right 500 counts", 10, 0, 50)
    trial("mouse left 500 counts", -10, 0, 50)
    trial("mouse up 300 counts", 0, -6, 50)
    trial("mouse down 300 counts", 0, 6, 50)
    trial("slow turn right 300 counts", 3, 0, 100, 12)
    trial("fast flick right 900 counts", 30, 0, 30, 4)

    if not abort and check_still_in_match():
        print("combo: run forward + sweep camera + fire, all at once", flush=True)
        QTest.keyPress(window, Qt.Key.Key_W)
        QTest.mousePress(video, Qt.MouseButton.LeftButton)
        sweep(8, 0, 60, 10)
        QTest.mouseRelease(video, Qt.MouseButton.LeftButton)
        QTest.keyRelease(window, Qt.Key.Key_W)
        snap("combo: run + aim + fire")
        pump(0.4)

    QTest.keyClick(window, Qt.Key.Key_Escape)
    pump(0.3)
    print(f"\nplayed through; stopped early: {abort or 'no'}")
    print(f"most fingers at once: {max_fingers} | touches left down: {engine.injector.active_count} | "
          f"mouse released: {not engine.look_captured}")
    print("camera change per trial (mean pixel difference in the middle of the view):")
    for label, value in results.items():
        print(f"  {label:34s} {value:6.2f}")
    code = cleanup(1 if abort else 0)

    cols, cw = 4, 500
    ch = round(cw * size[1] / size[0])
    rows = (len(shots) + cols - 1) // cols
    sheet = QImage(cols * cw, rows * ch, QImage.Format.Format_RGB32)
    sheet.fill(QColor("black"))
    painter = QPainter(sheet)
    font = QFont("Segoe UI", 9)
    font.setBold(True)
    painter.setFont(font)
    for i, (caption, img) in enumerate(shots):
        x, y = (i % cols) * cw, (i // cols) * ch
        painter.drawImage(QRect(x, y, cw, ch), img)
        painter.fillRect(QRect(x, y, cw, 20), QColor(0, 0, 0, 190))
        painter.setPen(QColor("#ffe45c"))
        painter.drawText(QRect(x + 6, y, cw - 6, 20), Qt.AlignmentFlag.AlignVCenter, caption)
    painter.end()
    sheet.save(args.sheet)
    print("saved", args.sheet)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
