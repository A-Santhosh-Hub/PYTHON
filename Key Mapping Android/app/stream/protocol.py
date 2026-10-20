"""scrcpy v5.0.1 wire protocol (pure functions, no I/O).

Layouts were taken from the pinned server source (ControlMessageReader.java, Streamer.java);
all integers are big-endian.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

# --- control messages (client -> device) ---------------------------------------------------
TYPE_INJECT_KEYCODE = 0
TYPE_INJECT_TEXT = 1
TYPE_INJECT_TOUCH_EVENT = 2
TYPE_INJECT_SCROLL_EVENT = 3
TYPE_BACK_OR_SCREEN_ON = 4
TYPE_EXPAND_NOTIFICATION_PANEL = 5
TYPE_COLLAPSE_PANELS = 7
TYPE_SET_DISPLAY_POWER = 10
TYPE_ROTATE_DEVICE = 11
TYPE_RESET_VIDEO = 17

# android.view.MotionEvent / KeyEvent actions as used by the protocol
TOUCH_DOWN = 0
TOUCH_UP = 1
TOUCH_MOVE = 2
KEY_DOWN = 0
KEY_UP = 1

KEYCODE_HOME = 3
KEYCODE_BACK = 4
KEYCODE_VOLUME_UP = 24
KEYCODE_VOLUME_DOWN = 25
KEYCODE_POWER = 26
KEYCODE_APP_SWITCH = 187

MAX_POINTERS = 10          # PointersState.MAX_POINTERS on the server
POINTER_ID_MOUSE = -1      # reserved by the server; use other ids for fingers

TOUCH_MESSAGE_SIZE = 32


def pressure_to_u16(pressure: float) -> int:
    if pressure >= 1.0:
        return 0xFFFF
    if pressure <= 0.0:
        return 0
    return int(pressure * 0x10000)


def encode_touch(action: int, pointer_id: int, x: int, y: int, width: int, height: int,
                 pressure: float = 1.0, action_button: int = 0, buttons: int = 0) -> bytes:
    """x/y are pixels inside a (width x height) frame - the *current video size*.

    The server drops positional events whose size differs from the current video size.
    """
    return struct.pack(
        ">BBqiiHHHII", TYPE_INJECT_TOUCH_EVENT, action, pointer_id, x, y, width, height,
        pressure_to_u16(pressure), action_button, buttons,
    )


def encode_keycode(action: int, keycode: int, repeat: int = 0, meta_state: int = 0) -> bytes:
    return struct.pack(">BBiii", TYPE_INJECT_KEYCODE, action, keycode, repeat, meta_state)


def _i16_fixed(value: float) -> int:
    """Scroll amounts use a signed 16-bit fixed point over the range [-16, 16]."""
    return max(-32768, min(32767, int(value / 16 * 32768)))


def encode_scroll(x: int, y: int, width: int, height: int, hscroll: float, vscroll: float,
                  buttons: int = 0) -> bytes:
    return struct.pack(">BiiHHhhI", TYPE_INJECT_SCROLL_EVENT, x, y, width, height,
                       _i16_fixed(hscroll), _i16_fixed(vscroll), buttons)


def encode_back_or_screen_on(action: int) -> bytes:
    return struct.pack(">BB", TYPE_BACK_OR_SCREEN_ON, action)


def encode_set_display_power(on: bool) -> bytes:
    return struct.pack(">BB", TYPE_SET_DISPLAY_POWER, 1 if on else 0)


def encode_empty(message_type: int) -> bytes:
    return struct.pack(">B", message_type)


# --- stream packets (device -> client) -----------------------------------------------------
CODEC_IDS = {0x68323634: "h264", 0x68323635: "hevc", 0x00617631: "av1"}
PACKET_HEADER_SIZE = 12
_FLAG_SESSION = 1 << 63
_FLAG_CONFIG = 1 << 62
_FLAG_KEY_FRAME = 1 << 61
_PTS_MASK = _FLAG_KEY_FRAME - 1


@dataclass(frozen=True)
class SessionPacket:
    width: int
    height: int
    client_resize: bool


@dataclass(frozen=True)
class MediaHeader:
    size: int
    pts: int
    config: bool
    key_frame: bool


def parse_packet_header(header: bytes) -> SessionPacket | MediaHeader:
    if len(header) != PACKET_HEADER_SIZE:
        raise ValueError(f"packet header must be {PACKET_HEADER_SIZE} bytes")
    flags, a, b = struct.unpack(">III", header)
    if flags & 0x80000000:
        return SessionPacket(width=a, height=b, client_resize=bool(flags & 1))
    pts_and_flags, size = struct.unpack(">QI", header)
    return MediaHeader(
        size=size,
        pts=pts_and_flags & _PTS_MASK,
        config=bool(pts_and_flags & _FLAG_CONFIG),
        key_frame=bool(pts_and_flags & _FLAG_KEY_FRAME),
    )
