"""Event-driven device hot-plug tracking through the adb server's `host:track-devices-l` service."""
from __future__ import annotations

import logging
import socket
import time

from PySide6.QtCore import QThread, Signal

from .adb import Adb, parse_device_lines

log = logging.getLogger(__name__)

ADB_SERVER = ("127.0.0.1", 5037)


class DeviceTracker(QThread):
    devicesChanged = Signal(list)   # list[DeviceInfo]
    trackerError = Signal(str)

    def __init__(self, adb: Adb, parent=None) -> None:
        super().__init__(parent)
        self._adb = adb
        self._stop = False
        self._sock: socket.socket | None = None

    def stop(self) -> None:
        self._stop = True
        sock = self._sock
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        self.wait(3000)

    def run(self) -> None:
        while not self._stop:
            try:
                self._adb.start_server()
                self._track()
            except Exception as exc:  # noqa: BLE001 - keep the tracker alive whatever happens
                if self._stop:
                    break
                log.warning("Device tracker: %s", exc)
                self.trackerError.emit(str(exc))
                self.devicesChanged.emit([])
            for _ in range(15):
                if self._stop:
                    return
                time.sleep(0.1)

    def _track(self) -> None:
        sock = socket.create_connection(ADB_SERVER, timeout=5)
        self._sock = sock
        try:
            request = b"host:track-devices-l"
            sock.sendall(b"%04x" % len(request) + request)
            if self._read_exact(sock, 4) != b"OKAY":
                raise ConnectionError("adb server rejected track-devices")
            sock.settimeout(None)
            while not self._stop:
                length = int(self._read_exact(sock, 4), 16)
                payload = self._read_exact(sock, length).decode("utf-8", "replace") if length else ""
                self.devicesChanged.emit(parse_device_lines(payload))
        finally:
            self._sock = None
            sock.close()

    @staticmethod
    def _read_exact(sock: socket.socket, count: int) -> bytes:
        chunks = []
        while count:
            data = sock.recv(count)
            if not data:
                raise ConnectionError("adb server closed the connection")
            chunks.append(data)
            count -= len(data)
        return b"".join(chunks)
