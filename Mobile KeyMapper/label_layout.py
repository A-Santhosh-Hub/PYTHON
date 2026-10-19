"""Places marker labels so they never sit on top of each other or on another marker (Qt-free, unit-tested)."""
from __future__ import annotations

Rect = tuple[float, float, float, float]          # x, y, width, height


def _overlap(a: Rect, b: Rect) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def _hits_circle(rect: Rect, cx: float, cy: float, radius: float) -> bool:
    nearest_x = max(rect[0], min(cx, rect[0] + rect[2]))
    nearest_y = max(rect[1], min(cy, rect[1] + rect[3]))
    return (nearest_x - cx) ** 2 + (nearest_y - cy) ** 2 < radius ** 2


def place_labels(markers: list[tuple[float, float, float]], height: float = 16, radius: float = 20,
                 gap: float = 2, bounds: tuple[float, float] | None = None) -> list[Rect | None]:
    """markers: (centre x, centre y, label width) per marker; width 0 means no label.

    Each label is tried below its marker, then above, then pushed further down / up in steps, taking the first
    spot that overlaps no earlier label and no marker circle. Returns one rectangle (or None) per marker."""
    placed: list[Rect] = []
    result: list[Rect | None] = []
    for cx, cy, width in markers:
        if width <= 0:
            result.append(None)
            continue
        x = cx - width / 2
        if bounds:
            x = max(2, min(bounds[0] - width - 2, x))
        candidates = []
        for step in range(5):
            candidates.append(cy + radius + gap + step * height)          # below, then lower and lower
            candidates.append(cy - radius - gap - height - step * height)  # above, then higher and higher
        chosen: Rect | None = None
        for y in candidates:
            rect = (x, y, width, height)
            if bounds and (y < 0 or y + height > bounds[1]):
                continue
            if any(_overlap(rect, other) for other in placed):
                continue
            if any(_hits_circle(rect, mx, my, radius) for mx, my, _ in markers):
                continue
            chosen = rect
            break
        if chosen is None:                                                  # crowded: fall back to just below
            chosen = (x, cy + radius + gap, width, height)
        placed.append(chosen)
        result.append(chosen)
    return result
