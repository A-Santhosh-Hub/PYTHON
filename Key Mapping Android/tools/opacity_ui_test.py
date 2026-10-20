"""GUI test of the key-marker opacity feature (hotkeys F2 / F3 / F4, the Settings slider, real rendered pixels).
Simulated phone: no touch reaches any real device. Your own settings and profiles are put back at the end."""
from __future__ import annotations

import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QImage, QRegion  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget  # noqa: E402

from app.logging_setup import setup_logging  # noqa: E402
from fake_phone import attach_fake_phone  # noqa: E402
from app.mapping import templates  # noqa: E402
from app.stream import protocol  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

RESULTS: list[bool] = []
KEY = Qt.Key


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

    attach_fake_phone(window)
    pump(0.4)
    sent: list[bytes] = []
    window.worker.control.send = lambda data: (sent.append(data), True)[1]
    window.router.window = type("A", (), {"isActiveWindow": staticmethod(lambda: True)})()
    overlay, dialog, engine = window.overlay, window.settings_dialog, window.engine
    name = "zz-opacity"
    window.store.save(templates.build(templates.BATTLE_ROYALE, name))
    window._refresh_profile_list(name)
    window._set_marker_opacity(100, toast=False)

    def touches() -> int:
        return sum(1 for m in sent if m[0] == protocol.TYPE_INJECT_TOUCH_EVENT)

    def layer() -> QImage:
        """The overlay drawn on a transparent image (no widget background)."""
        image = QImage(overlay.size(), QImage.Format.Format_ARGB32)
        image.fill(0)
        overlay.render(image, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
        return image

    def painted() -> tuple[int, int]:
        """(number of non-transparent pixels, strongest alpha) of the overlay layer."""
        overlay.show_toast("")
        image = layer()
        count, top = 0, 0
        for y in range(0, image.height(), 2):
            for x in range(0, image.width(), 2):
                alpha = image.pixelColor(x, y).alpha()
                if alpha:
                    count += 1
                    top = max(top, alpha)
        return count, top

    try:
        print("1. Hotkeys")
        check("three opacity hotkeys exist with default keys F2 / F3 / F4",
              (window.hotkeys["opacity_down"], window.hotkeys["opacity_up"], window.hotkeys["markers"])
              == ("F2", "F3", "F4"))
        check("they are listed in Settings > Shortcuts and can be rebound",
              {"opacity_down", "opacity_up", "markers"} <= set(window.controls.hotkey_buttons))
        window._set_mapping(True)
        pump(0.3)
        check("mapping is on", engine.mapping_active)
        sent.clear()
        full_count, full_top = painted()
        check("at 100 % the markers are drawn", full_count > 200 and overlay.effective_opacity() == 1.0,
              f"{full_count} px, alpha {full_top}")

        QTest.keyClick(window, KEY.Key_F2)
        pump(0.05)
        check("F2 makes the markers 10 % more transparent", window.marker_opacity == 90
              and abs(overlay.effective_opacity() - 0.9) < 1e-6, str(window.marker_opacity))
        for _ in range(4):
            QTest.keyClick(window, KEY.Key_F2)
        pump(0.05)
        half_count, half_top = painted()
        check("at 50 % the markers are fainter than at 100 %", window.marker_opacity == 50 and half_top < full_top,
              f"alpha {half_top} < {full_top}")
        for _ in range(8):
            QTest.keyClick(window, KEY.Key_F2)
        pump(0.05)
        check("it stops at 0 % (never negative)", window.marker_opacity == 0)
        zero_count, _ = painted()
        check("at 0 % nothing at all is drawn", zero_count == 0, f"{zero_count} px")
        overlay.show_toast("Key markers 0 %")
        image = layer()
        seen = any(image.pixelColor(x, y).alpha() for y in range(image.height() - 70, image.height() - 30, 2)
                   for x in range(0, image.width(), 4))
        check("the popup with the level is still drawn at 0 %, so you know what you pressed", seen)
        overlay.show_toast("")

        QTest.keyClick(window, KEY.Key_F3)
        check("F3 makes them 10 % more visible", window.marker_opacity == 10)
        for _ in range(12):
            QTest.keyClick(window, KEY.Key_F3)
        check("it stops at 100 %", window.marker_opacity == 100)

        print("2. Hide / show")
        window._set_marker_opacity(60, toast=False)
        QTest.keyClick(window, KEY.Key_F4)
        check("F4 hides the markers", window.marker_opacity == 0)
        QTest.keyClick(window, KEY.Key_F4)
        check("F4 again brings back the level you had (60 %)", window.marker_opacity == 60)

        print("3. The keys keep working while the markers are invisible")
        window._set_marker_opacity(0, toast=False)
        sent.clear()
        QTest.keyClick(window, KEY.Key_R)
        pump(0.3)
        n_r = touches()
        check("pressing R still taps the phone at 0 %", n_r >= 2, f"{n_r} touch messages")
        sent.clear()
        QTest.keyClick(window, KEY.Key_F2)
        QTest.keyClick(window, KEY.Key_F3)
        QTest.keyClick(window, KEY.Key_F4)
        pump(0.2)
        check("the opacity hotkeys are never sent to the phone", touches() == 0, f"{touches()} touches")

        print("4. Only while playing")
        window._set_mapping(False)
        pump(0.2)
        check("with mapping off the markers are fully visible so you can set up keys",
              overlay.effective_opacity() == 1.0)
        window._set_marker_opacity(30, toast=False)
        window._set_mapping(True)
        pump(0.2)
        check("playing uses the chosen level again", abs(overlay.effective_opacity() - 0.3) < 1e-6)
        window._set_mapping(False)
        window.controls.edit_btn.setChecked(True)
        pump(0.2)
        check("editing the layout always shows the markers fully", overlay.effective_opacity() == 1.0)
        window.controls.edit_btn.setChecked(False)
        pump(0.1)

        print("5. Settings slider and memory")
        dialog.opacity_slider.setValue(75)
        check("the Settings slider sets the opacity", window.marker_opacity == 75)
        window._set_marker_opacity(20, toast=False)
        check("the slider follows the hotkeys", dialog.opacity_slider.value() == 20
              and dialog.opacity_value.text() == "20 %")
        check("the level is saved in the settings file", int(window.settings.value("marker_opacity")) == 20)

        print("6. Rebinding and reset")
        window._on_hotkey_key("opacity_down", "F6")
        check("the 'more transparent' key can be changed to F6", window.hotkeys["opacity_down"] == "F6")
        window._on_hotkey_key("opacity_up", "F6")
        check("a key already used by another hotkey is refused", window.hotkeys["opacity_up"] == "F3")
        window._reset_hotkeys()
        check("Reset hotkeys restores F2 / F3 / F4", (window.hotkeys["opacity_down"], window.hotkeys["opacity_up"],
                                                      window.hotkeys["markers"]) == ("F2", "F3", "F4"))
        window._reset_all_settings()
        check("Reset all settings puts the opacity back to 100 %", window.marker_opacity == 100)
    finally:
        window._set_mapping(False)
        window.store.delete(name)
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
