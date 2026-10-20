import math

import pytest

from app.input.engine import InputEngine
from app.input.touch import TouchInjector
from app.mapping.profile import (Binding, Look, Profile, ProfileError, ProfileStore, Stick, make_combo, split_combo)
from app.stream import protocol
from test_mapping import FakeControl

W, H = 2400, 1080
D, U, M = protocol.TOUCH_DOWN, protocol.TOUCH_UP, protocol.TOUCH_MOVE


class Rig:
    """Engine + manual scheduler: timers only run when `advance(ms)` is called."""

    def __init__(self, profile=None, bindings=(), stick=None, look=None, size=(W, H)):
        self.control = FakeControl()
        self.now_ms = 0.0
        self.timers = []
        self.clock_t = 100.0
        injector = TouchInjector(lambda: self.control, lambda: size)
        self.engine = InputEngine(injector, lambda ms, fn: self.timers.append((self.now_ms + ms, fn)),
                                  clock=lambda: self.clock_t)
        self.profile = profile or Profile("t")
        for b in bindings:
            self.profile.add(b)
        if stick:
            self.profile.set_stick(stick)
        if look:
            self.profile.looks.append(look)
        self.engine.set_profile(self.profile)
        self.engine.set_mapping_active(True)

    def advance(self, ms):
        end = self.now_ms + ms
        while True:
            due = sorted((t for t in self.timers if t[0] <= end), key=lambda t: t[0])
            if not due:
                break
            t, fn = due[0]
            self.timers.remove(due[0])
            self.now_ms = t
            self.clock_t = 100.0 + t / 1000
            fn()
        self.now_ms = end
        self.clock_t = 100.0 + end / 1000

    def press(self, name, ms=0):
        r = self.engine.key_event(name, True)
        self.advance(ms)
        return r

    def release(self, name, ms=0):
        r = self.engine.key_event(name, False)
        self.advance(ms)
        return r

    def touches(self):
        return self.control.touches()

    def kinds(self):
        return [t[0] for t in self.touches()]


# ===================================================================== profile model
def test_combo_names_are_canonical():
    assert make_combo({"Alt", "Shift", "Ctrl"}, "W") == "Ctrl+Shift+Alt+W"
    assert split_combo("Shift+W") == (frozenset({"Shift"}), "W")
    assert split_combo("W") == (frozenset(), "W")
    assert Binding("Shift+Ctrl+W", 0.5, 0.5).input == "Ctrl+Shift+W"
    assert split_combo("Ctrl+WheelUp") == (frozenset({"Ctrl"}), "WheelUp")


def test_combo_needs_a_normal_key():
    with pytest.raises(ProfileError):
        Binding("Ctrl+Shift", 0.5, 0.5)
    assert Binding("Shift", 0.5, 0.5).input == "Shift"             # a lone modifier is a fine key


def test_every_mode_roundtrips(tmp_path):
    store = ProfileStore(tmp_path)
    p = Profile("m", bindings=[
        Binding("A", 0.1, 0.1, "toggle"),
        Binding("B", 0.2, 0.2, "repeat", rate_hz=14),
        Binding("C", 0.3, 0.3, "double"),
        Binding("D", 0.4, 0.4, "swipe", x2=0.6, y2=0.7, duration_ms=250),
        Binding("E", 0.5, 0.5, "drag", x2=0.9, y2=0.5),
        Binding("WheelUp", 0.5, 0.4, "pinch-out", span=0.15, duration_ms=300),
        Binding("WheelDown", 0.5, 0.4, "pinch-in"),
        Binding("F", 0.5, 0.5, "sequence", steps=[(0.1, 0.1, 0), (0.2, 0.2, 300), (0.3, 0.3, 100)]),
        Binding("RMB", 0.9, 0.5, "tap", scope=True),
    ])
    store.save(p)
    got = {b.input: b for b in store.load("m").bindings}
    assert got["B"].rate_hz == 14 and got["D"].x2 == 0.6 and got["D"].duration_ms == 250
    assert got["E"].mode == "drag" and (got["E"].x2, got["E"].y2) == (0.9, 0.5)
    assert got["WheelUp"].span == 0.15 and got["WheelDown"].mode == "pinch-in"
    assert got["F"].steps == [(0.1, 0.1, 0), (0.2, 0.2, 300), (0.3, 0.3, 100)]
    assert got["RMB"].scope is True and got["A"].scope is False


