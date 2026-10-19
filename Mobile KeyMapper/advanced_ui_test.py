"""GUI test of the advanced keyboard and mouse controls, on a simulated phone (no hardware, nothing is injected).

Covers: adding swipe / zoom / multi-tap / repeat / toggle / double controls with the click-then-key flow, combination
keys (Shift+W) captured through the real router, stick sprint / walk / auto-run keys, the Options dialog, the battle
royale template, and the real keyboard path (router -> engine -> touch messages) for sprint and scope-aware aiming.
Your own settings and profiles are put back at the end.
"""
from __future__ import annotations

import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint, Qt, QTimer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox  # noqa: E402

from app.logging_setup import setup_logging  # noqa: E402
from fake_phone import attach_fake_phone  # noqa: E402
from app.mapping import templates  # noqa: E402
from app.stream import protocol  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.binding_options import BindingOptionsDialog  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

RESULTS: list[bool] = []
KEY = Qt.Key
MOD = Qt.KeyboardModifier


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}", flush=True)


def main() -> int:
    setup_logging()
    app = QApplication([])
    app.setStyleSheet(theme.STYLE_SHEET)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    window = MainWindow()
    snapshot = {k: window.settings.value(k) for k in window.settings.allKeys()}
    window.show()
    window.raise_()
    window.activateWindow()

    def pump(seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.004)

    attach_fake_phone(window)                                           # always the simulated phone
    pump(0.4)
    sent: list[bytes] = []
    window.worker.control.send = lambda data: (sent.append(data), True)[1]
    window.router.window = type("A", (), {"isActiveWindow": staticmethod(lambda: True)})()
    video, overlay, controls, store, engine = window.video, window.overlay, window.controls, window.store, window.engine
    created: list[str] = []

    def pos(nx: float, ny: float) -> QPoint:
        r = video.target_rect()
        return QPoint(round(r.x() + nx * r.width()), round(r.y() + ny * r.height()))

    def new_profile(name: str, template: str) -> None:
        def drive():
            dialog = app.activeModalWidget()
            dialog.name_edit.setText(name)
            dialog.template_combo.setCurrentIndex(dialog.template_combo.findData(template))
            dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
        QTimer.singleShot(250, drive)
        window._new_profile()
        created.append(name)

    def touches() -> list[tuple]:
        out = []
        for m in sent:
            if m[0] == protocol.TYPE_INJECT_TOUCH_EVENT:
                _, action, pid, x, y, tw, th, _p, _ab, _b = struct.unpack(">BBqiiHHHII", m)
                out.append((action, pid, x, y))
        return out

    def add_via_palette(kind: str, clicks: list[tuple[float, float]], key, modifier=MOD.NoModifier) -> None:
        controls.addControl.emit(kind)
        for point in clicks:
            QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=pos(*point))
            pump(0.05)
        QTest.keyClick(window, key, modifier)
        pump(0.05)

    try:
        # ---- 1. adding the new kinds of control -------------------------------------------------
        print("1. Add controls with the click-then-key flow")
        new_profile("zz-adv-empty", templates.EMPTY)
        p = window.profile
        check("starts empty", not p.bindings)
        QTest.mouseClick(controls.edit_btn, Qt.MouseButton.LeftButton)
        check("the palette has a 'More controls' menu",
              controls.more_btn.menu() is not None and len(controls.more_btn.menu().actions()) == 8)

        controls.addControl.emit("swipe")
        check("swipe asks for the start first", window._add_state == "place" and "STARTS" in overlay.banner,
              overlay.banner)
        QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=pos(0.2, 0.5))
        check("then for the end", window._add_state == "place" and "ENDS" in overlay.banner, overlay.banner)
        QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=pos(0.6, 0.4))
        check("then for the key", window._add_state == "key", overlay.banner)
        QTest.keyClick(window, KEY.Key_Q)
        b = p.find("Q")
        check("Q is a swipe from A to B", b is not None and b.mode == "swipe" and abs(b.x - 0.2) < 0.01
              and abs(b.x2 - 0.6) < 0.01 and abs(b.y2 - 0.4) < 0.01, str(b))

        add_via_palette("pinch-out", [(0.5, 0.5)], KEY.Key_Plus)
        check("a zoom control is stored", any(x.mode == "pinch-out" for x in p.bindings))

        controls.addControl.emit("sequence")
        for point in ((0.1, 0.2), (0.2, 0.3), (0.3, 0.4)):
            QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=pos(*point))
            pump(0.05)
        check("multi-tap keeps collecting spots", window._add_state == "key" and len(window._add_points) == 3)
        QTest.keyClick(window, KEY.Key_F)
        f = p.find("F")
        check("F is a 3-point multi-tap", f is not None and f.mode == "sequence" and len(f.steps) == 3, str(f))

        add_via_palette("repeat", [(0.7, 0.6)], KEY.Key_X)
        add_via_palette("toggle", [(0.8, 0.6)], KEY.Key_T)
        add_via_palette("double", [(0.9, 0.6)], KEY.Key_V)
        check("repeat, toggle and double are stored",
              [p.find(k).mode for k in ("X", "T", "V")] == ["repeat", "toggle", "double"])
        check("every change was saved to disk", store.load(p.name).find("F").mode == "sequence")

        # ---- 2. combination keys ------------------------------------------------------------------
        print("2. Combination keys")
        controls.addControl.emit("custom")
        QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=pos(0.35, 0.8))
        QTest.keyClick(window, KEY.Key_R, MOD.ControlModifier)
        check("Ctrl+R is captured as one combination key", p.find("Ctrl+R") is not None,
              str([x.input for x in p.bindings]))
        controls.addControl.emit("custom")
        QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=pos(0.4, 0.8))
        QTest.keyClick(window, KEY.Key_Shift)
        check("Shift pressed alone is captured as 'Shift'", p.find("Shift") is not None)

        # ---- 3. the Options dialog ----------------------------------------------------------------
        print("3. Options dialog")
        rep = p.find("X")
        dialog = BindingOptionsDialog(rep, window)
        check("the dialog opens for a repeat key", dialog.windowTitle() != "")
        dialog.rate_spin.setValue(20)
        dialog.scope_check.setChecked(True)
        dialog.apply(rep)
        check("Apply writes the values back", rep.rate_hz == 20 and rep.scope, f"rate={rep.rate_hz} scope={rep.scope}")
        dialog.close()

        # ---- 4. battle royale template + stick extras ---------------------------------------------
        print("4. Battle royale template")
        new_profile("zz-adv-br", templates.BATTLE_ROYALE)
        p = window.profile
        s = p.sticks[0]
        check("template has sprint = Shift, walk = Ctrl", s.sprint_key == "Shift" and s.walk_key == "Ctrl")
        check("panel shows the sprint key", controls.stick_extra_btns["sprint"].text() == "Shift"
              and controls.stick_extra_btns["walk"].text() == "Ctrl")
        controls.stickExtraCleared.emit("walk")
        check("the walk key can be cleared", p.sticks[0].walk_key == "" and
              controls.stick_extra_btns["walk"].text() == "not set")
        controls.stickExtraRequested.emit("autorun")
        QTest.keyClick(window, KEY.Key_B)
        pump(0.05)
        check("auto-run key can be set (B)", p.sticks[0].autorun_key == "B", p.sticks[0].autorun_key)
        controls.stickExtraRequested.emit("walk")
        QTest.keyClick(window, KEY.Key_W)
        check("a stick key cannot be reused for walk", p.sticks[0].walk_key == "", p.sticks[0].walk_key)
        controls.stickExtraRequested.emit("walk")
        QTest.keyClick(window, KEY.Key_Control)
        check("walk is set to Ctrl again", p.sticks[0].walk_key == "Ctrl")
        controls.stickExtraCleared.emit("autorun")

        # ---- 5. real keyboard path ----------------------------------------------------------------
        print("5. Playing: sprint and scope-aware aiming through the real router")
        window.profile.orientation = "landscape"
        window._set_edit_mode(False) if overlay.edit else None
        window._set_mapping(True)
        pump(0.1)
        sent.clear()
        QTest.keyPress(window, KEY.Key_W)
        pump(0.25)
        walk = touches()
        QTest.keyPress(window, KEY.Key_Shift)
        pump(0.25)
        QTest.keyRelease(window, KEY.Key_Shift)
        QTest.keyRelease(window, KEY.Key_W)
        pump(0.2)
        all_touches = touches()
        ys = [t[3] for t in all_touches if t[0] == protocol.TOUCH_MOVE]
        check("W alone starts the stick", len(walk) > 0)
        stick_y = round(p.sticks[0].y * 864)
        deepest = max((abs(y - stick_y) for y in ys), default=0)
        normal = round(p.sticks[0].radius * 864)
        check("holding Shift pushes the stick further than the normal radius", deepest > normal + 5,
              f"deepest={deepest}px normal={normal}px")
        check("releasing everything lifts the finger", all_touches[-1][0] == protocol.TOUCH_UP,
              str(all_touches[-1:]))
        sent.clear()
        window._set_mapping(False)

    finally:
        window._set_mapping(False)
        for name in created:
            try:
                store.delete(name)
            except Exception:
                pass
        window._refresh_profile_list(str(snapshot.get("profile", "Default")))
        for key in window.settings.allKeys():
            if key not in snapshot:
                window.settings.remove(key)
        for key, value in snapshot.items():
            window.settings.setValue(key, value)
        window.settings.sync()
        window.close()

    passed = sum(RESULTS)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
