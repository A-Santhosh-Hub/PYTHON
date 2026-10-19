import pytest

from app.mapping import layout_edit as le
from app.mapping import templates
from app.mapping.profile import Binding, Profile, Stick

TW, TH = 1920.0, 864.0


def hit(p, x, y):
    return le.hit_test(p, x, y, TW, TH)


def drag(p, h, start, end):
    state = le.begin_drag(p, h, *start)
    le.update_drag(p, state, *end, TW, TH)


# ---------------------------------------------------------------- hit testing of the new handles
def test_swipe_end_handle_is_hit_before_anything_under_it():
    p = Profile("p", bindings=[Binding("Q", 0.2, 0.5, "swipe", x2=0.6, y2=0.5)])
    assert hit(p, 0.6, 0.5) == le.Hit("tap", 0, "end")
    assert hit(p, 0.2, 0.5) == le.Hit("tap", 0)


def test_multi_tap_points_are_hit_individually_and_the_first_is_the_marker():
    p = Profile("p", bindings=[Binding("F", 0.1, 0.1, "sequence", steps=[(0.1, 0.1, 0), (0.3, 0.3, 200), (0.5, 0.5, 200)])])
    assert hit(p, 0.1, 0.1) == le.Hit("tap", 0)
    assert hit(p, 0.3, 0.3) == le.Hit("tap", 0, "step1")
    assert hit(p, 0.5, 0.5) == le.Hit("tap", 0, "step2")


def test_swipe_handle_only_exists_for_two_point_modes():
    p = Profile("p", bindings=[Binding("Q", 0.2, 0.5, "tap")])
    assert hit(p, 0.35, 0.5) is None


# ---------------------------------------------------------------- dragging them
def test_dragging_the_end_handle_moves_only_the_end():
    p = Profile("p", bindings=[Binding("Q", 0.2, 0.5, "swipe", x2=0.6, y2=0.5)])
    drag(p, le.Hit("tap", 0, "end"), (0.6, 0.5), (0.8, 0.3))
    b = p.bindings[0]
    assert (b.x, b.y) == (0.2, 0.5) and (round(b.x2, 3), round(b.y2, 3)) == (0.8, 0.3)


def test_dragging_a_swipe_marker_carries_its_end_along():
    p = Profile("p", bindings=[Binding("Q", 0.2, 0.5, "swipe", x2=0.6, y2=0.5)])
    drag(p, le.Hit("tap", 0), (0.2, 0.5), (0.3, 0.6))
    b = p.bindings[0]
    assert (round(b.x, 3), round(b.y, 3)) == (0.3, 0.6) and (round(b.x2, 3), round(b.y2, 3)) == (0.7, 0.6)


def test_dragging_one_point_of_a_multi_tap_moves_just_that_point():
    p = Profile("p", bindings=[Binding("F", 0.1, 0.1, "sequence", steps=[(0.1, 0.1, 0), (0.3, 0.3, 200), (0.5, 0.5, 300)])])
    drag(p, le.Hit("tap", 0, "step1"), (0.3, 0.3), (0.4, 0.2))
    steps = p.bindings[0].steps
    assert (round(steps[1][0], 3), round(steps[1][1], 3), steps[1][2]) == (0.4, 0.2, 200)
    assert steps[0] == (0.1, 0.1, 0) and steps[2] == (0.5, 0.5, 300)


def test_dragging_a_multi_tap_marker_moves_the_whole_sequence():
    p = Profile("p", bindings=[Binding("F", 0.1, 0.1, "sequence", steps=[(0.1, 0.1, 0), (0.3, 0.3, 200)])])
    drag(p, le.Hit("tap", 0), (0.1, 0.1), (0.2, 0.2))
    b = p.bindings[0]
    assert (round(b.x, 3), round(b.y, 3)) == (0.2, 0.2)
    assert [(round(x, 3), round(y, 3)) for x, y, _ in b.steps] == [(0.2, 0.2), (0.4, 0.4)]


def test_a_dragged_swipe_cannot_leave_the_screen():
    p = Profile("p", bindings=[Binding("Q", 0.8, 0.5, "swipe", x2=0.95, y2=0.5)])
    drag(p, le.Hit("tap", 0), (0.8, 0.5), (0.99, 0.5))
    assert p.bindings[0].x2 <= 1.0


# ---------------------------------------------------------------- deleting / building
def test_deleting_one_point_keeps_the_sequence_but_two_points_delete_it():
    p = Profile("p", bindings=[Binding("F", 0.1, 0.1, "sequence", steps=[(0.1, 0.1, 0), (0.3, 0.3, 200), (0.5, 0.5, 300)])])
    le.delete(p, le.Hit("tap", 0, "step1"))
    assert len(p.bindings[0].steps) == 2
    le.delete(p, le.Hit("tap", 0, "step1"))
    assert p.bindings == []


def test_binding_from_points_for_each_kind():
    swipe = le.binding_from_points("Q", "swipe", [(0.2, 0.5), (0.6, 0.4)])
    assert (swipe.x, swipe.y, swipe.x2, swipe.y2) == (0.2, 0.5, 0.6, 0.4)
    seq = le.binding_from_points("F", "sequence", [(0.1, 0.1), (0.2, 0.2), (0.3, 0.3)])
    assert seq.steps == [(0.1, 0.1, 0), (0.2, 0.2, le.DEFAULT_STEP_DELAY_MS), (0.3, 0.3, le.DEFAULT_STEP_DELAY_MS)]
    zoom = le.binding_from_points("WheelUp", "pinch-out", [(0.5, 0.5)])
    assert zoom.mode == "pinch-out" and (zoom.x, zoom.y) == (0.5, 0.5)
    rep = le.binding_from_points("X", "repeat", [(0.5, 0.5)])
    assert rep.mode == "repeat" and rep.rate_hz == 10.0


def test_the_scope_preset_marks_the_binding_as_the_scope_button():
    p = Profile("p")
    le.add_preset(p, "scope")
    assert p.find("RMB").scope is True
    le.add_preset(p, "reload")
    assert p.find("R").scope is False


def test_changing_the_mode_fills_in_what_the_new_mode_needs():
    b = Binding("Q", 0.3, 0.4, "tap")
    b.set_mode("swipe")
    assert (b.x2, b.y2) == pytest.approx((0.45, 0.4))
    b.set_mode("sequence")
    assert b.steps == [(0.3, 0.4, 0)]
    with pytest.raises(Exception):
        b.set_mode("nonsense")


# ---------------------------------------------------------------- templates
@pytest.mark.parametrize("template", [templates.STANDARD, templates.BATTLE_ROYALE])
def test_templates_are_valid_and_roundtrip(template):
    p = templates.build(template, "t")
    assert Profile.from_dict(p.to_dict()).to_dict() == p.to_dict()
    inputs = [b.input for b in p.bindings]
    assert len(inputs) == len(set(inputs))
    assert not (set(inputs) & p.stick_keys())                         # no control fights the stick for a key
    assert any(b.scope for b in p.bindings) and p.looks[0].ads_scale < 1.0


def test_battle_royale_has_the_pc_keys_players_expect():
    p = templates.build(templates.BATTLE_ROYALE, "br")
    inputs = {b.input for b in p.bindings}
    assert {"LMB", "RMB", "R", "C", "Z", "Space", "Q", "E", "F", "G", "Tab", "M", "1", "2", "3", "WheelUp",
            "WheelDown"} <= inputs
    stick = p.sticks[0]
    assert stick.sprint_key == "Shift" and stick.walk_key == "Ctrl"
    assert "Shift" not in inputs and "Ctrl" not in inputs              # these belong to the stick
