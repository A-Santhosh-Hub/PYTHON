import pytest

from app.input.engine import LOOK_FLUSH_MS, LOOK_IDLE_MS, InputEngine
from app.input.touch import TouchInjector
from app.mapping.profile import Binding, Look, Profile, ProfileError, ProfileStore, Stick
from app.stream import protocol
from test_mapping import FakeControl


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class Rig:
    """Engine with a manual scheduler: nothing runs until `advance(ms)` is called."""

    def __init__(self, look=None, size=(2400, 1080), profile=None):
        self.control = FakeControl()
        self.clock = Clock()
        self.timers = []                                  # (due_ms, fn)
        self.now_ms = 0.0
        self.size = size
        injector = TouchInjector(lambda: self.control, lambda: self.size)
        self.engine = InputEngine(injector, lambda ms, fn: self.timers.append((self.now_ms + ms, fn)),
                                  clock=self.clock)
        self.profile = profile or Profile("l")
        if look is not None:
            self.profile.looks.append(look)
        self.engine.set_profile(self.profile)
        self.engine.set_mapping_active(True)
        self.engine.set_look_captured(True)

    def advance(self, ms):
        end = self.now_ms + ms
        while True:
            due = sorted((t for t in self.timers if t[0] <= end), key=lambda t: t[0])
            if not due:
                break
            t, fn = due[0]
            self.timers.remove(due[0])
            self.now_ms = t
            self.clock.t = 100.0 + t / 1000
            fn()
        self.now_ms = end
        self.clock.t = 100.0 + end / 1000

    def mouse(self, dx, dy, ms=LOOK_FLUSH_MS):
        self.engine.look_delta(dx, dy)
        self.advance(ms)

    def touches(self):
        return self.control.touches()

    def moves(self):
        return [t for t in self.touches() if t[0] == protocol.TOUCH_MOVE]


# Zone x 0.5..0.9, y 0.2..0.8 on a 2400x1080 screen: x 1200..2160, y 216..864, centre (1680, 540).
ZONE = dict(x0=0.5, y0=0.2, x1=0.9, y1=0.8)


def test_first_movement_puts_finger_in_zone_centre_then_moves():
    r = Rig(Look(**ZONE))
    r.mouse(10, -5)
    down, move = r.touches()
    assert down[0] == protocol.TOUCH_DOWN and (down[2], down[3]) == (1680, 540)
    assert move[0] == protocol.TOUCH_MOVE and (move[2], move[3]) == (1690, 535)


def test_sensitivity_scales_each_axis():
    r = Rig(Look(**ZONE, sens_x=2.0, sens_y=0.5))
    r.mouse(10, 10)
    assert r.moves()[-1][2:4] == (1680 + 20, 540 + 5)


def test_invert_y_flips_vertical_only():
    r = Rig(Look(**ZONE, invert_y=True))
    r.mouse(10, 10)
    assert r.moves()[-1][2:4] == (1690, 530)


def test_movements_accumulate_while_finger_is_down():
    r = Rig(Look(**ZONE))
    r.mouse(10, 0)
    r.mouse(10, 0)
    r.mouse(10, 0)
    assert [m[2] for m in r.moves()] == [1690, 1700, 1710]


def test_events_inside_one_batch_are_merged():
    r = Rig(Look(**ZONE))
    for _ in range(8):
        r.engine.look_delta(1, 0)                        # eight tiny events within 4 ms ...
    r.advance(LOOK_FLUSH_MS)
    assert len(r.moves()) == 1 and r.moves()[0][2] == 1688   # ... become one finger move


def test_edge_reached_lifts_and_recentres_so_turning_never_stops():
    r = Rig(Look(**ZONE))
    for _ in range(40):                                   # 40 x 100 counts = 4000 px, far wider than the zone
        r.mouse(100, 0)
    kinds = [t[0] for t in r.touches()]
    assert kinds.count(protocol.TOUCH_DOWN) >= 4 and kinds.count(protocol.TOUCH_UP) >= 3
    assert r.engine._looks[0].resets >= 3
    # the finger never leaves the zone, and every re-landing is at the centre
    for t in r.touches():
        assert 1200 <= t[2] <= 2160
        if t[0] == protocol.TOUCH_DOWN:
            assert (t[2], t[3]) == (1680, 540)
    # no movement is lost: each 100-count step moved the finger 100 px (or restarted from the centre)
    steps = [b[2] - a[2] for a, b in zip(r.moves(), r.moves()[1:]) if b[2] > a[2]]
    assert steps and all(step == 100 for step in steps)


def test_finger_lifts_when_mouse_stops():
    r = Rig(Look(**ZONE))
    r.mouse(10, 0)
    assert r.engine.injector.active_count == 1
    r.advance(LOOK_IDLE_MS - 10)
    assert r.engine.injector.active_count == 1
    r.advance(20)
    assert r.engine.injector.active_count == 0 and r.touches()[-1][0] == protocol.TOUCH_UP


