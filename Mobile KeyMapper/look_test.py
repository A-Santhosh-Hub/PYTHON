"""Step-4b test on the real phone: real Windows mouse movement (SendInput) -> Raw Input -> app -> phone.

The Android Settings list is the target: moving the mouse up must drag the finger up and scroll the list.
Needs the app window to have focus (Raw Input is only delivered to the focused window); do not touch the
mouse while it runs.
"""
from __future__ import annotations

import ctypes
import re
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.logging_setup import setup_logging  # noqa: E402
from app.mapping.profile import Look, Profile  # noqa: E402
from app.stream import protocol  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

TEST_PROFILE = "zz-look-test"
RESULTS: list[tuple[str, bool, str]] = []
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
    event = INPUT(0, INPUT._U(MOUSEINPUT(dx, dy, 0, 0x0001, 0, 0)))
    user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))


def cursor_pos() -> tuple[int, int]:
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def clip_rect() -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    user32.GetClipCursor(ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}", flush=True)


class Phone:
    def __init__(self, adb, serial: str) -> None:
        self.adb, self.serial = adb, serial

    def sh(self, *args: str) -> str:
        return self.adb.run("shell", *args, serial=self.serial, check=False).stdout

    def text_tops(self) -> dict[str, int]:
        self.sh("uiautomator", "dump", "/sdcard/ui.xml")
        raw = subprocess.run([self.adb.path, "-s", self.serial, "exec-out", "cat", "/sdcard/ui.xml"],
                             capture_output=True, timeout=30).stdout
        tops = {}
        for node in ET.fromstring(raw).iter("node"):
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
            if m and node.get("text") and int(m.group(2)) > 250:
                tops[node.get("text")] = int(m.group(2))
        return tops


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
            time.sleep(0.004)

    end = time.time() + 15
    while not any(d.usable for d in window.devices) and time.time() < end:
        pump(0.2)
    phone = Phone(window.adb, next(d.serial for d in window.devices if d.usable))
    phone.sh("input", "keyevent", "3")
    pump(1)
    phone.sh("am", "force-stop", "com.android.settings")
    phone.sh("am", "start", "-a", "android.settings.SETTINGS")
    pump(2.5)

    window._toggle_connection()
    end = time.time() + 15
    while window.video.frame_size() == (0, 0) and time.time() < end:
        pump(0.1)
    check("connected and receiving video", window.video.frame_size() != (0, 0))
    if window.video.frame_size() == (0, 0):
        return 1
    pump(1)
    end = time.time() + 3
    while not window.isActiveWindow() and time.time() < end:
        pump(0.1)
    if not window.isActiveWindow():
        print("SKIP: Windows did not give the app window focus; click it and rerun.")
        return 2

    sent: list[bytes] = []
    control = window.worker.control
    original_send = control.send
    control.send = lambda data: (sent.append(data), original_send(data))[1]

    def finger_events() -> list[tuple]:
        out = []
        for m in sent:
            if m[0] == protocol.TYPE_INJECT_TOUCH_EVENT:
                _, action, pid, x, y, w, h, _p, _ab, _b = struct.unpack(">BBqiiHHHII", m)
                out.append((action, pid, x, y, w, h))
        return out

    video = window.video
    previous_profile = str(window.settings.value("profile", "Default"))
    window.store.save(Profile(TEST_PROFILE))
    window._refresh_profile_list(TEST_PROFILE)

    def widget_pos(nx: float, ny: float) -> QPoint:
        r = video.target_rect()
        return QPoint(round(r.x() + nx * r.width()), round(r.y() + ny * r.height()))

    # ---- A: editor ---------------------------------------------------------------------------
    print("A. Setting the camera area with the editor")
    QTest.mouseClick(window.controls.look_place_btn, Qt.MouseButton.LeftButton)
    check("editor waits for the first corner", window._add_state == "look-1")
    QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=widget_pos(0.15, 0.40))
    check("editor waits for the second corner", window._add_state == "look-2")
    QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=widget_pos(0.85, 0.90))
    look = window.profile.looks[0] if window.profile.looks else None
    check("look zone created and saved",
          look is not None and abs(look.x0 - 0.15) < 0.01 and abs(look.y1 - 0.90) < 0.01
          and len(window.store.load(TEST_PROFILE).looks) == 1, str(look))
    check("editor finished", window._add_state is None)
    QTest.mouseClick(window.controls.look_place_btn, Qt.MouseButton.LeftButton)
    QTest.keyClick(window, Qt.Key.Key_Escape)
    check("Esc cancels the area editor", window._add_state is None)
    window.controls.look_sens_x.setValue(1.0)
    window.controls.look_sens_y.setValue(1.0)
    check("sensitivity edits are stored in the profile", window.profile.looks[0].sens_y == 1.0)

    # ---- B: capture ---------------------------------------------------------------------------
    print("B. Mouse capture")
    window.controls.mapping_btn.setChecked(True)
    pump(0.3)
    check("mapping on with only a look zone", window.engine.mapping_active)
    check("mouse captured automatically", window.engine.look_captured and window.raw_mouse.active)
    check("cursor hidden over the picture", video.cursor().shape() == Qt.CursorShape.BlankCursor)
    left, top, right, bottom = clip_rect()
    check("cursor confined to the picture", (right - left) < 1900 or (bottom - top) < 1000,
          f"clip {left},{top},{right},{bottom}")

    # ---- C: aiming drags the finger and scrolls the list --------------------------------------
    print("C. Moving the mouse drags the finger (list scrolls)")
    before = phone.text_tops()
    sent.clear()
    for _ in range(40):
        send_mouse(0, -12)                                  # 480 counts upward in total
        pump(0.012)
    pump(0.6)
    fe = finger_events()
    moves = [e for e in fe if e[0] == protocol.TOUCH_MOVE]
    travelled, last_y = 0, None
    for e in fe:                                            # add up every step, across edge re-centres
        if e[0] == protocol.TOUCH_DOWN:
            last_y = e[3]
        elif e[0] == protocol.TOUCH_MOVE and last_y is not None:
            travelled += last_y - e[3]
            last_y = e[3]
    check("a finger went down and moved", bool(fe) and fe[0][0] == protocol.TOUCH_DOWN and len(moves) > 5,
          f"{len(fe)} touch messages")
    check("finger travelled ~480 px (1 px per mouse count)", 440 <= travelled <= 520, f"{travelled} px")
    check("finger lifted after the mouse stopped", window.injector.active_count == 0
          and fe[-1][0] == protocol.TOUCH_UP)
    pump(1.8)
    after = phone.text_tops()
    common = [t for t in before if t in after]
    shift = max((before[t] - after[t] for t in common), default=0)
    check("the list scrolled up on the phone", shift > 150, f"{len(common)} common rows, shift {shift} px")

    # ---- D: sensitivity and invert -------------------------------------------------------------
    print("D. Sensitivity and invert Y")
    window.controls.look_sens_y.setValue(2.0)
    check("sensitivity is applied to the live profile", window.profile.looks[0].sens_y == 2.0)
    sent.clear()
    for _ in range(10):
        send_mouse(0, 10)
        pump(0.012)
    pump(0.5)
    moves = [e for e in finger_events() if e[0] == protocol.TOUCH_MOVE]
    travelled = (moves[-1][3] - moves[0][3]) if moves else 0
    centre_y = round((0.40 + 0.90) / 2 * moves[0][5]) if moves else 0
    check("Sens Y = 2 doubles the travel (100 counts -> ~200 px)", 170 <= (moves[-1][3] - centre_y) <= 230,
          f"{moves[-1][3] - centre_y} px from centre" if moves else "no moves")
    window.controls.look_sens_y.setValue(1.0)
    window.controls.look_invert.setChecked(True)
    sent.clear()
    for _ in range(10):
        send_mouse(0, 10)
        pump(0.012)
    pump(0.5)
    moves = [e for e in finger_events() if e[0] == protocol.TOUCH_MOVE]
    check("Invert Y reverses the vertical direction", bool(moves) and moves[-1][3] < centre_y,
          f"{moves[-1][3] - centre_y if moves else None} px from centre")
    window.controls.look_invert.setChecked(False)

    # ---- E: endless turning via edge reset ----------------------------------------------------------
    print("E. Edge reset: turning further than the zone is wide")
    resets_before = window.engine._looks[0].resets
    sent.clear()
    for _ in range(100):
        send_mouse(0, -25)                                  # 2500 counts, more than 2x the zone height
        pump(0.008)
    pump(0.6)
    fe = finger_events()
    downs = [e for e in fe if e[0] == protocol.TOUCH_DOWN]
    ups = [e for e in fe if e[0] == protocol.TOUCH_UP]
    zone_top = round(0.40 * fe[0][5]) if fe else 0
    zone_bottom = round(0.90 * fe[0][5]) if fe else 0
    check("the finger re-landed at least twice", window.engine._looks[0].resets - resets_before >= 2
          and len(downs) >= 3, f"{len(downs)} touch-downs, {len(ups)} lifts")
    check("the finger always stayed inside the camera area",
          all(zone_top <= e[3] <= zone_bottom for e in fe), f"zone y {zone_top}-{zone_bottom}")
    check("every re-landing is in the zone centre", all(abs(e[3] - (zone_top + zone_bottom) // 2) <= 2 for e in downs))
    pump(1.0)

    # ---- F: F8 frees the cursor, Esc releases everything --------------------------------------------
    print("F. F8 and Esc")
    QTest.keyClick(window, Qt.Key.Key_F8)
    pump(0.2)
    check("F8 frees the cursor", not window.engine.look_captured and not window.raw_mouse.active
          and window.engine.mapping_active)
    full = clip_rect()
    check("cursor no longer confined", (full[2] - full[0]) >= 1900, str(full))
    before_n = len(sent)
    send_mouse(0, -40)
    pump(0.3)
    check("mouse movement no longer reaches the phone", len([m for m in sent[before_n:]
                                                              if m[0] == protocol.TYPE_INJECT_TOUCH_EVENT]) == 0)
    QTest.keyClick(window, Qt.Key.Key_F8)
    pump(0.2)
    check("F8 captures again", window.engine.look_captured and window.raw_mouse.active)
    QTest.keyClick(window, Qt.Key.Key_Escape)
    pump(0.2)
    check("Esc turns mapping and capture off", not window.engine.mapping_active and not window.engine.look_captured
          and not window.raw_mouse.active)
    check("cursor released and visible again", (clip_rect()[2] - clip_rect()[0]) >= 1900
          and video.cursor().shape() != Qt.CursorShape.BlankCursor)
    check("no finger left down", window.injector.active_count == 0)

    # ---- cleanup -------------------------------------------------------------------------------
    window.store.delete(TEST_PROFILE)
    window._refresh_profile_list(previous_profile)
    phone.sh("input", "keyevent", "3")
    window.close()
    pump(0.4)
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
