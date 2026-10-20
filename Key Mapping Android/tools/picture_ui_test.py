"""GUI test of the picture settings: quality presets (up to Ultra / Max), the picture-look sliders, 'Apply now', and
the colour check against a phone screenshot. Simulated phone: nothing reaches a real device. Your own settings are put
back at the end."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.device.adb import AdbError, DeviceInfo  # noqa: E402
from app.logging_setup import setup_logging  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.main_window import DEFAULT_MBPS, QUALITY_PRESETS, MainWindow  # noqa: E402
from app.video import colorfit, look as look_mod  # noqa: E402
from app.video.frame import YuvFrame  # noqa: E402
from fake_phone import FAKE_SIZE, attach_fake_phone  # noqa: E402

RESULTS: list[bool] = []
W, H = FAKE_SIZE


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}", flush=True)


def colourful_frame(matrix: str, flagged_601: bool) -> YuvFrame:
    """A colourful picture encoded with `matrix` (limited range), possibly mislabelled in the flags."""
    xs, ys = np.meshgrid(np.linspace(0, 1, W), np.linspace(0, 1, H))
    rgb = np.stack([255 * xs, 255 * ys, 255 * (1 - xs) * (0.5 + 0.5 * ys)], axis=-1)
    rgb[100:300, 200:700] = (230, 40, 40)
    rgb[400:700, 900:1500] = (30, 90, 220)
    kr, kb = (0.2126, 0.0722) if matrix == "bt709" else (0.299, 0.114)
    kg = 1 - kr - kb
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    y = kr * r + kg * g + kb * b
    u, v = (b - y) / (2 * (1 - kb)), (r - y) / (2 * (1 - kr))
    y, u, v = 16 + y * 219 / 255, 128 + u * 224 / 255, 128 + v * 224 / 255
    sub = lambda p: p.reshape(H // 2, 2, W // 2, 2).mean(axis=(1, 3))
    to8 = lambda p: np.clip(np.rint(p), 0, 255).astype(np.uint8).tobytes()
    return YuvFrame(W, H, to8(y), to8(sub(u)), to8(sub(v)), bt601=flagged_601)


def png_of(rgb: np.ndarray) -> bytes:
    image = QImage(np.ascontiguousarray(rgb.astype(np.uint8)).data, rgb.shape[1], rgb.shape[0], rgb.shape[1] * 3,
                   QImage.Format.Format_RGB888)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def main() -> int:
    setup_logging()
    app = QApplication([])
    app.setStyleSheet(theme.STYLE_SHEET)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    window = MainWindow()
    snapshot = {k: window.settings.value(k) for k in window.settings.allKeys()}
    window.show()
    window.raise_()

    def pump(seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.004)

    panel = window.look_panel
    try:
        print("1. Quality presets")
        check("Ultra and Max presets exist", {"ultra", "max"} <= set(QUALITY_PRESETS))
        check("the bitrate can go up to 100 Mbps", window.bitrate_spin.maximum() == 100)
        check("the sharp preset is the recommended default for new installs", DEFAULT_MBPS == 16)
        for key, (_label, size, fps, mbps) in QUALITY_PRESETS.items():
            window.quality_combo.setCurrentIndex(window.quality_combo.findData(key))
            window._apply_quality_preset(key)
            got = (window.res_combo.currentData(), window.fps_combo.currentData(), window.bitrate_spin.value())
            check(f"preset '{key}' sets size / fps / bitrate", got == (size, fps, mbps) and
                  window.quality_combo.currentData() == key, str(got))
        window.bitrate_spin.setValue(37)
        check("a hand-made value shows as Custom", window.quality_combo.currentData() == "custom")
        check("the stream config carries the new values", window._stream_config().bit_rate == 37_000_000)
        window._apply_quality_preset("ultra")
        check("'original' resolution means the phone's own size", window._stream_config().max_size == 0)

        print("2. Picture look")
        attach_fake_phone(window)
        pump(0.3)
        check("a neutral look is the starting point", window.video.look().is_neutral and
              panel.preset_combo.currentData() == "natural")
        panel.sliders["saturation"].setValue(160)
        check("moving a slider changes the picture at once", abs(window.video.look().saturation - 1.6) < 1e-6)
        check("the preset box shows Custom", panel.preset_combo.currentData() == "custom")
        check("the value label follows", panel.value_labels["saturation"].text() == "160 %")
        panel.preset_combo.setCurrentIndex(panel.preset_combo.findData("vivid"))
        panel._on_preset()
        vivid = look_mod.PRESETS["vivid"][1]
        check("the Vivid preset sets all four sliders", window.video.look() == vivid and
              panel.sliders["sharpness"].value() == round(vivid.sharpness * 100), str(window.video.look()))
        panel.sliders["brightness"].setValue(10)
        check("brightness is stored as a fraction", abs(window.video.look().brightness - 0.10) < 1e-6)
        check("the look is saved in the settings file", abs(float(window.settings.value("look_brightness")) - 0.10) < 1e-6)
        panel.reset_btn.click()
        check("Reset puts everything back", window.video.look().is_neutral and panel.sliders["contrast"].value() == 100)

        print("3. Remembered across a restart")
        panel.sliders["contrast"].setValue(120)
        panel.color_combo.setCurrentIndex(panel.color_combo.findData("bt601"))
        panel._on_slider()
        window2 = MainWindow()
        check("a new window starts with the saved look", abs(window2.video.look().contrast - 1.2) < 1e-6
              and window2.video.look().color_mode == "bt601")
        window2.close()
        window._reset_all_settings()
        check("Reset all settings restores a neutral picture", window.video.look().is_neutral
              and window.video.look().color_mode == "auto")

        print("4. Apply now")
        check("Apply is only available while connected", window.apply_stream_btn.isEnabled())
        check("the quality boxes stay usable while connected", window.stream_box.isEnabled() and window.quality_combo.isEnabled())
        started: list = []
        window.devices = [DeviceInfo("FAKE-PHONE", "device", "fake")]
        window._wanted_serial = "FAKE-PHONE"
        window._start_worker = lambda device: started.append(device.serial)
        worker = window.worker
        window._apply_stream_now()
        check("Apply asks the connection to stop and remembers to come back", window._reapply)
        window._on_worker_finished(worker)
        check("when it has stopped, it reconnects at once with the new settings", started == ["FAKE-PHONE"]
              and not window._reapply, str(started))

        print("5. Colour check against a phone screenshot")
        attach_fake_phone(window)
        pump(0.2)

        def run_check(frame: YuvFrame, truth: np.ndarray | None, error: str | None = None) -> str:
            window.video.set_frame(frame, time.perf_counter())
            pump(0.15)
            window.adb.screencap = (lambda serial, timeout=20: (_ for _ in ()).throw(AdbError(error))) if error \
                else (lambda serial, timeout=20: png_of(truth))
            window._match_colours()
            return panel.match_btn.text()

        good = colourful_frame("bt709", False)
        text = run_check(good, colorfit.render(good, "bt709"))
        check("a correct stream is reported as matching and left alone",
              text.startswith("Colours already match") and window.video.look().color_mode == "auto", text)
        bad = colourful_frame("bt601", False)                              # data is BT.601, stream claims BT.709
        text = run_check(bad, colorfit.render(bad, "bt601"))
        check("a mislabelled stream is fixed", text.startswith("Fixed") and window.video.look().color_mode == "bt601"
              and panel.color_combo.currentData() == "bt601", text)
        panel.reset_btn.click()
        text = run_check(good, np.zeros((H, W, 3)))
        check("a black screenshot (blocked by the game) is explained", "blocks screenshots" in text, text)
        text = run_check(good, np.random.default_rng(1).integers(0, 255, (H, W, 3)))
        check("a screenshot of a different picture is not trusted", "moving too much" in text, text)
        check("...and changed nothing", window.video.look().color_mode == "auto")
        text = run_check(good, None, error="adb failed")
        check("a failing screenshot is reported, not a crash", "Could not check" in text, text)
        window._reset_match_text()
    finally:
        window._set_mapping(False)
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
