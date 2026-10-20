"""Tells game screens from menus by looking at the mirrored picture. Qt-free; needs only numpy.

How it works (the idea behind the "smart" modes of emulators, done on the mirrored picture of a real phone):
- While the game is on screen, the player presses "Learn": a small square patch around every control (the fire
  button, the jump button, ...) is cut out of the picture and kept as a tiny 12x12 grey-scale "signature".
- Later, every moment, the same places of the current picture are compared with the signatures (normalised
  correlation, so the brightness of the scenery behind the semi-transparent buttons hardly matters).
- If most of the places still look like the learned buttons, the game's controls are on screen: GAME. If not
  (lobby, menu, results, loading, another app): MENU.
- A tracker adds hysteresis, so one odd frame never flips the mode.

Nothing here touches the game or the phone: it only reads pixels the app already shows.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field

import numpy as np

GRID = 12                 # signature is GRID x GRID values
PATCH = 0.075             # side of the patch, as a fraction of the picture HEIGHT
MIN_STD = 6.0             # patches flatter than this (grey levels) carry no information
MAX_ANCHORS = 14
MIN_ANCHORS = 4           # fewer clear controls than this and the screen cannot be told apart reliably
MATCH = 0.55              # correlation at which one place "looks like the learned control"

GAME, MENU, UNKNOWN = "game", "menu", "unknown"


def luma(plane: bytes, width: int, height: int) -> np.ndarray:
    """A (height, width) uint8 view of a Y plane."""
    return np.frombuffer(plane, dtype=np.uint8, count=width * height).reshape(height, width)


def signature(gray: np.ndarray, cx: float, cy: float, size: float = PATCH) -> np.ndarray | None:
    """Zero-mean, unit-length GRIDxGRID signature of the square around the normalised point (cx, cy).
    None if the patch is (almost) flat or falls outside the picture."""
    h, w = gray.shape
    side = max(GRID, int(round(size * h)))
    x0 = int(round(cx * w - side / 2))
    y0 = int(round(cy * h - side / 2))
    x0 = max(0, min(w - side, x0))
    y0 = max(0, min(h - side, y0))
    if side > w or side > h:
        return None
    patch = gray[y0:y0 + side, x0:x0 + side].astype(np.float32)
    if float(patch.std()) < MIN_STD:
        return None
    edges = np.linspace(0, side, GRID + 1).astype(int)
    rows = np.add.reduceat(patch, edges[:-1], axis=0)
    cells = np.add.reduceat(rows, edges[:-1], axis=1)
    counts = np.outer(np.diff(edges), np.diff(edges)).astype(np.float32)
    small = (cells / counts).ravel()
    small -= small.mean()
    norm = float(np.linalg.norm(small))
    if norm < 1e-3:
        return None
    return small / norm


@dataclass
class Anchor:
    x: float
    y: float
    sig: np.ndarray = field(repr=False)


@dataclass
class SceneModel:
    anchors: list[Anchor]
    match: float = MATCH
    need: float = 0.5          # fraction of anchors that must match for GAME

    @property
    def usable(self) -> bool:
        return len(self.anchors) >= MIN_ANCHORS

    def to_dict(self) -> dict:
        return {"version": 1, "match": self.match, "need": self.need,
                "anchors": [{"x": round(a.x, 4), "y": round(a.y, 4),
                             "sig": base64.b64encode(a.sig.astype("<f2").tobytes()).decode("ascii")}
                            for a in self.anchors]}

    @staticmethod
    def from_dict(data: dict | None) -> "SceneModel | None":
        try:
            if not data:
                return None
            anchors = []
            for item in data["anchors"]:
                sig = np.frombuffer(base64.b64decode(item["sig"]), dtype="<f2").astype(np.float32)
                if sig.size != GRID * GRID:
                    return None
                anchors.append(Anchor(float(item["x"]), float(item["y"]), sig))
            model = SceneModel(anchors, float(data.get("match", MATCH)), float(data.get("need", 0.5)))
            return model if model.anchors else None
        except (KeyError, TypeError, ValueError):
            return None


def learn(gray: np.ndarray, points: list[tuple[float, float]]) -> SceneModel:
    """Build a model from the controls' positions on a picture where the game's controls are visible.
    Keeps the most distinctive places (flat background tells nothing)."""
    scored: list[tuple[float, Anchor]] = []
    seen: list[tuple[float, float]] = []
    for x, y in points:
        if any(abs(x - sx) < PATCH * 0.5 and abs(y - sy) < PATCH * 0.5 for sx, sy in seen):
            continue                                        # two controls on the same spot: one anchor is enough
        sig = signature(gray, x, y)
        if sig is None:
            continue
        h, w = gray.shape
        side = max(GRID, int(round(PATCH * h)))
        x0 = max(0, min(w - side, int(round(x * w - side / 2))))
        y0 = max(0, min(h - side, int(round(y * h - side / 2))))
        spread = float(gray[y0:y0 + side, x0:x0 + side].std())
        scored.append((spread, Anchor(x, y, sig)))
        seen.append((x, y))
    scored.sort(key=lambda item: -item[0])
    return SceneModel([a for _, a in scored[:MAX_ANCHORS]])


def score(model: SceneModel, gray: np.ndarray) -> float:
    """Fraction (0..1) of the learned places that look like the learned controls in this picture."""
    if not model.anchors:
        return 0.0
    hits = 0
    for anchor in model.anchors:
        sig = signature(gray, anchor.x, anchor.y)
        if sig is not None and float(np.dot(sig, anchor.sig)) >= model.match:
            hits += 1
    return hits / len(model.anchors)


class SceneTracker:
    """Turns a stream of scores into a steady GAME / MENU state.

    Needs `confirm` agreeing samples in a row to change state. Between the two thresholds the state stays as it
    was. Before the first decision the state is UNKNOWN, which callers treat like MENU (safe: keys paused)."""

    def __init__(self, enter: float = 0.5, leave: float = 0.3, confirm: int = 3) -> None:
        self.enter, self.leave, self.confirm = enter, leave, confirm
        self.state = UNKNOWN
        self._streak = 0
        self._candidate = UNKNOWN

    def reset(self) -> None:
        self.state, self._streak, self._candidate = UNKNOWN, 0, UNKNOWN

    def force(self, state: str) -> None:
        """Take a state without waiting for confirmation (used for the very first look)."""
        self.state, self._streak, self._candidate = state, 0, UNKNOWN

    def update(self, value: float) -> str:
        if value >= self.enter:
            candidate = GAME
        elif value <= self.leave:
            candidate = MENU
        else:
            self._streak = 0
            return self.state
        if candidate == self.state:
            self._streak = 0
            return self.state
        if candidate == self._candidate:
            self._streak += 1
        else:
            self._candidate, self._streak = candidate, 1
        if self._streak >= self.confirm:
            self.state, self._streak = candidate, 0
        return self.state
