"""GUI test of: custom key (click the spot, then press the key), new profile templates, Save / Undo / Reset,
section resets, hotkey rebinding and 'Reset all settings', and persistence across an app restart.

The phone is connected only for the picture; every touch is intercepted, so a running game is not affected.
Your own settings are put back at the end.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint, QPointF, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox  # noqa: E402

from app.logging_setup import setup_logging  # noqa: E402
from fake_phone import connect_window  # noqa: E402
from app.mapping import templates  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

RESULTS: list[bool] = []
YES = QMessageBox.StandardButton.Yes


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}", flush=True)


def main() -> int:
    setup_logging()
    app = QApplication([])
    app.setStyleSheet(theme.STYLE_SHEET)
    QMessageBox.question = staticmethod(lambda *a, **k: YES)          # confirmations answer "Yes"
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

    mode = connect_window(window, pump)
    print(f"  (phone: {mode})")
    check("connected and receiving video", window.video.frame_size() != (0, 0))
    window.worker.control.send = lambda data: True                     # swallow every touch
    window.router.window = type("A", (), {"isActiveWindow": staticmethod(lambda: True)})()
    video, overlay, controls, store = window.video, window.overlay, window.controls, window.store
    created: list[str] = []

    def pos(nx: float, ny: float) -> QPoint:
        r = video.target_rect()
        return QPoint(round(r.x() + nx * r.width()), round(r.y() + ny * r.height()))

    def new_profile(name: str, template_index: int) -> None:
        def drive():
            dialog = app.activeModalWidget()
            dialog.name_edit.setText(name)
            dialog.template_combo.setCurrentIndex(template_index)
            dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
        QTimer.singleShot(250, drive)
        window._new_profile()
        created.append(name)

    # ---- 1. new profile with a template ------------------------------------------------------
    print("1. New profile")
    new_profile("zz-ui-standard", 0)
    p = window.profile
    check("the new profile is selected", p.name == "zz-ui-standard")
    check("'Standard shooter' gives the default keys", {"LMB", "RMB", "R", "C", "Space", "Shift", "M", "WheelUp",
                                                        "WheelDown"} <= {b.input for b in p.bindings}
          and len(p.sticks) == 1 and len(p.looks) == 1, f"{len(p.bindings)} keys")
    check("it has a first restore point and says 'Saved'", store.has_checkpoint(p.name)
          and "Saved" in controls.save_label.text(), controls.save_label.text())

    def duplicate_attempt():
        dialog = app.activeModalWidget()
        dialog.name_edit.setText("ZZ-UI-STANDARD")                      # same name, different case
        check("a duplicate name is refused (OK is disabled)",
              not dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled(), dialog.error_label.text())
        dialog.reject()
    QTimer.singleShot(250, duplicate_attempt)
    window._new_profile()

    new_profile("zz-ui-empty", 2)
    p = window.profile
    check("'Empty' gives no controls", not p.bindings and not p.sticks and not p.looks)

    window.raise_()
    window.activateWindow()                                       # dialogs can leave the window without Windows focus
    pump(0.4)
    print(f"  (window has focus: {window.isActiveWindow()})")
    # ---- 2. custom key: click the spot, then press the key ----------------------------------
    print("2. Custom key (click the spot, then press the key)")
    QTest.mouseClick(controls.edit_btn, Qt.MouseButton.LeftButton)
    custom = next(b for b in controls.palette_buttons if b.text().startswith("Any other"))
    QTest.mouseClick(custom, Qt.MouseButton.LeftButton)
    check("Custom asks you to click the spot on the game screen first", window._add_state == "place"
          and "Click the spot" in overlay.banner)
    QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=pos(0.88, 0.13))      # the map button
    check("after the click it waits for the key and shows where the button will be",
          window._add_state == "key" and overlay.preview is not None
          and abs(overlay.preview[0] - 0.88) < 0.01)
    QTest.keyClick(window, Qt.Key.Key_M)
    m = p.find("M")
    check("pressing M creates the M button exactly where you clicked",
          m is not None and abs(m.x - 0.88) < 0.01 and abs(m.y - 0.13) < 0.01 and m.mode == "tap",
          str(m))
    check("it is selected and the editor is ready for the next one", window._selection is not None
          and window._add_state is None and overlay.edit and overlay.preview is None)
    check("it was stored in the profile file", store.load(p.name).find("M") is not None)

    window._ask_key_conflict = lambda name, label, can_both: "replace"        # the question is tested in smart_ui_test
    QTest.mouseClick(custom, Qt.MouseButton.LeftButton)
    QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=pos(0.5, 0.5))
    QTest.keyClick(window, Qt.Key.Key_M)
    moved = p.find("M")
    check("pressing an existing key again MOVES that key to the new spot (no duplicate)", window._add_state is None
          and len([b for b in p.bindings if b.input == "M"]) == 1 and abs(moved.x - 0.5) < 0.01
          and "rebound" in controls.hint.text(), controls.hint.text())
    QTest.mouseClick(custom, Qt.MouseButton.LeftButton)
    QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=pos(0.88, 0.13))
    QTest.keyClick(window, Qt.Key.Key_M)                  # put it back where it belongs
    QTest.mouseClick(custom, Qt.MouseButton.LeftButton)
    QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=pos(0.5, 0.5))
    QTest.keyClick(window, Qt.Key.Key_F9)
    check("a window hotkey (F9) cannot be used as a control key", p.find("F9") is None
          and window.hotkeys["mapping"] == "F9" and not window.engine.mapping_active, controls.hint.text())
    QTest.mouseClick(custom, Qt.MouseButton.LeftButton)
    QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=pos(0.3, 0.3))
    QTest.mouseClick(video, Qt.MouseButton.MiddleButton)
    check("a mouse button can be the key", p.find("MMB") is not None)
    QTest.mouseClick(custom, Qt.MouseButton.LeftButton)
    QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=pos(0.4, 0.3))
    QApplication.sendEvent(video, QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120),
                                              Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                              Qt.ScrollPhase.NoScrollPhase, False))
    check("a wheel direction can be the key", p.find("WheelUp") is not None)
    QTest.mouseClick(custom, Qt.MouseButton.LeftButton)
    state_before_esc = (window._add_state, custom.isEnabled(), overlay.banner[:30])
    QTest.keyClick(window, Qt.Key.Key_Escape)
    check("Esc cancels adding a key", window._add_state is None, f"before Esc {state_before_esc}, after {window._add_state}")

    # ---- 3. save / undo / reset --------------------------------------------------------------
    print("3. Save, Undo changes, Reset")
    check("the profile shows unsaved changes (they are auto-kept)", store.has_unsaved_changes(p)
          and "restore point" in controls.save_label.text())
    n_before = len(p.bindings)
    QTest.mouseClick(controls.undo_btn, Qt.MouseButton.LeftButton)
    p = window.profile
    check("Undo changes returns to the last Save (the empty profile)", not p.bindings and p.find("M") is None,
          f"{n_before} -> {len(p.bindings)} controls")
    check("after Undo the label says Saved", "Saved" in controls.save_label.text())

    QTest.mouseClick(custom, Qt.MouseButton.LeftButton)
    QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=pos(0.88, 0.13))
    QTest.keyClick(window, Qt.Key.Key_M)
    QTest.mouseClick(controls.save_btn, Qt.MouseButton.LeftButton)
    check("Save makes the current controls the restore point", not store.has_unsaved_changes(window.profile)
          and store.load_checkpoint(p.name).find("M") is not None)
    check("Undo is switched off while nothing has changed", not controls.undo_btn.isEnabled())
    window._undo_changes()
    check("...and asking anyway changes nothing", window.profile.find("M") is not None
          and "Nothing to undo" in controls.hint.text())

    QTest.mouseClick(controls.reset_btn, Qt.MouseButton.LeftButton)
    p = window.profile
    check("Reset puts back the standard shooter layout", p.find("LMB") is not None and len(p.sticks) == 1
          and p.find("M") is not None and len(p.bindings) == len(templates.standard_bindings()))
    QTest.mouseClick(controls.undo_btn, Qt.MouseButton.LeftButton)
    check("...and Undo changes still brings the previous controls back", len(window.profile.bindings) == 1
          and window.profile.find("M") is not None)

    # ---- 4. section resets ------------------------------------------------------------------------
    print("4. Section resets")
    window.profile.sticks = [templates.default_stick()]
    window.profile.looks = [templates.default_look()]
    stick, look = window.profile.sticks[0], window.profile.looks[0]
    stick.radius, stick.ramp_ms = 0.2, 200
    look.sens_x, look.sens_y, look.accel, look.invert_y = 5.0, 4.0, 0.9, True
    window._on_layout_edited()
    QTest.mouseClick(controls.stick_reset_btn, Qt.MouseButton.LeftButton)
    check("stick Defaults: radius 9 %, ramp 50 ms, keys WASD", abs(stick.radius - 0.09) < 1e-6 and stick.ramp_ms == 50
          and stick.keys["up"] == "W")
    QTest.mouseClick(controls.look_reset_btn, Qt.MouseButton.LeftButton)
    check("mouse-look Defaults: 1.00 / 1.00, accel 0, invert off", (look.sens_x, look.sens_y, look.accel, look.invert_y)
          == (1.0, 1.0, 0.0, False))

    # ---- 5. hotkeys -----------------------------------------------------------------------------------
    print("5. Hotkeys (shooting mode / mouse lock key)")
    QTest.mouseClick(controls.hotkey_buttons["capture"], Qt.MouseButton.LeftButton)
    check("clicking the hotkey button waits for a key", window._add_state == "capture")
    QTest.keyClick(window, Qt.Key.Key_F7)
    check("the shooting-mode key is now F7", window.hotkeys["capture"] == "F7"
          and controls.hotkey_buttons["capture"].text() == "F7" and "F7" in controls.capture_btn.text())
    check("the choice is stored", str(window.settings.value("hotkey_capture")) == "F7")
    QTest.mouseClick(controls.hotkey_buttons["mapping"], Qt.MouseButton.LeftButton)
    QTest.keyClick(window, Qt.Key.Key_F7)
    check("a hotkey already in use is refused", window.hotkeys["mapping"] == "F9")
    QTest.mouseClick(controls.hotkey_buttons["mapping"], Qt.MouseButton.LeftButton)
    QTest.keyClick(window, Qt.Key.Key_W)
    check("a typing key cannot be a hotkey", window.hotkeys["mapping"] == "F9")
    QTest.mouseClick(controls.hotkey_buttons["fullscreen"], Qt.MouseButton.LeftButton)
    QTest.keyClick(window, Qt.Key.Key_Escape)
    check("Esc cancels choosing a hotkey", window._add_state is None and window.hotkeys["fullscreen"] == "F11")
    btn_before = (controls.mapping_btn.isChecked(), window.engine.mapping_active, window.overlay.edit,
                  {k: s.isEnabled() for k, s in window._hk_shortcuts.items()})
    QTest.keyClick(window, Qt.Key.Key_F9)
    pump(0.3)
    check("F9 (unchanged) still turns key mapping on", window.engine.mapping_active and window.engine.look_captured,
          f"mapping={window.engine.mapping_active} captured={window.engine.look_captured} hint='{controls.hint.text()}' "
          f"orientation={window.profile.orientation} bindings={len(window.profile.bindings)} before F9: {btn_before}")
    QTest.keyClick(window, Qt.Key.Key_F7)
    pump(0.2)
    check("the NEW key F7 frees the mouse", not window.engine.look_captured and window.engine.mapping_active)
    QTest.keyClick(window, Qt.Key.Key_F8)
    pump(0.2)
    check("the OLD key F8 no longer does that", not window.engine.look_captured)
    QTest.keyClick(window, Qt.Key.Key_Escape)
    pump(0.2)
    QTest.mouseClick(controls.hotkeys_reset_btn, Qt.MouseButton.LeftButton)
    check("Reset hotkeys restores the defaults (F8 / F9 / F11 and F2 / F3 / F4)",
          window.hotkeys == {"capture": "F8", "cursor": "`", "mapping": "F9", "fullscreen": "F11", "opacity_down": "F2",
                             "opacity_up": "F3", "markers": "F4", "suspend": "Alt"})

    # ---- 6. reset all settings ------------------------------------------------------------------------
    print("6. Reset all settings")
    window.res_combo.setCurrentIndex(0)
    window.bitrate_spin.setValue(30)
    controls.direct_check.setChecked(False)
    controls.auto_load_check.setChecked(False)
    controls.auto_mapping_check.setChecked(True)
    check("settings were changed", window.bitrate_spin.value() == 30 and not window.engine.direct_touch)
    QTest.mouseClick(controls.reset_all_btn, Qt.MouseButton.LeftButton)
    check("all settings are back to the defaults", window.res_combo.currentData() == 1920
          and window.bitrate_spin.value() == 16 and window.engine.direct_touch and controls.auto_load_check.isChecked()
          and not controls.auto_mapping_check.isChecked() and window.hotkeys["capture"] == "F8")
    check("profiles were not touched", store.exists("zz-ui-empty") and window.profile.find("M") is not None)
    window.res_combo.setCurrentIndex(0)
    check("video options stay usable while connected ('Apply now' reconnects with them)",
          window.reset_video_btn.isEnabled() and window.apply_stream_btn.isEnabled())
    window._reset_video_settings()
    check("'Reset video settings' works on its own", window.res_combo.currentData() == 1920)

    # ---- 7. persistence across a restart -----------------------------------------------------------------
    print("7. Your last controls come back after restarting the app")
    window.profile.add(__import__("app.mapping.profile", fromlist=["Binding"]).Binding("N", 0.3, 0.4, "tap", "Test N"))
    window._profile_changed()
    controls.direct_check.setChecked(False)
    expected = window.profile.to_dict()
    name = window.profile.name
    window.close()
    pump(0.5)
    second = MainWindow()
    second.show()
    pump(0.5)
    check("the same profile is open", second.profile.name == name, second.profile.name)
    check("with exactly the controls you left", second.profile.to_dict() == expected)
    check("'Mouse acts as a finger' kept its value", not second.engine.direct_touch)
    check("the Save status is shown", bool(second.controls.save_label.text()))
    second.close()
    pump(0.3)

    # ---- cleanup: your settings and profiles as they were -------------------------------------------------
    from PySide6.QtCore import QSettings
    from app import paths
    from app.mapping.profile import ProfileStore
    test_store = ProfileStore(paths.data_dir() / "profiles")
    for name in created:
        if test_store.exists(name):
            test_store.delete(name)
    settings = QSettings(str(paths.data_dir() / "settings.ini"), QSettings.Format.IniFormat)
    for key in list(settings.allKeys()):
        settings.remove(key)
    for key, value in snapshot.items():
        settings.setValue(key, value)
    settings.sync()
    pump(0.2)
    failed = RESULTS.count(False)
    print(f"\n{len(RESULTS) - failed}/{len(RESULTS)} checks passed (no touch reached the phone)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
