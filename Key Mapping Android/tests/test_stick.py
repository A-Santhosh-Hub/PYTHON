import math

import pytest

from app.input.engine import InputEngine
from app.input.touch import TouchInjector
from app.mapping.profile import Binding, Profile, ProfileError, ProfileStore, Stick
from app.stream import protocol
from test_mapping import FakeControl, make_engine


def stick_engine(ramp_ms=0, size=(2400, 1080), radius=0.1, cx=0.12, cy=0.8):
    engine, control, scheduled = make_engine(size)
    profile = Profile("s")
    profile.set_stick(Stick(cx, cy, radius=radius, ramp_ms=ramp_ms))
    engine.set_profile(profile)
    engine.set_mapping_active(True)
    return engine, control, scheduled


def run_ticks(scheduled, limit=200):
    n = 0
    while scheduled and n < limit:
        _, fn = scheduled.pop(0)
        fn()
        n += 1
    return n


def moves(control):
    return [t for t in control.touches() if t[0] == protocol.TOUCH_MOVE]


# Screen 2400x1080, centre (0.12, 0.8) = pixel (288, 864); radius 10% of the short side = 108 px.
def test_up_key_drags_finger_up_by_radius():
    engine, control, _ = stick_engine()
    assert engine.key_event("W", True)
    down, move = control.touches()
    assert down[0] == protocol.TOUCH_DOWN and (down[2], down[3]) == (288, 864)
    assert move[0] == protocol.TOUCH_MOVE and (move[2], move[3]) == (288, 864 - 108)


@pytest.mark.parametrize("key,offset", [("W", (0, -108)), ("S", (0, 108)), ("A", (-108, 0)), ("D", (108, 0))])
def test_four_directions(key, offset):
    engine, control, _ = stick_engine()
    engine.key_event(key, True)
    x, y = moves(control)[-1][2:4]
    assert (x - 288, y - 864) == offset


def test_diagonal_keeps_full_radius_not_longer():
    engine, control, _ = stick_engine()
    engine.key_event("W", True)
    engine.key_event("D", True)
    x, y = moves(control)[-1][2:4]
    assert abs(math.hypot(x - 288, y - 864) - 108) <= 1.5
    assert x > 288 and y < 864


def test_opposite_keys_cancel_but_finger_stays_down():
    engine, control, _ = stick_engine()
    engine.key_event("A", True)
    engine.key_event("D", True)
    assert moves(control)[-1][2:4] == (288, 864)
    assert engine.injector.active_count == 1


def test_lifts_only_when_all_keys_released():
    engine, control, _ = stick_engine()
    engine.key_event("W", True)
    engine.key_event("D", True)
    engine.key_event("W", False)                       # still holding D: slides right, does not lift
    x, y = moves(control)[-1][2:4]
    assert x == 288 + 108 and abs(y - 864) <= 1
    assert protocol.TOUCH_UP not in [t[0] for t in control.touches()]
    engine.key_event("D", False)
    assert control.touches()[-1][0] == protocol.TOUCH_UP
    assert engine.injector.active_count == 0


def test_ramp_moves_in_small_steps_to_target():
    engine, control, scheduled = stick_engine(ramp_ms=40)
    engine.key_event("D", True)
    assert len(moves(control)) == 1 and moves(control)[0][2] - 288 < 108      # only part of the way at first
    run_ticks(scheduled)
    xs = [m[2] for m in moves(control)]
    assert xs == sorted(xs) and xs[-1] == 288 + 108
    assert 4 <= len(xs) <= 8                                                   # 40 ms / 8 ms ticks
    assert max(b - a for a, b in zip(xs, xs[1:])) <= 24


def test_release_cancels_pending_ramp():
    engine, control, scheduled = stick_engine(ramp_ms=200)
    engine.key_event("W", True)
    engine.key_event("W", False)
    sent = len(control.messages)
    run_ticks(scheduled)                                # stale ticks must do nothing
    assert len(control.messages) == sent
    assert control.touches()[-1][0] == protocol.TOUCH_UP


