"""Live PUBG experiment: (1) where must the stick be pushed for sprint to engage, (2) which part of the screen
turns the camera. Changes the loaded profile in memory only (nothing is saved). Safe keys only: W, Shift, mouse look.
usage: pubg_sprintlook_test.py <screenshot-folder>
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
from app.ui import theme  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

ADB = str(Path(__file__).resolve().parent.parent / "vendor" / "adb" / "adb.exe")
PACKAGE = "com.pubg.imobile"
KEY = Qt.Key


def adb(*args: str) -> bytes:
    return subprocess.run([ADB, *args], capture_output=True, timeout=20).stdout


def foreground() -> str:
    for line in adb("shell", "dumpsys", "activity", "activities").decode(errors="ignore").splitlines():
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

    if connect_window(window, pump) != "real" or foreground() != PACKAGE:
        print("no real phone or PUBG not in front: abort")
        return 2
    window.router.window = type("A", (), {"isActiveWindow": staticmethod(lambda: True)})()
    window._choose_profile("PUBG Battle Royale")
    engine = window.engine
    window._set_mapping(True)
    pump(0.3)
    stick, look = window.profile.sticks[0], window.profile.looks[0]
    try:
        # ---- 1. sprint: how far must the stick go?
        for radius in (0.11, 0.15, 0.19):
            if foreground() != PACKAGE:
                break
            stick.radius = radius
            engine.refresh_profile()
            print(f"sprint push = {radius * 720 * stick.sprint_scale:.0f} px above the stick centre")
            QTest.keyPress(window, KEY.Key_W)
            QTest.keyPress(window, KEY.Key_Shift)
            pump(0.9)
            shot(f"s_{int(radius * 100)}_a")
            pump(0.5)
            shot(f"s_{int(radius * 100)}_b")
            QTest.keyRelease(window, KEY.Key_Shift)
            QTest.keyRelease(window, KEY.Key_W)
            pump(1.2)
        # ---- 2. look: right-of-centre zone
        zone = (0.62, 0.12, 0.76, 0.40)
        look.x0, look.y0, look.x1, look.y1 = zone
        engine.refresh_profile()
        shot("l_0_before")
        for _ in range(25):
            engine.look_delta(8, 0)
            pump(0.02)
        pump(0.4)
        shot("l_1_right")
        for _ in range(25):
            engine.look_delta(-8, 0)
            pump(0.02)
        pump(0.4)
        shot("l_2_back")
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
        window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
