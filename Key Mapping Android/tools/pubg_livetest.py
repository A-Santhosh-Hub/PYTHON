"""Live check of the 'PUBG Battle Royale' profile in a running PUBG match, through the real pipeline
(Qt key events -> router -> engine -> scrcpy touches -> phone). After every step a screenshot is saved so the
effect can be seen. Only harmless keys are used: movement, sprint, look, jump, crouch, prone, scope, FPP/TPP,
reload, weapon wheel. Never fire, grenade, heal, backpack, map or shop.

Run only when a match is on screen and the user has said go. Aborts if PUBG is not in the foreground.
usage: pubg_livetest.py <screenshot-folder>
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.logging_setup import setup_logging  # noqa: E402
from fake_phone import connect_window  # noqa: E402
from app.stream import protocol  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

ADB = str(Path(__file__).resolve().parent.parent / "vendor" / "adb" / "adb.exe")
PACKAGE = "com.pubg.imobile"
KEY = Qt.Key


def adb(*args: str) -> bytes:
    return subprocess.run([ADB, *args], capture_output=True, timeout=20).stdout


def foreground() -> str:
    out = adb("shell", "dumpsys", "activity", "activities").decode(errors="ignore")
    for line in out.splitlines():
        if "topResumedActivity" in line:
            return line.split("u0 ")[-1].split("/")[0]
    return ""


def main() -> int:
    shots = Path(sys.argv[1])
    shots.mkdir(parents=True, exist_ok=True)
    setup_logging()
    app = QApplication([])
    app.setStyleSheet(theme.STYLE_SHEET)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    window = MainWindow()
    snapshot = {k: window.settings.value(k) for k in window.settings.allKeys()}
    window.show()
    window.raise_()
    window.activateWindow()

    def pump(seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.004)

    def shot(name: str) -> None:
        (shots / f"{name}.png").write_bytes(adb("exec-out", "screencap", "-p"))

    mode = connect_window(window, pump)
    if mode != "real":
        print("no real phone: abort")
        return 2
    if foreground() != PACKAGE:
        print(f"PUBG is not in front ({foreground()}): abort")
        return 2
    sent: list[bytes] = []
    real_send = window.worker.control.send
    window.worker.control.send = lambda data: (sent.append(data), real_send(data))[1]
    window.router.window = type("A", (), {"isActiveWindow": staticmethod(lambda: True)})()
    window._choose_profile("PUBG Battle Royale")
    print("profile:", window.profile.name, "| bindings:", len(window.profile.bindings))
    engine = window.engine
    window._set_mapping(True)
    pump(0.3)
    print("mapping active:", engine.mapping_active, "| look captured:", engine.look_captured)

    def touch_summary() -> str:
        n = sum(1 for m in sent if m[0] == protocol.TYPE_INJECT_TOUCH_EVENT)
        sent.clear()
        return f"{n} touch messages"

    def safe() -> bool:
        if foreground() != PACKAGE:
            print("PUBG left the foreground: stopping")
            return False
        return True

    def tap(label: str, key, hold: float = 0.12, after: float = 0.6) -> bool:
        QTest.keyPress(window, key)
        pump(hold)
        QTest.keyRelease(window, key)
        pump(after)
        shot(label)
        print(f"  {label}: {touch_summary()}")
        return safe()

    try:
        shot("00_before")
        steps_ok = True

        # ---- walking and sprinting
        QTest.keyPress(window, KEY.Key_W)
        pump(0.9)
        shot("01_W_walk")
        QTest.keyPress(window, KEY.Key_Shift)
        pump(1.0)
        shot("02_W_Shift_sprint")
        QTest.keyRelease(window, KEY.Key_Shift)
        pump(0.4)
        QTest.keyRelease(window, KEY.Key_W)
        pump(0.5)
        print(f"  walk + sprint: {touch_summary()}")
        steps_ok = safe()

        # ---- mouse look: turn right, then back
        if steps_ok:
            for _ in range(20):
                engine.look_delta(8, 0)
                pump(0.02)
            pump(0.3)
            shot("03_look_right")
            for _ in range(20):
                engine.look_delta(-8, 0)
                pump(0.02)
            pump(0.4)
            shot("04_look_back")
            print(f"  look: {touch_summary()}")
            steps_ok = safe()

        for label, key in (("05_Space_jump", KEY.Key_Space), ("06_C_crouch", KEY.Key_C), ("07_C_stand", KEY.Key_C),
                           ("08_Z_prone", KEY.Key_Z), ("09_Z_stand", KEY.Key_Z)):
            if steps_ok:
                steps_ok = tap(label, key, after=0.9)

        # ---- scope (right click), through the real mouse path of the router
        if steps_ok:
            for label in ("10_RMB_scope_on", "11_RMB_scope_off"):
                engine.mouse_button("RMB", True, (0.9, 0.5))
                pump(0.1)
                engine.mouse_button("RMB", False, (0.9, 0.5))
                pump(0.8)
                shot(label)
                print(f"  {label}: {touch_summary()}")
            steps_ok = safe()

        for label, key in (("12_V_view", KEY.Key_V), ("13_V_view_back", KEY.Key_V), ("14_R_reload", KEY.Key_R)):
            if steps_ok:
                steps_ok = tap(label, key, after=1.0)

        # ---- weapon wheel and number keys
        if steps_ok:
            for label, notches in (("15_wheel_down", -1), ("16_wheel_up", 1)):
                engine.wheel_binding(notches)
                pump(0.9)
                shot(label)
                print(f"  {label}: {touch_summary()}")
            steps_ok = safe()
        if steps_ok:
            steps_ok = tap("17_key1", KEY.Key_1, after=0.9)
        if steps_ok:
            steps_ok = tap("18_key2", KEY.Key_2, after=0.9)
        print("finished" if steps_ok else "stopped early")
    finally:
        for k in (KEY.Key_W, KEY.Key_Shift):
            QTest.keyRelease(window, k)
        window._set_mapping(False)
        pump(0.3)
        for key in window.settings.allKeys():
            if key not in snapshot:
                window.settings.remove(key)
        for key, value in snapshot.items():
            window.settings.setValue(key, value)
        window.settings.sync()
        shot("99_after")
        window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
