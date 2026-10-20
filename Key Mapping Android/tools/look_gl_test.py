"""GPU test of the picture controls: renders the real VideoWidget and measures the pixels it draws.

Checks saturation, brightness, contrast, sharpness, the colour-conversion override and that shrinking a big picture into
a small window is filtered (mipmaps) instead of aliased. No phone needed."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import av  # noqa: E402
import numpy as np  # noqa: E402
from PySide6.QtOpenGL import QOpenGLTexture  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.video.frame import frame_to_yuv  # noqa: E402
from app.video.look import PictureLook  # noqa: E402
from app.video.widget import VideoWidget  # noqa: E402

RESULTS: list[bool] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}", flush=True)


def to_frame(rgb: np.ndarray, colorspace: int = 1):
    """RGB picture -> a frame as the phone would send it (limited range). colorspace 1 = BT.709, 5 = BT.601."""
    src = av.VideoFrame.from_ndarray(np.ascontiguousarray(rgb), format="rgb24")
    return frame_to_yuv(src.reformat(format="yuv420p", dst_colorspace=colorspace, dst_color_range=1))


def main() -> int:
    app = QApplication(sys.argv)

    def render(widget: VideoWidget, frame, look: PictureLook) -> np.ndarray:
        widget.set_look(look)
        widget.set_frame(frame, time.perf_counter())
        for _ in range(8):
            app.processEvents()
            time.sleep(0.03)
        image = widget.grabFramebuffer().convertToFormat(widget.grabFramebuffer().Format.Format_RGB888)
        data = np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.bytesPerLine())
        return data[:, : image.width() * 3].reshape(image.height(), image.width(), 3).astype(np.float32).copy()

    # ---------------------------------------------------------------- colour controls on flat patches
    W, H = 320, 180
    widget = VideoWidget()
    widget.setFixedSize(W, H)
    widget.show()
    patches = np.zeros((H, W, 3), np.uint8)
    patches[:, :80] = (200, 60, 60)         # red
    patches[:, 80:160] = (60, 160, 70)      # green
    patches[:, 160:240] = (110, 110, 110)   # mid grey
    patches[:, 240:] = (60, 90, 200)        # blue
    frame = to_frame(patches)
    base = render(widget, frame, PictureLook())
    if base.shape[:2] != (H, W):
        print(f"framebuffer is {base.shape[1]}x{base.shape[0]} (display scaling); size-based checks skipped")
        return 0
    mid = lambda img, x: img[H // 2 - 10:H // 2 + 10, x - 10:x + 10].reshape(-1, 3).mean(axis=0)
    spread = lambda px: float(px.max() - px.min())
    print("1. Colour controls")
    check("neutral look reproduces the picture", np.abs(base - patches.astype(np.float32))[:, 5:75].mean() < 3,
          f"{np.abs(base - patches.astype(np.float32))[:, 5:75].mean():.2f}")
    grey = render(widget, frame, PictureLook(saturation=0.0))
    check("saturation 0 makes colours grey", all(spread(mid(grey, x)) < 3 for x in (40, 120, 280)),
          f"spread red {spread(mid(grey, 40)):.1f}")
    check("saturation 0 leaves grey alone", abs(mid(grey, 200).mean() - mid(base, 200).mean()) < 3)
    vivid = render(widget, frame, PictureLook(saturation=1.6))
    check("saturation 1.6 makes colours stronger", spread(mid(vivid, 40)) > spread(mid(base, 40)) + 20,
          f"{spread(mid(base, 40)):.0f} -> {spread(mid(vivid, 40)):.0f}")
    bright = render(widget, frame, PictureLook(brightness=0.15))
    check("brightness +0.15 lifts the grey by about 38", 32 < (mid(bright, 200).mean() - mid(base, 200).mean()) < 44,
          f"+{mid(bright, 200).mean() - mid(base, 200).mean():.1f}")
    contrast = render(widget, frame, PictureLook(contrast=1.5))
    expect = (mid(base, 200).mean() - 127.5) * 1.5 + 127.5
    check("contrast 1.5 pushes the grey away from the middle", abs(mid(contrast, 200).mean() - expect) < 4,
          f"{mid(contrast, 200).mean():.0f} (expected {expect:.0f})")
    widget.set_look(PictureLook())
    widget.close()

    # ---------------------------------------------------------------- sharpness
    print("2. Sharpness")
    widget = VideoWidget()
    widget.setFixedSize(W, H)
    widget.show()
    edge = np.zeros((H, W, 3), np.uint8)
    edge[:, :160] = 90
    edge[:, 160:] = 170
    frame = to_frame(edge)
    plain = render(widget, frame, PictureLook())
    sharp = render(widget, frame, PictureLook(sharpness=0.6))
    row = H // 2
    check("a plain edge has no overshoot", plain[row, 150:160, 1].min() > 85 and plain[row, 160:170, 1].max() < 175,
          f"{plain[row, 150:160, 1].min():.0f} / {plain[row, 160:170, 1].max():.0f}")
    check("sharpening adds crispness at the edge (dark side darker, bright side brighter)",
          sharp[row, 150:160, 1].min() < plain[row, 150:160, 1].min() - 8
          and sharp[row, 160:170, 1].max() > plain[row, 160:170, 1].max() + 8,
          f"{sharp[row, 150:160, 1].min():.0f} / {sharp[row, 160:170, 1].max():.0f}")
    check("sharpening leaves flat areas alone", abs(sharp[row, 20:100, 1].mean() - plain[row, 20:100, 1].mean()) < 1.5)
    widget.close()

    # ---------------------------------------------------------------- colour conversion override
    print("3. Colour conversion override")
    widget = VideoWidget()
    widget.setFixedSize(W, H)
    widget.show()
    frame601 = to_frame(patches, colorspace=5)
    frame601.bt601 = False                                   # the stream wrongly claims BT.709
    wrong = render(widget, frame601, PictureLook())
    fixed = render(widget, frame601, PictureLook(color_mode="bt601"))
    err = lambda img: float(np.abs(img - patches.astype(np.float32))[:, 5:75].mean())
    check("a mislabelled stream shows wrong colours in automatic mode", err(wrong) > 3.5, f"error {err(wrong):.1f}")
    check("forcing BT.601 puts them right", err(fixed) < 3, f"error {err(fixed):.1f}")
    widget.close()

    # ---------------------------------------------------------------- shrinking a big picture
    print("4. Shrinking a big picture into a small window")
    BW, BH, SW, SH = 1920, 864, 640, 288                    # exactly 3:1
    rng = np.random.default_rng(3)
    noise = rng.integers(0, 256, (BH, BW, 1), dtype=np.uint8).repeat(3, axis=2)
    ideal = noise[..., 1].astype(np.float32).reshape(SH, 3, SW, 3).mean(axis=(1, 3))      # what a perfect resize gives
    widget = VideoWidget()
    widget.setFixedSize(SW, SH)
    widget.show()
    big = to_frame(noise)
    filtered = render(widget, big, PictureLook())
    if filtered.shape[:2] == (SH, SW):
        mae = lambda img: float(np.abs(img[..., 1] - ideal).mean())
        mip = mae(filtered)
        for tex in widget._textures:                         # the old behaviour: plain bilinear, no mipmaps
            tex.setMinMagFilters(QOpenGLTexture.Filter.Linear, QOpenGLTexture.Filter.Linear)
        plain = mae(render(widget, big, PictureLook()))
        check("mipmapped shrinking is closer to a perfect resize than plain bilinear", mip < plain * 0.8,
              f"error {mip:.1f} vs {plain:.1f}")
    else:
        print("  (skipped: display scaling changes the framebuffer size)")
    widget.close()

    passed = sum(RESULTS)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
