"""Plays a live Battle Prime match through the key-mapping layer for N seconds and reports what happened.

Everything goes through the real app path: synthetic keyboard / mouse events -> router -> engine -> phone.
Camera turning is emulated with a finger drag (mouse aiming is not built yet).

Safety: before each manoeuvre it checks that the game is still the foreground app and that the match HUD
(the joystick knob) is still on screen. It stops at once if either is false (menu, results, other app).

Usage:  .venv\\Scripts\\python.exe tools\\game_play.py <sheet.png> [--seconds 120]
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
from PySide6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.logging_setup import setup_logging  # noqa: E402
from app.mapping.profile import Binding, Profile, Stick  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

PROFILE = "zz-play-test"
GAME_PACKAGE = "com.blitzteam.battleprime"
K = Qt.Key

BINDINGS = [
    Binding("LMB", 0.856, 0.700, "hold", "Fire"),
    Binding("RMB", 0.931, 0.442, "tap", "Aim"),
    Binding("R", 0.761, 0.841, "tap", "Reload"),
    Binding("Space", 0.9475, 0.676, "tap", "Jump"),
    Binding("C", 0.855, 0.898, "tap", "Crouch"),
    Binding("1", 0.4075, 0.894, "tap", "Rifle"),
    Binding("2", 0.490, 0.894, "tap", "Weapon 2"),
]
STICK = Stick(0.1265, 0.814, radius=0.10, ramp_ms=50)
CAMERA_ZONE = (0.46, 0.64, 0.22, 0.50)          # x0, x1, y0, y1: empty view area, clear of every button


def knob_fraction(img: QImage, cx: float = STICK.x, cy: float = STICK.y, radius: float = 0.028) -> float:
    """Share of bright pixels in a disc on the joystick centre. The game's white knob rests there during a
    match (about 1.0); on menus and loading screens it is 0.0. Only meaningful while no stick key is held."""
    gray = img.convertToFormat(QImage.Format.Format_Grayscale8)
    buf = np.frombuffer(gray.constBits(), np.uint8).reshape(gray.height(), gray.bytesPerLine())[:, : gray.width()]
    h, w = buf.shape
    yy, xx = np.ogrid[:h, :w]
    mask = (xx - cx * w) ** 2 + (yy - cy * h) ** 2 <= (radius * h) ** 2
    return float((buf[mask] > 215).mean())


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
    window.activateWindow()
    prev_touches = window.touches_check.isChecked()
    prev_profile = str(window.settings.value("profile", "Default"))
    window.touches_check.setChecked(True)

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
    size = window.video.frame_size()
    print("video size:", size, flush=True)
    if size[0] <= size[1]:
        print("The phone is not in landscape - is the game open? Aborting.")
        return 2
    pump(1.0)
    if not window.isActiveWindow():
        window.router.window = type("Active", (), {"isActiveWindow": staticmethod(lambda: True)})()

    video, engine = window.video, window.engine
    profile = Profile(PROFILE, "landscape", list(BINDINGS))
    profile.set_stick(STICK)
    window.store.save(profile)
    window._refresh_profile_list(PROFILE)
    window._set_mapping(True)
    if not engine.mapping_active:
        print("Mapping did not turn on:", window.controls.hint.text())
        return 2

    def frame() -> QImage:
        return video.grabFramebuffer().copy(video.target_rect().toRect())

    def foreground_is_game() -> bool:
        out = window.adb.run("shell", "dumpsys", "activity", "activities", serial=serial, check=False).stdout
        line = next((l for l in out.splitlines() if "topResumedActivity" in l), "")
        return GAME_PACKAGE in line

    pump(0.5)
    baseline = knob_fraction(frame())
    print(f"match check (joystick knob at rest): {baseline:.2f}", flush=True)
    if baseline < 0.8 or not foreground_is_game():
        print("The match HUD is not on screen (menu or other app) - not sending any input. Aborting.")
        window._set_mapping(False)
        window.store.delete(PROFILE)
        window._refresh_profile_list(prev_profile)
        window.touches_check.setChecked(prev_touches)
        window._save_settings()
        window.close()
        return 3

    rng = random.Random(20261018)
    counts: Counter = Counter()
    shots: list[tuple[str, QImage]] = []
    state = {"max_fingers": 0, "last_shot": -99.0, "last_fg": 0.0, "min_knob": 1.0, "abort": ""}
    t_start = time.perf_counter()

    def now() -> float:
        return time.perf_counter() - t_start

    def periodic() -> None:
        state["max_fingers"] = max(state["max_fingers"], engine.injector.active_count)
        if now() - state["last_shot"] >= 6.0:
            state["last_shot"] = now()
            shots.append((f"t={now():5.1f}s", frame()))

    def press(key) -> None:
        counts[f"key {key.name.replace('Key_', '')}"] += 1
        QTest.keyPress(window, key)

    def release(key) -> None:
        QTest.keyRelease(window, key)

    centre = QPoint(video.width() // 2, video.height() // 2)

    def mouse_down(button) -> None:
        counts[f"mouse {button.name}"] += 1
        QTest.mousePress(video, button, pos=centre)

    def mouse_up(button) -> None:
        QTest.mouseRelease(video, button, pos=centre)

    def camera(events, t, dx, dy, dur=0.28) -> None:
        x0 = rng.uniform(CAMERA_ZONE[0] + 0.05, CAMERA_ZONE[1] - 0.05)
        y0 = rng.uniform(CAMERA_ZONE[2] + 0.05, CAMERA_ZONE[3] - 0.05)
        owner = ("bot", "camera", t)
        steps = 12
        events.append((t, lambda: (counts.update(["camera drag"]), engine.injector.down(owner, x0, y0))))
        for i in range(1, steps + 1):
            events.append((t + dur * i / steps,
                           lambda i=i: engine.injector.move(owner, min(0.98, max(0.02, x0 + dx * i / steps)),
                                                            min(0.98, max(0.02, y0 + dy * i / steps)))))
        events.append((t + dur + 0.03, lambda: engine.injector.up(owner)))

    def hold(events, key, t, dur) -> None:
        events.append((t, lambda: press(key)))
        events.append((t + dur, lambda: release(key)))

    def fire(events, t, dur) -> None:
        events.append((t, lambda: mouse_down(Qt.MouseButton.LeftButton)))
        events.append((t + dur, lambda: mouse_up(Qt.MouseButton.LeftButton)))
        counts["fire bursts"] += 1

    def tap(events, key, t) -> None:
        events.append((t, lambda: press(key)))
        events.append((t + 0.07, lambda: release(key)))

    def click_right(events, t) -> None:
        events.append((t, lambda: mouse_down(Qt.MouseButton.RightButton)))
        events.append((t + 0.07, lambda: mouse_up(Qt.MouseButton.RightButton)))

    def turn() -> float:
        return rng.choice([-1, 1]) * rng.uniform(0.07, 0.16)

    # ---- manoeuvres: each returns (name, events) --------------------------------------------------
    def m_forward():
        ev, d = [], rng.uniform(2.0, 3.5)
        hold(ev, K.Key_W, 0, d)
        if rng.random() < 0.7:
            camera(ev, 0.4, turn(), rng.uniform(-0.03, 0.03))
        if rng.random() < 0.6:
            fire(ev, 1.0, rng.uniform(0.5, 1.1))
        return "run forward", ev

    def m_strafe():
        ev, d = [], rng.uniform(1.0, 1.8)
        hold(ev, rng.choice([K.Key_A, K.Key_D]), 0, d)
        if rng.random() < 0.5:
            hold(ev, K.Key_W, 0, d)
        fire(ev, 0.3, rng.uniform(0.5, 1.0))
        return "strafe + shoot", ev

    def m_diagonal():
        ev, d = [], rng.uniform(1.5, 2.5)
        hold(ev, K.Key_W, 0, d)
        hold(ev, rng.choice([K.Key_A, K.Key_D]), 0.1, d - 0.2)
        camera(ev, 0.6, turn(), 0.0)
        if rng.random() < 0.5:
            fire(ev, 1.1, 0.6)
        return "diagonal run + turn", ev

    def m_jump_run():
        ev = []
        hold(ev, K.Key_W, 0, 2.0)
        tap(ev, K.Key_Space, 0.5)
        tap(ev, K.Key_Space, 1.2)
        counts["jumps"] += 2
        return "run + jump", ev

    def m_crouch_fire():
        ev = []
        tap(ev, K.Key_C, 0.0)
        fire(ev, 0.9, 0.9)
        tap(ev, K.Key_C, 2.3)
        counts["crouch toggles"] += 2
        return "crouch + shoot + stand", ev

    def m_ads_burst():
        ev = []
        click_right(ev, 0.0)
        fire(ev, 0.8, 0.7)
        click_right(ev, 1.9)
        counts["aim toggles"] += 2
        return "aim down sights + shoot", ev

    def m_retreat():
        ev = []
        hold(ev, K.Key_S, 0, rng.uniform(0.8, 1.3))
        fire(ev, 0.2, 0.6)
        return "back off + shoot", ev

    def m_look():
        ev = []
        camera(ev, 0.0, turn(), rng.uniform(-0.04, 0.04))
        camera(ev, 0.7, turn(), 0.0)
        return "look around", ev

    manoeuvres = [(m_forward, 25), (m_strafe, 20), (m_diagonal, 15), (m_jump_run, 7), (m_crouch_fire, 6),
                  (m_ads_burst, 8), (m_retreat, 6), (m_look, 8)]

    def run(events) -> None:
        events.sort(key=lambda e: e[0])
        t0 = time.perf_counter()
        for t, fn in events:
            while time.perf_counter() - t0 < t:
                app.processEvents()
                periodic()
                time.sleep(0.003)
            fn()
        # nothing may stay pressed after a manoeuvre
        engine.release_all()

    # take the rifle first, then play
    ev0: list = []
    tap(ev0, K.Key_1, 0.0)
    run(ev0)
    pump(0.8)

    log: list[str] = []
    fire_since_reload = 0
    last_fg_check = 0.0
    try:
        while now() < args.seconds and not state["abort"]:
            # safety checks
            current = knob_fraction(frame())
            state["min_knob"] = min(state["min_knob"], current)
            if current < 0.5:
                pump(0.5)                            # a finger of yours or a respawn may hide the knob briefly
                again = knob_fraction(frame())
                if again < 0.5:
                    state["abort"] = f"match HUD not visible (joystick check {current:.2f}/{again:.2f})"
                    break
            if now() - last_fg_check > 10:
                last_fg_check = now()
                if not foreground_is_game():
                    state["abort"] = "the game is no longer the foreground app"
                    break
            fn = rng.choices([m for m, _ in manoeuvres], [w for _, w in manoeuvres])[0]
            bursts_before = counts["fire bursts"]
            name, events = fn()
            if counts["fire bursts"] > bursts_before:
                fire_since_reload += 1
            if fire_since_reload >= 4:
                tap(events, K.Key_R, max(e[0] for e in events) + 0.2)
                counts["reloads"] += 1
                fire_since_reload = 0
            log.append(f"{now():6.1f}s  {name}")
            run(events)
            pump(0.15)
    finally:
        engine.release_all()

    elapsed = now()
    shots.append((f"end t={elapsed:5.1f}s", frame()))
    print(f"\nplayed {elapsed:.0f} s" + (f"  (STOPPED EARLY: {state['abort']})" if state["abort"] else ""))
    print(f"touches still down: {engine.injector.active_count} | most fingers at once: {state['max_fingers']}")
    print(f"joystick-knob check never fell below {state['min_knob']:.2f} (1.0 = match HUD present)")
    print("inputs sent:")
    for name, n in sorted(counts.items()):
        print(f"  {name:18s} {n}")
    print("timeline:")
    for line in log:
        print("  " + line)

    window._set_mapping(False)
    window.store.delete(PROFILE)
    window._refresh_profile_list(prev_profile)
    window.touches_check.setChecked(prev_touches)
    window._save_settings()
    window.close()
    pump(0.3)

    cols, cw = 4, 500
    ch = round(cw * size[1] / size[0])
    rows = (len(shots) + cols - 1) // cols
    sheet = QImage(cols * cw, rows * ch, QImage.Format.Format_RGB32)
    sheet.fill(QColor("#000000"))
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
    print("saved", args.sheet, f"({len(shots)} frames)")
    return 1 if state["abort"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