def test_direction_change_while_ramping_ends_at_new_target():
    engine, control, scheduled = stick_engine(ramp_ms=40)
    engine.key_event("A", True)
    run_ticks(scheduled)
    engine.key_event("D", True)
    engine.key_event("A", False)
    run_ticks(scheduled)
    xs = [m[2] for m in moves(control)]
    assert xs[-1] == 288 + 108 and 288 - 108 in xs and any(abs(x - 288) <= 12 for x in xs[len(xs) // 2:])


def test_ignored_when_mapping_off():
    engine, control, _ = stick_engine()
    engine.set_mapping_active(False)
    assert engine.key_event("W", True) is False
    assert control.touches() == []


def test_reports_held_keys_for_overlay():
    engine, _, _ = stick_engine()
    seen = []
    engine.on_press_changed = lambda keys: seen.append(sorted(keys))
    engine.key_event("W", True)
    engine.key_event("D", True)
    engine.key_event("W", False)
    engine.key_event("D", False)
    assert seen == [["W"], ["D", "W"], ["D"], []]


def test_stick_and_tap_keys_work_together_as_multitouch():
    engine, control, _ = make_engine((2400, 1080))
    p = Profile("m", bindings=[Binding("Space", 0.9, 0.7)])
    p.set_stick(Stick(0.12, 0.8, ramp_ms=0))
    engine.set_profile(p)
    engine.set_mapping_active(True)
    engine.key_event("W", True)
    engine.key_event("Space", True)
    downs = [t for t in control.touches() if t[0] == protocol.TOUCH_DOWN]
    assert len(downs) == 2 and downs[0][1] != downs[1][1]
    engine.key_event("Space", False)
    assert engine.injector.active_count == 1            # the stick finger is still down


def test_survives_rotation():
    size = [(2400, 1080)]
    control = FakeControl()
    injector = TouchInjector(lambda: control, lambda: size[0])
    engine = InputEngine(injector, lambda ms, fn: None)
    p = Profile("r")
    p.set_stick(Stick(0.12, 0.8, ramp_ms=0))
    engine.set_profile(p)
    engine.set_mapping_active(True)
    engine.key_event("W", True)
    size[0] = (1080, 2400)
    engine.key_event("W", False)
    engine.key_event("W", True)                         # a fresh finger on the rotated screen
    assert injector.active_count == 1 and control.touches()[-1][4:] == (1080, 2400)


def test_turning_mapping_off_lifts_the_stick():
    engine, control, _ = stick_engine()
    engine.key_event("W", True)
    engine.set_mapping_active(False)
    assert engine.injector.active_count == 0 and control.touches()[-1][0] == protocol.TOUCH_UP


# ---------------------------------------------------------------- profile data
def test_roundtrip(tmp_path):
    store = ProfileStore(tmp_path)
    p = Profile("g", "landscape", [Binding("Space", 0.9, 0.7)])
    p.set_stick(Stick(0.1265, 0.8144, radius=0.085, keys={"up": "I", "left": "J", "down": "K", "right": "L"},
                      ramp_ms=30))
    store.save(p)
    loaded = store.load("g")
    stick = loaded.sticks[0]
    assert (stick.x, stick.radius, stick.ramp_ms, stick.keys["up"]) == (0.1265, 0.085, 30, "I")
    assert loaded.find("Space") is not None


def test_validation():
    with pytest.raises(ProfileError):
        Stick(0.5, 0.5, keys={"up": "W", "left": "W", "down": "S", "right": "D"})
    with pytest.raises(ProfileError):
        Stick(0.5, 0.5, keys={"up": "W", "left": "A", "down": "S"})
    s = Stick(2, -1, radius=9, ramp_ms=9999)
    assert (s.x, s.y, s.radius, s.ramp_ms) == (1.0, 0.0, 0.5, 500)


def test_set_stick_removes_clashing_taps_and_reports_them():
    p = Profile("c", bindings=[Binding("W", 0.1, 0.1), Binding("Space", 0.2, 0.2)])
    removed = p.set_stick(Stick(0.1, 0.8))
    assert removed == ["W"] and [b.input for b in p.bindings] == ["Space"]
    assert p.key_owner("A") == "the movement stick" and p.key_owner("Space") == "another control"
    assert p.key_owner("Q") is None


def test_profile_file_with_stick_tap_clash_is_rejected():
    data = {"name": "bad", "bindings": [{"type": "tap", "input": "W", "x": .1, "y": .1}],
            "sticks": [Stick(0.1, 0.8).to_dict()]}
    with pytest.raises(ProfileError):
        Profile.from_dict(data)


def test_old_profiles_without_sticks_still_load():
    assert Profile.from_dict({"version": 1, "name": "old", "bindings": []}).sticks == []
