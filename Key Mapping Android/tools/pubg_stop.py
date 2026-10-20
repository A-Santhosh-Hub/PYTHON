"""Cancels PUBG's sprint lock with one short backward tap (S) through the app pipeline. Use after a sprint test."""
from __future__ import annotations

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


def main() -> int:
    setup_logging()
    app = QApplication([])
    app.setStyleSheet(theme.STYLE_SHEET)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    window = MainWindow()
    snapshot = {k: window.settings.value(k) for k in window.settings.allKeys()}
    window.show()
    window.activateWindow()

    def pump(seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.004)

    if connect_window(window, pump) != "real":
        return 2
    window.router.window = type("A", (), {"isActiveWindow": staticmethod(lambda: True)})()
    window._choose_profile("PUBG Battle Royale")
    window._set_mapping(True)
    pump(0.3)
    QTest.keyPress(window, Qt.Key.Key_S)
    pump(0.25)
    QTest.keyRelease(window, Qt.Key.Key_S)
    pump(0.3)
    window._set_mapping(False)
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
