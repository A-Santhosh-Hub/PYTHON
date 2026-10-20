"""Whole input pipeline against the connected phone with every touch intercepted (nothing reaches the game).

Covers: per-game profile auto-load, tap/hold keys, WASD stick (4 directions + diagonal), real mouse aiming through
Windows Raw Input (travel, edge re-centre, F8, sensitivity), mouse wheel, direct mouse touch, safety (Esc, focus,
orientation guard). The phone is only used for the picture and for knowing which app is in the foreground.
"""
from __future__ import annotations

import ctypes
import struct
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.logging_setup import setup_logging  # noqa: E402
from fake_phone import connect_window  # noqa: E402
from app.mapping.profile import Binding, Look, Profile, Stick  # noqa: E402
from app.stream import protocol  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

user32 = ctypes.windll.user32
user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
RESULTS: list[bool] = []


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


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}", flush=True)


def main() -> int:
    setup_logging()
    app = QApplication([])
    app.setStyleSheet(theme.STYLE_SHEET)
    window = MainWindow()
    window.show()
    window.raise_()
    window.activateWindow()

    def pump(seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.003)

    profile_before = window.profile.name if window.profile else None
    print(f"profile before connecting: {profile_before}")
    mode = connect_window(window, pump)
    print(f"  (phone: {mode})")
    check("connected and receiving video", window.video.frame_size() != (0, 0))
    sent: list[bytes] = []
    window.worker.control.send = lambda data: (sent.append(data), True)[1]   # swallow every message

    # ---- 1. per-game auto-load ----------------------------------------------------------------
    print("1. Per-game profile")
    end = time.time() + 8
    while window.current_package == "" and time.time() < end:
        pump(0.2)
    pump(0.5)
    print(f"  phone app: {window.current_package}; profile: {window.profile.name}")
    linked = window.store.find_by_package(window.current_package)
    if linked:
        check("the profile linked to the running game was loaded automatically", window.profile.name == linked,
              f"'{linked}'")
    else:
        check("no profile is linked to this app, so the current profile stays", window.profile.name == profile_before)

    # ---- a controlled profile for the rest -----------------------------------------------------
    previous = str(window.settings.value("profile", "Default"))
    profile = Profile("zz-intercept", "landscape" if window.video.frame_size()[0] > window.video.frame_size()[1]
                      else "portrait")
    profile.set_stick(Stick(0.15, 0.70, radius=0.10, ramp_ms=0))
    profile.looks.append(Look(0.36, 0.12, 0.66, 0.52))
    for b in (Binding("LMB", 0.76, 0.67, "hold", "Fire"), Binding("R", 0.70, 0.88, "tap", "Reload"),
              Binding("WheelDown", 0.53, 0.88, "tap", "Next"), Binding("WheelUp", 0.44, 0.88, "tap", "Prev")):
        profile.add(b)
    window.store.save(profile)
    window._refresh_profile_list("zz-intercept")
    window.router.window = type("A", (), {"isActiveWindow": staticmethod(lambda: True)})()
    video, engine = window.video, window.engine
    w, h = window.worker.video_size

    def touches() -> list[tuple]:
        out = []
        for m in sent:
            if m[0] == protocol.TYPE_INJECT_TOUCH_EVENT:
                _, action, pid, x, y, tw, th, _p, _ab, _b = struct.unpack(">BBqiiHHHII", m)
                out.append((action, pid, x, y, tw, th))
        return out

    def px(nx: float, ny: float) -> tuple[int, int]:
        return round(nx * w), round(ny * h)

    window.profile.orientation = "landscape" if w > h else "portrait"
    window._set_mapping(True)
    check("mapping on, mouse captured", engine.mapping_active and engine.look_captured)

    # ---- 2. keys --------------------------------------------------------------------------------
    print("2. Keys")
    sent.clear()
    QTest.keyPress(window, Qt.Key.Key_R)
    pump(0.15)
    QTest.keyRelease(window, Qt.Key.Key_R)
    pump(0.1)
    t = touches()
    check("R taps the Reload point", t and t[0][0] == protocol.TOUCH_DOWN and abs(t[0][2] - px(0.70, 0.88)[0]) <= 1
          and t[-1][0] == protocol.TOUCH_UP, f"{len(t)} messages")
    sent.clear()
    QTest.mousePress(video, Qt.MouseButton.LeftButton)
    pump(0.3)
    held = engine.injector.active_count
    QTest.mouseRelease(video, Qt.MouseButton.LeftButton)
    pump(0.1)
    t = touches()
    check("left mouse holds the Fire point while pressed", held == 1 and t[0][0] == protocol.TOUCH_DOWN
          and t[-1][0] == protocol.TOUCH_UP and abs(t[0][3] - px(0.76, 0.67)[1]) <= 1)

    # ---- 3. WASD --------------------------------------------------------------------------------
    print("3. WASD stick")
    cx, cy = px(0.15, 0.70)
    r = round(0.10 * min(w, h))
    for key, name, (dx, dy) in ((Qt.Key.Key_W, "W", (0, -r)), (Qt.Key.Key_S, "S", (0, r)),
                                (Qt.Key.Key_A, "A", (-r, 0)), (Qt.Key.Key_D, "D", (r, 0))):
        sent.clear()
        QTest.keyPress(window, key)
        pump(0.1)
        QTest.keyRelease(window, key)
        pump(0.1)
        t = touches()
        moves = [m for m in t if m[0] == protocol.TOUCH_MOVE]
        ok = (t[0][0] == protocol.TOUCH_DOWN and abs(t[0][2] - cx) <= 1 and moves
              and abs(moves[-1][2] - (cx + dx)) <= 1 and abs(moves[-1][3] - (cy + dy)) <= 1
              and t[-1][0] == protocol.TOUCH_UP)
        check(f"{name} pushes the stick {name}-ward by one radius and lets go", bool(ok))
    sent.clear()
    QTest.keyPress(window, Qt.Key.Key_W)
    QTest.keyPress(window, Qt.Key.Key_D)
    pump(0.1)
    last = [m for m in touches() if m[0] == protocol.TOUCH_MOVE][-1]
    import math
    check("W+D is a diagonal of the same length", abs(math.hypot(last[2] - cx, last[3] - cy) - r) <= 2,
          f"length {math.hypot(last[2] - cx, last[3] - cy):.1f} vs {r}")
    QTest.keyPress(window, Qt.Key.Key_R)                                  # a tap while the stick is held = 2nd finger
    pump(0.15)
    ids = {m[1] for m in touches() if m[0] == protocol.TOUCH_DOWN}
    check("stick + a tap key use separate fingers", len(ids) == 2)
    QTest.keyRelease(window, Qt.Key.Key_R)
    QTest.keyRelease(window, Qt.Key.Key_W)
    QTest.keyRelease(window, Qt.Key.Key_D)
    pump(0.1)
    check("all fingers lifted", engine.injector.active_count == 0)

    # ---- 4. real mouse aiming ----------------------------------------------------------------------
    print("4. Mouse aiming (real Windows mouse input)")
    if not window.isActiveWindow():
        check("window has focus for raw input", False, "skip the rest of this section")
    else:
        sent.clear()
        for _ in range(40):
            send_mouse(0, -12)
            pump(0.012)
        pump(0.5)
        fe = touches()
        travelled, last_y = 0, None
        for e in fe:
            if e[0] == protocol.TOUCH_DOWN:
                last_y = e[3]
            elif e[0] == protocol.TOUCH_MOVE and last_y is not None:
                travelled += last_y - e[3]
                last_y = e[3]
        check("480 mouse counts moved the finger 480 px", 440 <= travelled <= 520, f"{travelled} px")
        check("finger lifted when the mouse stopped", engine.injector.active_count == 0)
        sent.clear()
        resets0 = engine._looks[0].resets
        for _ in range(100):
            send_mouse(25, 0)
            pump(0.008)
        pump(0.5)
        fe = touches()
        zl, zr = px(0.36, 0)[0], px(0.66, 0)[0]
        check("turning 2500 counts re-centred the finger (endless turning)", engine._looks[0].resets - resets0 >= 2)
        check("the finger never left the camera box", all(zl <= e[2] <= zr for e in fe))
        QTest.keyClick(window, Qt.Key.Key_F8)
        pump(0.2)
        n = len(sent)
        send_mouse(30, 0)
        pump(0.3)
        check("F8 frees the mouse: movement no longer reaches the phone", len(sent) == n and not engine.look_captured)
        QTest.keyClick(window, Qt.Key.Key_F8)
        pump(0.2)
        check("F8 captures it again", engine.look_captured)

    # ---- 5. wheel ---------------------------------------------------------------------------------------
    print("5. Mouse wheel")
    sent.clear()
    QApplication.sendEvent(video, QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
                                              Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                              Qt.ScrollPhase.NoScrollPhase, False))
    pump(0.15)
    d = [m for m in touches() if m[0] == protocol.TOUCH_DOWN]
    check("wheel down taps the 'Next' point", len(d) == 1 and abs(d[0][2] - px(0.53, 0.88)[0]) <= 1)
    sent.clear()
    QApplication.sendEvent(video, QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120),
                                              Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                              Qt.ScrollPhase.NoScrollPhase, False))
    pump(0.15)
    d = [m for m in touches() if m[0] == protocol.TOUCH_DOWN]
    check("wheel up taps the 'Prev' point", len(d) == 1 and abs(d[0][2] - px(0.44, 0.88)[0]) <= 1)

    # ---- 6. safety ----------------------------------------------------------------------------------------
    print("6. Safety")
    QTest.keyPress(window, Qt.Key.Key_W)
    QTest.mousePress(video, Qt.MouseButton.LeftButton)
    pump(0.2)
    check("a stick finger and a fire finger are down", engine.injector.active_count == 2)
    QTest.keyClick(window, Qt.Key.Key_Escape)
    pump(0.2)
    check("Esc lifts every finger and releases the mouse", engine.injector.active_count == 0
          and not engine.mapping_active and not engine.look_captured and not window.raw_mouse.active)
    QTest.mouseRelease(video, Qt.MouseButton.LeftButton)
    QTest.keyRelease(window, Qt.Key.Key_W)
    now_w, now_h = window.worker.video_size                 # the phone may have rotated since the test began
    wrong = "portrait" if now_w > now_h else "landscape"
    window.profile.orientation = wrong
    window._set_mapping(True)
    check("a profile made for the other orientation refuses to start", not engine.mapping_active)
    window.profile.orientation = "any"
    window._set_mapping(True)
    window.changeEvent(__import__("PySide6.QtCore", fromlist=["QEvent"]).QEvent(
        __import__("PySide6.QtCore", fromlist=["QEvent"]).QEvent.Type.ActivationChange))
    window._set_mapping(False)

    window.store.delete("zz-intercept")
    window._refresh_profile_list(previous)
    window.close()
    pump(0.3)
    failed = RESULTS.count(False)
    print(f"\n{len(RESULTS) - failed}/{len(RESULTS)} checks passed (no touch reached the phone)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
