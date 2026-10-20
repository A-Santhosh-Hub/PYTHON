import struct

import pytest

from app.device.adb import parse_device_lines
from app.stream import protocol


def test_touch_message_layout():
    msg = protocol.encode_touch(protocol.TOUCH_DOWN, 3, 540, 1200, 1080, 2400, pressure=1.0)
    assert len(msg) == protocol.TOUCH_MESSAGE_SIZE == 32
    kind, action, pid, x, y, w, h, pressure, action_button, buttons = struct.unpack(">BBqiiHHHII", msg)
    assert (kind, action, pid, x, y, w, h) == (2, 0, 3, 540, 1200, 1080, 2400)
    assert pressure == 0xFFFF and action_button == 0 and buttons == 0


def test_touch_negative_pointer_id_roundtrips():
    msg = protocol.encode_touch(protocol.TOUCH_MOVE, -1, 0, 0, 100, 100)
    assert struct.unpack(">q", msg[2:10])[0] == -1


@pytest.mark.parametrize("value,expected", [(0.0, 0), (-1.0, 0), (1.0, 0xFFFF), (2.0, 0xFFFF), (0.5, 0x8000)])
def test_pressure_fixed_point(value, expected):
    assert protocol.pressure_to_u16(value) == expected


def test_keycode_message_layout():
    msg = protocol.encode_keycode(protocol.KEY_DOWN, protocol.KEYCODE_BACK)
    assert len(msg) == 14
    assert struct.unpack(">BBiii", msg) == (0, 0, 4, 0, 0)


def test_display_power_message():
    assert protocol.encode_set_display_power(False) == b"\x0a\x00"
    assert protocol.encode_set_display_power(True) == b"\x0a\x01"


def test_parse_session_packet():
    header = struct.pack(">III", 0x80000000, 864, 1920)
    packet = protocol.parse_packet_header(header)
    assert packet == protocol.SessionPacket(864, 1920, False)
    assert protocol.parse_packet_header(struct.pack(">III", 0x80000001, 1, 2)).client_resize


def test_parse_media_header_flags():
    pts = 123456
    key = struct.pack(">QI", (1 << 61) | pts, 5000)
    config = struct.pack(">QI", 1 << 62, 40)
    plain = struct.pack(">QI", pts, 700)
    assert protocol.parse_packet_header(key) == protocol.MediaHeader(5000, pts, False, True)
    assert protocol.parse_packet_header(config).config is True
    assert protocol.parse_packet_header(plain) == protocol.MediaHeader(700, pts, False, False)


def test_parse_header_rejects_wrong_size():
    with pytest.raises(ValueError):
        protocol.parse_packet_header(b"\0" * 5)


def test_parse_adb_devices_output():
    text = (
        "List of devices attached\n"
        "10BE6R1CD1000BB        device product:I2302T model:I2302 device:I2302 transport_id:1\n"
        "ABC123                 unauthorized transport_id:2\n"
        "* daemon started successfully\n"
    )
    devices = parse_device_lines(text)
    assert [d.serial for d in devices] == ["10BE6R1CD1000BB", "ABC123"]
    assert devices[0].usable and devices[0].model == "I2302"
    assert not devices[1].usable and "Allow" in devices[1].hint


def test_parse_track_devices_payload_empty():
    assert parse_device_lines("") == []
