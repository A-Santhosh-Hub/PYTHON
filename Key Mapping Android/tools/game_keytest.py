"""Live in-game key-mapping test (Battle Prime, landscape).

Presses mapped keys / mouse buttons through the real app and records what the mirrored game shows after
each action, as one contact sheet. Android's "show touches" is enabled so every injected touch is visible.
Usage:  .venv\\Scripts\\python.exe tools\\game_keytest.py <output.png>
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.logging_setup import setup_logging  # noqa: E402
from app.mapping.profile import Binding, Profile  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

PROFILE = "zz-battleprime-test"
# Positions of the on-screen buttons as fractions of the 2400x1080 screen (read from a screenshot).
BINDINGS = [
    Binding("F", 0.856, 0.700, "hold", "Fire"),
    Binding("LMB", 0.856, 0.700, "hold", "Fire (mouse)"),
    Binding("RMB", 0.931, 0.442, "tap", "Aim"),
    Binding("R", 0.761, 0.841, "tap", "Reload"),
    Binding("Space", 0.9475, 0.676, "tap", "Jump"),
    Binding("C", 0.855, 0.898, "tap", "Crouch"),
    Binding("1", 0.4075, 0.894, "tap", "Weapon 1"),
    Binding("2", 0.490, 0.894, "tap", "Weapon 2"),
]


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def main() -> int:
    out_path = sys.argv[1]
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
    profile = Profile(PROFILE, "landscape", list(BINDINGS))
    window.store.save(profile)
    window._refresh_profile_list(PROFILE)
    window._set_mapping(True)
    print("mapping active:", window.engine.mapping_active, "| hint:", window.controls.hint.text(), flush=True)
    video = window.video
    centre = QPoint(video.width() // 2, video.height() // 2)

    shots: list[tuple[str, QImage]] = []

    def snap(caption: str) -> None:
        pump(app, 0.02)
        img = video.grabFramebuffer()
        shots.append((caption, img.copy(video.target_rect().toRect())))

    def key_hold(key, seconds, snap_at, caption):
        QTest.keyPress(window, key)
        pump(app, snap_at)
        snap(caption)
        pump(app, max(0.0, seconds - snap_at))
        QTest.keyRelease(window, key)

    def mouse_hold(button, seconds, snap_at, caption):
        QTest.mousePress(video, button, pos=centre)
        pump(app, snap_at)
        snap(caption)
        pump(app, max(0.0, seconds - snap_at))
        QTest.mouseRelease(video, button, pos=centre)

    def key_tap(key, wait, caption):
        QTest.keyPress(window, key)
        pump(app, 0.08)
        QTest.keyRelease(window, key)
        pump(app, wait)
        snap(caption)

    snap("0 baseline (before any key)")
    key_hold(Qt.Key.Key_F, 1.0, 0.6, "1 key F held: Fire")
    pump(app, 0.5)
    snap("2 after releasing F")
    mouse_hold(Qt.MouseButton.LeftButton, 1.0, 0.6, "3 left mouse held: Fire")
    pump(app, 0.5)
    snap("4 after releasing mouse")
    key_tap(Qt.Key.Key_R, 0.6, "5 R: Reload (0.6 s later)")
    pump(app, 3.0)
    snap("6 reload finished (+3 s)")
    QTest.mouseClick(video, Qt.MouseButton.RightButton, pos=centre)
    pump(app, 0.8)
    snap("7 right mouse: Aim")
    QTest.mouseClick(video, Qt.MouseButton.RightButton, pos=centre)
    pump(app, 0.8)
    snap("8 right mouse again: Aim off")
    key_tap(Qt.Key.Key_C, 0.8, "9 C: Crouch")
    key_tap(Qt.Key.Key_C, 0.8, "10 C again: Stand")
    key_tap(Qt.Key.Key_Space, 0.3, "11 Space: Jump (0.3 s later)")
    key_tap(Qt.Key.Key_2, 1.2, "12 key 2: Weapon 2")
    key_tap(Qt.Key.Key_1, 1.2, "13 key 1: Weapon 1")

    window._set_mapping(False)
    window.store.delete(PROFILE)
    window._refresh_profile_list(previous_profile)
    window.touches_check.setChecked(previous_touches)
    window._save_settings()
    window.close()
    pump(app, 0.5)

    # contact sheet: 3 columns
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
    sheet.save(out_path)
    print("saved", out_path, f"({len(shots)} shots)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