def test_new_movement_after_idle_starts_from_centre_again():
    r = Rig(Look(**ZONE))
    r.mouse(50, 0)
    r.advance(LOOK_IDLE_MS + 20)
    r.mouse(10, 0)
    downs = [t for t in r.touches() if t[0] == protocol.TOUCH_DOWN]
    assert len(downs) == 2 and all((d[2], d[3]) == (1680, 540) for d in downs)
    assert r.moves()[-1][2] == 1690


def test_continuous_movement_keeps_idle_timer_from_firing():
    r = Rig(Look(**ZONE))
    for _ in range(20):
        r.mouse(1, 0, ms=20)
    assert r.engine.injector.active_count == 1


def test_acceleration_amplifies_fast_flicks_only():
    slow, fast = Rig(Look(**ZONE, accel=1.0)), Rig(Look(**ZONE, accel=1.0))
    slow.mouse(2, 0)                                       # 2 counts in 4 ms = 0.5 counts/ms
    fast.mouse(40, 0)                                      # 40 counts in 4 ms = 10 counts/ms
    slow_px = slow.moves()[-1][2] - 1680
    fast_px = fast.moves()[-1][2] - 1680
    assert slow_px >= 2 and slow_px / 2 < 1.4
    assert fast_px / 40 > 3.5                              # capped at 1 + 3 = 4x


def test_no_acceleration_by_default_is_linear():
    r = Rig(Look(**ZONE))
    r.mouse(40, 0)
    assert r.moves()[-1][2] - 1680 == 40


def test_ignored_unless_mapping_active_and_captured():
    r = Rig(Look(**ZONE))
    r.engine.set_look_captured(False)
    assert r.engine.look_delta(5, 5) is False
    r.advance(10)
    assert r.touches() == []
    r.engine.set_look_captured(True)
    r.engine.set_mapping_active(False)
    assert r.engine.look_captured is False                 # turning mapping off drops capture


def test_cannot_capture_without_a_look_zone():
    r = Rig(look=None)
    r.engine.set_look_captured(True)
    assert r.engine.look_captured is False and r.engine.has_look() is False


def test_releasing_capture_lifts_the_finger():
    r = Rig(Look(**ZONE))
    r.mouse(10, 0)
    r.engine.set_look_captured(False)
    assert r.engine.injector.active_count == 0
    r.advance(200)                                         # stale timers do nothing
    assert r.touches()[-1][0] == protocol.TOUCH_UP and len(r.touches()) == 3


def test_look_runs_together_with_stick_and_tap_keys():
    profile = Profile("all", bindings=[Binding("Space", 0.9, 0.9)])
    profile.set_stick(Stick(0.12, 0.8, ramp_ms=0))
    r = Rig(Look(**ZONE), profile=profile)
    r.engine.key_event("W", True)
    r.mouse(20, 0)
    r.engine.key_event("Space", True)
    downs = [t for t in r.touches() if t[0] == protocol.TOUCH_DOWN]
    assert len(downs) == 3 and len({d[1] for d in downs}) == 3     # three different fingers at once


def test_mouse_buttons_do_not_touch_at_the_hidden_cursor_while_aiming():
    r = Rig(Look(**ZONE))
    assert r.engine.mouse_button("LMB", True, (0.3, 0.3)) is False
    assert r.touches() == []


def test_mapped_buttons_still_work_while_aiming():
    profile = Profile("f", bindings=[Binding("LMB", 0.85, 0.7)])
    r = Rig(Look(**ZONE), profile=profile)
    assert r.engine.mouse_button("LMB", True, None) is True
    assert r.touches()[-1][2:4] == (2040, 756)


def test_rotation_drops_the_look_finger_cleanly():
    r = Rig(Look(**ZONE))
    r.mouse(10, 0)
    r.size = (1080, 2400)
    r.mouse(10, 0)
    last = r.touches()[-1]
    assert last[4:] == (1080, 2400) and last[0] in (protocol.TOUCH_DOWN, protocol.TOUCH_MOVE)


# ---------------------------------------------------------------- profile data
def test_look_validation_and_normalisation():
    look = Look(0.9, 0.8, 0.5, 0.2, sens_x=99, sens_y=0, accel=5)
    assert (look.x0, look.x1, look.y0, look.y1) == (0.5, 0.9, 0.2, 0.8)
    assert (look.sens_x, look.sens_y, look.accel) == (20.0, 0.05, 1.0)
    with pytest.raises(ProfileError):
        Look(0.5, 0.5, 0.52, 0.9)                          # too narrow


def test_look_roundtrip_and_old_profiles(tmp_path):
    store = ProfileStore(tmp_path)
    p = Profile("g", "landscape", [Binding("R", 0.7, 0.8)])
    p.looks.append(Look(0.42, 0.22, 0.74, 0.56, sens_x=1.4, sens_y=1.1, accel=0.3, invert_y=True))
    store.save(p)
    look = store.load("g").looks[0]
    assert (look.x0, look.y1, look.sens_x, look.sens_y, look.accel, look.invert_y) == (0.42, 0.56, 1.4, 1.1, 0.3, True)
    assert Profile.from_dict({"name": "old", "bindings": []}).looks == []
