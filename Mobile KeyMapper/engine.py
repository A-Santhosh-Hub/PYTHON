"""Decides what a key / mouse event does: mapped touches in many modes, direct finger, scroll, back/home.

Modes (see mapping.profile.MODES): hold, tap, toggle, repeat, double, swipe, drag, pinch-out, pinch-in, sequence.
Combination keys ("Shift+W") are looked up first, so a held modifier can give a key a different meaning.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Callable

from ..mapping.profile import ALSO_MODES, MODIFIERS, Binding, Look, Profile, Stick
from ..stream import protocol
from .touch import TouchInjector

log = logging.getLogger(__name__)

TAP_DURATION_MS = 40
DOUBLE_TAP_GAP_MS = 60                  # pause between the two taps of a double tap
MOTION_TICK_MS = 8                      # swipe / drag / pinch move the finger this often
STICK_TICK_MS = 8                       # how often a ramping stick moves its finger
LOOK_FLUSH_MS = 4                       # mouse movement is batched and sent at most every 4 ms (250 Hz)
LOOK_IDLE_MS = 120                      # the look finger lifts after this long without mouse movement
LOOK_EDGE_MARGIN = 0.12                 # re-centre when the finger gets within 12% of the zone edge
LOOK_ACCEL_REF = 2.0                    # mouse speed (counts per ms) at which acceleration starts to bite
LOOK_ACCEL_MAX = 3.0                    # ... capped at this many reference speeds
PINCH_NEAR = 0.4                        # the close position of a pinch, as a fraction of the far position
DIRECT_OWNER = ("mouse", "direct")

# modes that follow the key (they last until it is released)
FOLLOWS_KEY = ("hold", "repeat", "drag")
# when a wheel notch triggers a mode that normally follows the key, it runs as a one-shot instead
WHEEL_EQUIVALENT = {"hold": "tap", "repeat": "tap", "drag": "swipe"}


@dataclass
class _LookRuntime:
    look: Look
    owner: tuple
    down: bool = False
    pos: tuple = (0.0, 0.0)                         # finger position in pixels
    pending: tuple = (0.0, 0.0)                     # mouse counts not yet sent
    flush_scheduled: bool = False
    last_flush: float = 0.0
    generation: int = 0                             # invalidates idle-lift timers already scheduled
    resets: int = 0                                 # how many times the finger was re-centred (diagnostics)


@dataclass
class _StickRuntime:
    stick: Stick
    owner: tuple
    held: set = field(default_factory=set)          # directions currently held: "up", "left", ...
    mods: set = field(default_factory=set)          # "sprint" / "walk" while their key is held
    autorun: bool = False                           # walking forward by itself until cancelled
    offset: tuple = (0.0, 0.0)                      # finger offset from the centre, in pixels
    down: bool = False
    generation: int = 0                             # invalidates ramp ticks that are already scheduled


@dataclass
class _Action:
    binding: Binding
    trigger: str                                    # the input name that started it ("R", "Shift+W", "WheelUp")
    mode: str                                       # effective mode
    owners: list                                    # finger owners used by this action
    required: set                                   # physical keys that must stay down (hold-like modes)
    epoch: int
    active: bool = True
    toggled: bool = False


class InputEngine:
    """Qt-free. `schedule(delay_ms, fn)` runs fn later (QTimer.singleShot in the app)."""

    def __init__(self, injector: TouchInjector, schedule: Callable[[int, Callable[[], None]], None],
                 clock: Callable[[], float] = time.perf_counter) -> None:
        self.injector = injector
        self._schedule = schedule
        self._clock = clock
        self._looks: list[_LookRuntime] = []
        self.look_captured = False           # the mouse is captured and drives the camera
        self._lookup: dict[str, Binding] = {}                           # bindings without modifiers
        self._combos: dict[tuple[frozenset, str], Binding] = {}         # bindings like Shift+W
        self._sticks: list[_StickRuntime] = []
        self._stick_keys: dict[str, tuple[_StickRuntime, str]] = {}
        self._stick_extra: dict[str, tuple[_StickRuntime, str]] = {}    # sprint / walk / autorun keys
        self._profile: Profile | None = None
        self.mapping_active = False          # keyboard/mouse bindings are applied
        self.direct_touch = True             # the mouse acts as a finger on the phone screen
        self.on_press_changed: Callable[[set[str]], None] | None = None
        self._pressed: set[str] = set()
        self._mods: set[str] = set()         # modifier keys physically held (Ctrl / Shift / Alt)
        self._actions: dict[str, _Action] = {}
        self._epoch = 0
        self.scope_active = False            # the scope / aim button is on: look sensitivity uses ads_scale

    # -- configuration ---------------------------------------------------------------------
    def set_profile(self, profile: Profile | None) -> None:
        self._profile = profile
        self.refresh_profile()

    def refresh_profile(self) -> None:
        """Call after the current profile's bindings were edited."""
        self.release_all()
        profile = self._profile
        self._lookup, self._combos = {}, {}
        for binding in (profile.bindings if profile else []):
            mods, base = binding.combo
            if mods:
                self._combos[(mods, base)] = binding
            else:
                self._lookup[base] = binding
        self._sticks = [_StickRuntime(s, ("stick", i)) for i, s in enumerate(profile.sticks if profile else [])]
        self._looks = [_LookRuntime(lk, ("look", i)) for i, lk in enumerate(profile.looks if profile else [])]
        self._stick_keys = {key: (rt, direction) for rt in self._sticks for direction, key in rt.stick.keys.items()}
        self._stick_extra = {key: (rt, kind) for rt in self._sticks for kind, key in rt.stick.extra_keys().items()}

    def set_mapping_active(self, active: bool) -> None:
        if not active:
            self.release_all()
            self.look_captured = False
        self.mapping_active = active

    def has_look(self) -> bool:
        return bool(self._looks)

    def set_look_captured(self, captured: bool) -> None:
        """Turn mouse-look on or off. Only has an effect while key mapping is active and a look zone exists."""
        captured = bool(captured and self.mapping_active and self._looks)
        if not captured:
            for runtime in self._looks:
                self._look_lift(runtime)
        self.look_captured = captured

    # -- binding lookup -------------------------------------------------------------------
    def _resolve(self, base: str) -> Binding | None:
        """The binding for `base` given the modifiers held right now: a combination wins over the plain key."""
        if self._mods:
            combo = self._combos.get((frozenset(self._mods), base))
            if combo is not None:
                return combo
        return self._lookup.get(base)

    def _resolve_combo_only(self, base: str) -> Binding | None:
        if not self._mods:
            return None
        return self._combos.get((frozenset(self._mods), base))

    def _bases(self) -> set[str]:
        return set(self._lookup) | {base for _, base in self._combos}

    # -- events ----------------------------------------------------------------------------
    def key_event(self, name: str, pressed: bool) -> bool:
        """Returns True if the event was handled by a binding or the stick."""
        if not self.mapping_active:
            return False
        if name in MODIFIERS:
            (self._mods.add if pressed else self._mods.discard)(name)
        handled = False

        stick_key = self._stick_keys.get(name)
        if stick_key is not None:
            runtime, direction = stick_key
            if pressed and direction == "down" and runtime.autorun:
                runtime.autorun = False                       # walking backwards cancels auto-run
            (runtime.held.add if pressed else runtime.held.discard)(direction)
            self._set_pressed(name, pressed)
            self._stick_update(runtime)
            handled = True
        extra = self._stick_extra.get(name)
        if extra is not None:
            runtime, kind = extra
            if kind == "autorun":
                if pressed:
                    runtime.autorun = not runtime.autorun
            else:
                (runtime.mods.add if pressed else runtime.mods.discard)(kind)
            self._set_pressed(name, pressed)
            self._stick_update(runtime)
            handled = True

        if not pressed:
            for action in [a for a in self._actions.values() if a.active and name in a.required]:
                self._finish(action)
                handled = True
            return handled

        binding = self._resolve_combo_only(name) if handled else self._resolve(name)
        if binding is not None:
            self._start(binding, binding.input, self._required_for(binding, name), impulse=False)
            handled = True
        return handled

    def _required_for(self, binding: Binding, base: str) -> set[str]:
        mods, _ = binding.combo
        return {base} | set(mods)

    def mouse_button(self, name: str, pressed: bool, pos: tuple[float, float] | None) -> bool:
        """`pos` is the normalized position on the phone screen, or None when outside the picture."""
        if self.mapping_active and (self._resolve(name) is not None or
                                    any(name in a.required for a in self._actions.values() if a.active)):
            return self.key_event(name, pressed)
        if not self.direct_touch or self.look_captured:
            return False                         # while aiming, the cursor is hidden: no click-to-touch
        if name == "LMB":
            if pressed:
                return pos is not None and self.injector.down(DIRECT_OWNER, *pos)
            return self.injector.up(DIRECT_OWNER)
        if not self.mapping_active:             # right/middle click act as Back/Home like scrcpy
            if name == "RMB":
                return self.injector.back_or_screen_on(pressed)
            if name == "MMB":
                return self.injector.key(protocol.KEYCODE_HOME, pressed)
        return False

    def mouse_move(self, pos: tuple[float, float]) -> None:
        if self.injector.is_down(DIRECT_OWNER):
            self.injector.move(DIRECT_OWNER, *pos)

    def has_wheel_binding(self) -> bool:
        return self.mapping_active and bool(self._bases() & {"WheelUp", "WheelDown"})

    def wheel_binding(self, vertical: float) -> bool:
        """A mouse-wheel notch (+ = scrolled up) triggers the binding for WheelUp / WheelDown.
        Returns True if a binding handled it."""
        if not self.mapping_active or vertical == 0:
            return False
        name = "WheelUp" if vertical > 0 else "WheelDown"
        binding = self._resolve(name)
        if binding is None:
            return False
        self._start(binding, binding.input, set(), impulse=True)
        return True

    def wheel(self, pos: tuple[float, float], hscroll: float, vscroll: float) -> bool:
        return self.direct_touch and self.injector.scroll(*pos, hscroll, vscroll)

    def release_all(self) -> None:
        self._epoch += 1                          # every timer scheduled before now becomes a no-op
        self._actions.clear()
        self._mods.clear()
        self.scope_active = False
        for runtime in self._looks:
            runtime.generation += 1
            runtime.down = False
            runtime.pending = (0.0, 0.0)
        for runtime in self._sticks:
            runtime.held.clear()
            runtime.mods.clear()
            runtime.autorun = False
            runtime.down = False
            runtime.offset = (0.0, 0.0)
            runtime.generation += 1
        self.injector.release_all()
        if self._pressed:
            self._pressed.clear()
            self._notify()

    # -- actions -----------------------------------------------------------------------------
    def _alive(self, action: _Action) -> bool:
        return action.active and action.epoch == self._epoch

    def _after(self, delay_ms: int, action: _Action, fn: Callable[[], None]) -> None:
        self._schedule(delay_ms, lambda: fn() if self._alive(action) else None)

    def _start(self, binding: Binding, trigger: str, required: set[str], impulse: bool) -> None:
        mode = WHEEL_EQUIVALENT.get(binding.mode, binding.mode) if impulse else binding.mode
        existing = self._actions.get(trigger)
        if mode == "toggle" and existing is not None and existing.active and existing.toggled:
            self._finish(existing)                            # the second press lets go
            return
        if existing is not None and existing.active:
            return                                            # a key repeat / duplicate press while running
        owners: list = [("input", trigger)]
        if mode in ALSO_MODES:
            owners += [("input", trigger, "also", i) for i in range(len(binding.also))]
        if mode in ("pinch-out", "pinch-in"):
            owners = [("input", trigger, "a"), ("input", trigger, "b")]
        action = _Action(binding, trigger, mode, owners,
                         required if mode in FOLLOWS_KEY and not impulse else set(), self._epoch)
        self._actions[trigger] = action
        getattr(self, "_do_" + mode.replace("-", "_"))(action)

    def _finish(self, action: _Action) -> None:
        if not action.active:
            return
        action.active = False
        for owner in action.owners:
            self.injector.up(owner)
        self._set_pressed(action.trigger, False)
        if action.binding.scope and action.mode in FOLLOWS_KEY + ("toggle",):
            self.scope_active = False
        if self._actions.get(action.trigger) is action:
            del self._actions[action.trigger]

    def _touch_down(self, action: _Action, x: float | None = None, y: float | None = None, owner=None) -> bool:
        b = action.binding
        if not self.injector.down(owner or action.owners[0], b.x if x is None else x, b.y if y is None else y):
            self._abort(action)
            return False
        if owner is None and x is None and action.mode in ALSO_MODES:      # the key's extra spots, with their own fingers
            for extra_owner, (ex, ey) in zip(action.owners[1:], b.also):
                self.injector.down(extra_owner, ex, ey)
        return True

    def _abort(self, action: _Action) -> None:
        action.active = False
        if self._actions.get(action.trigger) is action:
            del self._actions[action.trigger]

    def _scope_flip(self, action: _Action) -> None:
        if action.binding.scope:
            self.scope_active = not self.scope_active

    # hold / tap / toggle / double / repeat -------------------------------------------------------
    def _do_hold(self, action: _Action) -> None:
        if self._touch_down(action):
            self._set_pressed(action.trigger, True)
            if action.binding.scope:
                self.scope_active = True

    def _do_tap(self, action: _Action) -> None:
        if self._touch_down(action):
            self._set_pressed(action.trigger, True)
            self._scope_flip(action)
            self._after(TAP_DURATION_MS, action, lambda: self._finish_tap(action))

    def _finish_tap(self, action: _Action) -> None:
        for owner in action.owners:
            self.injector.up(owner)
        action.active = False
        self._set_pressed(action.trigger, False)
        if self._actions.get(action.trigger) is action:
            del self._actions[action.trigger]

    def _do_toggle(self, action: _Action) -> None:
        if self._touch_down(action):
            action.toggled = True
            self._set_pressed(action.trigger, True)
            if action.binding.scope:
                self.scope_active = True

    def _do_double(self, action: _Action) -> None:
        if not self._touch_down(action):
            return
        self._set_pressed(action.trigger, True)
        self._scope_flip(action)
        owner = action.owners[0]
        self._after(TAP_DURATION_MS, action, lambda: self.injector.up(owner))
        self._after(TAP_DURATION_MS + DOUBLE_TAP_GAP_MS, action, lambda: self._touch_down(action))
        self._after(2 * TAP_DURATION_MS + DOUBLE_TAP_GAP_MS, action, lambda: self._finish_tap(action))

    def _do_repeat(self, action: _Action) -> None:
        self._set_pressed(action.trigger, True)
        if action.binding.scope:
            self.scope_active = True
        self._repeat_step(action)

    def _repeat_step(self, action: _Action) -> None:
        if not self._alive(action):
            return
        period = max(int(1000 / action.binding.rate_hz), 34)
        hold = min(TAP_DURATION_MS, period // 2)
        if self._touch_down(action):
            self._after(hold, action, lambda: self.injector.up(action.owners[0]))
            self._after(period, action, lambda: self._repeat_step(action))

    # swipe / drag / pinch / sequence ------------------------------------------------------------
    def _motion(self, action: _Action, steps: int, apply: Callable[[float], None], done: Callable[[], None]) -> None:
        def step(i: int) -> None:
            if not self._alive(action):
                return
            apply(i / steps)
            if i < steps:
                self._schedule(MOTION_TICK_MS, lambda: step(i + 1))
            else:
                done()
        self._schedule(MOTION_TICK_MS, lambda: step(1))

    def _do_swipe(self, action: _Action, hold_at_end: bool = False) -> None:
        b = action.binding
        if not self._touch_down(action):
            return
        self._set_pressed(action.trigger, True)
        self._scope_flip(action)
        owner = action.owners[0]
        steps = max(2, b.duration_ms // MOTION_TICK_MS)
        self._motion(action, steps,
                     lambda t: self.injector.move(owner, b.x + (b.x2 - b.x) * t, b.y + (b.y2 - b.y) * t),
                     (lambda: None) if hold_at_end else (lambda: self._finish(action)))

    def _do_drag(self, action: _Action) -> None:
        self._do_swipe(action, hold_at_end=True)

    def _do_pinch_out(self, action: _Action) -> None:
        self._pinch(action, PINCH_NEAR, 1.0)

    def _do_pinch_in(self, action: _Action) -> None:
        self._pinch(action, 1.0, PINCH_NEAR)

    def _pinch(self, action: _Action, start: float, end: float) -> None:
        b = action.binding
        w, h = self.injector.size()
        if w <= 0 or h <= 0:
            self._abort(action)
            return
        far = b.span * min(w, h) / w                               # horizontal distance of one finger, normalized

        def place(factor: float, down: bool) -> bool:
            ok = True
            for owner, sign in ((action.owners[0], -1), (action.owners[1], 1)):
                x = b.x + sign * far * factor
                ok = (self.injector.down(owner, x, b.y) if down else self.injector.move(owner, x, b.y)) and ok
            return ok

        if not place(start, True):
            self._abort(action)
            for owner in action.owners:
                self.injector.up(owner)
            return
        self._set_pressed(action.trigger, True)
        steps = max(2, b.duration_ms // MOTION_TICK_MS)
        self._motion(action, steps, lambda t: place(start + (end - start) * t, False), lambda: self._finish(action))

    def _do_sequence(self, action: _Action) -> None:
        b = action.binding
        self._set_pressed(action.trigger, True)
        t = 0
        last = len(b.steps) - 1
        for index, (x, y, delay) in enumerate(b.steps):
            t += delay if index == 0 else max(delay, TAP_DURATION_MS + 20)       # the previous tap must have ended
            self._after(t, action, lambda x=x, y=y: self._touch_down(action, x, y))
            self._after(t + TAP_DURATION_MS, action,
                        (lambda: self._finish(action)) if index == last else (lambda: self.injector.up(action.owners[0])))
        if not b.steps:
            self._finish(action)

    # -- movement stick --------------------------------------------------------------------
    def _effective_held(self, runtime: _StickRuntime) -> set:
        return runtime.held | ({"up"} if runtime.autorun else set())

    def _stick_target(self, runtime: _StickRuntime) -> tuple[float, float]:
        """Finger offset (pixels) the held keys ask for. Opposite keys cancel; diagonals keep full radius.
        The sprint key pushes further (sprint_scale), the walk key less far (walk_scale)."""
        held = self._effective_held(runtime)
        vx = ("right" in held) - ("left" in held)
        vy = ("down" in held) - ("up" in held)
        length = math.hypot(vx, vy)
        if length == 0:
            return (0.0, 0.0)
        w, h = self.injector.size()
        radius = runtime.stick.radius * min(w, h)
        if "sprint" in runtime.mods:
            radius *= runtime.stick.sprint_scale
        elif "walk" in runtime.mods:
            radius *= runtime.stick.walk_scale
        return (vx / length * radius, vy / length * radius)

    def _stick_update(self, runtime: _StickRuntime) -> None:
        stick = runtime.stick
        if runtime.down and not self.injector.is_down(runtime.owner):
            runtime.down = False                      # the injector dropped it (e.g. the screen rotated)
        if not self._effective_held(runtime):         # all keys up: the finger lifts at once
            runtime.generation += 1
            if runtime.down:
                self.injector.up(runtime.owner)
                runtime.down = False
            runtime.offset = (0.0, 0.0)
            return
        if not runtime.down:
            if not self.injector.down(runtime.owner, stick.x, stick.y):
                return
            runtime.down = True
            runtime.offset = (0.0, 0.0)
        runtime.generation += 1
        self._stick_step(runtime, runtime.generation)

    def _stick_step(self, runtime: _StickRuntime, generation: int) -> None:
        if generation != runtime.generation or not runtime.down:
            return
        tx, ty = self._stick_target(runtime)
        ox, oy = runtime.offset
        w, h = self.injector.size()
        reach = max(runtime.stick.radius * min(w, h), math.hypot(tx, ty))      # sprint pushes beyond the ring
        ramp = runtime.stick.ramp_ms
        step = reach if ramp <= 0 else reach * STICK_TICK_MS / ramp
        dx, dy = tx - ox, ty - oy
        distance = math.hypot(dx, dy)
        if distance <= step:
            ox, oy = tx, ty
        else:
            ox, oy = ox + dx / distance * step, oy + dy / distance * step
        runtime.offset = (ox, oy)
        self.injector.move(runtime.owner, runtime.stick.x + ox / w, runtime.stick.y + oy / h)
        if (ox, oy) != (tx, ty):
            self._schedule(STICK_TICK_MS, lambda: self._stick_step(runtime, generation))

    # -- mouse look ------------------------------------------------------------------------
    def look_delta(self, dx: float, dy: float) -> bool:
        """Raw relative mouse movement in counts. Batched, then sent as finger moves."""
        if not (self.mapping_active and self.look_captured and self._looks):
            return False
        runtime = self._looks[0]
        px, py = runtime.pending
        runtime.pending = (px + dx, py + dy)
        if not runtime.flush_scheduled:
            runtime.flush_scheduled = True
            runtime.last_flush = self._clock()          # start of this batch: dt = how long the batch took
            self._schedule(LOOK_FLUSH_MS, lambda: self._look_flush(runtime))
        return True

    def _look_zone_px(self, look: Look) -> tuple[float, float, float, float]:
        w, h = self.injector.size()
        return look.x0 * w, look.y0 * h, look.x1 * w, look.y1 * h

    def _look_lift(self, runtime: _LookRuntime) -> None:
        runtime.generation += 1
        runtime.pending = (0.0, 0.0)
        if runtime.down:
            self.injector.up(runtime.owner)
            runtime.down = False

    def _look_flush(self, runtime: _LookRuntime) -> None:
        runtime.flush_scheduled = False
        if not (self.mapping_active and self.look_captured):
            runtime.pending = (0.0, 0.0)
            return
        counts_x, counts_y = runtime.pending
        runtime.pending = (0.0, 0.0)
        now = self._clock()
        dt_ms = max((now - runtime.last_flush) * 1000.0, 1.0)
        runtime.last_flush = now
        if counts_x == 0 and counts_y == 0:
            return
        look = runtime.look
        # acceleration: fast flicks travel further than slow movements
        speed = math.hypot(counts_x, counts_y) / dt_ms
        gain = 1.0 + look.accel * min(speed / LOOK_ACCEL_REF, LOOK_ACCEL_MAX)
        if self.scope_active:
            gain *= look.ads_scale                       # slower, steadier aim while scoped in
        dx = counts_x * look.sens_x * gain
        dy = counts_y * look.sens_y * gain * (-1.0 if look.invert_y else 1.0)

        w, h = self.injector.size()
        if w <= 0 or h <= 0:
            return
        if runtime.down and not self.injector.is_down(runtime.owner):
            runtime.down = False                  # the injector dropped it (screen rotated)
        zx0, zy0, zx1, zy1 = self._look_zone_px(look)
        cx, cy = (zx0 + zx1) / 2, (zy0 + zy1) / 2
        mx, my = (zx1 - zx0) * LOOK_EDGE_MARGIN, (zy1 - zy0) * LOOK_EDGE_MARGIN
        inner = (zx0 + mx, zy0 + my, zx1 - mx, zy1 - my)

        def inside(x: float, y: float) -> bool:
            return inner[0] <= x <= inner[2] and inner[1] <= y <= inner[3]

        if runtime.down and not inside(runtime.pos[0] + dx, runtime.pos[1] + dy):
            # Reached the edge: lift and land again in the centre, then apply this movement from there.
            self.injector.up(runtime.owner)
            runtime.down = False
            runtime.resets += 1
        if not runtime.down:
            if not self.injector.down(runtime.owner, cx / w, cy / h):
                return
            runtime.down = True
            runtime.pos = (cx, cy)
        x = min(max(runtime.pos[0] + dx, inner[0]), inner[2])
        y = min(max(runtime.pos[1] + dy, inner[1]), inner[3])
        runtime.pos = (x, y)
        self.injector.move(runtime.owner, x / w, y / h)

        runtime.generation += 1
        generation = runtime.generation
        self._schedule(LOOK_IDLE_MS, lambda: self._look_idle(runtime, generation))

    def _look_idle(self, runtime: _LookRuntime, generation: int) -> None:
        if generation == runtime.generation and runtime.down:
            self.injector.up(runtime.owner)
            runtime.down = False

    # -- internals -------------------------------------------------------------------------
    def _set_pressed(self, name: str, down: bool) -> None:
        (self._pressed.add if down else self._pressed.discard)(name)
        self._notify()

    def _notify(self) -> None:
        if self.on_press_changed:
            self.on_press_changed(set(self._pressed))
