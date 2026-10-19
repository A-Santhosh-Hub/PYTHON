"""Decoded frame in planar YUV 4:2:0 form, ready for upload to the GPU."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_COLORSPACE_BT601 = (5, 6)      # AVCOL_SPC_BT470BG, AVCOL_SPC_SMPTE170M
_RANGE_FULL = 2                 # AVCOL_RANGE_JPEG


@dataclass
class YuvFrame:
    width: int
    height: int
    y: bytes
    u: bytes
    v: bytes
    bt601: bool = False
    full_range: bool = False

    @property
    def chroma_size(self) -> tuple[int, int]:
        return (self.width + 1) // 2, (self.height + 1) // 2


def _plane_bytes(plane) -> bytes:
    raw = np.frombuffer(plane, dtype=np.uint8)[: plane.height * plane.line_size]
    return raw.reshape(plane.height, plane.line_size)[:, : plane.width].tobytes()   # drops row padding


def frame_to_yuv(frame) -> YuvFrame:
    """Convert a PyAV VideoFrame into a YuvFrame (no colour conversion for yuv420p input)."""
    if frame.format.name != "yuv420p":
        frame = frame.reformat(format="yuv420p")
    y, u, v = (_plane_bytes(p) for p in frame.planes[:3])
    return YuvFrame(
        width=frame.width, height=frame.height, y=y, u=u, v=v,
        bt601=int(frame.colorspace) in _COLORSPACE_BT601,
        full_range=int(frame.color_range) == _RANGE_FULL,
    )
