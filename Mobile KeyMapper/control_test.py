"""Step-3 test on a real phone: synthetic Qt keyboard/mouse events -> app -> phone, verified by reading
the phone's UI (uiautomator) and foreground activity before/after each action.

The test drives the Android Settings app, so it never changes anything but screen position and pages.
Usage:  .venv\\Scripts\\python.exe tools\\control_test.py
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.logging_setup import setup_logging  # noqa: E402
from app.mapping.profile import Binding, Profile  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

TEST_PROFILE = "zz-control-test"
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}", flush=True)


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


class Phone:
    def __init__(self, adb, serial: str) -> None:
        self.adb, self.serial = adb, serial
        self.min_top = 250

    def sh(self, *args: str) -> str:
        return self.adb.run("shell", *args, serial=self.serial, check=False).stdout

    def top_activity(self) -> str:
        out = self.sh("dumpsys", "activity", "activities")
        for line in out.splitlines():
            if "topResumedActivity" in line:
                return line.strip()
        return "?"

    def ui_nodes(self) -> list[dict]:
        self.sh("uiautomator", "dump", "/sdcard/ui.xml")
        raw = subprocess.run([self.adb.path, "-s", self.serial, "exec-out", "cat", "/sdcard/ui.xml"],
                             capture_output=True, timeout=30).stdout
        nodes = []
        for node in ET.fromstring(raw).iter("node"):
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
            if m:
                l, t, r, b = map(int, m.groups())
                nodes.append({"text": node.get("text", ""), "clickable": node.get("clickable") == "true",
                              "l": l, "t": t, "r": r, "b": b})
        return nodes

    def text_tops(self) -> dict[str, int]:
        return {n["text"]: n["t"] for n in self.ui_nodes() if n["text"] and n["t"] > self.min_top}


def main() -> int:
    setup_logging()
    app = QApplication([])
    app.setStyleSheet(theme.STYLE_SHEET)
    window = MainWindow()
    window.show()
    window.activateWindow()

    deadline = time.time() + 15
    while not any(d.usable for d in window.devices) and time.time() < deadline:
        pump(app, 0.2)
    phone = Phone(window.adb, next(d.serial for d in window.devices if d.usable))
    phone.sh("input", "keyevent", "3")
    pump(app, 1)
    phone.sh("am", "force-stop", "com.android.settings")        # always start from the Settings main page
    phone.sh("am", "start", "-a", "android.settings.SETTINGS")
    pump(app, 2)

    print("Preparing: reading the Settings screen layout")
    nodes = phone.ui_nodes()
    sw, sh_ = max(n["r"] for n in nodes), max(n["b"] for n in nodes)      # real screen size (portrait or landscape)
    phone.min_top = sh_ * 0.1
    candidates = [n for n in nodes if n["clickable"] and (n["r"] - n["l"]) > sw * 0.5 and sh_ * 0.25 < n["t"] < sh_ * 0.7
                  and n["b"] - n["t"] < sh_ * 0.17]
    if not candidates:
        print("Could not find a tappable row in Settings; aborting")
        return 2
    target = candidates[0]
    tx, ty = (target["l"] + target["r"]) / 2 / sw, (target["t"] + target["b"]) / 2 / sh_
    print(f"  tap target: row at x={tx:.3f} y={ty:.3f}  ({target['text'] or 'no text'})")

    window._toggle_connection()
    deadline = time.time() + 15
    while window.video.frame_size() == (0, 0) and time.time() < deadline:
        pump(app, 0.1)
    check("connected and receiving video", window.video.frame_size() != (0, 0), str(window.video.frame_size()))
    if window.video.frame_size() == (0, 0):
        return 1
    pump(app, 1)

    video = window.video
    router = window.router
    if not window.isActiveWindow():
        router.window = type("Active", (), {"isActiveWindow": staticmethod(lambda: True)})()
        print("  (window could not be activated by Windows; treating it as active for the test)")

    def widget_pos(nx: float, ny: float) -> QPoint:
        r = video.target_rect()
        return QPoint(round(r.x() + nx * r.width()), round(r.y() + ny * r.height()))

    home_activity = phone.top_activity()

    # ---- A: keyboard key -> mapped tap ---------------------------------------------------------
    print("A. Keyboard key bound to a screen point")
    profile = Profile("test", bindings=[Binding("J", tx, ty, "tap", "Open row")])
    window.profile = profile
    window.engine.set_profile(profile)
    window.controls.set_profile(profile)
    window._set_mapping(True)
    check("key mapping switched on", window.engine.mapping_active)
    QTest.keyPress(window, Qt.Key.Key_J)
    pump(app, 0.15)
    QTest.keyRelease(window, Qt.Key.Key_J)
    pump(app, 1.5)
    after_a = phone.top_activity()
    check("pressing J opened the Settings row on the phone", after_a != home_activity)
    window._set_mapping(False)

    # ---- B: right click -> Back ----------------------------------------------------------------
    print("B. Right mouse click = Back")
    QTest.mouseClick(video, Qt.MouseButton.RightButton, pos=widget_pos(0.5, 0.5))
    pump(app, 1.5)
    check("right-click went Back to the Settings main page", phone.top_activity() == home_activity)

    # ---- C: left click -> direct touch ---------------------------------------------------------
    print("C. Left mouse click = finger tap")
    QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=widget_pos(tx, ty))
    pump(app, 1.5)
    check("left-click opened the same row", phone.top_activity() != home_activity)
    QTest.mouseClick(video, Qt.MouseButton.RightButton, pos=widget_pos(0.5, 0.5))
    pump(app, 1.5)
    check("back on the main page again", phone.top_activity() == home_activity)

    # ---- D: drag + wheel -----------------------------------------------------------------------
    print("D. Mouse drag and wheel scroll the list")
    before = phone.text_tops()
    QTest.mousePress(video, Qt.MouseButton.LeftButton, pos=widget_pos(0.5, 0.75))
    for step in range(1, 11):
        QTest.mouseMove(video, widget_pos(0.5, 0.75 - 0.025 * step))
        pump(app, 0.04)
    pump(app, 0.3)                                        # stop before releasing so the list does not fling
    QTest.mouseRelease(video, Qt.MouseButton.LeftButton, pos=widget_pos(0.5, 0.5))
    pump(app, 1.8)
    after = phone.text_tops()
    common = [t for t in before if t in after]
    moved = [before[t] - after[t] for t in common]
    check("dragging up scrolled the content up", bool(moved) and max(moved) > 150,
          f"{len(common)} common rows, best shift {max(moved) if moved else 'n/a'} px")

    before = phone.text_tops()
    pos = widget_pos(0.5, 0.5)
    wheel_up = QWheelEvent(QPointF(pos), QPointF(video.mapToGlobal(pos)), QPoint(0, 0), QPoint(0, 360),
                           Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase,
                           False)
    QApplication.sendEvent(video, wheel_up)
    pump(app, 1.8)
    after = phone.text_tops()
    common = [t for t in before if t in after]
    moved = [after[t] - before[t] for t in common]
    check("wheel up scrolled the content back down", bool(moved) and max(moved) > 100,
          f"{len(common)} common rows, best shift {max(moved) if moved else 'n/a'} px")

    # ---- E: binding editor flow ----------------------------------------------------------------
    print("E. Adding a binding with the editor (click spot, then press key)")
    previous_profile = str(window.settings.value("profile", "Default"))
    window.store.save(Profile(TEST_PROFILE))              # throwaway profile; your own profiles are untouched
    window._refresh_profile_list(TEST_PROFILE)
    window.profile.bindings.clear()
    window.profile.orientation = "any"
    QTest.mouseClick(window.controls.add_btn, Qt.MouseButton.LeftButton)
    check("editor is waiting for a click", window._add_state == "place")
    QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=widget_pos(0.25, 0.75))
    check("editor is waiting for a key", window._add_state == "key")
    QTest.keyClick(window, Qt.Key.Key_K)
    binding = window.profile.find("K")
    check("binding K created at the clicked point",
          binding is not None and abs(binding.x - 0.25) < 0.01 and abs(binding.y - 0.75) < 0.01,
          f"{binding}")
    check("editor finished", window._add_state is None)
    saved = window.store.load(TEST_PROFILE)
    check("binding was saved to disk", saved.find("K") is not None)
    check("orientation recorded", saved.orientation == ("landscape" if sw > sh_ else "portrait"), saved.orientation)

    QTest.mouseClick(window.controls.add_btn, Qt.MouseButton.LeftButton)
    QTest.keyClick(window, Qt.Key.Key_Escape)
    check("Esc cancels adding", window._add_state is None)
    window.profile.bindings.clear()
    window._profile_changed()

    # ---- G: movement stick editor + real drag --------------------------------------------------
    print("G. Movement stick (WASD): editor, keys and a real drag on the phone")
    window.profile.bindings.clear()
    window.profile.sticks.clear()
    window.profile.orientation = "any"
    window._profile_changed()
    window.controls.set_profile(window.profile)
    QTest.mouseClick(window.controls.stick_place_btn, Qt.MouseButton.LeftButton)
    check("stick editor waits for the centre click", window._add_state == "stick-place")
    QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=widget_pos(0.5, 0.65))
    stick = window.profile.sticks[0] if window.profile.sticks else None
    check("stick placed with default W A S D",
          stick is not None and abs(stick.x - 0.5) < 0.01 and abs(stick.y - 0.65) < 0.01
          and stick.keys == {"up": "W", "left": "A", "down": "S", "right": "D"}, str(stick.keys if stick else None))
    check("stick saved to disk", len(window.store.load(TEST_PROFILE).sticks) == 1)

    QTest.mouseClick(window.controls.stick_keys["up"], Qt.MouseButton.LeftButton)
    QTest.keyClick(window, Qt.Key.Key_I)
    check("up key rebound to I", window.profile.sticks[0].keys["up"] == "I")
    QTest.mouseClick(window.controls.stick_keys["down"], Qt.MouseButton.LeftButton)
    QTest.keyClick(window, Qt.Key.Key_I)
    check("a key already used by the stick is refused", window.profile.sticks[0].keys["down"] == "S")
    QTest.mouseClick(window.controls.stick_keys["up"], Qt.MouseButton.LeftButton)
    QTest.keyClick(window, Qt.Key.Key_W)
    check("up key set back to W", window.profile.sticks[0].keys["up"] == "W")

    window.profile.sticks[0].radius = 0.25            # 270 px drag
    window.profile.sticks[0].ramp_ms = 120
    window._profile_changed()
    before = phone.text_tops()
    window._set_mapping(True)
    QTest.keyPress(window, Qt.Key.Key_W)
    pump(app, 0.5)
    check("a finger is held on the stick", window.injector.active_count == 1)
    QTest.keyRelease(window, Qt.Key.Key_W)
    pump(app, 2.0)
    after = phone.text_tops()
    common = [t for t in before if t in after]
    moved = [before[t] - after[t] for t in common]
    check("holding W dragged the list up", bool(moved) and max(moved) > 100,
          f"{len(common)} common rows, best shift {max(moved) if moved else 'n/a'} px")
    check("releasing W lifted the finger", window.injector.active_count == 0)

    before = after
    QTest.keyPress(window, Qt.Key.Key_S)
    pump(app, 0.5)
    QTest.keyRelease(window, Qt.Key.Key_S)
    pump(app, 2.0)
    after = phone.text_tops()
    moved = [after[t] - before[t] for t in before if t in after]
    check("holding S dragged the list back down", bool(moved) and max(moved) > 100,
          f"best shift {max(moved) if moved else 'n/a'} px")
    window._set_mapping(False)

    window.profile.add(Binding("H", 0.2, 0.2))
    window._profile_changed()
    QTest.mouseClick(window.controls.add_btn, Qt.MouseButton.LeftButton)
    QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=widget_pos(0.3, 0.3))
    QTest.keyClick(window, Qt.Key.Key_D)
    check("a tap binding cannot steal a stick key", window.profile.find("D") is None
          and window.profile.sticks[0].keys["right"] == "D")
    QTest.mouseClick(window.controls.stick_remove_btn, Qt.MouseButton.LeftButton)
    check("stick removed", not window.profile.sticks)
    window.profile.bindings.clear()
    window._profile_changed()

    # ---- F: safety -----------------------------------------------------------------------------
    print("F. Safety")
    window.profile.add(Binding("H", 0.5, 0.5, "hold"))
    window._profile_changed()
    window._set_mapping(True)
    QTest.keyPress(window, Qt.Key.Key_H)
    pump(app, 0.2)
    check("a finger is held down", window.injector.active_count == 1)
    QTest.keyClick(window, Qt.Key.Key_Escape)
    check("Esc releases mapping and every held touch", window.injector.active_count == 0
          and not window.engine.mapping_active)
    window.profile.bindings.clear()
    window._profile_changed()

    window.store.delete(TEST_PROFILE)
    window._refresh_profile_list(previous_profile)
    phone.sh("input", "keyevent", "3")
    window.close()
    pump(app, 0.5)

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
