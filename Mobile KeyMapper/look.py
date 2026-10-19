"""How the phone picture looks on the PC: brightness, contrast, saturation, sharpness and the colour conversion.

These are drawn by the GPU (see widget.py), so they apply at once, cost almost nothing and never touch the stream.
They exist because a phone's own screen (often a vivid AMOLED panel) looks different from a PC monitor even when the
picture data is identical.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

# Colour conversion of the video: what matrix and range the phone's encoder used. "auto" trusts the stream's own flags.
COLOR_MODES = {
    "auto": "Automatic (recommended)",
    "bt709": "BT.709, limited range",
    "bt601": "BT.601, limited range",
    "bt709_full": "BT.709, full range",
    "bt601_full": "BT.601, full range",
}

BRIGHTNESS = (-0.30, 0.30)
CONTRAST = (0.60, 1.60)
SATURATION = (0.0, 2.0)
SHARPNESS = (0.0, 1.0)


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    return max(bounds[0], min(bounds[1], float(value)))


@dataclass(frozen=True)
class PictureLook:
    brightness: float = 0.0       # added to every colour (-0.3 .. +0.3)
    contrast: float = 1.0         # 1 = unchanged
    saturation: float = 1.0       # 0 = grey, 1 = unchanged, 2 = double
    sharpness: float = 0.0        # 0 = off; unsharp mask amount
    color_mode: str = "auto"

    def __post_init__(self) -> None:
        object.__setattr__(self, "brightness", _clamp(self.brightness, BRIGHTNESS))
        object.__setattr__(self, "contrast", _clamp(self.contrast, CONTRAST))
        object.__setattr__(self, "saturation", _clamp(self.saturation, SATURATION))
        object.__setattr__(self, "sharpness", _clamp(self.sharpness, SHARPNESS))
        if self.color_mode not in COLOR_MODES:
            object.__setattr__(self, "color_mode", "auto")

    @property
    def is_neutral(self) -> bool:
        return (self.brightness, self.contrast, self.saturation, self.sharpness) == (0.0, 1.0, 1.0, 0.0)

    def with_values(self, **changes) -> "PictureLook":
        return replace(self, **changes)


# One-click looks. They change only the four sliders, never the colour conversion.
PRESETS = {
    "natural": ("Natural  -  exactly what the phone sends", PictureLook()),
    "vivid": ("Vivid  -  closer to a phone's bright screen", PictureLook(saturation=1.25, contrast=1.08, sharpness=0.25)),
    "crisp": ("Crisp  -  sharper details, for fast shooters", PictureLook(saturation=1.08, contrast=1.05, sharpness=0.55)),
}

_KEYS = ("brightness", "contrast", "saturation", "sharpness")


def load(settings) -> PictureLook:
    values = {}
    for key in _KEYS:
        try:
            values[key] = float(settings.value(f"look_{key}", getattr(PictureLook(), key)))
        except (TypeError, ValueError):
            pass
    return PictureLook(color_mode=str(settings.value("look_color_mode", "auto")), **values)


def save(settings, look: PictureLook) -> None:
    for key in _KEYS:
        settings.setValue(f"look_{key}", round(getattr(look, key), 4))
    settings.setValue("look_color_mode", look.color_mode)


def matching_preset(look: PictureLook) -> str | None:
    for key, (_label, preset) in PRESETS.items():
        if all(abs(getattr(look, k) - getattr(preset, k)) < 1e-6 for k in _KEYS):
            return key
    return None
