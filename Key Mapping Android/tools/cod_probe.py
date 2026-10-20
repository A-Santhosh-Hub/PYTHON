"""Presses unknown COD Mobile buttons through the app and records a rapid burst of frames after each press,
so the effect (jump, crouch, ...) can be seen. Usage: cod_probe.py <sheet.png> <label=nx,ny> [<label=nx,ny> ...]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.logging_setup import setup_logging  # noqa: E402
from app.mapping.profile import Binding  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

COD_PACKAGE = "com.activision.callofduty.shooter"
FRAMES, GAP = 8, 0.11
SHOW = (0, 2, 4, 7)            # frames shown in the sheet (all frames are measured)


def vertical_shift(a: QImage, b: QImage) -> int:
    """How many pixels the middle of the picture moved down (+) or up (-) between two frames."""
    def profile(img):
        g = img.convertToFormat(QImage.Format.Format_Grayscale8)
        arr = np.frombuffer(g.constBits(), np.uint8).reshape(g.height(), g.bytesPerLine())[:, : g.width()]
        h, w = arr.shape
        strip = arr[:, int(w * 0.34):int(w * 0.62)].astype(np.float32).mean(axis=1)
        return strip - strip.mean(), h
    pa, h = profile(a)
    pb, _ = profile(b)
    lo, hi = int(h * 0.16), int(h * 0.60)
    best, best_score = 0, -1e18
    for shift in range(-int(h * 0.12), int(h * 0.12) + 1):
        seg_a = pa[lo:hi]
        seg_b = pb[lo + shift:hi + shift]
        score = float((seg_a * seg_b).sum() / (np.linalg.norm(seg_a) * np.linalg.norm(seg_b) + 1e-6))
        if score > best_score:
            best, best_score = shift, score
    return -best


def main() -> int:
    sheet_path = sys.argv[1]
    probes = []
    for arg in sys.argv[2:]:
        label, pos = arg.split("=")
        x, y = pos.split(",")
        probes.append((label, float(x), float(y)))
    setup_logging()
    app = QApplication([])
    app.setStyleSheet(theme.STYLE_SHEET)
    window = MainWindow()
    window.show()
    window.raise_()
    window.activateWindow()

    def pump(seconds: float) -> None:
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            app.processEvents()
            time.sleep(0.003)

    end = time.time() + 15
    while not any(d.usable for d in window.devices) and time.time() < end:
        pump(0.2)
    window._toggle_connection()
    end = time.time() + 15
    while window.video.frame_size() == (0, 0) and time.time() < end:
        pump(0.1)
    end = time.time() + 8
    while window.current_package != COD_PACKAGE and time.time() < end:
        pump(0.2)
    if window.current_package != COD_PACKAGE or window.video.frame_size()[0] <= window.video.frame_size()[1]:
        print("COD is not in the foreground in landscape - sending no input.")
        window.close()
        return 3
    if not window.isActiveWindow():
        print("SKIP: app window has no focus.")
        window.close()
        return 2
    video, engine = window.video, window.engine
    keys = [Qt.Key.Key_F5, Qt.Key.Key_F6, Qt.Key.Key_F7, Qt.Key.Key_F10]
    for (label, x, y), key in zip(probes, keys):
        window.profile.add(Binding(key.name.replace("Key_", ""), x, y, "tap", label))
    window._profile_changed()
    window._set_mapping(True)
    window._set_capture(False)                           # cursor stays free for this probe

    def frame() -> QImage:
        return video.grabFramebuffer().copy(video.target_rect().toRect())

    rows: list[tuple[str, list[QImage]]] = []
    for (label, x, y), key in zip(probes, keys):
        pump(1.0)
        frames = [frame()]
        QTest.keyPress(window, key)
        pump(0.07)
        QTest.keyRelease(window, key)
        for _ in range(FRAMES - 1):
            pump(GAP)
            frames.append(frame())
        rows.append((label, frames))
        pump(1.2)

    window._set_mapping(False)
    for (label, _, _), key in zip(probes, keys):
        window.profile.remove(key.name.replace("Key_", ""))
    window._profile_changed()
    window.close()
    pump(0.3)

    for label, frames in rows:
        print(f"{label:14s} vertical shift of the scene vs. before (px, + = down): "
              + "  ".join(f"{vertical_shift(frames[0], f):+d}" for f in frames[1:]))
    cw = 500
    size = rows[0][1][0].size()
    ch = round(cw * size.height() / size.width())
    sheet = QImage(len(SHOW) * cw, len(rows) * ch, QImage.Format.Format_RGB32)
    sheet.fill(QColor("black"))
    painter = QPainter(sheet)
    font = QFont("Segoe UI", 9)
    font.setBold(True)
    painter.setFont(font)
    for r, (label, frames) in enumerate(rows):
        for col, c in enumerate(SHOW):
            img = frames[c]
            painter.drawImage(QRect(col * cw, r * ch, cw, ch), img)
            painter.fillRect(QRect(col * cw, r * ch, cw, 18), QColor(0, 0, 0, 190))
            painter.setPen(QColor("#ffe45c"))
            painter.drawText(QRect(col * cw + 4, r * ch, cw, 18), Qt.AlignmentFlag.AlignVCenter,
                             f"{label}  {'before' if c == 0 else f'+{c * (GAP + 0.003):.2f}s'}")
    painter.end()
    sheet.save(sheet_path)
    print("saved", sheet_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
