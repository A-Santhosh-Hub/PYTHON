"""GUI test of smart mode (game screen vs menu), hold-to-free key, duplicate keys and extra spots.

Simulated phone: the test shows it a game-like picture (icons where the controls are) or a menu-like picture, and
drives the real window. Nothing reaches a real device. Your own settings and profiles are put back at the end."""
from __future__ import annotations

import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QImage, QRegion  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget  # noqa: E402

from app.logging_setup import setup_logging  # noqa: E402
from fake_phone import FAKE_SIZE, attach_fake_phone, frame_from_gray  # noqa: E402
from app.mapping import layout_edit as le  # noqa: E402
from app.mapping import templates  # noqa: E402
from app.mapping.profile import Binding  # noqa: E402
from app.stream import protocol  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

RESULTS: list[bool] = []
KEY = Qt.Key
W, H = FAKE_SIZE


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}", flush=True)


def hud(seed: int, points) -> np.ndarray:
    """A game-like picture: noisy scenery with a distinctive semi-transparent icon at every control position."""
    rng = np.random.default_rng(seed)
    img = rng.normal(110, 28, (H, W)).clip(0, 255)
    side = int(0.075 * H)
    for index, (x, y) in enumerate(points):
        x0, y0 = max(0, int(x * W - side / 2)), max(0, int(y * H - side / 2))
        icon = np.zeros((side, side))
        icon[:, : side // 3 * (1 + index % 2)] = 235
        icon[index % side :: 4, :] = 20
        region = img[y0:y0 + side, x0:x0 + side]
        region[:] = 0.25 * region + 0.75 * icon[: region.shape[0], : region.shape[1]]
    return img.astype(np.uint8)


def menu(seed: int = 9) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = rng.normal(80, 30, (H, W)).clip(0, 255)
    img[H // 4: H // 2, W // 4: W // 2] = 200                         # a big panel, like a lobby card
    return img.astype(np.uint8)


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
    video, overlay, controls, engine, store = window.video, window.overlay, window.controls, window.engine, window.store

    name = "zz-smart"
    window.store.save(templates.build(templates.BATTLE_ROYALE, name))
    window._refresh_profile_list(name)
    p = window.profile
    points = [(b.x, b.y) for b in p.bindings] + [(p.sticks[0].x, p.sticks[0].y)]

    def show(gray) -> None:
        video.set_frame(frame_from_gray(gray), time.perf_counter())
        pump(0.05)

    def touches() -> list[tuple]:
        out = []
        for m in sent:
            if m[0] == protocol.TYPE_INJECT_TOUCH_EVENT:
                _, action, pid, x, y, tw, th, _p, _ab, _b = struct.unpack(">BBqiiHHHII", m)
                out.append((action, pid, x, y))
        return out

    def pos(nx: float, ny: float) -> QPoint:
        r = video.target_rect()
        return QPoint(round(r.x() + nx * r.width()), round(r.y() + ny * r.height()))

    try:
        # ------------------------------------------------------------------------------------------
        print("1. Learning the game screen")
        check("a new profile starts without smart mode", not p.scene and not controls.smart_check.isChecked())
        controls.smart_check.setChecked(True)
        check("switching it on before learning is refused with advice",
              not controls.smart_check.isChecked() and "Learn the game screen" in controls.hint.text())
        show(np.full((H, W), 100, np.uint8))
        controls.smart_learn_btn.click()
        check("learning on a flat picture is refused (no buttons to recognise)",
              not p.scene and "clear button" in controls.hint.text(), controls.hint.text())
        show(hud(1, points))
        controls.smart_learn_btn.click()
        pump(0.1)
        check("learning on the game picture works and turns smart mode on",
              p.scene and p.scene.get("enabled") and len(p.scene["anchors"]) >= 4 and controls.smart_check.isChecked(),
              f"{len(p.scene['anchors']) if p.scene else 0} anchors")
        check("it is stored in the profile file", store.load(name).scene is not None)
        check("the sidebar says what was learned", "Learned from" in controls.smart_status.text(),
              controls.smart_status.text())

        # ------------------------------------------------------------------------------------------
        print("2. Playing: the game screen")
        window._set_mapping(True)
        pump(0.3)
        check("with the game on screen, keys are on and the mouse is locked for aiming",
              engine.mapping_active and engine.look_captured and not window._scene_paused)
        check("the controls are drawn", len(overlay.bindings) == len(p.bindings) and overlay.active)
        sent.clear()
        QTest.keyClick(window, KEY.Key_R)
        pump(0.3)
        check("pressing R taps the phone", len(touches()) >= 2, str(len(touches())))

        # ------------------------------------------------------------------------------------------
        print("3. A menu appears")
        show(menu())
        pump(1.4)
        check("after a moment smart mode pauses the keys and frees the mouse",
              window._scene_paused and not engine.mapping_active and not engine.look_captured)
        check("the controls are hidden in the menu", overlay.bindings == [] and "SMART MODE" in overlay.banner,
              overlay.banner)
        check("Start playing stays switched on", controls.mapping_btn.isChecked())
        check("the sidebar shows what the app sees", "menu" in controls.smart_status.text(), controls.smart_status.text())
        sent.clear()
        QTest.keyClick(window, KEY.Key_R)
        pump(0.3)
        check("pressing R in a menu does nothing (no accidental taps)", touches() == [])
        QTest.mousePress(video, Qt.MouseButton.LeftButton, pos=pos(0.5, 0.5))
        QTest.mouseRelease(video, Qt.MouseButton.LeftButton, pos=pos(0.5, 0.5))
        pump(0.1)
        acts = [t[0] for t in touches()]
        check("clicking in a menu taps the phone, like a finger",
              acts[:1] == [protocol.TOUCH_DOWN] and acts[-1:] == [protocol.TOUCH_UP], str(acts))

        # ------------------------------------------------------------------------------------------
        print("4. Back to the game")
        show(hud(2, points))                                          # other scenery behind the same buttons
        pump(1.4)
        check("the keys come back and the mouse locks again",
              engine.mapping_active and engine.look_captured and not window._scene_paused)
        check("the controls are drawn again", len(overlay.bindings) == len(p.bindings))
        sent.clear()
        QTest.keyClick(window, KEY.Key_R)
        pump(0.3)
        check("R works again", len(touches()) >= 2)

        print("5. One odd frame changes nothing")
        show(menu(3))
        pump(0.3)
        show(hud(3, points))
        pump(1.2)
        check("a single odd frame did not pause the keys", engine.mapping_active and not window._scene_paused)

        # ------------------------------------------------------------------------------------------
        print("6. Esc while paused, and starting in a menu")
        show(menu())
        pump(1.4)
        check("(paused again)", window._scene_paused)
        QTest.keyClick(window, KEY.Key_Escape)
        pump(0.2)
        check("Esc stops playing even while paused",
              not controls.mapping_btn.isChecked() and not window._scene_paused and not engine.mapping_active)
        check("the controls are drawn again for editing (not stuck hidden)", len(overlay.bindings) == len(p.bindings))
        window._set_mapping(True)
        pump(0.2)
        check("starting while a menu is showing: keys stay paused at once", window._scene_paused and not engine.mapping_active)
        show(hud(1, points))
        pump(1.4)
        check("and start as soon as the game screen appears", engine.mapping_active and not window._scene_paused)

        print("7. Switching smart mode off")
        controls.smart_check.setChecked(False)
        pump(0.1)
        check("smart mode off while playing keeps the keys on", engine.mapping_active)
        show(menu())
        pump(1.4)
        check("and a menu no longer pauses anything", engine.mapping_active and not window._scene_paused)
        controls.smart_check.setChecked(True)
        pump(1.4)
        check("switching it on again while in a menu pauses", window._scene_paused)
        controls.smart_check.setChecked(False)
        pump(0.2)
        check("switching it off while paused resumes the keys", engine.mapping_active and not window._scene_paused)
        window._set_mapping(False)
        pump(0.1)

        # ------------------------------------------------------------------------------------------
        print("8. Learning is refused while playing")
        controls.smart_check.setChecked(True)
        show(hud(1, points))
        window._set_mapping(True)
        pump(0.3)
        controls.smart_learn_btn.click()
        check("'Learn' while playing asks you to stop first", "Stop playing first" in controls.hint.text())
        window._set_mapping(False)
        pump(0.1)

        # ------------------------------------------------------------------------------------------
        print("9. Hold-to-free key")
        p.add(Binding("Alt+Z", 0.6, 0.6, "tap", "Test"))
        window._profile_changed()
        controls.smart_check.setChecked(False)
        window._set_mapping(True)
        pump(0.3)
        check("(mouse locked)", engine.look_captured)
        QTest.keyPress(window, KEY.Key_Alt)
        pump(0.1)
        check("holding the hold-to-free key frees the mouse", not engine.look_captured)
        sent.clear()
        QTest.keyClick(window, KEY.Key_Z)
        pump(0.3)
        check("Alt+Z combinations still work while it is held", len(touches()) >= 2, str(len(touches())))
        QTest.keyRelease(window, KEY.Key_Alt)
        pump(0.1)
        check("letting go locks the mouse again", engine.look_captured)
        QTest.keyClick(window, KEY.Key_QuoteLeft)
        pump(0.1)
        QTest.keyPress(window, KEY.Key_Alt)
        QTest.keyRelease(window, KEY.Key_Alt)
        pump(0.1)
        check("it never locks a mouse that you had freed yourself", not engine.look_captured)
        QTest.keyClick(window, KEY.Key_QuoteLeft)
        pump(0.1)
        window._set_mapping(False)
        p.remove("Alt+Z")
        window._profile_changed()

        # ------------------------------------------------------------------------------------------
        print("10. Duplicate keys")
        asked: list[tuple] = []
        original = p.find("R")
        spot_before = (original.x, original.y)

        def start_custom(spot, key) -> None:
            QTest.mouseClick(controls.edit_btn, Qt.MouseButton.LeftButton) if not overlay.edit else None
            custom = next(b for b in controls.palette_buttons if b.text().startswith("Any other"))
            QTest.mouseClick(custom, Qt.MouseButton.LeftButton)
            QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=pos(*spot))
            QTest.keyClick(window, key)

        window._ask_key_conflict = lambda n, label, can_both: (asked.append((n, label, can_both)), "cancel")[1]
        start_custom((0.30, 0.30), KEY.Key_R)
        check("a used key asks what to do", asked and asked[0][0] == "R" and asked[0][2] is True, str(asked))
        check("Cancel changes nothing", p.find("R") is original and (original.x, original.y) == spot_before
              and original.also == [] and window._add_state is None)

        window._ask_key_conflict = lambda n, label, can_both: "both"
        count_before = len(p.bindings)
        start_custom((0.30, 0.30), KEY.Key_R)
        check("'Touch both spots' adds an extra spot to the same key",
              len(p.bindings) == count_before and len(original.also) == 1
              and abs(original.also[0][0] - 0.30) < 0.01, str(original.also))
        check("only one control still owns R", [b.input for b in p.bindings].count("R") == 1)
        check("the extra spot is selected", overlay.selection == le.Hit("tap", p.bindings.index(original), "also0"))
        image = QImage(overlay.size(), QImage.Format.Format_ARGB32)
        image.fill(0)
        overlay.render(image, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
        px = pos(0.30, 0.30)
        check("the extra spot is drawn on the picture", image.pixelColor(px.x(), px.y()).alpha() > 0 or
              image.pixelColor(px.x() - 6, px.y()).alpha() > 0)

        window._set_mapping(True)
        pump(0.2)
        sent.clear()
        QTest.keyPress(window, KEY.Key_R)
        pump(0.05)
        downs = [t for t in touches() if t[0] == protocol.TOUCH_DOWN]
        QTest.keyRelease(window, KEY.Key_R)
        pump(0.3)
        check("pressing R now touches both spots at once", len(downs) == 2 and len({d[1] for d in downs}) == 2, str(downs))
        window._set_mapping(False)

        window._ask_key_conflict = lambda n, label, can_both: "replace"
        start_custom((0.45, 0.45), KEY.Key_R)
        new_r = p.find("R")
        check("'Use it for the new spot only' replaces the old control",
              new_r is not original and abs(new_r.x - 0.45) < 0.01 and new_r.also == []
              and [b.input for b in p.bindings].count("R") == 1)

        # swapping when changing a key
        a, b_ = p.find("G"), p.find("Tab")
        la, lb = a.input, b_.input
        window._ask_key_swap = lambda name, mine, other: True
        window._on_rebind(le.Hit("tap", p.bindings.index(a)), "Tab")
        check("changing a key to one that is used offers to swap", a.input == lb and b_.input == la,
              f"{a.input}/{b_.input}")
        window._ask_key_swap = lambda name, mine, other: False
        window._on_rebind(le.Hit("tap", p.bindings.index(a)), la)
        check("declining the swap changes nothing", a.input == lb and b_.input == la)

        # ------------------------------------------------------------------------------------------
        print("11. Adding an extra spot from the right-click menu")
        fire = p.find("LMB")
        index = p.bindings.index(fire)
        window._begin_also(le.Hit("tap", index))
        check("it asks you to click the extra spot", window._add_state == "also" and "extra spot" in overlay.banner,
              overlay.banner)
        QTest.mouseClick(video, Qt.MouseButton.LeftButton, pos=pos(0.2, 0.3))
        check("the click adds it and ends the flow", len(fire.also) == 1 and window._add_state is None
              and abs(fire.also[0][0] - 0.2) < 0.01, str(fire.also))
        check("it was saved", store.load(name).find("LMB").also != [])
        sw = p.find("Tab")
        sw.set_mode("swipe")
        window._begin_also(le.Hit("tap", p.bindings.index(sw)))
        check("a swipe key cannot take extra spots", window._add_state is None and "hold" in controls.hint.text(),
              controls.hint.text())
        window._delete_hit(le.Hit("tap", index, "also0"))
        check("deleting an extra spot keeps the control", p.find("LMB") is fire and fire.also == [])

        # ------------------------------------------------------------------------------------------
        print("12. Hotkey list")
        check("the hold-to-free key is listed in Shortcuts and defaults to Alt",
              window.hotkeys["suspend"] == "Alt" and "suspend" in controls.hotkey_buttons)
        window._on_hotkey_key("suspend", "Ctrl")
        check("a modifier the profile already uses (Ctrl = walk) is refused", window.hotkeys["suspend"] == "Alt"
              and "used by a control" in controls.hint.text(), controls.hint.text())
        p.sticks[0].walk_key = ""
        window._on_hotkey_key("suspend", "Ctrl")
        check("a free modifier such as Ctrl is accepted for it", window.hotkeys["suspend"] == "Ctrl")
        window._on_hotkey_key("capture", "Alt")
        check("but ordinary hotkeys cannot", window.hotkeys["capture"] == "F8")
        window._reset_hotkeys()
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
