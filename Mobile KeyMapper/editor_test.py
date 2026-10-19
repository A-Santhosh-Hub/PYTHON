"""Test of the drag-and-drop layout editor with real Qt mouse/keyboard events.

The phone is connected only to get the picture. Every touch the app would send is intercepted and recorded, never
forwarded, so a game running on the phone is not affected.
"""
from __future__ import annotations

import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.logging_setup import setup_logging  # noqa: E402
from fake_phone import connect_window  # noqa: E402
from app.mapping.profile import Profile  # noqa: E402
from app.stream import protocol  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

TEST_PROFILE = "zz-editor-test"
RESULTS: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}", flush=True)


def main() -> int:
    setup_logging()
    app = QApplication([])
    app.setStyleSheet(theme.STYLE_SHEET)
    window = MainWindow()
    window.show()
    window.raise_()
    window.activateWindow()

    def pump(seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.004)

    mode = connect_window(window, pump)
    print(f"  (phone: {mode})")
    check("connected and receiving video", window.video.frame_size() != (0, 0))
    pump(0.8)

    sent: list[bytes] = []
    window.worker.control.send = lambda data: (sent.append(data), True)[1]       # swallow: nothing reaches the phone

    def touches() -> list[tuple]:
        out = []
        for m in sent:
            if m[0] == protocol.TYPE_INJECT_TOUCH_EVENT:
                _, action, pid, x, y, w, h, _p, _ab, _b = struct.unpack(">BBqiiHHHII", m)
                out.append((action, pid, x, y, w, h))
        return out

    previous = str(window.settings.value("profile", "Default"))
    window.store.save(Profile(TEST_PROFILE))
    window._refresh_profile_list(TEST_PROFILE)
    video, overlay, controls = window.video, window.overlay, window.controls
    window.router.window = type("A", (), {"isActiveWindow": staticmethod(lambda: True)})()

    def pos(nx: float, ny: float) -> QPoint:
        r = video.target_rect()
        return QPoint(round(r.x() + nx * r.width()), round(r.y() + ny * r.height()))

    def norm(point: QPoint) -> tuple[float, float]:
        r = video.target_rect()
        return (point.x() - r.x()) / r.width(), (point.y() - r.y()) / r.height()

    def palette(text_start: str) -> None:
        button = next(b for b in controls.palette_buttons if b.text().startswith(text_start))
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        pump(0.1)

    def drag(from_pos: QPoint, to_pos: QPoint) -> None:
        QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=from_pos)
        for i in range(1, 9):
            QTest.mouseMove(overlay, QPoint(from_pos.x() + (to_pos.x() - from_pos.x()) * i // 8,
                                            from_pos.y() + (to_pos.y() - from_pos.y()) * i // 8))
            pump(0.01)
        QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=to_pos)
        pump(0.1)

    p = window.profile

    # ---- A: palette -------------------------------------------------------------------------
    print("A. Palette: adding controls")
    QTest.mouseClick(controls.edit_btn, Qt.MouseButton.LeftButton)
    check("Edit layout turns the editor on", overlay.edit and window.overlay.edit_profile is p)
    for text in ("Fire", "Aim", "Reload", "Next weapon", "Prev. weapon", "Walk", "Look"):
        palette(text)
    check("Fire / Scope / Reload added with default keys and modes",
          [(b.input, b.mode) for b in p.bindings[:3]] == [("LMB", "hold"), ("RMB", "tap"), ("R", "tap")],
          str([(b.input, b.mode) for b in p.bindings]))
    check("wheel controls added", {"WheelUp", "WheelDown"} <= {b.input for b in p.bindings})
    check("WASD stick and mouse-look area added",
          len(p.sticks) == 1 and len(p.looks) == 1 and p.sticks[0].keys["up"] == "W")
    spots = {(round(b.x, 2), round(b.y, 2)) for b in p.bindings}
    check("new markers are not stacked on each other", len(spots) == len(p.bindings))
    check("saved to disk", len(window.store.load(TEST_PROFILE).bindings) == len(p.bindings))
    palette("Fire")
    fire = p.find("LMB")
    check("adding Fire again does not duplicate: it selects the existing one and says so",
          [b.input for b in p.bindings].count("LMB") == 1 and window._add_state is None
          and window._selection is not None and window._selection.index == p.bindings.index(fire)
          and "already have" in window.controls.hint.text(), window.controls.hint.text())
    QTest.keyClick(window, Qt.Key.Key_Escape)
    check("Esc leaves nothing half-done", window._add_state is None)

    # ---- B: dragging -------------------------------------------------------------------------
    print("B. Dragging markers")
    r_binding = p.find("R")
    start = pos(r_binding.x, r_binding.y)
    drag(start, pos(0.76, 0.84))
    nx, ny = norm(pos(0.76, 0.84))
    check("dragging the Reload marker moves it", abs(r_binding.x - nx) < 0.01 and abs(r_binding.y - ny) < 0.01,
          f"now ({r_binding.x:.3f}, {r_binding.y:.3f})")
    check("the move was saved", abs(window.store.load(TEST_PROFILE).find("R").x - r_binding.x) < 1e-3)

    stick = p.sticks[0]
    drag(pos(stick.x, stick.y), pos(0.14, 0.68))
    check("dragging the stick moves it", abs(stick.x - 0.14) < 0.02 and abs(stick.y - 0.68) < 0.02,
          f"({stick.x:.3f}, {stick.y:.3f})")
    old_radius = stick.radius
    r_px = stick.radius * min(video.target_rect().width(), video.target_rect().height())
    drag(pos(stick.x + r_px / video.target_rect().width(), stick.y),
         pos(stick.x + 2.2 * r_px / video.target_rect().width(), stick.y))
    check("dragging a key node resizes the stick", stick.radius > old_radius * 1.6, f"{old_radius:.3f} -> {stick.radius:.3f}")

    look = p.looks[0]
    w0 = look.x1 - look.x0
    drag(pos(look.x1, look.y1), pos(look.x1 + 0.08, look.y1 + 0.06))
    check("dragging the camera-box corner resizes it", (look.x1 - look.x0) > w0 + 0.05, f"{w0:.2f} -> {look.x1 - look.x0:.2f}")
    cx, cy = (look.x0 + look.x1) / 2, (look.y0 + look.y1) / 2 + 0.05
    before = (look.x0, look.y0)
    drag(pos(cx, cy), pos(cx - 0.05, cy - 0.05))
    check("dragging the camera-box body moves it", look.x0 < before[0] - 0.03 and look.y0 < before[1] - 0.03)

    # ---- C: rebinding -------------------------------------------------------------------------
    print("C. Changing keys")
    point = pos(r_binding.x, r_binding.y)
    QTest.mouseDClick(overlay, Qt.MouseButton.LeftButton, pos=point)
    check("double-click asks for a new key", window._add_state == "capture")
    QTest.keyClick(window, Qt.Key.Key_G)
    check("Reload is now on G", r_binding.input == "G" and p.find("R") is None)
    window._ask_key_swap = lambda name, mine, other: False                    # declining the swap = "refused"
    QTest.mouseDClick(overlay, Qt.MouseButton.LeftButton, pos=pos(r_binding.x, r_binding.y))
    QTest.mouseClick(video, Qt.MouseButton.RightButton)
    check("a key already in use is refused", r_binding.input == "G" and window._add_state is None)
    QTest.mouseDClick(overlay, Qt.MouseButton.LeftButton, pos=pos(r_binding.x, r_binding.y))
    QTest.mouseClick(video, Qt.MouseButton.MiddleButton)
    check("a mouse button can be assigned", r_binding.input == "MMB")

    palette("Any other")
    check("Custom waits for a click on the game screen", window._add_state == "place")
    QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=pos(0.30, 0.30))
    check("then it waits for the key", window._add_state == "key")
    QTest.keyClick(window, Qt.Key.Key_Q)
    q = p.find("Q")
    check("a custom key was added exactly where it was clicked", q is not None and abs(q.x - 0.30) < 0.01
          and abs(q.y - 0.30) < 0.01)
    window.profile.bindings = [b for b in p.bindings if b.input != "WheelUp"]
    window._on_layout_edited()
    palette("Any other")
    QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=pos(0.36, 0.30))
    wheel = QWheelEvent(QPointF(video.width() / 2, video.height() / 2), QPointF(video.mapToGlobal(QPoint(5, 5))),
                        QPoint(0, 0), QPoint(0, 120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(video, wheel)
    check("scrolling the wheel assigns WheelUp", p.find("WheelUp") is not None)

    # ---- D: delete ----------------------------------------------------------------------------
    print("D. Deleting")
    q = p.find("Q")
    QTest.mouseClick(overlay, Qt.MouseButton.LeftButton, pos=pos(q.x, q.y))
    check("clicking a marker selects it", window._selection is not None and window._selection.kind == "tap")
    QTest.keyClick(window, Qt.Key.Key_Delete)
    check("Delete removes the selected marker", p.find("Q") is None)
    QTest.mouseClick(overlay, Qt.MouseButton.LeftButton, pos=pos(0.97, 0.03))
    QTest.keyClick(window, Qt.Key.Key_Delete)
    check("Delete with nothing selected does nothing", p.find("MMB") is not None)

    # ---- E: running it ------------------------------------------------------------------------
    print("E. Mapping with the new layout (touches are intercepted)")
    QTest.keyClick(window, Qt.Key.Key_F9)
    pump(0.3)
    check("F9 leaves the editor and turns mapping on", not overlay.edit and window.engine.mapping_active)
    sent.clear()
    down_binding = p.find("WheelDown")
    for _ in range(4):                                                      # a smooth wheel: 4 x 30 = one notch
        QApplication.sendEvent(video, QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, -30),
                                                  Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                                  Qt.ScrollPhase.NoScrollPhase, False))
    pump(0.15)
    downs = [t for t in touches() if t[0] == protocol.TOUCH_DOWN]
    ups = [t for t in touches() if t[0] == protocol.TOUCH_UP]
    w, h = window.worker.video_size
    check("one wheel notch = one tap at the WheelDown point",
          len(downs) == 1 and len(ups) == 1 and abs(downs[0][2] - down_binding.x * w) <= 1
          and abs(downs[0][3] - down_binding.y * h) <= 1, f"{len(downs)} down, {len(ups)} up")
    sent.clear()
    QApplication.sendEvent(video, QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, 120),
                                              Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                              Qt.ScrollPhase.NoScrollPhase, False))
    pump(0.15)
    d2 = [t for t in touches() if t[0] == protocol.TOUCH_DOWN]
    up_binding = p.find("WheelUp")
    check("wheel up taps the WheelUp point", len(d2) == 1 and abs(d2[0][2] - up_binding.x * w) <= 1)
    sent.clear()
    QTest.mousePress(video, Qt.MouseButton.LeftButton)
    pump(0.1)
    QTest.mouseRelease(video, Qt.MouseButton.LeftButton)
    pump(0.1)
    d3 = [t for t in touches() if t[0] == protocol.TOUCH_DOWN]
    fire = p.find("LMB")
    check("left mouse = the Fire marker's position (after dragging)", len(d3) == 1 and abs(d3[0][2] - fire.x * w) <= 1)
    QTest.keyClick(window, Qt.Key.Key_Escape)
    pump(0.2)
    check("Esc releases everything", not window.engine.mapping_active and window.injector.active_count == 0)

    window.store.delete(TEST_PROFILE)
    window._refresh_profile_list(previous)
    window.close()
    pump(0.3)
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
