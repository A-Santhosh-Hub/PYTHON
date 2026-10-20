"""A simulated phone for GUI tests: lets the app be tested without hardware.

`connect_window()` connects to a real phone when one is attached and otherwise attaches a fake one that supplies a
synthetic landscape picture and swallows every touch. Either way the test then drives the real window.
"""
from __future__ import annotations

import time

import numpy as np

from app.video.frame import YuvFrame

FAKE_SIZE = (1920, 864)


class FakeControl:
    """Stands in for the control channel: records messages, sends nothing anywhere."""

    def __init__(self) -> None:
        self.messages: list[bytes] = []
        self.closed = False

    def send(self, data: bytes) -> bool:
        self.messages.append(data)
        return True

    def key(self, keycode: int) -> None:
        pass


class FakeWorker:
    serial = "FAKE-PHONE"

    def __init__(self, size: tuple[int, int] = FAKE_SIZE) -> None:
        self.video_size = size
        self.control = FakeControl()

    def stop(self) -> None:
        pass

    def wait(self, *_args) -> bool:
        return True

    def take_frame(self):
        return None, 0.0

    def snapshot(self):
        from app.stream.worker import StatsSnapshot
        return StatsSnapshot()


def synthetic_frame(size: tuple[int, int] = FAKE_SIZE) -> YuvFrame:
    w, h = size
    y = np.tile(np.linspace(40, 200, w, dtype=np.uint8), (h, 1))
    y[h // 2 - 2:h // 2 + 2, :] = 235                       # a horizon line, so the picture is not a flat colour
    u = np.full(((h + 1) // 2, (w + 1) // 2), 128, np.uint8)
    return YuvFrame(w, h, y.tobytes(), u.tobytes(), u.tobytes())


def frame_from_gray(gray: np.ndarray) -> YuvFrame:
    """A grey picture (rows x columns, uint8) as a frame, for tests that need a specific picture on the 'phone'."""
    h, w = gray.shape
    u = np.full(((h + 1) // 2, (w + 1) // 2), 128, np.uint8)
    return YuvFrame(w, h, np.ascontiguousarray(gray).tobytes(), u.tobytes(), u.tobytes())


def attach_fake_phone(window, size: tuple[int, int] = FAKE_SIZE) -> FakeWorker:
    worker = FakeWorker(size)
    window.worker = worker
    window._set_connected(True)
    window.video.set_frame(synthetic_frame(size), time.perf_counter())
    return worker


def connect_window(window, pump, wait_for_phone: float = 4.0) -> str:
    """Returns 'real' or 'fake'."""
    end = time.time() + wait_for_phone
    while not any(d.usable for d in window.devices) and time.time() < end:
        pump(0.2)
    if any(d.usable for d in window.devices):
        window._toggle_connection()
        end = time.time() + 15
        while window.video.frame_size() == (0, 0) and time.time() < end:
            pump(0.1)
        if window.video.frame_size() != (0, 0):
            return "real"
    attach_fake_phone(window)
    pump(0.3)
    return "fake"