def test_old_binding_files_still_load():
    b = Binding.from_dict({"type": "tap", "input": "R", "x": 0.7, "y": 0.8, "mode": "tap", "label": "Reload"})
    assert (b.mode, b.scope, b.rate_hz) == ("tap", False, 10.0)


def test_two_point_modes_get_a_default_end_and_sequence_a_default_step():
    s = Binding("Q", 0.5, 0.5, "swipe")
    assert (s.x2, s.y2) == (0.65, 0.5)
    q = Binding("Q", 0.4, 0.6, "sequence")
    assert q.steps == [(0.4, 0.6, 0)]


def test_binding_values_are_clamped():
    b = Binding("Q", 2, -1, "repeat", rate_hz=999, duration_ms=1, span=9)
    assert (b.x, b.y, b.rate_hz) == (1.0, 0.0, 30.0)
    assert Binding("Q", 0.5, 0.5, "pinch-in", span=9).span == 0.40 and Binding("Q", .5, .5, duration_ms=1).duration_ms == 40


def test_stick_extra_keys_validate_and_claim_their_keys():
    s = Stick(0.1, 0.8, sprint_key="Shift", walk_key="Ctrl", autorun_key="Q")
    assert s.key_set() >= {"W", "A", "S", "D", "Shift", "Ctrl", "Q"}
    with pytest.raises(ProfileError):
        Stick(0.1, 0.8, sprint_key="W")                              # same as a direction key
    with pytest.raises(ProfileError):
        Stick(0.1, 0.8, sprint_key="Shift", walk_key="Shift")        # sprint and walk the same
    p = Profile("p", bindings=[Binding("Shift", 0.8, 0.3)])
    assert p.set_stick(s) == ["Shift"]                               # a tap on Shift would clash, so it is removed
    assert p.key_owner("Ctrl") == "the movement stick"


def test_stick_and_look_new_fields_roundtrip(tmp_path):
    store = ProfileStore(tmp_path)
    p = Profile("p")
    p.set_stick(Stick(0.1, 0.8, sprint_key="Shift", sprint_scale=1.6, walk_key="Ctrl", walk_scale=0.4, autorun_key="Q"))
    p.looks.append(Look(0.4, 0.1, 0.7, 0.5, ads_scale=0.6))
    store.save(p)
    q = store.load("p")
    st, lk = q.sticks[0], q.looks[0]
    assert (st.sprint_key, st.sprint_scale, st.walk_key, st.walk_scale, st.autorun_key) == ("Shift", 1.6, "Ctrl", 0.4, "Q")
    assert lk.ads_scale == 0.6
    old = Profile.from_dict({"name": "o", "sticks": [{"type": "stick", "x": .1, "y": .8}], "looks": [
        {"type": "look", "x0": .4, "y0": .1, "x1": .7, "y1": .5}]})
    assert old.sticks[0].sprint_key == "" and old.looks[0].ads_scale == 1.0


# ===================================================================== toggle / repeat / double
def test_toggle_keeps_touching_until_pressed_again():
    r = Rig(bindings=[Binding("X", 0.5, 0.5, "toggle")])
    r.press("X")
    r.release("X", 500)
    assert r.kinds() == [D]                                          # still down after the key came up
    r.press("X")
    assert r.kinds() == [D, U]
    r.release("X")


def test_toggle_is_cleared_by_release_all():
    r = Rig(bindings=[Binding("X", 0.5, 0.5, "toggle")])
    r.press("X")
    r.engine.release_all()
    assert r.kinds() == [D, U] and r.engine.injector.active_count == 0
    r.press("X")                                                     # works again from a clean state
    assert r.kinds()[-1] == D


def test_repeat_taps_at_the_rate_while_held_and_stops_on_release():
    r = Rig(bindings=[Binding("F", 0.5, 0.5, "repeat", rate_hz=10)])
    r.press("F")
    r.advance(1000)
    downs = r.kinds().count(D)
    assert 9 <= downs <= 11, downs                                   # ~10 taps in one second
    r.release("F")
    n = len(r.touches())
    r.advance(1000)
    assert len(r.touches()) == n and r.engine.injector.active_count == 0


def test_repeat_never_leaves_a_finger_down_between_taps():
    r = Rig(bindings=[Binding("F", 0.5, 0.5, "repeat", rate_hz=30)])
    r.press("F")
    r.advance(200)
    kinds = r.kinds()
    assert all(a != b for a, b in zip(kinds, kinds[1:])) and kinds[0] == D        # strictly down/up/down/up


