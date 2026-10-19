import json
import struct

import pytest

from app.input.engine import InputEngine
from app.input.touch import TouchInjector
from app.mapping.profile import Binding, Profile, ProfileError, ProfileStore
from app.stream import protocol


class FakeControl:
    def __init__(self):
        self.messages = []

    def send(self, data):
        self.messages.append(data)
        return True

    def touches(self):
        """Decoded (action, pointer_id, x, y, w, h) for every touch message sent."""
        out = []
        for m in self.messages:
            if m[0] == protocol.TYPE_INJECT_TOUCH_EVENT:
                _, action, pid, x, y, w, h, _p, _ab, _b = struct.unpack(">BBqiiHHHII", m)
                out.append((action, pid, x, y, w, h))
        return out


def make_engine(size=(1080, 2400)):
    control = FakeControl()
    scheduled = []
    injector = TouchInjector(lambda: control, lambda: size)
    engine = InputEngine(injector, lambda ms, fn: scheduled.append((ms, fn)))
    return engine, control, scheduled


def profile_with(*bindings):
    p = Profile("t")
    for b in bindings:
        p.add(b)
    return p


# ---------------------------------------------------------------- profile storage
def test_binding_validation_and_clamping():
    b = Binding("W", 1.5, -0.2)
    assert (b.x, b.y) == (1.0, 0.0)
    with pytest.raises(ProfileError):
        Binding("", 0.5, 0.5)
    with pytest.raises(ProfileError):
        Binding("W", 0.5, 0.5, mode="bogus")


def test_profile_add_replaces_same_input():
    p = profile_with(Binding("Space", 0.1, 0.1), Binding("Space", 0.9, 0.9))
    assert len(p.bindings) == 1 and p.find("Space").x == 0.9


def test_store_roundtrip_and_atomic_save(tmp_path):
    store = ProfileStore(tmp_path)
    p = profile_with(Binding("W", 0.2, 0.7, "hold", "Forward"), Binding("LMB", 0.8, 0.8, "tap"))
    p.orientation = "landscape"
    store.save(p)
    loaded = store.load("t")
    assert loaded.orientation == "landscape"
    assert [(b.input, b.x, b.y, b.mode, b.label) for b in loaded.bindings] == \
           [("W", 0.2, 0.7, "hold", "Forward"), ("LMB", 0.8, 0.8, "tap", "")]
    assert not list(tmp_path.glob("*.tmp"))
    assert store.names() == ["t"]
    store.delete("t")
    store.delete("t")                       # deleting twice is fine
    assert store.names() == []


def test_store_rejects_bad_files(tmp_path):
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "old.json").write_text(json.dumps({"version": 99, "name": "future"}), encoding="utf-8")
    store = ProfileStore(tmp_path)
    assert store.names() == ["future"]       # unreadable file ignored, not fatal
    with pytest.raises(ProfileError):
        store.load("future")
    with pytest.raises(ProfileError):
        store.load("bad")


def test_filename_sanitized():
    assert ProfileStore.filename('PUBG: "Mobile"/1') == "PUBG_ _Mobile__1.json"
    with pytest.raises(ProfileError):
        ProfileStore.filename("  ..  ")


def test_unknown_binding_types_skipped():
    p = Profile.from_dict({"name": "x", "bindings": [
        {"type": "joystick", "input": "WASD", "x": 0, "y": 0}, {"type": "tap", "input": "Q", "x": .1, "y": .2}]})
    assert [b.input for b in p.bindings] == ["Q"]


# ---------------------------------------------------------------- touch injector
def test_injector_pointer_ids_and_pixels():
    control = FakeControl()
    inj = TouchInjector(lambda: control, lambda: (1080, 2400))
    assert inj.down("a", 0.5, 0.5) and inj.down("b", 1.0, 1.0)
    assert control.touches() == [(0, 0, 540, 1200, 1080, 2400), (0, 1, 1079, 2399, 1080, 2400)]
    inj.up("a")
    inj.down("c", 0.0, 0.0)               # reuses the freed id 0
    assert control.touches()[-1][:2] == (0, 0)
    assert inj.active_count == 2


def test_injector_limits_ten_fingers():
    inj = TouchInjector(lambda: FakeControl(), lambda: (100, 100))
    assert all(inj.down(i, 0.5, 0.5) for i in range(protocol.MAX_POINTERS))
    assert inj.down("extra", 0.5, 0.5) is False


def test_injector_up_without_down_and_double_down():
    control = FakeControl()
    inj = TouchInjector(lambda: control, lambda: (100, 100))
    assert inj.up("nope") is False
    assert inj.down("k", 0.1, 0.1) and inj.down("k", 0.9, 0.9) is False
    assert len(control.touches()) == 1


def test_injector_no_control_or_size_does_nothing():
    inj = TouchInjector(lambda: None, lambda: (100, 100))
    assert inj.down("k", 0.5, 0.5) is False and inj.active_count == 0
    inj = TouchInjector(lambda: FakeControl(), lambda: (0, 0))
    assert inj.down("k", 0.5, 0.5) is False


def test_injector_rotation_drops_fingers():
    size = [(1080, 2400)]
    control = FakeControl()
    inj = TouchInjector(lambda: control, lambda: size[0])
    inj.down("k", 0.5, 0.5)
    size[0] = (2400, 1080)
    assert inj.move("k", 0.6, 0.6) is False and inj.active_count == 0
    assert len(control.touches()) == 1       # nothing sent for the stale finger


