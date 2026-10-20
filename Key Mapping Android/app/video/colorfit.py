"""Checks the colour conversion against the truth: a screenshot of the phone taken at the same moment.

The phone sends video as YUV; turning that into the colours you see needs the right matrix (BT.709 or BT.601) and range
(limited or full). Streams normally say which, but not always. A screenshot (plain RGB) is the ground truth, so the
conversion that reproduces it best is the right one. Qt-free; needs only numpy.
"""
from __future__ import annotations

import numpy as np

from .frame import YuvFrame

# r = y + c*v ; g = y - a*u - d*v ; b = y + b*u
COEFFICIENTS = {"bt709": (1.5748, 0.187324, 0.468124, 1.8556), "bt601": (1.402, 0.344136, 0.714136, 1.772)}
# a difference this small is codec noise, not a wrong conversion
SIGNIFICANT = 0.6

MODES = {"bt709": ("bt709", False), "bt601": ("bt601", False), "bt709_full": ("bt709", True), "bt601_full": ("bt601", True)}


def flagged_mode(frame: YuvFrame) -> str:
    """What the stream itself says (the mode the app uses in 'automatic')."""
    return ("bt601" if frame.bt601 else "bt709") + ("_full" if frame.full_range else "")


def planes(frame: YuvFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    y = np.frombuffer(frame.y, np.uint8, count=frame.width * frame.height).reshape(frame.height, frame.width)
    cw, ch = frame.chroma_size
    u = np.frombuffer(frame.u, np.uint8, count=cw * ch).reshape(ch, cw)
    v = np.frombuffer(frame.v, np.uint8, count=cw * ch).reshape(ch, cw)
    up = lambda p: np.repeat(np.repeat(p, 2, 0), 2, 1)[: frame.height, : frame.width]
    return y.astype(np.float32), up(u).astype(np.float32), up(v).astype(np.float32)


def render(frame: YuvFrame, mode: str) -> np.ndarray:
    """The picture as float RGB (0..255) if the conversion `mode` were the right one."""
    matrix, full = MODES[mode]
    c, a, d, b = COEFFICIENTS[matrix]
    y, u, v = planes(frame)
    if full:
        yy, uu, vv = y, u - 128, v - 128
    else:
        yy, uu, vv = (y - 16) * (255 / 219), (u - 128) * (255 / 224), (v - 128) * (255 / 224)
    return np.clip(np.stack([yy + c * vv, yy - a * uu - d * vv, yy + b * uu], axis=-1), 0, 255)


def fit(frame: YuvFrame, truth: np.ndarray) -> dict[str, float]:
    """Mean absolute error (0..255 per channel) of each conversion against `truth` (height x width x 3, uint8)."""
    if truth.shape != (frame.height, frame.width, 3):
        raise ValueError("the screenshot must be the same size as the video frame")
    reference = truth.astype(np.float32)
    return {mode: float(np.abs(render(frame, mode) - reference).mean()) for mode in MODES}


def choose(frame: YuvFrame, truth: np.ndarray) -> tuple[str, dict[str, float], bool]:
    """(best mode, error of every mode, True if the stream's own flags are already as good as the best)."""
    errors = fit(frame, truth)
    best = min(errors, key=errors.get)
    flagged = flagged_mode(frame)
    already_right = errors[flagged] - errors[best] < SIGNIFICANT
    return (flagged if already_right else best), errors, already_right