def test_double_tap():
    r = Rig(bindings=[Binding("G", 0.5, 0.5, "double")])
    r.press("G")
    r.release("G", 400)
    assert r.kinds() == [D, U, D, U]


# ===================================================================== swipe / drag
def test_swipe_moves_from_a_to_b_and_lets_go_without_the_key_being_released():
    r = Rig(bindings=[Binding("Q", 0.2, 0.5, "swipe", x2=0.6, y2=0.3, duration_ms=160)])
    r.press("Q", 400)
    t = r.touches()
    assert t[0][0] == D and (t[0][2], t[0][3]) == (480, 540)
    assert t[-1][0] == U and (t[-1][2], t[-1][3]) == (1440, 324)
    moves = [m for m in t if m[0] == M]
    assert len(moves) >= 10 and [m[2] for m in moves] == sorted(m[2] for m in moves)       # smooth, monotonic
    assert r.engine.injector.active_count == 0


def test_drag_stays_at_the_end_until_the_key_is_released():
    r = Rig(bindings=[Binding("Q", 0.2, 0.5, "drag", x2=0.6, y2=0.5, duration_ms=80)])
    r.press("Q", 300)
    assert r.kinds()[-1] == M and r.engine.injector.active_count == 1
    r.release("Q")
    assert r.touches()[-1][0] == U and r.touches()[-1][2] == 1440


def test_releasing_a_drag_early_lifts_the_finger_where_it_is():
    r = Rig(bindings=[Binding("Q", 0.2, 0.5, "drag", x2=0.8, y2=0.5, duration_ms=400)])
    r.press("Q", 160)
    r.release("Q", 500)                                              # stale motion ticks must not move it further
    t = r.touches()
    assert t[-1][0] == U and 480 < t[-1][2] < 1920
    assert t[-2][0] in (M, D)


# ===================================================================== pinch
def test_pinch_out_spreads_two_fingers_and_pinch_in_closes_them():
    for mode, spreading in (("pinch-out", True), ("pinch-in", False)):
        r = Rig(bindings=[Binding("Z", 0.5, 0.5, mode, span=0.2, duration_ms=160)])
        r.press("Z", 400)
        t = r.touches()
        assert {x[1] for x in t if x[0] == D} == {0, 1}              # two different fingers
        first = {x[1]: x[2] for x in t if x[0] == D}
        last = {x[1]: x[2] for x in t if x[0] == U}
        gap_start = abs(first[0] - first[1])
        gap_end = abs(last[0] - last[1])
        assert (gap_end > gap_start) == spreading and gap_start != gap_end
        assert r.engine.injector.active_count == 0
        assert (first[0] + first[1]) / 2 == pytest.approx(1200, abs=2)                # centred on the point


def test_pinch_on_the_wheel_is_a_one_shot():
    r = Rig(bindings=[Binding("WheelUp", 0.5, 0.5, "pinch-out", duration_ms=80),
                      Binding("WheelDown", 0.5, 0.5, "pinch-in", duration_ms=80)])
    assert r.engine.wheel_binding(+1) is True
    r.advance(300)
    assert r.engine.injector.active_count == 0 and r.kinds().count(D) == 2
    r.engine.wheel_binding(-1)
    r.advance(300)
    assert r.kinds().count(D) == 4


# ===================================================================== sequence
def test_sequence_taps_each_spot_in_order_with_the_delays():
    r = Rig(bindings=[Binding("F", 0.5, 0.5, "sequence", steps=[(0.1, 0.1, 0), (0.2, 0.2, 300), (0.3, 0.3, 100)])])
    r.press("F")
    r.advance(10)
    assert r.kinds() == [D] and r.touches()[0][2] == 240
    r.advance(80)
    assert r.kinds() == [D, U]
    r.advance(300)
    assert r.kinds() == [D, U, D, U] and r.touches()[2][2] == 480
    r.advance(500)
    assert r.kinds() == [D, U, D, U, D, U] and r.engine.injector.active_count == 0


def test_sequence_with_zero_delays_still_separates_the_taps():
    r = Rig(bindings=[Binding("F", 0.5, 0.5, "sequence", steps=[(0.1, 0.1, 0), (0.2, 0.2, 0), (0.3, 0.3, 0)])])
    r.press("F")
    r.advance(500)
    assert r.kinds() == [D, U, D, U, D, U]


