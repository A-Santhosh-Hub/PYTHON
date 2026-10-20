"""Control profiles: which key / mouse button taps which point of the phone screen.

Positions are stored as fractions (0..1) of the video frame, so a profile works at any
resolution. Profiles are plain JSON files, one per game.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

PROFILE_VERSION = 1

# What a key does when pressed:
#   hold      touch the point while the key is down            tap       one quick touch
#   toggle    first press touches and keeps touching, next press lets go
#   repeat    touch again and again while the key is held (auto-click)      double   two quick taps
#   swipe     drag from the point to a second point and let go             drag     same, but stays at the end until release
#   pinch-out two fingers move apart (zoom in)                             pinch-in two fingers move together (zoom out)
#   sequence  touch several points in order, with delays between them
MODES = ("hold", "tap", "toggle", "repeat", "double", "swipe", "drag", "pinch-out", "pinch-in", "sequence")
MODE_SHORT = {"hold": "hold", "tap": "tap", "toggle": "toggle", "repeat": "repeat", "double": "double tap",
              "swipe": "swipe", "drag": "drag", "pinch-out": "zoom in", "pinch-in": "zoom out", "sequence": "multi-tap"}
MODE_HELP = {
    "hold": "Touches the spot for as long as the key is held (fire, aim).",
    "tap": "One quick touch each time the key is pressed (reload, jump, map).",
    "toggle": "Press once to start touching and keep touching, press again to let go (sprint lock, hold-to-toggle buttons).",
    "repeat": "Taps again and again while the key is held (auto-click). Some online games treat this as cheating.",
    "double": "Two quick taps for each key press.",
    "swipe": "Drags from the spot to a second spot and lets go (slide, lean, throw).",
    "drag": "Drags from the spot to a second spot and stays there until the key is released.",
    "pinch-out": "Two fingers move apart around the spot (zoom in on a map).",
    "pinch-in": "Two fingers move together around the spot (zoom out on a map).",
    "sequence": "Touches several spots one after another (open a menu, pick an item).",
}
TWO_POINT_MODES = ("swipe", "drag")
ALSO_MODES = ("hold", "tap", "toggle")     # modes where one key can touch extra spots at the same time
MAX_ALSO = 4
PINCH_MODES = ("pinch-out", "pinch-in")
ORIENTATIONS = ("any", "portrait", "landscape")

MODIFIERS = ("Ctrl", "Shift", "Alt")       # canonical order inside a combination name, e.g. "Ctrl+Shift+W"


def split_combo(name: str) -> tuple[frozenset, str]:
    """'Shift+W' -> ({'Shift'}, 'W'). A name without modifiers gives an empty set."""
    mods: list[str] = []
    rest = name
    changed = True
    while changed:
        changed = False
        for modifier in MODIFIERS:
            if rest.startswith(modifier + "+") and len(rest) > len(modifier) + 1:
                mods.append(modifier)
                rest = rest[len(modifier) + 1:]
                changed = True
                break
    return frozenset(mods), rest


def make_combo(mods, base: str) -> str:
    return "+".join([m for m in MODIFIERS if m in mods] + [base])


class ProfileError(ValueError):
    pass


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass
class Binding:
    input: str                      # "W", "Space", "LMB", "WheelUp", "Shift+W", ...
    x: float
    y: float
    mode: str = "hold"
    label: str = ""
    x2: float | None = None         # swipe / drag: where the finger goes
    y2: float | None = None
    rate_hz: float = 10.0           # repeat: taps per second
    duration_ms: int = 160          # swipe / drag / pinch: how long the movement takes
    span: float = 0.10              # pinch: finger distance from the centre (fraction of the shorter screen side)
    scope: bool = False             # this is the scope / aim button: mouse sensitivity drops while it is active
    steps: list = field(default_factory=list)      # sequence: [(x, y, delay_ms before this tap), ...]
    also: list = field(default_factory=list)       # hold / tap / toggle: extra spots touched together [(x, y), ...]

    def __post_init__(self) -> None:
        if not self.input:
            raise ProfileError("A binding needs an input key")
        if self.mode not in MODES:
            raise ProfileError(f"Unknown binding mode: {self.mode!r}")
        mods, base = split_combo(self.input)
        if mods and base in MODIFIERS:
            raise ProfileError("A key combination needs a normal key after the modifiers (e.g. Shift+W)")
        self.input = make_combo(mods, base)
        self.x, self.y = _clamp01(self.x), _clamp01(self.y)
        self.rate_hz = max(1.0, min(30.0, float(self.rate_hz)))
        self.duration_ms = max(40, min(3000, int(self.duration_ms)))
        self.span = max(0.02, min(0.40, float(self.span)))
        self.scope = bool(self.scope)
        cleaned_also = []
        for spot in self.also[:MAX_ALSO]:
            try:
                ax, ay = spot
                cleaned_also.append((_clamp01(ax), _clamp01(ay)))
            except (TypeError, ValueError) as exc:
                raise ProfileError(f"Invalid extra spot {spot!r}") from exc
        self.also = cleaned_also
        if self.mode in TWO_POINT_MODES:
            if self.x2 is None or self.y2 is None:
                self.x2, self.y2 = _clamp01(self.x + 0.15), self.y
            self.x2, self.y2 = _clamp01(self.x2), _clamp01(self.y2)
        if self.mode == "sequence":
            cleaned = []
            for step in self.steps:
                try:
                    sx, sy, delay = step
                    cleaned.append((_clamp01(sx), _clamp01(sy), max(0, min(5000, int(delay)))))
                except (TypeError, ValueError) as exc:
                    raise ProfileError(f"Invalid multi-tap step {step!r}") from exc
            self.steps = cleaned or [(self.x, self.y, 0)]

    def set_mode(self, mode: str) -> None:
        """Change the mode and fill in what the new mode needs (a second point, a first step)."""
        if mode not in MODES:
            raise ProfileError(f"Unknown binding mode: {mode!r}")
        self.mode = mode
        if mode in TWO_POINT_MODES and (self.x2 is None or self.y2 is None):
            self.x2, self.y2 = _clamp01(self.x + 0.15), self.y
        if mode == "sequence" and not self.steps:
            self.steps = [(self.x, self.y, 0)]

    @property
    def combo(self) -> tuple[frozenset, str]:
        return split_combo(self.input)

    def to_dict(self) -> dict:
        data = {"type": "tap", "input": self.input, "x": round(self.x, 5), "y": round(self.y, 5),
                "mode": self.mode, "label": self.label}
        if self.scope:
            data["scope"] = True
        if self.mode in TWO_POINT_MODES:
            data.update(x2=round(self.x2, 5), y2=round(self.y2, 5), duration_ms=self.duration_ms)
        if self.mode == "repeat":
            data["rate_hz"] = self.rate_hz
        if self.mode in PINCH_MODES:
            data.update(span=round(self.span, 4), duration_ms=self.duration_ms)
        if self.mode == "sequence":
            data["steps"] = [[round(sx, 5), round(sy, 5), delay] for sx, sy, delay in self.steps]
        if self.also:
            data["also"] = [[round(ax, 5), round(ay, 5)] for ax, ay in self.also]
        return data

    @staticmethod
    def from_dict(data: dict) -> "Binding":
        try:
            return Binding(
                input=str(data["input"]), x=float(data["x"]), y=float(data["y"]),
                mode=str(data.get("mode", "hold")), label=str(data.get("label", "")),
                x2=None if data.get("x2") is None else float(data["x2"]),
                y2=None if data.get("y2") is None else float(data["y2"]),
                rate_hz=float(data.get("rate_hz", 10.0)), duration_ms=int(data.get("duration_ms", 160)),
                span=float(data.get("span", 0.10)), scope=bool(data.get("scope", False)),
                steps=[tuple(step) for step in data.get("steps", [])],
                also=[tuple(spot) for spot in data.get("also", [])])
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ProfileError):
                raise
            raise ProfileError(f"Invalid binding {data!r}: {exc}") from exc


DIRECTIONS = ("up", "left", "down", "right")
DEFAULT_STICK_KEYS = {"up": "W", "left": "A", "down": "S", "right": "D"}
STICK_EXTRAS = ("sprint", "walk", "autorun")


@dataclass
class Stick:
    """A virtual joystick: four keys drag one finger away from (x, y) by up to `radius`.

    `radius` is a fraction of the shorter screen side, so the stick is round on any aspect ratio.
    `ramp_ms` is how long the finger takes to travel from the centre to full deflection.
    Optional keys: `sprint_key` held = push the stick `sprint_scale` times further (many games sprint when the
    stick is pushed to its edge), `walk_key` held = push only `walk_scale` of the way (slow, quiet walking),
    `autorun_key` pressed = keep walking forward until a backward key (or the key again) cancels it.
    """
    x: float
    y: float
    radius: float = 0.09
    keys: dict = field(default_factory=lambda: dict(DEFAULT_STICK_KEYS))
    ramp_ms: int = 50
    label: str = "Move"
    sprint_key: str = ""
    sprint_scale: float = 1.35
    walk_key: str = ""
    walk_scale: float = 0.5
    autorun_key: str = ""

    def __post_init__(self) -> None:
        self.x, self.y = _clamp01(self.x), _clamp01(self.y)
        self.radius = max(0.01, min(0.5, float(self.radius)))
        self.ramp_ms = max(0, min(500, int(self.ramp_ms)))
        self.sprint_scale = max(1.0, min(4.0, float(self.sprint_scale)))
        self.walk_scale = max(0.1, min(0.95, float(self.walk_scale)))
        if set(self.keys) != set(DIRECTIONS) or not all(self.keys.values()):
            raise ProfileError("A stick needs a key for up, left, down and right")
        if len(set(self.keys.values())) != 4:
            raise ProfileError("The four stick keys must all be different")
        extras = [k for k in (self.sprint_key, self.walk_key, self.autorun_key) if k]
        if len(set(extras)) != len(extras):
            raise ProfileError("The sprint, walk and auto-run keys must all be different")
        if set(extras) & set(self.keys.values()):
            raise ProfileError("The sprint, walk and auto-run keys cannot be the same as a direction key")

    def extra_keys(self) -> dict[str, str]:
        return {name: key for name, key in (("sprint", self.sprint_key), ("walk", self.walk_key),
                                            ("autorun", self.autorun_key)) if key}

    def key_set(self) -> set[str]:
        return set(self.keys.values()) | set(self.extra_keys().values())

    def to_dict(self) -> dict:
        return {"type": "stick", "x": round(self.x, 5), "y": round(self.y, 5), "radius": round(self.radius, 4),
                "keys": dict(self.keys), "ramp_ms": self.ramp_ms, "label": self.label,
                "sprint_key": self.sprint_key, "sprint_scale": round(self.sprint_scale, 3),
                "walk_key": self.walk_key, "walk_scale": round(self.walk_scale, 3), "autorun_key": self.autorun_key}

    @staticmethod
    def from_dict(data: dict) -> "Stick":
        try:
            return Stick(x=float(data["x"]), y=float(data["y"]), radius=float(data.get("radius", 0.09)),
                         keys=dict(data.get("keys", DEFAULT_STICK_KEYS)), ramp_ms=int(data.get("ramp_ms", 50)),
                         label=str(data.get("label", "Move")),
                         sprint_key=str(data.get("sprint_key", "")), sprint_scale=float(data.get("sprint_scale", 1.35)),
                         walk_key=str(data.get("walk_key", "")), walk_scale=float(data.get("walk_scale", 0.5)),
                         autorun_key=str(data.get("autorun_key", "")))
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ProfileError):
                raise
            raise ProfileError(f"Invalid stick {data!r}: {exc}") from exc


@dataclass
class Look:
    """Mouse look: mouse movement drags one finger inside the zone (x0, y0)-(x1, y1).

    Sensitivity is phone-screen pixels per mouse count. When the finger nears the zone edge it is lifted and
    put back in the centre, so the camera can keep turning in one direction. `ads_scale` multiplies the
    sensitivity while a binding marked as the scope button is active (1.0 = no change).
    """
    x0: float
    y0: float
    x1: float
    y1: float
    sens_x: float = 1.0
    sens_y: float = 1.0
    accel: float = 0.0           # 0 = none .. 1 = strong: fast flicks are amplified
    invert_y: bool = False
    label: str = "Look"
    ads_scale: float = 1.0

    MIN_SIZE = 0.06

    def __post_init__(self) -> None:
        a, b = sorted((_clamp01(self.x0), _clamp01(self.x1)))
        c, d = sorted((_clamp01(self.y0), _clamp01(self.y1)))
        if b - a < self.MIN_SIZE or d - c < self.MIN_SIZE:
            raise ProfileError("The look area is too small")
        self.x0, self.x1, self.y0, self.y1 = a, b, c, d
        self.sens_x = max(0.05, min(20.0, float(self.sens_x)))
        self.sens_y = max(0.05, min(20.0, float(self.sens_y)))
        self.accel = max(0.0, min(1.0, float(self.accel)))
        self.invert_y = bool(self.invert_y)
        self.ads_scale = max(0.1, min(1.5, float(self.ads_scale)))

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    def to_dict(self) -> dict:
        return {"type": "look", "x0": round(self.x0, 5), "y0": round(self.y0, 5), "x1": round(self.x1, 5),
                "y1": round(self.y1, 5), "sens_x": round(self.sens_x, 3), "sens_y": round(self.sens_y, 3),
                "accel": round(self.accel, 3), "invert_y": self.invert_y, "label": self.label,
                "ads_scale": round(self.ads_scale, 3)}

    @staticmethod
    def from_dict(data: dict) -> "Look":
        try:
            return Look(x0=float(data["x0"]), y0=float(data["y0"]), x1=float(data["x1"]), y1=float(data["y1"]),
                        sens_x=float(data.get("sens_x", 1.0)), sens_y=float(data.get("sens_y", 1.0)),
                        accel=float(data.get("accel", 0.0)), invert_y=bool(data.get("invert_y", False)),
                        label=str(data.get("label", "Look")), ads_scale=float(data.get("ads_scale", 1.0)))
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ProfileError):
                raise
            raise ProfileError(f"Invalid look area {data!r}: {exc}") from exc


@dataclass
class Profile:
    name: str
    orientation: str = "any"
    bindings: list[Binding] = field(default_factory=list)
    sticks: list[Stick] = field(default_factory=list)
    looks: list[Look] = field(default_factory=list)
    package: str = ""          # Android app id this profile belongs to ("" = not linked to a game)
    scene: dict | None = None  # smart mode: {"enabled": bool, + the learned look of the game's controls (app/scene.py)}

    def find(self, input_name: str) -> Binding | None:
        return next((b for b in self.bindings if b.input == input_name), None)

    def add(self, binding: Binding) -> None:
        """Add a binding, replacing any existing binding for the same input."""
        self.bindings = [b for b in self.bindings if b.input != binding.input]
        self.bindings.append(binding)

    def remove(self, input_name: str) -> None:
        self.bindings = [b for b in self.bindings if b.input != input_name]

    def lookup(self) -> dict[str, Binding]:
        return {b.input: b for b in self.bindings}

    def stick_keys(self) -> set[str]:
        return {k for stick in self.sticks for k in stick.key_set()}

    def key_owner(self, input_name: str) -> str | None:
        """Describes what an input is already used for ('another control' / 'the movement stick'), or None."""
        if self.find(input_name):
            return "another control"
        if input_name in self.stick_keys():
            return "the movement stick"
        return None

    def set_stick(self, stick: Stick) -> list[str]:
        """Replace the profile's stick. Tap bindings on its keys are removed; returns their names."""
        clash = [b.input for b in self.bindings if b.input in stick.key_set()]
        self.bindings = [b for b in self.bindings if b.input not in stick.key_set()]
        self.sticks = [stick]
        return clash

    def to_dict(self) -> dict:
        return {"version": PROFILE_VERSION, "name": self.name, "orientation": self.orientation,
                "package": self.package,
                **({"scene": self.scene} if self.scene else {}),
                "bindings": [b.to_dict() for b in self.bindings],
                "sticks": [s.to_dict() for s in self.sticks],
                "looks": [l.to_dict() for l in self.looks]}

    @staticmethod
    def from_dict(data: dict) -> "Profile":
        if not isinstance(data, dict) or "name" not in data:
            raise ProfileError("Not a profile file")
        if int(data.get("version", 1)) > PROFILE_VERSION:
            raise ProfileError("This profile was made by a newer version of the app")
        orientation = data.get("orientation", "any")
        if orientation not in ORIENTATIONS:
            orientation = "any"
        bindings: list[Binding] = []
        for raw in data.get("bindings", []):
            if raw.get("type", "tap") != "tap":
                log.warning("Skipping unsupported binding type %r", raw.get("type"))
                continue
            bindings.append(Binding.from_dict(raw))
        scene = data.get("scene")
        profile = Profile(name=str(data["name"]), orientation=orientation, package=str(data.get("package", "")),
                          scene=scene if isinstance(scene, dict) else None)
        for binding in bindings:
            profile.add(binding)
        for raw in data.get("sticks", []):
            stick = Stick.from_dict(raw)
            if stick.key_set() & {b.input for b in profile.bindings}:
                raise ProfileError("A stick key is also used by a tap binding")
            profile.sticks.append(stick)
        for raw in data.get("looks", []):
            profile.looks.append(Look.from_dict(raw))
        return profile


