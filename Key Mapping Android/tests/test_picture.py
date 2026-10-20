import numpy as np
import pytest

from app.video import colorfit, look
from app.video.frame import YuvFrame


class FakeSettings(dict):
    def value(self, key, default=None):
        return self.get(key, default)

    def setValue(self, key, value):
        self[key] = value


# ===================================================================== picture look
def test_default_look_changes_nothing():
    assert look.PictureLook().is_neutral
    assert look.PRESETS["natural"][1].is_neutral


def test_values_are_clamped_and_a_bad_colour_mode_falls_back():
    p = look.PictureLook(brightness=5, contrast=-3, saturation=9, sharpness=2, color_mode="nonsense")
    assert (p.brightness, p.contrast, p.saturation, p.sharpness) == (0.30, 0.60, 2.0, 1.0)
    assert p.color_mode == "auto"


def test_look_roundtrips_through_settings():
    s = FakeSettings()
    original = look.PictureLook(brightness=0.1, contrast=1.2, saturation=1.4, sharpness=0.35, color_mode="bt601")
    look.save(s, original)
    assert look.load(s) == original


def test_damaged_settings_fall_back_to_the_defaults():
    s = FakeSettings({"look_contrast": "abc", "look_saturation": None, "look_color_mode": "x"})
    loaded = look.load(s)
    assert loaded.contrast == 1.0 and loaded.saturation == 1.0 and loaded.color_mode == "auto"


def test_presets_are_recognised_and_custom_values_are_not():
    for key, (_label, preset) in look.PRESETS.items():
        assert look.matching_preset(preset) == key
    assert look.matching_preset(look.PictureLook(saturation=1.11)) is None
    assert look.PRESETS["vivid"][1].saturation > 1.0 and look.PRESETS["crisp"][1].sharpness > look.PRESETS["vivid"][1].sharpness


# ===================================================================== colour fitting
def to_yuv(rgb: np.ndarray, matrix: str, full: bool, flags=(False, False)) -> YuvFrame:
    """Encode an RGB picture to 4:2:0 YUV with a known conversion (the opposite of what the shader does)."""
    kr, kb = (0.2126, 0.0722) if matrix == "bt709" else (0.299, 0.114)
    kg = 1 - kr - kb
    r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
    y = kr * r + kg * g + kb * b
    u = (b - y) / (2 * (1 - kb))
    v = (r - y) / (2 * (1 - kr))
    if full:
        y, u, v = y, u + 128, v + 128
    else:
        y, u, v = 16 + y * 219 / 255, 128 + u * 224 / 255, 128 + v * 224 / 255
    h, w = y.shape
    sub = lambda p: p.reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3))
    to8 = lambda p: np.clip(np.rint(p), 0, 255).astype(np.uint8)
    return YuvFrame(w, h, to8(y).tobytes(), to8(sub(u)).tobytes(), to8(sub(v)).tobytes(), bt601=flags[0], full_range=flags[1])


def smooth_picture(w=192, h=108) -> np.ndarray:
    xs, ys = np.meshgrid(np.linspace(0, 1, w), np.linspace(0, 1, h))
    rgb = np.stack([255 * xs, 255 * ys, 255 * (1 - xs) * (0.5 + 0.5 * ys)], axis=-1)
    rgb[20:50, 30:90] = (230, 40, 40)
    rgb[60:90, 100:170] = (30, 90, 220)
    return np.clip(rgb, 0, 255).astype(np.uint8)


@pytest.mark.parametrize("matrix,full", [("bt709", False), ("bt601", False), ("bt709", True), ("bt601", True)])
def test_the_true_conversion_gives_the_smallest_error(matrix, full):
    truth = smooth_picture()
    frame = to_yuv(truth, matrix, full)
    errors = colorfit.fit(frame, truth)
    key = matrix + ("_full" if full else "")
    assert min(errors, key=errors.get) == key
    assert errors[key] < 1.5


def test_a_mislabelled_stream_is_corrected():
    truth = smooth_picture()
    frame = to_yuv(truth, "bt601", False, flags=(False, False))        # data is BT.601 but the stream claims BT.709
    best, errors, already_right = colorfit.choose(frame, truth)
    assert best == "bt601" and not already_right
    assert errors["bt709"] > errors["bt601"] + colorfit.SIGNIFICANT


def test_a_correctly_labelled_stream_is_left_alone():
    truth = smooth_picture()
    frame = to_yuv(truth, "bt709", False, flags=(False, False))
    best, _errors, already_right = colorfit.choose(frame, truth)
    assert already_right and best == "bt709"


def test_flagged_mode_reads_the_stream_flags():
    f = YuvFrame(2, 2, bytes(4), bytes(1), bytes(1), bt601=True, full_range=True)
    assert colorfit.flagged_mode(f) == "bt601_full"
    assert colorfit.flagged_mode(YuvFrame(2, 2, bytes(4), bytes(1), bytes(1))) == "bt709"


def test_a_screenshot_of_another_size_is_refused():
    frame = to_yuv(smooth_picture(), "bt709", False)
    with pytest.raises(ValueError):
        colorfit.fit(frame, smooth_picture(100, 60))
