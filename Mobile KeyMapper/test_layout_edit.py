import pytest

from app.input.engine import InputEngine
from app.input.touch import TouchInjector
from app.mapping import layout_edit as le
from app.mapping.profile import Binding, Look, Profile, Stick
from app.stream import protocol
from test_mapping import FakeControl

TW, TH = 1920.0, 864.0              # picture size in pixels (for tolerances)


def make_profile():
    p = Profile("p", bindings=[Binding("R", 0.70, 0.80, "tap", "Reload"), Binding("LMB", 0.75, 0.67, "hold", "Fire")])
    p.set_stick(Stick(0.14, 0.67, radius=0.10))
    p.looks.append(Look(0.36, 0.12, 0.66, 0.52))
    return p


# ---------------------------------------------------------------- hit testing
def test_hit_tap_binding_and_topmost_wins():
    p = make_profile()
    assert le.hit_test(p, 0.70, 0.80, TW, TH) == le.Hit("tap", 0)
    p.add(Binding("T", 0.701, 0.801))                                    # a marker on top of another
    assert le.hit_test(p, 0.70, 0.80, TW, TH).index == 2


def test_hit_stick_parts():
    p = make_profile()
    r = 0.10 * min(TW, TH)
    assert le.hit_test(p, 0.14, 0.67, TW, TH) == le.Hit("stick", 0, "center")
    assert le.hit_test(p, 0.14, 0.67 - r / TH, TW, TH) == le.Hit("stick", 0, "up")
    assert le.hit_test(p, 0.14 + r / TW, 0.67, TW, TH) == le.Hit("stick", 0, "right")
    assert le.hit_test(p, 0.14 + 0.5 * r / TW, 0.67 + 0.5 * r / TH, TW, TH) == le.Hit("stick", 0, "center")


def test_hit_look_corners_and_body_and_nothing():
    p = make_profile()
    assert le.hit_test(p, 0.36, 0.12, TW, TH) == le.Hit("look", 0, "tl")
    assert le.hit_test(p, 0.66, 0.52, TW, TH) == le.Hit("look", 0, "br")
    assert le.hit_test(p, 0.5, 0.3, TW, TH) == le.Hit("look", 0, "move")
    assert le.hit_test(p, 0.95, 0.95, TW, TH) is None


# ---------------------------------------------------------------- dragging
def drag(p, hit, start, end):
    state = le.begin_drag(p, hit, *start)
    le.update_drag(p, state, *end, TW, TH)


def test_drag_tap_keeps_grab_offset_and_clamps():
    p = make_profile()
    drag(p, le.Hit("tap", 0), (0.71, 0.81), (0.40, 0.50))              # grabbed slightly off-centre
    assert (round(p.bindings[0].x, 3), round(p.bindings[0].y, 3)) == (0.39, 0.49)
    drag(p, le.Hit("tap", 0), (0.39, 0.49), (1.5, -0.5))
    assert (p.bindings[0].x, p.bindings[0].y) == (1.0, 0.0)


def test_drag_stick_center_moves_whole_stick():
    p = make_profile()
    drag(p, le.Hit("stick", 0, "center"), (0.14, 0.67), (0.2, 0.7))
    assert (round(p.sticks[0].x, 3), round(p.sticks[0].y, 3)) == (0.2, 0.7)


def test_drag_stick_node_resizes_ring_within_limits():
    p = make_profile()
    drag(p, le.Hit("stick", 0, "up"), (0.14, 0.60), (0.14, 0.67 - 0.12 * TH / TH * 0.5))
    assert 0.0 < p.sticks[0].radius < 0.14
    drag(p, le.Hit("stick", 0, "right"), (0.2, 0.67), (0.9, 0.67))
    assert p.sticks[0].radius == le.MAX_STICK_RADIUS
    drag(p, le.Hit("stick", 0, "right"), (0.2, 0.67), (0.14, 0.67))
    assert p.sticks[0].radius == le.MIN_STICK_RADIUS


