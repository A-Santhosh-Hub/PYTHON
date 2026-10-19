"""Live PUBG verification of the saved profile (sprint, look): (1) where must the stick be pushed for sprint to engage, (2) which part of the screen
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
    try:
        # saved profile as it is: short sprint, cancel with S, then turn the camera
        shot("v_0_before")
        QTest.keyPress(window, KEY.Key_W)
        QTest.keyPress(window, KEY.Key_Shift)
        pump(0.8)
        shot("v_1_sprint")
        QTest.keyRelease(window, KEY.Key_Shift)
        QTest.keyRelease(window, KEY.Key_W)
        pump(0.2)
        QTest.keyPress(window, KEY.Key_S)
        pump(0.25)
        QTest.keyRelease(window, KEY.Key_S)
        pump(0.6)
        shot("v_2_stopped")
        for _ in range(25):
            engine.look_delta(8, 0)
            pump(0.02)
        pump(0.4)
        shot("v_3_look_right")
        for _ in range(25):
            engine.look_delta(-8, 0)
            pump(0.02)
        pump(0.4)
        shot("v_4_look_back")
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