def orientation_of(width: int, height: int) -> str:
    return "landscape" if width > height else "portrait"


class ProfileStore:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def filename(name: str) -> str:
        safe = re.sub(r"[^\w\- .]", "_", name).strip(" .")
        if not safe:
            raise ProfileError("Profile name is empty")
        return safe + ".json"

    def path(self, name: str) -> Path:
        return self.folder / self.filename(name)

    def names(self) -> list[str]:
        names = []
        for file in sorted(self.folder.glob("*.json")):
            try:
                names.append(json.loads(file.read_text(encoding="utf-8"))["name"])
            except (OSError, ValueError, KeyError):
                log.warning("Ignoring unreadable profile file %s", file.name)
        return sorted(names, key=str.lower)

    def find_by_package(self, package: str) -> str | None:
        """Name of the profile linked to an Android app id, or None."""
        if not package:
            return None
        for file in sorted(self.folder.glob("*.json")):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if data.get("package") == package and "name" in data:
                return str(data["name"])
        return None

    def link_package(self, profile: "Profile", package: str) -> list[str]:
        """Link `profile` to an app id (saving it). Other profiles lose that link; returns their names."""
        unlinked = []
        for name in self.names():
            if name != profile.name:
                other = self.load(name)
                if other.package == package and package:
                    other.package = ""
                    self.save(other)
                    unlinked.append(name)
        profile.package = package
        self.save(profile)
        return unlinked

    def exists(self, name: str) -> bool:
        return self.path(name).is_file()

    def load(self, name: str) -> Profile:
        try:
            return Profile.from_dict(json.loads(self.path(name).read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            if isinstance(exc, ProfileError):
                raise
            raise ProfileError(f"Could not read profile '{name}': {exc}") from exc

    def save(self, profile: Profile) -> None:
        target = self.path(profile.name)
        temp = target.with_suffix(".tmp")
        try:
            temp.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
            os.replace(temp, target)           # atomic: a crash never leaves a half-written profile
        except OSError as exc:
            raise ProfileError(f"Could not save profile '{profile.name}': {exc}") from exc

    def delete(self, name: str) -> None:
        for path in (self.path(name), self.checkpoint_path(name)):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise ProfileError(f"Could not delete profile '{name}': {exc}") from exc

    # -- restore points ("Save" in the UI) -------------------------------------------------------
    # Edits are written to the profile file at once (nothing is ever lost). A restore point is a second copy that
    # only changes when the user presses Save, so accidental edits can be undone with "Undo changes".
    def checkpoint_path(self, name: str) -> Path:
        return self.folder / "saved" / self.filename(name)

    def has_checkpoint(self, name: str) -> bool:
        return self.checkpoint_path(name).is_file()

    def save_checkpoint(self, profile: Profile) -> float:
        target = self.checkpoint_path(profile.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(".tmp")
        try:
            temp.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
            os.replace(temp, target)
        except OSError as exc:
            raise ProfileError(f"Could not save a restore point for '{profile.name}': {exc}") from exc
        return time.time()

    def load_checkpoint(self, name: str) -> Profile:
        try:
            return Profile.from_dict(json.loads(self.checkpoint_path(name).read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            if isinstance(exc, ProfileError):
                raise
            raise ProfileError(f"No restore point for '{name}': {exc}") from exc

    def checkpoint_time(self, name: str) -> float | None:
        try:
            return self.checkpoint_path(name).stat().st_mtime
        except OSError:
            return None

    def has_unsaved_changes(self, profile: Profile) -> bool:
        """True if the profile differs from its restore point (a profile without one counts as unchanged)."""
        if not self.has_checkpoint(profile.name):
            return False
        try:
            return self.load_checkpoint(profile.name).to_dict() != profile.to_dict()
        except ProfileError:
            return False