def test_drag_look_zone_move_and_resize():
    p = make_profile()
    drag(p, le.Hit("look", 0, "move"), (0.5, 0.3), (0.55, 0.35))
    look = p.looks[0]
    assert (round(look.x0, 3), round(look.y0, 3), round(look.x1, 3), round(look.y1, 3)) == (0.41, 0.17, 0.71, 0.57)
    drag(p, le.Hit("look", 0, "move"), (0.5, 0.3), (5.0, 5.0))          # cannot leave the screen
    assert look.x1 <= 1.0 and look.y1 <= 1.0 and look.x1 - look.x0 == pytest.approx(0.30)
    drag(p, le.Hit("look", 0, "br"), (look.x1, look.y1), (0.9, 0.9))
    assert (look.x1, look.y1) == (0.9, 0.9)
    drag(p, le.Hit("look", 0, "br"), (0.9, 0.9), (look.x0 - 0.5, look.y0 - 0.5))   # cannot collapse
    assert look.x1 - look.x0 >= Look.MIN_SIZE - 1e-9 and look.y1 - look.y0 >= Look.MIN_SIZE - 1e-9


# ---------------------------------------------------------------- palette
def test_presets_are_added_at_free_spots_and_unique():
    p = Profile("e")
    hits = [le.add_preset(p, k) for k in ("fire", "scope", "reload", "crouch", "jump", "sprint")]
    assert all(h is not None for h in hits)
    assert [b.input for b in p.bindings] == ["LMB", "RMB", "R", "C", "Space", "Shift"]
    assert len({(round(b.x, 3), round(b.y, 3)) for b in p.bindings}) == 6                 # none stacked
    assert p.find("LMB").mode == "hold" and p.find("RMB").mode == "tap"


def test_preset_refused_when_its_key_is_taken():
    p = Profile("e", bindings=[Binding("R", 0.1, 0.1)])
    assert le.add_preset(p, "reload") is None
    q = Profile("q")
    q.set_stick(Stick(0.1, 0.8, keys={"up": "R", "left": "A", "down": "S", "right": "D"}))
    assert le.add_preset(q, "reload") is None


def test_wheel_presets_use_wheel_inputs():
    p = Profile("w")
    le.add_preset(p, "next weapon")
    le.add_preset(p, "previous weapon")
    assert {b.input for b in p.bindings} == {"WheelUp", "WheelDown"}


def test_add_stick_and_look_and_delete():
    p = Profile("s", bindings=[Binding("W", 0.3, 0.3)])
    hit, removed = le.add_stick(p)
    assert removed == ["W"] and len(p.sticks) == 1 and hit.kind == "stick"
    le.add_look(p)
    assert len(p.looks) == 1
    le.delete(p, le.Hit("stick", 0, "center"))
    le.delete(p, le.Hit("look", 0, "move"))
    assert not p.sticks and not p.looks
    p.add(Binding("Q", 0.1, 0.1))
    le.delete(p, le.Hit("tap", 0))
    le.delete(p, le.Hit("tap", 9))                                       # out of range: ignored
    assert p.bindings == []


# ---------------------------------------------------------------- mouse wheel in the engine
def wheel_engine(bindings):
    control, timers = FakeControl(), []
    engine = InputEngine(TouchInjector(lambda: control, lambda: (2400, 1080)), lambda ms, fn: timers.append(fn))
    engine.set_profile(Profile("w", bindings=bindings))
    engine.set_mapping_active(True)
    return engine, control, timers


def test_wheel_up_and_down_tap_their_points():
    engine, control, timers = wheel_engine([Binding("WheelDown", 0.5, 0.89), Binding("WheelUp", 0.4, 0.89)])
    assert engine.wheel_binding(-1) is True
    assert control.touches()[-1][2:4] == (1200, 961)
    timers.pop()()                                                       # the tap ends
    assert control.touches()[-1][0] == protocol.TOUCH_UP
    assert engine.wheel_binding(+1) is True
    assert control.touches()[-1][2:4] == (960, 961)


def test_wheel_without_binding_or_mapping_is_not_consumed():
    engine, control, _ = wheel_engine([Binding("R", 0.5, 0.5)])
    assert engine.wheel_binding(1) is False and control.touches() == []
    assert engine.has_wheel_binding() is False
    engine.set_mapping_active(False)
    assert engine.wheel_binding(1) is False


def test_wheel_taps_do_not_stack_while_one_is_still_down():
    engine, control, timers = wheel_engine([Binding("WheelDown", 0.5, 0.89)])
    assert engine.has_wheel_binding() is True
    engine.wheel_binding(-1)
    engine.wheel_binding(-1)
    assert [t[0] for t in control.touches()] == [protocol.TOUCH_DOWN]
