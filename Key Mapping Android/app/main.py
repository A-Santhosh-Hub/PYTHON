from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .logging_setup import setup_logging
from .ui import theme
from .ui.main_window import MainWindow


def _run_selftest(window: MainWindow, seconds: float, screenshot: str | None) -> None:
    """Connect to the first usable device, run for `seconds`, save a screenshot, print stats, exit."""
    state = {"started": False}

    def poll() -> None:
        if not state["started"]:
            if any(d.usable for d in window.devices):
                state["started"] = True
                window._toggle_connection()
                QTimer.singleShot(int(seconds * 1000), finish)
            return

    def finish() -> None:
        print("STATUS :", window.status_label.text())
        print("STATS  :", window.stats_label.text())
        print("SCREEN :", window.video.frame_size())
        if screenshot:
            window.grab().save(screenshot)
            print("SHOT   :", screenshot)
        window.close()

    timer = QTimer(window, interval=200)
    timer.timeout.connect(poll)
    timer.start()
    QTimer.singleShot(int((seconds + 20) * 1000), lambda: (print("SELFTEST TIMEOUT"), window.close()))


def main() -> int:
    parser = argparse.ArgumentParser(prog="mobile-key-one")
    parser.add_argument("--selftest", type=float, metavar="SECONDS",
                        help="connect automatically, run for SECONDS, print stats and exit")
    parser.add_argument("--screenshot", metavar="PNG", help="with --selftest: save a window screenshot")
    args = parser.parse_args()

    setup_logging()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Mobile Key One")
    app.setStyleSheet(theme.STYLE_SHEET)
    window = MainWindow()
    window.show()
    if args.selftest:
        _run_selftest(window, args.selftest, args.screenshot)
    return app.exec()
