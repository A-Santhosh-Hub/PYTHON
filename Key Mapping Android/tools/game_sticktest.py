"""Live in-game test of the WASD movement stick (Battle Prime, landscape).

Only the stick is used - no fire, no buttons - so it is safe in a match or in the practice range, but it must
NOT be run on a menu screen (a drag there would be a swipe). Pass --in-match to confirm you are in a match.

Usage:  .venv\\Scripts\\python.exe tools\\game_sticktest.py <output.png> --in-match [--x 0.1265 --y 0.814 --radius 0.09]
"""
from __future__ import annotations

import argparse
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
from app.mapping.profile import Profile, Stick  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

PROFILE = "zz-stick-test"


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.004)


def to_array(img: QImage) -> np.ndarray:
    img = img.convertToFormat(QImage.Format.Format_RGB888)
    buf = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())
    return buf[:, : img.width() * 3].reshape(img.height(), img.width(), 3).astype(np.int16)


def scene_diff(a: QImage, b: QImage) -> float:
    """Mean abs pixel change in the middle of the picture (away from the on-screen controls)."""
    x, y = to_array(a), to_array(b)
    h, w = x.shape[:2]
    box = (slice(int(h * 0.15), int(h * 0.75)), slice(int(w * 0.30), int(w * 0.70)))
    return float(np.abs(x[box] - y[box]).mean())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("output")
    ap.add_argument("--in-match", action="store_true", help="confirm the game is in a match / practice range")
    ap.add_argument("--x", type=float, default=0.1265)
    ap.add_argument("--y", type=float, default=0.814)
    ap.add_argument("--radius", type=float, default=0.09)
    ap.add_argument("--ramp", type=int, default=50)
    args = ap.parse_args()
    if not args.in_match:
        print("Refusing to run: pass --in-match once the game is in a match (not on a menu).")
        return 2

    setup_logging()
    app = QApplication([])
    app.setStyleSheet(theme.STYLE_SHEET)
    window = MainWindow()
    window.show()
    window.activateWindow()
    previous_touches = window.touches_check.isChecked()
    previous_profile = str(window.settings.value("profile", "Default"))
    window.touches_check.setChecked(True)
    end = time.time() + 15
    while not any(d.usable for d in window.devices) and time.time() < end:
        pump(app, 0.2)
    window._toggle_connection()
    end = time.time() + 15
    while window.video.frame_size() == (0, 0) and time.time() < end:
        pump(app, 0.1)
    size = window.video.frame_size()
    print("video size:", size, flush=True)
    if size == (0, 0):
        return 1
    pump(app, 1.0)
    if not window.isActiveWindow():
        window.router.window = type("Active", (), {"isActiveWindow": staticmethod(lambda: True)})()

    profile = Profile(PROFILE, "landscape" if size[0] > size[1] else "portrait")
    profile.set_stick(Stick(args.x, args.y, radius=args.radius, ramp_ms=args.ramp))
    window.store.save(profile)
    window._refresh_profile_list(PROFILE)
    window._set_mapping(True)
    print("mapping active:", window.engine.mapping_active, "| hint:", window.controls.hint.text(), flush=True)
    video = window.video
    shots: list[tuple[str, QImage]] = []

    def snap(caption: str) -> QImage:
        pump(app, 0.02)
        img = video.grabFramebuffer().copy(video.target_rect().toRect())
        shots.append((caption, img))
        return img

    results: dict[str, float] = {}

    def move(label: str, keys: list, hold: float = 1.4) -> None:
        start = snap(f"{label} - start")
        for key in keys:
            QTest.keyPress(window, key)
        pump(app, hold * 0.7)
        mid = snap(f"{label} - held")
        pump(app, hold * 0.3)
        for key in reversed(keys):
            QTest.keyRelease(window, key)
        results[label] = scene_diff(start, mid)
        pump(app, 0.6)

    idle_a = snap("idle - start")
    pump(app, 1.0)
    idle_b = snap("idle - 1 s later")
    results["idle (no keys)"] = scene_diff(idle_a, idle_b)
    move("W forward", [Qt.Key.Key_W])
    move("S backward", [Qt.Key.Key_S])
    move("A left", [Qt.Key.Key_A])
    move("D right", [Qt.Key.Key_D])
    move("W+D diagonal", [Qt.Key.Key_W, Qt.Key.Key_D])
    after_a = snap("after release - start")
    pump(app, 1.0)
    after_b = snap("after release - 1 s later")
    results["after release (should stop)"] = scene_diff(after_a, after_b)

    print(f"touches still down: {window.injector.active_count}")
    window._set_mapping(False)
    window.store.delete(PROFILE)
    window._refresh_profile_list(previous_profile)
    window.touches_check.setChecked(previous_touches)
    window._save_settings()
    window.close()
    pump(app, 0.5)

    print("\nscene change (mean pixel difference, higher = more movement):")
    for label, value in results.items():
        print(f"  {label:30s} {value:6.2f}")

    cols, cw = 3, 760
    ch = round(cw * size[1] / size[0])
    rows = (len(shots) + cols - 1) // cols
    sheet = QImage(cols * cw, rows * ch, QImage.Format.Format_RGB32)
    sheet.fill(QColor("#000000"))
    painter = QPainter(sheet)
    font = QFont("Segoe UI", 11)
    font.setBold(True)
    painter.setFont(font)
    for i, (caption, img) in enumerate(shots):
        x, y = (i % cols) * cw, (i // cols) * ch
        painter.drawImage(QRect(x, y, cw, ch), img)
        painter.fillRect(QRect(x, y, cw, 26), QColor(0, 0, 0, 190))
        painter.setPen(QColor("#ffe45c"))
        painter.drawText(QRect(x + 8, y, cw - 8, 26), Qt.AlignmentFlag.AlignVCenter, caption)
    painter.end()
    sheet.save(args.output)
    print("saved", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