def test_release_all_cancels_a_running_sequence():
    r = Rig(bindings=[Binding("F", 0.5, 0.5, "sequence", steps=[(0.1, 0.1, 0), (0.2, 0.2, 400)])])
    r.press("F", 100)
    r.engine.release_all()
    n = len(r.touches())
    r.advance(1000)
    assert len(r.touches()) == n                                     # the second tap never happens


# ===================================================================== combination keys
def combo_rig(**kw):
    p = Profile("c")
    p.set_stick(Stick(0.15, 0.7, radius=0.1, ramp_ms=0))
    return Rig(profile=p, bindings=[Binding("Shift+W", 0.8, 0.3, "hold", "Sprint"),
                                    Binding("R", 0.7, 0.9, "tap", "Reload"),
                                    Binding("Shift+R", 0.5, 0.9, "tap", "Reload all")], **kw)


def test_shift_w_presses_the_sprint_button_while_w_keeps_walking():
    r = combo_rig()
    r.press("W")
    assert r.kinds() == [D, M]                                       # the stick only
    r.press("Shift")
    r.press("W") if False else None
    # Shift pressed after W: the combination starts on the NEXT W press, like BlueStacks
    r.release("W")
    r.press("W")
    downs = [t for t in r.touches() if t[0] == D]
    assert len(downs) == 3 and (downs[-1][2], downs[-1][3]) == (1920, 324)          # the sprint button was touched
    assert r.engine.injector.active_count == 2                       # stick + sprint button, two fingers


def test_the_combination_ends_when_either_key_is_released():
    r = combo_rig()
    r.press("Shift")
    r.press("W")
    assert r.engine.injector.active_count == 2
    r.release("Shift")
    assert r.engine.injector.active_count == 1                       # sprint finger lifted, stick still walking
    r.release("W")
    assert r.engine.injector.active_count == 0
    r.press("Shift")
    r.press("W")
    r.release("W")
    assert r.engine.injector.active_count == 0


def test_plain_key_does_nothing_special_without_the_modifier():
    r = combo_rig()
    r.press("R", 100)
    assert r.touches()[0][2:4] == (1680, 972)                        # plain R -> reload point
    r2 = combo_rig()
    r2.press("Shift")
    r2.press("R", 100)
    assert r2.touches()[0][2:4] == (1200, 972)                       # Shift+R -> the combination wins


def test_a_modifier_with_no_combination_falls_back_to_the_plain_key():
    r = Rig(bindings=[Binding("R", 0.7, 0.9, "tap")])
    r.press("Ctrl")
    r.press("R", 100)
    assert r.kinds()[0] == D and r.touches()[0][2] == 1680


def test_wheel_combination():
    r = Rig(bindings=[Binding("WheelUp", 0.3, 0.9, "tap"), Binding("Ctrl+WheelUp", 0.6, 0.5, "pinch-out", duration_ms=80)])
    r.engine.wheel_binding(+1)
    r.advance(100)
    assert r.kinds() == [D, U]
    r.press("Ctrl")
    r.engine.wheel_binding(+1)
    r.advance(300)
    assert r.kinds().count(D) == 3                                   # one finger for the plain tap + two for the pinch


def test_modifier_state_is_forgotten_on_release_all():
    r = combo_rig()
    r.press("Shift")
    r.engine.release_all()
    r.press("R", 100)
    assert r.touches()[0][2] == 1680                                 # no phantom Shift


# ===================================================================== stick: sprint / walk / auto-run
def stick_rig(**stick_kw):
    return Rig(stick=Stick(0.15, 0.7, radius=0.10, ramp_ms=0, **stick_kw))


def test_sprint_key_pushes_the_stick_further():
    r = stick_rig(sprint_key="Shift", sprint_scale=1.5)
    r.press("W")
    normal = r.touches()[-1]
    assert normal[3] == 756 - 108
    r.press("Shift")
    sprint = r.touches()[-1]
    assert sprint[3] == 756 - round(108 * 1.5)
    r.release("Shift")
    assert r.touches()[-1][3] == 756 - 108                           # back to a normal run


