"""Raw relative mouse movement (Windows Raw Input) and cursor confinement.

Raw Input delivers the mouse's own movement counts, untouched by Windows pointer speed / acceleration and
unaffected by the cursor hitting the edge of the screen - what a game needs for aiming.
"""
from __future__ import annotations

import atexit
import ctypes
import logging
import struct
import sys
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"
WM_INPUT = 0x00FF
RID_INPUT = 0x10000003
RIDEV_REMOVE = 0x00000001
RIM_TYPEMOUSE = 0
MOUSE_MOVE_ABSOLUTE = 0x01

# RAWINPUTHEADER is {DWORD type, DWORD size, HANDLE device, WPARAM wParam}; the mouse data follows it:
# RAWMOUSE is {USHORT flags, (2 bytes padding), 4 bytes button data, ULONG raw buttons, LONG x, LONG y, ULONG extra}
_HEADER_SIZE = 24 if ctypes.sizeof(ctypes.c_void_p) == 8 else 16


def parse_raw_input(buf: bytes) -> tuple[int, int] | None:
    """Relative (dx, dy) of a RAWINPUT mouse packet, or None if it is not a relative mouse move."""
    if len(buf) < _HEADER_SIZE + 20:
        return None
    (kind,) = struct.unpack_from("<I", buf, 0)
    if kind != RIM_TYPEMOUSE:
        return None
    (flags,) = struct.unpack_from("<H", buf, _HEADER_SIZE)
    if flags & MOUSE_MOVE_ABSOLUTE:
        return None                       # absolute devices (touch screens, remote desktop) are not mice
    dx, dy = struct.unpack_from("<ii", buf, _HEADER_SIZE + 12)
    return (dx, dy) if (dx or dy) else None


if IS_WINDOWS:
    _user32 = ctypes.windll.user32

    class RAWINPUTDEVICE(ctypes.Structure):
        _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                    ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]

    _user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]
    _user32.RegisterRawInputDevices.restype = wintypes.BOOL
    _user32.GetRawInputData.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p,
                                        ctypes.POINTER(wintypes.UINT), wintypes.UINT]
    _user32.GetRawInputData.restype = wintypes.UINT
    _user32.ClipCursor.argtypes = [ctypes.POINTER(wintypes.RECT)]
    _user32.ClipCursor.restype = wintypes.BOOL


def clip_cursor(left: int, top: int, right: int, bottom: int) -> bool:
    """Confine the cursor to a screen rectangle (physical pixels)."""
    if not IS_WINDOWS:
        return False
    rect = wintypes.RECT(left, top, right, bottom)
    return bool(_user32.ClipCursor(ctypes.byref(rect)))


def release_cursor() -> None:
    if IS_WINDOWS:
        _user32.ClipCursor(None)


atexit.register(release_cursor)           # never leave the cursor trapped if the app exits unexpectedly


class RawMouse(QAbstractNativeEventFilter):
    """While started, calls `on_delta(dx, dy)` for every raw mouse movement sent to the app's window."""

    def __init__(self, on_delta: Callable[[int, int], None]) -> None:
        super().__init__()
        self._on_delta = on_delta
        self._active = False
        self._buffer = ctypes.create_string_buffer(128)

    @property
    def active(self) -> bool:
        return self._active

    def start(self, hwnd: int) -> bool:
        if not IS_WINDOWS or self._active:
            return self._active
        device = RAWINPUTDEVICE(0x01, 0x02, 0, hwnd)            # generic desktop / mouse, window must have focus
        if not _user32.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(device)):
            log.error("RegisterRawInputDevices failed (error %d)", ctypes.get_last_error())
            return False
        QCoreApplication.instance().installNativeEventFilter(self)
        self._active = True
        return True

    def stop(self) -> None:
        if not self._active:
            return
        self._active = False
        QCoreApplication.instance().removeNativeEventFilter(self)
        device = RAWINPUTDEVICE(0x01, 0x02, RIDEV_REMOVE, None)
        _user32.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(device))

    def nativeEventFilter(self, event_type, message):
        if self._active and bytes(event_type) == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_INPUT:
                size = wintypes.UINT(len(self._buffer))
                got = _user32.GetRawInputData(ctypes.c_void_p(msg.lParam), RID_INPUT, self._buffer,
                                              ctypes.byref(size), _HEADER_SIZE)
                if got != 0xFFFFFFFF and got:
                    delta = parse_raw_input(self._buffer.raw[:got])
                    if delta:
                        self._on_delta(*delta)
        return False, 0
