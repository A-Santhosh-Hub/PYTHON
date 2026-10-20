"""Smart-mode pieces: scene recognition, extra spots on one key, their editing, and the hold-to-free hotkey rules."""
import numpy as np
import pytest

from app import hotkeys, scene
from app.input.engine import InputEngine
from app.mapping import layout_edit as le
from app.mapping.profile import MAX_ALSO, Binding, Profile, ProfileStore
from app.stream import protocol
from test_advanced import Rig

D, U = protocol.TOUCH_DOWN, protocol.TOUCH_UP
W, H = 1600, 720


# ===================================================================== scene recognition
def make_hud(background_seed: int, points, size=(W, H)) -> np.ndarray:
    """A fake game picture: a noisy scene with a distinctive icon drawn at every control position."""
    w, h = size
    rng = np.random.default_rng(background_seed)
    img = rng.normal(110, 28, (h, w)).clip(0, 255)
    for index, (x, y) in enumerate(points):
        side = int(0.075 * h)
        x0, y0 = int(x * w - side / 2), int(y * h - side / 2)
        icon = np.zeros((side, side))
        icon[:, : side // 3 * (1 + index % 2)] = 235                  # each control has its own shape
        icon[index % side :: 4, :] = 20
        img[y0:y0 + side, x0:x0 + side] = 0.25 * img[y0:y0 + side, x0:x0 + side] + 0.75 * icon      # semi-transparent
    return img.astype(np.uint8)


POINTS = [(0.1, 0.2), (0.9, 0.3), (0.85, 0.75), (0.15, 0.8), (0.5, 0.9), (0.7, 0.5), (0.3, 0.6)]


def test_hud_is_recognised_on_a_different_background():
    model = scene.learn(make_hud(1, POINTS), POINTS)
    assert model.usable and len(model.anchors) == len(POINTS)
    assert scene.score(model, make_hud(1, POINTS)) == 1.0
    assert scene.score(model, make_hud(2, POINTS)) >= 0.85            # other scenery behind the same buttons


def test_menus_and_other_pictures_are_not_the_hud():
    model = scene.learn(make_hud(1, POINTS), POINTS)
    rng = np.random.default_rng(5)
    assert scene.score(model, rng.normal(120, 40, (H, W)).clip(0, 255).astype(np.uint8)) <= 0.2     # noise
    assert scene.score(model, np.full((H, W), 90, np.uint8)) == 0.0                                 # flat colour
    other = make_hud(3, [(0.2, 0.5), (0.8, 0.5), (0.5, 0.2), (0.5, 0.8)])
    assert scene.score(model, other) <= 0.3


def test_the_hud_is_found_at_another_resolution():
    model = scene.learn(make_hud(1, POINTS), POINTS)
    assert scene.score(model, make_hud(1, POINTS, size=(2400, 1080))) >= 0.85


def test_flat_places_are_not_used_and_too_few_controls_is_reported():
    flat = np.full((H, W), 100, np.uint8)
    assert scene.learn(flat, POINTS).anchors == []
    assert not scene.learn(make_hud(1, POINTS[:2]), POINTS[:2]).usable


def test_close_controls_share_one_anchor_and_the_number_is_capped():
    model = scene.learn(make_hud(1, [(0.5, 0.5)]), [(0.5, 0.5), (0.505, 0.5), (0.5, 0.505)])
    assert len(model.anchors) == 1
    many = [(0.05 + 0.06 * i, 0.1 + 0.05 * (i % 7)) for i in range(15)]
    assert len(scene.learn(make_hud(1, many), many).anchors) <= scene.MAX_ANCHORS


def test_model_roundtrips_through_a_profile_file(tmp_path):
    model = scene.learn(make_hud(1, POINTS), POINTS)
    p = Profile("s", scene={"enabled": True, **model.to_dict()})
    store = ProfileStore(tmp_path)
    store.save(p)
    loaded = store.load("s")
    again = scene.SceneModel.from_dict(loaded.scene)
    assert loaded.scene["enabled"] is True and len(again.anchors) == len(model.anchors)
    assert scene.score(again, make_hud(2, POINTS)) == pytest.approx(scene.score(model, make_hud(2, POINTS)), abs=0.01)


@pytest.mark.parametrize("bad", [None, {}, {"anchors": [{"x": 1}]}, {"anchors": [{"x": 0.1, "y": 0.1, "sig": "!!"}]}, 5])
def test_a_damaged_model_is_ignored_not_a_crash(bad):
    assert scene.SceneModel.from_dict(bad) is None


def test_profiles_without_a_scene_still_load_and_save_nothing_extra(tmp_path):
    store = ProfileStore(tmp_path)
    store.save(Profile("plain", bindings=[Binding("R", 0.5, 0.5, "tap")]))
    assert store.load("plain").scene is None
    assert "scene" not in store.path("plain").read_text(encoding="utf-8")


# ===================================================================== steady state
def test_tracker_needs_agreement_and_starts_unknown():
    t = scene.SceneTracker(confirm=3)
    assert t.state == scene.UNKNOWN
    t.update(0.9)
    t.update(0.9)
    assert t.state == scene.UNKNOWN                                    # two samples are not enough
    assert t.update(0.9) == scene.GAME


def test_one_odd_frame_never_flips_the_mode():
    t = scene.SceneTracker(confirm=3)
    for _ in range(3):
        t.update(0.9)
    t.update(0.0)
    t.update(0.9)
    t.update(0.0)
    assert t.state == scene.GAME


def test_menu_after_a_steady_miss_and_back_again():
    t = scene.SceneTracker(confirm=3)
    for _ in range(3):
        t.update(1.0)
    for _ in range(3):
        t.update(0.0)
    assert t.state == scene.MENU
    for _ in range(3):
        t.update(0.8)
    assert t.state == scene.GAME


def test_in_between_scores_keep_the_current_state():
    t = scene.SceneTracker(enter=0.5, leave=0.3, confirm=2)
    for _ in range(2):
        t.update(0.9)
    for _ in range(10):
        t.update(0.4)                                                  # e.g. swimming: some buttons changed
    assert t.state == scene.GAME
    t.reset()
    assert t.state == scene.UNKNOWN


# ===================================================================== one key, several spots
def test_extra_spots_roundtrip_and_are_limited(tmp_path):
    b = Binding("F", 0.5, 0.5, "tap", also=[(0.1, 0.2), (0.3, 0.4)] + [(0.5, 0.5)] * 6)
    assert len(b.also) == MAX_ALSO
    store = ProfileStore(tmp_path)
    store.save(Profile("a", bindings=[b]))
    assert store.load("a").bindings[0].also == b.also
    assert "also" not in Binding("G", 0.5, 0.5, "tap").to_dict()


def test_a_key_touches_all_its_spots_together_and_lets_go_together():
    r = Rig(bindings=[Binding("LMB", 0.8, 0.7, "hold", also=[(0.1, 0.4), (0.2, 0.5)])])
    r.press("LMB")
    downs = [t for t in r.touches() if t[0] == D]
    assert len(downs) == 3 and len({t[1] for t in downs}) == 3         # three fingers
    assert r.engine.injector.active_count == 3
    r.release("LMB")
    assert [t[0] for t in r.touches()].count(U) == 3 and r.engine.injector.active_count == 0


def test_a_tapped_key_with_extra_spots_taps_all_of_them():
    r = Rig(bindings=[Binding("R", 0.7, 0.8, "tap", also=[(0.3, 0.3)])])
    r.press("R", 200)
    kinds = r.kinds()
    assert kinds.count(D) == 2 and kinds.count(U) == 2 and r.engine.injector.active_count == 0


def test_extra_spots_follow_a_toggle_and_the_wheel():
    r = Rig(bindings=[Binding("T", 0.5, 0.5, "toggle", also=[(0.2, 0.2)]), Binding("WheelUp", 0.9, 0.9, "hold", also=[(0.8, 0.8)])])
    r.press("T")
    r.release("T")
    assert r.engine.injector.active_count == 2                         # toggled on: both fingers stay down
    r.press("T")
    r.release("T")
    assert r.engine.injector.active_count == 0
    r.engine.wheel_binding(1)                                          # wheel makes a quick tap of both spots
    r.advance(300)
    assert r.kinds().count(D) == 4 and r.engine.injector.active_count == 0


def test_extra_spots_are_ignored_by_modes_that_cannot_use_them():
    r = Rig(bindings=[Binding("Q", 0.2, 0.5, "swipe", x2=0.6, y2=0.5, also=[(0.9, 0.9)])])
    r.press("Q", 400)
    assert r.kinds().count(D) == 1


def test_releasing_everything_lifts_the_extra_fingers_too():
    r = Rig(bindings=[Binding("LMB", 0.8, 0.7, "hold", also=[(0.1, 0.4)])])
    r.press("LMB")
    r.engine.release_all()
    assert r.engine.injector.active_count == 0


# ===================================================================== editing extra spots
TW, TH = 1920.0, 864.0


def test_extra_spots_can_be_found_dragged_and_deleted():
    p = Profile("p", bindings=[Binding("F", 0.2, 0.5, "tap", also=[(0.6, 0.5), (0.7, 0.3)])])
    assert le.hit_test(p, 0.6, 0.5, TW, TH) == le.Hit("tap", 0, "also0")
    assert le.hit_test(p, 0.7, 0.3, TW, TH) == le.Hit("tap", 0, "also1")
    state = le.begin_drag(p, le.Hit("tap", 0, "also0"), 0.6, 0.5)
    le.update_drag(p, state, 0.65, 0.55, TW, TH)
    assert p.bindings[0].also[0] == pytest.approx((0.65, 0.55))
    assert (p.bindings[0].x, p.bindings[0].y) == (0.2, 0.5)
    le.delete(p, le.Hit("tap", 0, "also0"))
    assert len(p.bindings) == 1 and p.bindings[0].also == [pytest.approx((0.7, 0.3))]


def test_moving_the_main_marker_carries_the_extra_spots():
    p = Profile("p", bindings=[Binding("F", 0.2, 0.5, "tap", also=[(0.6, 0.5)])])
    state = le.begin_drag(p, le.Hit("tap", 0), 0.2, 0.5)
    le.update_drag(p, state, 0.3, 0.6, TW, TH)
    assert p.bindings[0].also[0] == pytest.approx((0.7, 0.6))


def test_add_also_respects_mode_and_limit():
    p = Profile("p", bindings=[Binding("F", 0.2, 0.5, "tap"), Binding("Q", 0.3, 0.5, "swipe")])
    assert le.add_also(p, 0, (0.5, 0.5)) and p.bindings[0].also == [(0.5, 0.5)]
    assert not le.add_also(p, 1, (0.5, 0.5))                           # a swipe cannot
    assert not le.add_also(p, 9, (0.5, 0.5))
    for _ in range(10):
        le.add_also(p, 0, (0.4, 0.4))
    assert len(p.bindings[0].also) == MAX_ALSO


# ===================================================================== hold-to-free key
def test_suspend_key_may_be_a_modifier_but_other_hotkeys_may_not():
    current = dict(hotkeys.DEFAULT_HOTKEYS)
    assert hotkeys.validate(current, "suspend", "Alt", set()) is None
    assert hotkeys.validate(current, "suspend", "F7", set()) is None
    assert "cannot be a hotkey" in hotkeys.validate(current, "capture", "Alt", set())
    assert "cannot be a hotkey" in hotkeys.validate(current, "suspend", "W", set())
    assert "used by a control" in hotkeys.validate(current, "suspend", "Ctrl", {"Ctrl"})


def test_defaults_are_distinct_and_valid():
    values = list(hotkeys.DEFAULT_HOTKEYS.values())
    assert len(values) == len(set(values))
    for action, key in hotkeys.DEFAULT_HOTKEYS.items():
        assert hotkeys.validate({}, action, key, set()) is None
