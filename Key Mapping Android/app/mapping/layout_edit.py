"""Qt-free logic of the drag-and-drop layout editor: what is under the pointer, how dragging changes it, and the
palette of ready-made controls (fire, scope, reload, ... and the WASD stick / mouse-look area)."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .profile import ALSO_MODES, DIRECTIONS, MAX_ALSO, TWO_POINT_MODES, Binding, Look, Profile, Stick

TAP_TOLERANCE_PX = 22
NODE_TOLERANCE_PX = 16
CORNER_TOLERANCE_PX = 14
MIN_STICK_RADIUS = 0.02
MAX_STICK_RADIUS = 0.40
STICK_NODE_ORDER = DIRECTIONS
DEFAULT_STEP_DELAY_MS = 250             # pause between the points of a multi-tap

# name -> (input, mode, label). Wheel inputs fire a quick tap per notch of the mouse wheel.
PRESETS: dict[str, tuple[str, str, str]] = {
    "fire": ("LMB", "hold", "Fire"),
    "scope": ("RMB", "tap", "Scope"),
    "reload": ("R", "tap", "Reload"),
    "crouch": ("C", "tap", "Crouch"),
    "jump": ("Space", "tap", "Jump"),
    "sprint": ("Shift", "tap", "Sprint"),
    "next weapon": ("WheelDown", "tap", "Next weapon"),
    "previous weapon": ("WheelUp", "tap", "Previous weapon"),
}


@dataclass(frozen=True)
class Hit:
    kind: str          # "tap" | "stick" | "look"
    index: int
    part: str = ""     # tap: "" | end | stepN | alsoN ; stick: center | up | left | down | right ; look: move | tl | tr | bl | br


def _dist_px(ax: float, ay: float, bx: float, by: float, tw: float, th: float) -> float:
    return math.hypot((ax - bx) * tw, (ay - by) * th)


def step_index(part: str) -> int | None:
    return int(part[4:]) if part.startswith("step") and part[4:].isdigit() else None


def also_index(part: str) -> int | None:
    return int(part[4:]) if part.startswith("also") and part[4:].isdigit() else None


def hit_test(profile: Profile, nx: float, ny: float, tw: float, th: float) -> Hit | None:
    """What is at normalized position (nx, ny)? `tw`/`th` = size in pixels of the picture, for tolerances."""
    for i in reversed(range(len(profile.bindings))):
        b = profile.bindings[i]
        if b.mode in ALSO_MODES:
            for k in range(len(b.also) - 1, -1, -1):
                ax, ay = b.also[k]
                if _dist_px(nx, ny, ax, ay, tw, th) <= TAP_TOLERANCE_PX:
                    return Hit("tap", i, f"also{k}")
        if b.mode in TWO_POINT_MODES and b.x2 is not None and _dist_px(nx, ny, b.x2, b.y2, tw, th) <= TAP_TOLERANCE_PX:
            return Hit("tap", i, "end")
        if b.mode == "sequence":
            for k in range(len(b.steps) - 1, 0, -1):
                sx, sy, _ = b.steps[k]
                if _dist_px(nx, ny, sx, sy, tw, th) <= TAP_TOLERANCE_PX:
                    return Hit("tap", i, f"step{k}")
        if _dist_px(nx, ny, b.x, b.y, tw, th) <= TAP_TOLERANCE_PX:
            return Hit("tap", i)
    for i, stick in enumerate(profile.sticks):
        r_px = stick.radius * min(tw, th)
        offsets = {"up": (0.0, -r_px / th), "down": (0.0, r_px / th), "left": (-r_px / tw, 0.0), "right": (r_px / tw, 0.0)}
        for part in STICK_NODE_ORDER:
            ox, oy = offsets[part]
            if _dist_px(nx, ny, stick.x + ox, stick.y + oy, tw, th) <= NODE_TOLERANCE_PX:
                return Hit("stick", i, part)
        if _dist_px(nx, ny, stick.x, stick.y, tw, th) <= TAP_TOLERANCE_PX:
            return Hit("stick", i, "center")
    for i, look in enumerate(profile.looks):
        corners = {"tl": (look.x0, look.y0), "tr": (look.x1, look.y0), "bl": (look.x0, look.y1), "br": (look.x1, look.y1)}
        for part, (cx, cy) in corners.items():
            if _dist_px(nx, ny, cx, cy, tw, th) <= CORNER_TOLERANCE_PX:
                return Hit("look", i, part)
    for i, stick in enumerate(profile.sticks):
        if _dist_px(nx, ny, stick.x, stick.y, tw, th) <= stick.radius * min(tw, th):
            return Hit("stick", i, "center")                    # grab the ring's inside to move the whole stick
    for i, look in enumerate(profile.looks):
        if look.x0 <= nx <= look.x1 and look.y0 <= ny <= look.y1:
            return Hit("look", i, "move")
    return None


@dataclass
class DragState:
    hit: Hit
    grab_dx: float = 0.0               # pointer offset from the object's anchor, so it does not jump
    grab_dy: float = 0.0
    origin: tuple = ()                 # what the object looked like when the drag began


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def begin_drag(profile: Profile, hit: Hit, nx: float, ny: float) -> DragState:
    if hit.kind == "tap":
        b = profile.bindings[hit.index]
        if hit.part == "end":
            return DragState(hit, b.x2 - nx, b.y2 - ny)
        k = step_index(hit.part)
        if k is not None:
            return DragState(hit, b.steps[k][0] - nx, b.steps[k][1] - ny)
        a = also_index(hit.part)
        if a is not None:
            return DragState(hit, b.also[a][0] - nx, b.also[a][1] - ny)
        return DragState(hit, b.x - nx, b.y - ny, (b.x, b.y, b.x2, b.y2, list(b.steps), list(b.also)))
    if hit.kind == "stick":
        s = profile.sticks[hit.index]
        return DragState(hit, s.x - nx, s.y - ny)
    look = profile.looks[hit.index]
    return DragState(hit, 0.0, 0.0, (look.x0, look.y0, look.x1, look.y1, nx, ny))


def update_drag(profile: Profile, state: DragState, nx: float, ny: float, tw: float, th: float) -> None:
    hit = state.hit
    if hit.kind == "tap":
        b = profile.bindings[hit.index]
        px, py = _clamp01(nx + state.grab_dx), _clamp01(ny + state.grab_dy)
        k = step_index(hit.part)
        a = also_index(hit.part)
        if hit.part == "end":
            b.x2, b.y2 = px, py
        elif k is not None:
            b.steps[k] = (px, py, b.steps[k][2])
        elif a is not None:
            b.also[a] = (px, py)
        else:                                                   # the whole control moves, with its second point(s)
            ox, oy, ox2, oy2, osteps, oalso = state.origin
            dx, dy = px - ox, py - oy
            b.x, b.y = px, py
            if ox2 is not None:
                b.x2, b.y2 = _clamp01(ox2 + dx), _clamp01(oy2 + dy)
            if osteps:
                b.steps = [(_clamp01(sx + dx), _clamp01(sy + dy), delay) for sx, sy, delay in osteps]
            if oalso:
                b.also = [(_clamp01(ax + dx), _clamp01(ay + dy)) for ax, ay in oalso]
    elif hit.kind == "stick":
        s = profile.sticks[hit.index]
        if hit.part == "center":
            s.x, s.y = _clamp01(nx + state.grab_dx), _clamp01(ny + state.grab_dy)
        else:                                                       # dragging a key node resizes the ring
            s.radius = max(MIN_STICK_RADIUS, min(MAX_STICK_RADIUS,
                                                 _dist_px(nx, ny, s.x, s.y, tw, th) / min(tw, th)))
    else:
        look = profile.looks[hit.index]
        x0, y0, x1, y1, sx, sy = state.origin
        gap = Look.MIN_SIZE
        if hit.part == "move":
            dx, dy = nx - sx, ny - sy
            dx = max(-x0, min(1.0 - x1, dx))
            dy = max(-y0, min(1.0 - y1, dy))
            look.x0, look.x1, look.y0, look.y1 = x0 + dx, x1 + dx, y0 + dy, y1 + dy
        else:
            nx, ny = _clamp01(nx), _clamp01(ny)
            if "l" in hit.part:
                look.x0 = min(nx, look.x1 - gap)
            else:
                look.x1 = max(nx, look.x0 + gap)
            if "t" in hit.part:
                look.y0 = min(ny, look.y1 - gap)
            else:
                look.y1 = max(ny, look.y0 + gap)


# ---------------------------------------------------------------- palette
def free_spot(profile: Profile, x: float = 0.40, y: float = 0.62, step: float = 0.045) -> tuple[float, float]:
    """A position near (x, y) that does not sit on top of an existing marker."""
    taken = [(b.x, b.y) for b in profile.bindings] + [(s.x, s.y) for s in profile.sticks]
    for i in range(40):
        cx, cy = _clamp01(x + (i % 8) * step), _clamp01(y + (i // 8) * step)
        if all(abs(cx - tx) > 0.03 or abs(cy - ty) > 0.04 for tx, ty in taken):
            return cx, cy
    return x, y


def add_preset(profile: Profile, kind: str) -> Hit | None:
    """Add a ready-made tap control. Returns None if its default key is already used by something else."""
    key, mode, label = PRESETS[kind]
    if profile.key_owner(key):
        return None
    x, y = free_spot(profile)
    profile.add(Binding(key, x, y, mode, label, scope=(kind == "scope")))
    return Hit("tap", len(profile.bindings) - 1)


def add_stick(profile: Profile) -> tuple[Hit, list[str]]:
    removed = profile.set_stick(Stick(0.14, 0.70))
    return Hit("stick", 0, "center"), removed


def add_look(profile: Profile) -> Hit:
    profile.looks = [Look(0.40, 0.15, 0.65, 0.50)]
    return Hit("look", 0, "move")


def binding_from_points(name: str, mode: str, points: list[tuple[float, float]], label: str = "") -> Binding:
    """Builds a binding from the spots the user clicked, for the modes that need more than one."""
    x, y = points[0]
    if mode in TWO_POINT_MODES:
        x2, y2 = points[1] if len(points) > 1 else (None, None)
        return Binding(name, x, y, mode, label, x2=x2, y2=y2)
    if mode == "sequence":
        steps = [(px, py, 0 if i == 0 else DEFAULT_STEP_DELAY_MS) for i, (px, py) in enumerate(points)]
        return Binding(name, x, y, mode, label, steps=steps)
    return Binding(name, x, y, mode, label)


def add_also(profile: Profile, index: int, spot: tuple[float, float]) -> bool:
    """Make the key of binding `index` touch one more spot at the same time. False if its mode cannot do that."""
    if not (0 <= index < len(profile.bindings)):
        return False
    b = profile.bindings[index]
    if b.mode not in ALSO_MODES or len(b.also) >= MAX_ALSO:
        return False
    b.also.append((_clamp01(spot[0]), _clamp01(spot[1])))
    return True


def delete(profile: Profile, hit: Hit) -> None:
    if hit.kind == "tap" and 0 <= hit.index < len(profile.bindings):
        k = step_index(hit.part)
        b = profile.bindings[hit.index]
        a = also_index(hit.part)
        if a is not None and a < len(b.also):
            del b.also[a]                                       # just that extra spot; the control stays
        elif k is not None and len(b.steps) > 2:
            del b.steps[k]                                      # removing one point of a multi-tap keeps the rest
        else:
            del profile.bindings[hit.index]
    elif hit.kind == "stick" and 0 <= hit.index < len(profile.sticks):
        del profile.sticks[hit.index]
    elif hit.kind == "look" and 0 <= hit.index < len(profile.looks):
        del profile.looks[hit.index]
