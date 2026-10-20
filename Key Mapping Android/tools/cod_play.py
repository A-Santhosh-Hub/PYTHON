"""Plays Call of Duty Mobile training mode for N seconds through the key-mapping layer (profile auto-loaded).

Movement, shooting, reloading, stance, weapon swaps and mouse turning all go through the real path
(Qt key events / Windows SendInput -> Raw Input -> app -> phone). There is no auto-aim: turning is random.
Stops at once if COD leaves the foreground or the HUD changes. Keep your hands off the mouse.

Usage:  .venv\\Scripts\\python.exe tools\\cod_play.py <sheet.png> [--seconds 120]
"""
from __future__ import annotations

import argparse
import ctypes
import random
import sys
import time
from collections import Counter
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


def knob_signature(img: QImage, cx: float, cy: float) -> float:
    g = img.convertToFormat(QImage.Format.Format_Grayscale8)
    a = np.frombuffer(g.constBits(), np.uint8).reshape(g.height(), g.bytesPerLine())[:, : g.width()]
    h, w = a.shape
    yy, xx = np.ogrid[:h, :w]
    return float(a[(xx - cx * w) ** 2 + (yy - cy * h) ** 2 <= (0.025 * h) ** 2].mean())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("--seconds", type=float, default=120)
    args = ap.parse_args()

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
    window._toggle_connection()
    end = time.time() + 15
    while window.video.frame_size() == (0, 0) and time.time() < end:
        pump(0.1)
    end = time.time() + 8
    while (not window.profile or window.profile.name != PROFILE_NAME) and time.time() < end:
        pump(0.2)
    size = window.video.frame_size()
    if (window.current_package != COD_PACKAGE or not window.profile or window.profile.name != PROFILE_NAME
            or size[0] <= size[1]):
        print("COD is not in the foreground in landscape (or its profile did not load) - sending no input.")
        window.close()
        return 3
    if not window.isActiveWindow():
        print("SKIP: the app window has no focus (Raw Input needs it). Click the window and rerun.")
        window.close()
        return 2

    video, engine = window.video, window.engine
    stick = window.profile.sticks[0]
    print(f"auto-loaded profile: {window.profile.name} ({len(window.profile.bindings)} bindings)", flush=True)

    def frame() -> QImage:
        return video.grabFramebuffer().copy(video.target_rect().toRect())

    pump(0.5)
    baseline = knob_signature(frame(), stick.x, stick.y)
    window._set_mapping(True)
    print(f"mapping on: {engine.mapping_active} | mouse captured: {engine.look_captured}", flush=True)
    if not engine.mapping_active:
        window.close()
        return 2

    rng = random.Random(20261019)
    counts: Counter = Counter()
    shots: list[tuple[str, QImage]] = []
    state = {"last_shot": -99.0, "max_fingers": 0, "abort": "", "pitch": 0}
    t_start = time.perf_counter()

    def now() -> float:
        return time.perf_counter() - t_start

    def periodic() -> None:
        state["max_fingers"] = max(state["max_fingers"], engine.injector.active_count)
        if now() - state["last_shot"] >= 6.0:
            state["last_shot"] = now()
            shots.append((f"t={now():5.1f}s", frame()))

    def press(key, name) -> None:
        counts[name] += 1
        QTest.keyPress(window, key)

    def release(key) -> None:
        QTest.keyRelease(window, key)

    def sweep_events(ev, t, dx, dy, dur):
        steps = max(4, int(dur / 0.012))
        for i in range(steps):
            ev.append((t + dur * i / steps, lambda a=round(dx / steps), b=round(dy / steps): send_mouse(a, b)))
        counts["mouse sweeps"] += 1
        state["pitch"] += dy

    def turn(ev, t, dur=None):
        dur = dur or rng.uniform(0.25, 0.6)
        dx = rng.choice([-1, 1]) * rng.uniform(150, 700)
        dy = rng.uniform(-90, 90)
        # keep the camera roughly level: lean against accumulated pitch
        dy -= state["pitch"] * 0.5
        dy = max(-160, min(160, dy))
        sweep_events(ev, t, dx, dy, dur)

    def hold(ev, key, name, t, dur):
        ev.append((t, lambda: press(key, name)))
        ev.append((t + dur, lambda: release(key)))

    def fire(ev, t, dur):
        ev.append((t, lambda: (counts.update(["fire bursts"]), QTest.mousePress(video, Qt.MouseButton.LeftButton))))
        ev.append((t + dur, lambda: QTest.mouseRelease(video, Qt.MouseButton.LeftButton)))

    def tap(ev, key, name, t):
        ev.append((t, lambda: press(key, name)))
        ev.append((t + 0.07, lambda: release(key)))

    def scope(ev, t):
        ev.append((t, lambda: (counts.update(["scope toggles"]), QTest.mouseClick(video, Qt.MouseButton.RightButton))))

    def m_forward():
        ev, d = [], rng.uniform(2.0, 3.2)
        hold(ev, K.Key_W, "key W", 0, d)
        turn(ev, 0.4)
        if rng.random() < 0.7:
            fire(ev, 1.0, rng.uniform(0.5, 1.0))
        return "run + turn", ev

    def m_strafe_fire():
        ev, d = [], rng.uniform(1.0, 1.8)
        hold(ev, rng.choice([K.Key_A, K.Key_D]), "key A/D", 0, d)
        fire(ev, 0.2, rng.uniform(0.5, 0.9))
        return "strafe + shoot", ev

    def m_diag():
        ev, d = [], rng.uniform(1.5, 2.4)
        hold(ev, K.Key_W, "key W", 0, d)
        hold(ev, rng.choice([K.Key_A, K.Key_D]), "key A/D", 0.1, d - 0.2)
        turn(ev, 0.5)
        turn(ev, 1.2)
        return "diagonal run + 2 turns", ev

    def m_scope_burst():
        ev = []
        scope(ev, 0.0)
        fire(ev, 0.6, 0.7)
        scope(ev, 1.6)
        return "scope + shoot", ev

    def m_crouch_fire():
        ev = []
        tap(ev, K.Key_C, "key C", 0.0)
        fire(ev, 0.8, 0.8)
        tap(ev, K.Key_C, "key C", 2.0)
        return "crouch + shoot + stand", ev

    def m_back():
        ev = []
        hold(ev, K.Key_S, "key S", 0, rng.uniform(0.7, 1.2))
        fire(ev, 0.2, 0.6)
        return "back off + shoot", ev

    def m_swap():
        ev = []
        tap(ev, K.Key_2, "key 2", 0.0)
        fire(ev, 0.9, 0.5)
        tap(ev, K.Key_1, "key 1", 1.8)
        return "swap weapon + shoot", ev

    def m_sprint():
        ev = []
        tap(ev, K.Key_Shift, "key Shift", 0.0)
        hold(ev, K.Key_W, "key W", 0.2, 2.0)
        turn(ev, 0.8)
        tap(ev, K.Key_Shift, "key Shift", 2.4)
        return "sprint lock run", ev

    def m_look():
        ev = []
        turn(ev, 0.0)
        turn(ev, 0.7)
        return "look around", ev

    manoeuvres = [(m_forward, 24), (m_strafe_fire, 18), (m_diag, 14), (m_scope_burst, 8), (m_crouch_fire, 6),
                  (m_back, 6), (m_swap, 6), (m_sprint, 6), (m_look, 8)]

    def run(events):
        events.sort(key=lambda e: e[0])
        t0 = time.perf_counter()
        for t, fn in events:
            while time.perf_counter() - t0 < t:
                app.processEvents()
                periodic()
                time.sleep(0.002)
            fn()

    def check_in_game() -> bool:
        pump(0.35)
        sig = knob_signature(frame(), stick.x, stick.y)
        if abs(sig - baseline) > 90:
            pump(1.0)
            sig = knob_signature(frame(), stick.x, stick.y)
            if abs(sig - baseline) > 90:
                state["abort"] = f"the HUD changed (knob check {sig:.0f} vs {baseline:.0f})"
                return False
        return True

    log: list[str] = []
    last_fg = 0.0
    bursts_since_reload = 0
    if True:
        while now() < args.seconds and not state["abort"]:
            if not check_in_game():
                break
            if now() - last_fg > 10:
                last_fg = now()
                fg = window.adb.run("shell", "dumpsys activity activities | grep -m1 topResumedActivity",
                                    serial=serial, check=False).stdout
                if COD_PACKAGE not in fg:
                    state["abort"] = "COD is no longer the foreground app"
                    break
            fn = rng.choices([m for m, _ in manoeuvres], [w for _, w in manoeuvres])[0]
            name, events = fn()
            end_t = max(e[0] for e in events)
            if bursts_since_reload >= 3:
                tap(events, K.Key_R, "key R", end_t + 0.2)
                bursts_since_reload = 0
            log.append(f"{now():6.1f}s  {name}")
            run(events)
            bursts_since_reload += 1 if name in ("strafe + shoot", "scope + shoot", "crouch + shoot + stand",
                                                 "back off + shoot", "swap weapon + shoot", "run + turn") else 0
            pump(0.15)

    elapsed = now()
    shots.append((f"end t={elapsed:5.1f}s", frame()))
    QTest.keyClick(window, K.Key_Escape)
    pump(0.3)
    print(f"\nplayed {elapsed:.0f} s" + (f"  (STOPPED EARLY: {state['abort']})" if state["abort"] else ""))
    print(f"touches left down: {engine.injector.active_count} | most fingers at once: {state['max_fingers']} | "
          f"mouse released: {not engine.look_captured}")
    print("inputs sent:")
    for name, n in sorted(counts.items()):
        print(f"  {name:14s} {n}")
    print("timeline:")
    for line in log:
        print("  " + line)
    window.close()
    pump(0.3)

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
    print("saved", args.sheet, f"({len(shots)} frames)")
    return 1 if state["abort"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
