"""Renders the real window (simulated phone, edit mode with the key palette open) at several sizes to PNG files, so the
layout can be checked by eye. usage: ui_shots.py <output-folder>. Nothing is sent anywhere; settings are restored."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.logging_setup import setup_logging  # noqa: E402
from fake_phone import attach_fake_phone  # noqa: E402
from app.mapping import templates  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

SIZES = [(1920, 1040), (1180, 820), (1060, 700)]


def main() -> int:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    setup_logging()
    app = QApplication([])
    app.setStyleSheet(theme.STYLE_SHEET)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    window = MainWindow()
    snapshot = {k: window.settings.value(k) for k in window.settings.allKeys()}
    window.show()

    def pump(seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.005)

    attach_fake_phone(window)
    pump(0.3)
    name = "zz-ui-shots"
    window.store.save(templates.build(templates.BATTLE_ROYALE, name))
    window._refresh_profile_list(name)
    try:
        window.controls.edit_btn.setChecked(True)
        pump(0.3)
        for w, h in SIZES:
            window.resize(w, h)
            pump(0.5)
            window.grab().save(str(out / f"edit_{w}x{h}.png"))
            print(f"{w}x{h}: sidebar {window.sidebar.width()} px wide, scroll {window.sidebar.scroll.verticalScrollBar().maximum()} px")
        window.resize(1060, 700)
        window.controls.edit_btn.setChecked(False)
        pump(0.3)
        before = window.sidebar.scroll.verticalScrollBar().value()
        window.controls.edit_btn.setChecked(True)
        pump(0.4)
        sb = window.sidebar.scroll.verticalScrollBar()
        print(f"auto-scroll when the editor opens at 1060x700: {before} -> {sb.value()} of {sb.maximum()}")
        window.grab().save(str(out / "edit_autoscroll_1060x700.png"))
        window.controls.set_hint("You already have 'Fire' on LMB. It is selected on the picture: drag it to move it, "
                                 "or press Delete to remove it.")
        window.resize(1180, 820)
        pump(0.4)
        window.grab().save(str(out / "edit_hint.png"))
    finally:
        window.store.delete(name)
        window._refresh_profile_list(str(snapshot.get("profile", "Default")))
        for key in window.settings.allKeys():
            if key not in snapshot:
                window.settings.remove(key)
        for key, value in snapshot.items():
            window.settings.setValue(key, value)
        window.settings.sync()
        window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
