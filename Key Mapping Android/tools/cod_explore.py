"""Call of Duty Mobile training-mode test: auto-load of the profile, every mapped key, WASD and real mouse aiming.

Everything goes through the real path (Qt key/mouse events and Windows SendInput -> Raw Input -> app -> phone).
Stops at once if COD is not the foreground app or the HUD changes (menu / pause). Keep your hands off the mouse.

Usage:  .venv\\Scripts\\python.exe tools\\cod_explore.py <sheet.png>
"""
from __future__ import annotations

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
from app.ui import theme  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

COD_PACKAGE = "com.activision.callofduty.shooter"
PROFILE_NAME = "Call of Duty Mobile"
K = Qt.Key
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


def gray(img: QImage) -> np.ndarray:
    g = img.convertToFormat(QImage.Format.Format_Grayscale8)
    return np.frombuffer(g.constBits(), np.uint8).reshape(g.height(), g.bytesPerLine())[:, : g.width()].astype(np.int16)


def knob_signature(img: QImage, cx: float, cy: float) -> float:
    a = gray(img)
    h, w = a.shape
    yy, xx = np.ogrid[:h, :w]
    mask = (xx - cx * w) ** 2 + (yy - cy * h) ** 2 <= (0.025 * h) ** 2
    return float(a[mask].mean())


def scene_diff(a: QImage, b: QImage) -> float:
    x, y = gray(a), gray(b)
    h, w = x.shape
    box = (slice(int(h * 0.15), int(h * 0.55)), slice(int(w * 0.30), int(w * 0.70)))
    return float(np.abs(x[box] - y[box]).mean())


