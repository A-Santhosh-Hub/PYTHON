"""In-game test of mouse-wheel weapon switching (Call of Duty Mobile, landscape).

Scrolls the REAL mouse wheel (Windows SendInput -> Qt -> app -> phone). Wheel down taps weapon slot 2, wheel up
taps weapon slot 1, and the game's own highlight on the slots proves it worked. Only the two weapon slots are
touched - no movement, no fire. Weapon switching is the one thing this changes in your game.

Safety: refuses unless COD is the foreground app in landscape, and (unless --allow-active) the screen is calm,
i.e. you are not mid-fight. Pass --ok-to-switch-weapon to confirm.

Usage:  .venv\\Scripts\\python.exe tools\\game_wheeltest.py <sheet.png> --ok-to-switch-weapon
        [--slot1 0.45,0.864] [--slot2 0.54,0.864] [--allow-active]
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
from PySide6.QtCore import QRect, QPoint, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.logging_setup import setup_logging  # noqa: E402
from app.mapping.profile import Binding, Profile  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

COD_PACKAGE = "com.activision.callofduty.shooter"
PROFILE = "zz-wheel-test"
WHEEL_DELTA = 120
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


def real_wheel(notches: int) -> None:
    """notches > 0 scrolls up (away from you), < 0 down - exactly like turning the physical wheel."""
    data = ctypes.c_ulong(notches * WHEEL_DELTA & 0xFFFFFFFF).value
    event = INPUT(0, INPUT._U(MOUSEINPUT(0, 0, data, 0x0800, 0, 0)))          # MOUSEEVENTF_WHEEL
    user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))


def gray(img: QImage) -> np.ndarray:
    g = img.convertToFormat(QImage.Format.Format_Grayscale8)
    return np.frombuffer(g.constBits(), np.uint8).reshape(g.height(), g.bytesPerLine())[:, : g.width()].astype(np.int16)


def gold_share(img: QImage, cx: float, cy: float, half_w: float = 0.045, half_h: float = 0.055) -> float:
    """How 'yellow' the outline around a weapon slot is. The game outlines the active slot in yellow; video
    compression shifts the exact colour, so this scores yellowness ((R+G)/2 - B) of the most yellow pixels and the
    two slots are compared with each other instead of against a fixed threshold."""
    rgb = img.convertToFormat(QImage.Format.Format_RGB888)
    arr = np.frombuffer(rgb.constBits(), np.uint8).reshape(rgb.height(), rgb.bytesPerLine())[:, : rgb.width() * 3]
    arr = arr.reshape(rgb.height(), rgb.width(), 3).astype(np.float32)
    h, w = arr.shape[:2]
    box = arr[int((cy - half_h) * h):int((cy + half_h) * h), int((cx - half_w) * w):int((cx + half_w) * w)]
    yellow = (box[..., 0] + box[..., 1]) / 2 - box[..., 2]
    top = np.sort(yellow.ravel())[-max(10, yellow.size // 33):]            # the most yellow ~3% of pixels
    return float(top.mean())


def pair(text: str) -> tuple[float, float]:
    x, y = text.split(",")
    return float(x), float(y)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("--ok-to-switch-weapon", action="store_true")
    ap.add_argument("--allow-active", action="store_true")
    ap.add_argument("--slot1", default="0.45,0.864")
    ap.add_argument("--slot2", default="0.54,0.864")
    args = ap.parse_args()
    if not args.ok_to_switch_weapon:
        print("Refusing to run: this switches your weapon in the game. Pass --ok-to-switch-weapon to confirm.")
        return 2
    slot1, slot2 = pair(args.slot1), pair(args.slot2)

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

    def finish(code: int, message: str = "") -> int:
        if message:
            print(message)
        window._set_mapping(False)
        window.store.delete(PROFILE)
        window._refresh_profile_list(previous_profile)
        window.close()
        return code

    previous_profile = str(window.settings.value("profile", "Default"))
    end = time.time() + 15
    while not any(d.usable for d in window.devices) and time.time() < end:
        pump(0.2)
    window._toggle_connection()
    end = time.time() + 15
    while window.video.frame_size() == (0, 0) and time.time() < end:
        pump(0.1)
    end = time.time() + 8
    while window.current_package != COD_PACKAGE and time.time() < end:
        pump(0.2)
    size = window.video.frame_size()
    if window.current_package != COD_PACKAGE or size[0] <= size[1]:
        return finish(3, "COD is not in the foreground in landscape - sending no input.")
    if not window.isActiveWindow():
        return finish(2, "SKIP: the app window has no focus, so the wheel would go elsewhere. Click it and rerun.")

    video, engine = window.video, window.engine

    def frame() -> QImage:
        return video.grabFramebuffer().copy(video.target_rect().toRect())

    pump(0.5)
    a = frame()
    pump(1.2)
    g1, g2 = gray(a), gray(frame())
    h, w = g1.shape
    box = (slice(int(h * 0.15), int(h * 0.75)), slice(int(w * 0.30), int(w * 0.70)))
    activity = float(np.abs(g1[box] - g2[box]).mean())
    print(f"scene activity {activity:.1f} (idle ~1, running 30+)", flush=True)
    if activity > 12 and not args.allow_active:
        return finish(4, "The screen is changing a lot - you look mid-fight. Not sending input. "
                         "Stand still / go to training mode, or pass --allow-active.")

    profile = Profile(PROFILE, "landscape", [
        Binding("WheelDown", slot2[0], slot2[1], "tap", "Wheel down: slot 2"),
        Binding("WheelUp", slot1[0], slot1[1], "tap", "Wheel up: slot 1"),
    ])
    window.store.save(profile)
    window._refresh_profile_list(PROFILE)
    window._set_mapping(True)
    if not engine.mapping_active:
        return finish(2, "Mapping did not turn on: " + window.controls.hint.text())

    r = video.target_rect()
    centre_global = video.mapToGlobal(QPoint(int(r.center().x()), int(r.center().y())))
    ratio = video.devicePixelRatioF()
    user32.SetCursorPos(round(centre_global.x() * ratio), round(centre_global.y() * ratio))   # wheel goes to what is under the cursor
    pump(0.3)

    shots: list[tuple[str, QImage]] = []
    rows: list[tuple[str, float, float]] = []

    def observe(label: str) -> None:
        pump(0.9)
        img = frame()
        shots.append((label, img))
        rows.append((label, gold_share(img, *slot1), gold_share(img, *slot2)))

    observe("start")
    start_active = 1 if rows[0][1] >= rows[0][2] else 2
    steps = [("wheel DOWN x1", -1, 2), ("wheel UP x1", +1, 1), ("wheel DOWN x1 again", -1, 2), ("wheel UP x1 again", +1, 1)]
    for label, notches, _expected in steps:
        real_wheel(notches)
        observe(label)

    window._set_mapping(False)
    print(f"\nslot highlight (yellowness of the outline around each weapon slot; higher = active):")
    print(f"  {'step':24s} {'slot 1':>8s} {'slot 2':>8s}  active")
    for label, s1, s2 in rows:
        print(f"  {label:24s} {s1:8.1f} {s2:8.1f}  slot {1 if s1 >= s2 else 2}")
    expected = [start_active] + [e for _, _, e in steps]
    actual = [1 if s1 >= s2 else 2 for _, s1, s2 in rows]
    margins = [abs(s1 - s2) for _, s1, s2 in rows]
    ok = actual[1:] == expected[1:]
    print("\nWHEEL SWITCHING:", "WORKS (the active slot followed the wheel every time)" if ok
          else f"NOT CONFIRMED (expected {expected[1:]}, saw {actual[1:]}) - check the slot positions with --slot1/--slot2")
    print(f"touches left down: {engine.injector.active_count}")
    code = finish(0 if ok else 1)

    cols, cw = 3, 640
    ch = round(cw * size[1] / size[0])
    sheet = QImage(cols * cw, ((len(shots) + cols - 1) // cols) * ch, QImage.Format.Format_RGB32)
    sheet.fill(QColor("black"))
    painter = QPainter(sheet)
    font = QFont("Segoe UI", 10)
    font.setBold(True)
    painter.setFont(font)
    for i, (caption, img) in enumerate(shots):
        x, y = (i % cols) * cw, (i // cols) * ch
        painter.drawImage(QRect(x, y, cw, ch), img)
        painter.fillRect(QRect(x, y, cw, 22), QColor(0, 0, 0, 190))
        painter.setPen(QColor("#ffe45c"))
        painter.drawText(QRect(x + 6, y, cw - 6, 22), Qt.AlignmentFlag.AlignVCenter, caption)
    painter.end()
    sheet.save(args.sheet)
    print("saved", args.sheet)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

