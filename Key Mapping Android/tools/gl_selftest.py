"""Step-2 test: the OpenGL YUV->RGB path must reproduce a known colour pattern.

Builds an RGB test image, encodes it to BT.709 limited-range YUV420 (as the phone sends),
renders it through VideoWidget and compares the framebuffer with the original.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import av  # noqa: E402
import numpy as np  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.video.frame import frame_to_yuv  # noqa: E402
from app.video.widget import VideoWidget  # noqa: E402

W, H = 270, 600


def make_pattern() -> np.ndarray:
    img = np.zeros((H, W, 3), np.uint8)
    bars = [(255, 255, 255), (255, 255, 0), (0, 255, 255), (0, 255, 0), (255, 0, 255), (255, 0, 0), (0, 0, 255),
            (0, 0, 0), (128, 128, 128), (255, 128, 0)]
    for i, color in enumerate(bars):
        img[i * (H // 2 // len(bars)):(i + 1) * (H // 2 // len(bars)), :] = color
    ramp = np.linspace(0, 255, W, dtype=np.uint8)
    img[H // 2:, :, 0] = ramp
    img[H // 2:, :, 1] = ramp[::-1]
    img[H // 2:, :, 2] = 128
    return img


def main() -> int:
    app = QApplication(sys.argv)
    rgb = make_pattern()
    src = av.VideoFrame.from_ndarray(rgb, format="rgb24")
    yuv = src.reformat(format="yuv420p", dst_colorspace=1, dst_color_range=1)     # BT.709, limited
    frame = frame_to_yuv(yuv)
    print(f"frame: {frame.width}x{frame.height} bt601={frame.bt601} full_range={frame.full_range}")

    widget = VideoWidget()
    widget.setFixedSize(W, H)
    widget.show()
    widget.set_frame(frame, time.perf_counter())
    for _ in range(10):
        app.processEvents()
        time.sleep(0.05)
    grabbed = widget.grabFramebuffer()
    if len(sys.argv) > 1:
        grabbed.save(sys.argv[1])
        from PySide6.QtGui import QImage
        QImage(rgb.data, W, H, W * 3, QImage.Format.Format_RGB888).save(sys.argv[1].replace('.png', '_src.png'))
    img = grabbed.convertToFormat(grabbed.Format.Format_RGB888)
    ptr = img.constBits()
    out = np.frombuffer(ptr, np.uint8).reshape(img.height(), img.bytesPerLine())[:, : img.width() * 3]
    out = out.reshape(img.height(), img.width(), 3)
    print(f"framebuffer: {img.width()}x{img.height()} (device pixel ratio {widget.devicePixelRatioF()})")
    if out.shape != rgb.shape:
        print("size differs from source (HiDPI scaling); resampling comparison skipped -> use 100% scaling")
        return 1
    diff = np.abs(out.astype(int) - rgb.astype(int))
    # chroma subsampling blurs colour at bar edges, so judge the middle of each bar
    bar = H // 2 // 10
    interior = np.concatenate([diff[i * bar + 8:(i + 1) * bar - 8, 20:W - 20].ravel() for i in range(10)])
    print(f"mean abs error (bar centres): {interior.mean():.2f}   max: {interior.max()}")
    print(f"mean abs error (gradient)   : {diff[H // 2 + 5:].mean():.2f}")
    ok = interior.mean() < 2.0 and diff[H // 2 + 5:].mean() < 4.0
    print("PASS" if ok else "FAIL")
    widget.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
