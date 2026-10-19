"""GUI test of the ~ key: it frees / locks the mouse while playing (like GameLoop), alongside F8.
Simulated phone: nothing reaches a real device. Your own settings and profiles are put back at the end."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox  # noqa: E402

from app.logging_setup import setup_logging  # noqa: E402
from fake_phone import attach_fake_phone  # noqa: E402
from app.mapping import templates  # noqa: E402
from app.stream import protocol  # noqa: E402
from app.ui import theme  # noqa: E402
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

    attach_fake_phone(window)
    pump(0.4)
    sent: list[bytes] = []
    window.worker.control.send = lambda data: (sent.append(data), True)[1]
    window.router.window = type("A", (), {"isActiveWindow": staticmethod(lambda: True)})()
    engine = window.engine
    name = "zz-tilde"
    window.store.save(templates.build(templates.BATTLE_ROYALE, name))
    window._refresh_profile_list(name)

    def touches() -> int:
        return sum(1 for m in sent if m[0] == protocol.TYPE_INJECT_TOUCH_EVENT)

    try:
        check("the ~ key is a hotkey next to F8", window.hotkeys["cursor"] == "`" and window.hotkeys["capture"] == "F8")
        check("it is shown to the user as ~ (not as a backtick)",
              window.controls.hotkey_buttons["cursor"].text() == "~", window.controls.hotkey_buttons["cursor"].text())
        window._set_mapping(True)
        pump(0.3)
        check("playing starts with the mouse locked for aiming", engine.look_captured)
        check("the on-screen text names the key", "~" in window.overlay.banner and "~" in window.controls.capture_btn.text(),
              window.overlay.banner)
        sent.clear()
        QTest.keyClick(window, KEY.Key_QuoteLeft)
        pump(0.1)
        check("pressing ~ frees the mouse", not engine.look_captured)
        check("the banner now says the cursor is free", "cursor free" in window.overlay.banner, window.overlay.banner)
        before = touches()
        engine.look_delta(40, 0)
        pump(0.1)
        check("while free, mouse movement does not turn the camera", touches() == before)
        QTest.keyClick(window, KEY.Key_QuoteLeft)
        pump(0.1)
        check("pressing ~ again locks it for aiming", engine.look_captured)
        QTest.keyClick(window, KEY.Key_F8)
        pump(0.1)
        check("F8 still works too", not engine.look_captured)
        QTest.keyClick(window, KEY.Key_F8)
        pump(0.1)
        check("and toggles back", engine.look_captured)

        sent.clear()
        QTest.keyClick(window, KEY.Key_QuoteLeft)
        pump(0.1)
        QTest.keyClick(window, KEY.Key_QuoteLeft)
        pump(0.1)
        check("the ~ key is never sent to the phone as a touch", touches() == 0, f"{touches()} touches {[(m[1]) for m in sent if m[0] == protocol.TYPE_INJECT_TOUCH_EVENT]}")

        print("Holding Shift (sprint) while pressing ~")
        QTest.keyPress(window, KEY.Key_Shift)
        QTest.keyClick(window, KEY.Key_AsciiTilde, MOD.ShiftModifier)
        QTest.keyRelease(window, KEY.Key_Shift)
        pump(0.1)
        check("Shift + ~ also frees the mouse", not engine.look_captured)
        QTest.keyClick(window, KEY.Key_QuoteLeft)
        pump(0.1)
        check("(and plain ~ locks it again)", engine.look_captured)

        print("Rebinding")
        window._on_hotkey_key("cursor", "F10")
        check("it can be moved to another key (F10)", window.hotkeys["cursor"] == "F10"
              and "F10" in window.controls.capture_btn.text(), window.controls.capture_btn.text())
        QTest.keyClick(window, KEY.Key_QuoteLeft)
        pump(0.1)
        check("the old ~ key then does nothing as a hotkey", engine.look_captured)
        window._reset_hotkeys()
        check("Reset hotkeys brings ~ back", window.hotkeys["cursor"] == "`")

        print("Typing")
        window._set_mapping(False)
        box = QLineEdit(window)
        box.show()
        box.setFocus()
        pump(0.1)
        QTest.keyClicks(box, "a`b")
        check("a ` can still be typed in a text box (the hotkey does not steal it)", box.text() == "a`b", box.text())
        box.deleteLater()
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