def main() -> int:
    sheet_path = sys.argv[1]
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

    end = time.time() + 15
    while not any(d.usable for d in window.devices) and time.time() < end:
        pump(0.2)
    serial = next(d.serial for d in window.devices if d.usable)
    print("profile before connecting:", window.profile.name if window.profile else None, flush=True)
    window._toggle_connection()
    end = time.time() + 15
    while window.video.frame_size() == (0, 0) and time.time() < end:
        pump(0.1)
    size = window.video.frame_size()

    # ---- auto-load -------------------------------------------------------------------------
    end = time.time() + 8
    while (not window.profile or window.profile.name != PROFILE_NAME) and time.time() < end:
        pump(0.2)
    loaded = window.profile.name if window.profile else None
    print(f"phone app: {window.current_package} | profile now: {loaded} "
          f"-> AUTO-LOAD {'WORKS' if loaded == PROFILE_NAME else 'FAILED'}", flush=True)
    if loaded != PROFILE_NAME or window.current_package != COD_PACKAGE or size[0] <= size[1]:
        print("COD is not in the foreground in landscape (or the profile did not load) - sending no input.")
        window.close()
        return 3
    if not window.isActiveWindow():
        print("SKIP: the app window has no focus (Raw Input needs it). Click the window and rerun.")
        window.close()
        return 2

    profile, engine, video = window.profile, window.engine, window.video
    stick = profile.sticks[0]

    def frame() -> QImage:
        return video.grabFramebuffer().copy(video.target_rect().toRect())

    pump(0.5)
    baseline_sig = knob_signature(frame(), stick.x, stick.y)
    window._set_mapping(True)
    print(f"mapping on: {engine.mapping_active} | mouse captured: {engine.look_captured} | "
          f"knob signature {baseline_sig:.0f}", flush=True)
    if not engine.mapping_active:
        window.close()
        return 2

    shots: list[tuple[str, QImage]] = []
    diffs: dict[str, float] = {}
    abort = ""

    def snap(caption: str) -> QImage:
        img = frame()
        shots.append((caption, img))
        return img

    def in_game() -> bool:
        nonlocal abort
        pump(0.4)
        sig = knob_signature(frame(), stick.x, stick.y)
        fg = window.adb.run("shell", "dumpsys activity activities | grep -m1 topResumedActivity", serial=serial,
                            check=False).stdout
        if COD_PACKAGE not in fg:
            abort = "COD is no longer the foreground app"
        elif abs(sig - baseline_sig) > 90:
            pump(1.0)                                    # the sprint-lock icon may be showing: look again
            sig2 = knob_signature(frame(), stick.x, stick.y)
            if abs(sig2 - baseline_sig) > 90:
                abort = f"the HUD changed (knob check {sig:.0f}/{sig2:.0f} vs {baseline_sig:.0f})"
        return not abort

    def key_hold(key, seconds, snap_at, caption):
        QTest.keyPress(window, key)
        pump(snap_at)
        snap(caption)
        pump(max(0, seconds - snap_at))
        QTest.keyRelease(window, key)

    def key_tap(key, wait, caption):
        QTest.keyPress(window, key)
        pump(0.07)
        QTest.keyRelease(window, key)
        pump(wait)
        if caption:
            snap(caption)

    def mouse_hold(button, seconds, snap_at, caption):
        QTest.mousePress(video, button)
        pump(snap_at)
        snap(caption)
        pump(max(0, seconds - snap_at))
        QTest.mouseRelease(video, button)

    def sweep(dx, dy, steps, ms=10):
        for _ in range(steps):
            send_mouse(dx, dy)
            pump(ms / 1000)

    def measure(label, action):
        if abort or not in_game():
            return
        start = snap(f"{label} - before")
        action()
        pump(0.35)
        diffs[label] = scene_diff(start, snap(f"{label} - after"))

    def snap_scope():
        QTest.mouseClick(video, Qt.MouseButton.RightButton)
        pump(0.8)
        snap("RMB: scope")
        QTest.mouseClick(video, Qt.MouseButton.RightButton)
        pump(0.8)
        snap("RMB again: scope off")

    plan = [
        lambda: snap("0 baseline"),
        lambda: mouse_hold(Qt.MouseButton.LeftButton, 1.0, 0.6, "1 LMB held: fire"),
        lambda: key_hold(K.Key_F, 0.9, 0.5, "2 F held: left fire button"),
        lambda: (key_tap(K.Key_R, 0.5, "3 R: reload +0.5 s"), pump(2.5), snap("4 reload done +3 s")),
        snap_scope,
        lambda: (key_tap(K.Key_C, 1.0, "7 C: crouch"), key_tap(K.Key_C, 1.0, "8 C again: stand")),
        lambda: (key_tap(K.Key_X, 1.0, "9 X: stance button"), key_tap(K.Key_X, 1.0, "10 X again")),
        lambda: (key_tap(K.Key_Shift, 0.8, "11 Shift: sprint lock on"), key_tap(K.Key_Shift, 0.8, "12 Shift again: off")),
        lambda: key_tap(K.Key_2, 1.2, "13 key 2: weapon 2"),
        lambda: key_tap(K.Key_1, 1.2, "14 key 1: weapon 1"),
    ]
    for step in plan:
        if abort or not in_game():
            break
        step()

    def move(label, keys, hold=1.3):
        def run():
            for key in keys:
                QTest.keyPress(window, key)
            pump(hold)
            for key in reversed(keys):
                QTest.keyRelease(window, key)
        measure(label, run)

    if not abort:
        pump(0.5)
        measure("idle (no input, 1 s)", lambda: pump(1.0))
        move("W forward", [K.Key_W])
        move("S back", [K.Key_S], 1.0)
        move("A left", [K.Key_A], 1.0)
        move("D right", [K.Key_D], 1.0)
        move("W+D diagonal", [K.Key_W, K.Key_D])
        measure("mouse right 500 counts", lambda: sweep(10, 0, 50))
        measure("mouse left 500 counts", lambda: sweep(-10, 0, 50))
        measure("mouse up 300 counts", lambda: sweep(0, -6, 50))
        measure("mouse down 300 counts", lambda: sweep(0, 6, 50))
        measure("slow turn right 300", lambda: sweep(3, 0, 100, 12))
        measure("fast flick right 900", lambda: sweep(30, 0, 30, 4))

    max_fingers = 0
    if not abort and in_game():
        print("combo: run + turn + fire together", flush=True)
        QTest.keyPress(window, K.Key_W)
        QTest.mousePress(video, Qt.MouseButton.LeftButton)
        for _ in range(60):
            send_mouse(8, 0)
            max_fingers = max(max_fingers, engine.injector.active_count)
            pump(0.01)
        QTest.mouseRelease(video, Qt.MouseButton.LeftButton)
        QTest.keyRelease(window, K.Key_W)
        snap("combo: run + aim + fire")
        pump(0.4)

    QTest.keyClick(window, K.Key_Escape)
    pump(0.3)
    print(f"\nstopped early: {abort or 'no'} | most fingers at once: {max_fingers} | "
          f"touches left down: {engine.injector.active_count} | mouse released: {not engine.look_captured}")
    print("scene change (mean pixel difference; higher = more movement):")
    for label, value in diffs.items():
        print(f"  {label:26s} {value:6.2f}")

    window.close()
    pump(0.3)

    cols, cw = 4, 480
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
    sheet.save(sheet_path)
    print("saved", sheet_path, f"({len(shots)} frames)")
    return 1 if abort else 0


if __name__ == "__main__":
    raise SystemExit(main())
