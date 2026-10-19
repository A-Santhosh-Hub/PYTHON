"""Watches which Android app is in the foreground, so the matching game profile can load by itself."""
from __future__ import annotations

import logging
import re
import time

from PySide6.QtCore import QThread, Signal

from .adb import Adb, AdbError

log = logging.getLogger(__name__)

_TOP_ACTIVITY = re.compile(r"\bu\d+\s+([A-Za-z0-9_.]+)/")


def parse_foreground_package(text: str) -> str:
    """Extract the app id from a `topResumedActivity=ActivityRecord{... u0 com.pkg/.Activity t12 d0}` line."""
    match = _TOP_ACTIVITY.search(text)
    return match.group(1) if match else ""


class ForegroundWatcher(QThread):
    packageChanged = Signal(str)

    def __init__(self, adb: Adb, serial: str, interval: float = 1.2, parent=None) -> None:
        super().__init__(parent)
        self._adb = adb
        self._serial = serial
        self._interval = interval
        self._stop = False

    def stop(self) -> None:
        self._stop = True
        self.wait(4000)

    def run(self) -> None:
        last = None
        while not self._stop:
            try:
                out = self._adb.run("shell", "dumpsys activity activities | grep -m1 topResumedActivity",
                                    serial=self._serial, check=False, timeout=8).stdout
                package = parse_foreground_package(out)
                if package and package != last:
                    last = package
                    self.packageChanged.emit(package)
            except AdbError as exc:
                log.debug("Foreground check failed: %s", exc)
            end = time.time() + self._interval
            while time.time() < end and not self._stop:
                time.sleep(0.05)