def test_walk_key_pushes_the_stick_less_far():
    r = stick_rig(walk_key="Ctrl", walk_scale=0.5)
    r.press("W")
    r.press("Ctrl")
    assert r.touches()[-1][3] == 756 - 54
    r.release("Ctrl")
    assert r.touches()[-1][3] == 756 - 108


def test_sprint_with_no_direction_does_not_touch_the_screen():
    r = stick_rig(sprint_key="Shift")
    r.press("Shift")
    assert r.touches() == []


def test_sprint_works_when_pressed_before_the_direction():
    r = stick_rig(sprint_key="Shift", sprint_scale=1.5)
    r.press("Shift")
    r.press("D")
    assert r.touches()[-1][2] == 360 + round(108 * 1.5)


def test_autorun_keeps_walking_forward_until_cancelled():
    r = stick_rig(autorun_key="Q")
    r.press("Q")
    r.release("Q", 50)
    assert r.engine.injector.active_count == 1 and r.touches()[-1][3] == 756 - 108
    r.press("A")                                                    # steering sideways while auto-running
    assert r.touches()[-1][2] < 360
    r.release("A")
    r.press("S")                                                    # a backward key cancels auto-run
    r.release("S")
    assert r.engine.injector.active_count == 0


def test_autorun_pressed_twice_stops():
    r = stick_rig(autorun_key="Q")
    r.press("Q")
    r.release("Q")
    r.press("Q")
    r.release("Q")
    assert r.engine.injector.active_count == 0


def test_autorun_with_sprint_runs_faster():
    r = stick_rig(autorun_key="Q", sprint_key="Shift", sprint_scale=1.4)
    r.press("Q")
    r.press("Shift")
    assert abs(r.touches()[-1][3] - (756 - 108 * 1.4)) <= 1


# ===================================================================== scope-aware sensitivity
def aim_rig(scope_mode="tap", ads=0.5):
    return Rig(bindings=[Binding("RMB", 0.9, 0.5, scope_mode, scope=True)],
               look=Look(0.5, 0.2, 0.9, 0.8, ads_scale=ads))


def finger_travel(rig, counts=20):
    rig.engine.set_look_captured(True)
    rig.advance(300)                                                 # let the idle timer lift any earlier finger
    n = len(rig.touches())
    rig.engine.look_delta(counts, 0)
    rig.advance(10)
    moves = [t for t in rig.touches()[n:] if t[0] == M]
    return moves[-1][2] - 1680


def test_sensitivity_drops_while_scoped_in_and_returns_after():
    r = aim_rig("tap")
    assert finger_travel(r) == 20                                    # not scoped
    r.engine.mouse_button("RMB", True, None)
    r.engine.mouse_button("RMB", False, None)
    r.advance(100)
    assert r.engine.scope_active is True
    assert finger_travel(r) == 10                                    # scoped: half speed
    r.engine.mouse_button("RMB", True, None)
    r.engine.mouse_button("RMB", False, None)
    r.advance(100)
    assert r.engine.scope_active is False and finger_travel(r) == 20


def test_hold_scope_is_active_only_while_held():
    r = aim_rig("hold", 0.25)
    r.engine.mouse_button("RMB", True, None)
    assert r.engine.scope_active is True and finger_travel(r, 40) == 10
    r.engine.mouse_button("RMB", False, None)
    assert r.engine.scope_active is False


def test_toggle_scope_follows_the_toggle_state():
    r = aim_rig("toggle")
    r.engine.mouse_button("RMB", True, None)
    r.engine.mouse_button("RMB", False, None)
    assert r.engine.scope_active is True
    r.engine.mouse_button("RMB", True, None)
    assert r.engine.scope_active is False


def test_scope_state_is_cleared_when_mapping_stops():
    r = aim_rig("toggle")
    r.engine.mouse_button("RMB", True, None)
    r.engine.set_mapping_active(False)
    assert r.engine.scope_active is False


# ===================================================================== behaviour that must not change
def test_overlay_highlight_names_include_combinations():
    r = combo_rig()
    seen = []
    r.engine.on_press_changed = lambda keys: seen.append(sorted(keys))
    r.press("Shift")
    r.press("W")
    assert any("Shift+W" in keys for keys in seen)
    r.release("W")
    assert "Shift+W" not in seen[-1]


def test_duplicate_press_of_a_running_key_is_ignored():
    r = Rig(bindings=[Binding("R", 0.5, 0.5, "hold")])
    r.press("R")
    r.press("R")
    assert r.kinds() == [D]