# ---------------------------------------------------------------- engine
def test_hold_binding_follows_key():
    engine, control, _ = make_engine()
    engine.set_profile(profile_with(Binding("Space", 0.9, 0.5, "hold")))
    engine.set_mapping_active(True)
    assert engine.key_event("Space", True) is True
    engine.key_event("Space", True)                       # key repeat / duplicate press is ignored
    assert [t[0] for t in control.touches()] == [protocol.TOUCH_DOWN]
    engine.key_event("Space", False)
    assert [t[0] for t in control.touches()] == [protocol.TOUCH_DOWN, protocol.TOUCH_UP]
    assert control.touches()[0][2:4] == (972, 1200)


def test_tap_binding_releases_after_delay():
    engine, control, scheduled = make_engine()
    engine.set_profile(profile_with(Binding("F", 0.5, 0.5, "tap")))
    engine.set_mapping_active(True)
    engine.key_event("F", True)
    engine.key_event("F", False)                          # releasing early does not cancel a tap
    assert [t[0] for t in control.touches()] == [protocol.TOUCH_DOWN]
    delay, fn = scheduled[0]
    assert delay > 0
    fn()
    assert [t[0] for t in control.touches()] == [protocol.TOUCH_DOWN, protocol.TOUCH_UP]


def test_unmapped_key_and_inactive_mapping_ignored():
    engine, control, _ = make_engine()
    engine.set_profile(profile_with(Binding("W", 0.5, 0.5)))
    assert engine.key_event("W", True) is False           # mapping off
    engine.set_mapping_active(True)
    assert engine.key_event("Q", True) is False           # not bound
    assert control.touches() == []


def test_two_keys_make_two_simultaneous_touches():
    engine, control, _ = make_engine()
    engine.set_profile(profile_with(Binding("W", 0.2, 0.8), Binding("Space", 0.9, 0.5)))
    engine.set_mapping_active(True)
    engine.key_event("W", True)
    engine.key_event("Space", True)
    downs = [t for t in control.touches() if t[0] == protocol.TOUCH_DOWN]
    assert {t[1] for t in downs} == {0, 1}                # distinct pointer ids = real multi-touch
    engine.key_event("W", False)
    ups = [t for t in control.touches() if t[0] == protocol.TOUCH_UP]
    assert [t[1] for t in ups] == [0]                     # Space (pointer 1) is still held


def test_turning_mapping_off_releases_everything():
    engine, control, _ = make_engine()
    engine.set_profile(profile_with(Binding("W", 0.2, 0.8), Binding("Space", 0.9, 0.5)))
    engine.set_mapping_active(True)
    engine.key_event("W", True)
    engine.key_event("Space", True)
    engine.set_mapping_active(False)
    assert engine.injector.active_count == 0
    assert [t[0] for t in control.touches()].count(protocol.TOUCH_UP) == 2


def test_mouse_direct_touch_drag():
    engine, control, _ = make_engine()
    assert engine.mouse_button("LMB", True, (0.5, 0.8))
    engine.mouse_move((0.5, 0.5))
    engine.mouse_move((0.5, 0.2))
    engine.mouse_button("LMB", False, (0.5, 0.2))
    assert [t[0] for t in control.touches()] == [0, 2, 2, 1]
    assert [t[3] for t in control.touches()] == [1920, 1200, 480, 480]


def test_mouse_click_outside_picture_ignored_and_direct_can_be_disabled():
    engine, control, _ = make_engine()
    assert engine.mouse_button("LMB", True, None) is False
    engine.direct_touch = False
    assert engine.mouse_button("LMB", True, (0.5, 0.5)) is False
    assert control.touches() == []


def test_mapped_mouse_button_beats_direct_touch():
    engine, control, _ = make_engine()
    engine.set_profile(profile_with(Binding("LMB", 0.9, 0.9)))
    engine.set_mapping_active(True)
    engine.mouse_button("LMB", True, (0.1, 0.1))          # clicking elsewhere still fires the mapped point
    assert control.touches()[0][2:4] == (972, 2160)
    engine.mouse_button("LMB", False, (0.1, 0.1))
    assert [t[0] for t in control.touches()] == [0, 1]


def test_right_click_is_back_only_when_mapping_off():
    engine, control, _ = make_engine()
    engine.mouse_button("RMB", True, (0.5, 0.5))
    assert control.messages[-1] == protocol.encode_back_or_screen_on(protocol.KEY_DOWN)
    engine.set_profile(profile_with(Binding("W", 0.5, 0.5)))
    engine.set_mapping_active(True)
    n = len(control.messages)
    engine.mouse_button("RMB", True, (0.5, 0.5))
    assert len(control.messages) == n


def test_wheel_sends_scroll():
    engine, control, _ = make_engine()
    assert engine.wheel((0.5, 0.5), 0, 1.0)
    assert control.messages[-1][0] == protocol.TYPE_INJECT_SCROLL_EVENT
    assert len(control.messages[-1]) == 21


def test_scroll_fixed_point():
    msg = protocol.encode_scroll(10, 20, 100, 200, 0.0, 1.0)
    vscroll = struct.unpack(">h", msg[15:17])[0]
    assert vscroll == 2048                                 # 1.0 / 16 * 32768
    assert struct.unpack(">h", protocol.encode_scroll(0, 0, 1, 1, 0, 99)[15:17])[0] == 32767
