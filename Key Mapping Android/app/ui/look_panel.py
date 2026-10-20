"""Settings > Picture > 'Picture look': presets and sliders for brightness, contrast, saturation and sharpness, the
colour-conversion choice and the 'match colours to the phone' button. Everything here applies at once."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QGridLayout, QGroupBox, QLabel, QPushButton, QSlider, QVBoxLayout

from ..video import look as look_mod
from ..video.look import PictureLook


class LookPanel(QGroupBox):
    lookChanged = Signal(object)          # PictureLook
    matchRequested = Signal()

    # (key, caption, slider range as whole numbers, scale to the real value, text of a value)
    ROWS = (
        ("brightness", "Brightness", (-30, 30), 0.01, lambda v: f"{v:+d}"),
        ("contrast", "Contrast", (60, 160), 0.01, lambda v: f"{v} %"),
        ("saturation", "Colour strength", (0, 200), 0.01, lambda v: f"{v} %"),
        ("sharpness", "Sharpness", (0, 100), 0.01, lambda v: f"{v} %"),
    )

    def __init__(self) -> None:
        super().__init__("Picture look")
        self._silent = False
        self._look = PictureLook()

        note = QLabel("A phone's own screen is often brighter and more colourful than a PC monitor, even when the picture "
                      "is identical. These settings change only how the picture is drawn here, at once, and never touch "
                      "the stream.")
        note.setObjectName("muted")
        note.setWordWrap(True)

        self.preset_combo = QComboBox()
        for key, (label, _preset) in look_mod.PRESETS.items():
            self.preset_combo.addItem(label, key)
        self.preset_combo.addItem("Custom (set below)", "custom")
        self.preset_combo.activated.connect(self._on_preset)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.sliders: dict[str, QSlider] = {}
        self.value_labels: dict[str, QLabel] = {}
        for row, (key, caption, (low, high), _scale, fmt) in enumerate(self.ROWS):
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(low, high)
            slider.setSingleStep(1)
            slider.setPageStep(5)
            value = QLabel("")
            value.setMinimumWidth(46)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            slider.valueChanged.connect(lambda v, k=key, f=fmt, lab=value: (lab.setText(f(v)), self._on_slider()))
            grid.addWidget(QLabel(caption), row, 0)
            grid.addWidget(slider, row, 1)
            grid.addWidget(value, row, 2)
            grid.setColumnStretch(1, 1)
            self.sliders[key] = slider
            self.value_labels[key] = value

        self.color_combo = QComboBox()
        for key, label in look_mod.COLOR_MODES.items():
            self.color_combo.addItem(label, key)
        self.color_combo.setToolTip("How the phone's video colours are decoded. Leave on 'Automatic' unless colours look\n"
                                    "wrong (for example a green or purple tint).")
        self.color_combo.activated.connect(lambda _i: self._on_slider())
        self.match_btn = QPushButton("Check the colours against the phone screen")
        self.match_btn.setToolTip("Takes a screenshot of the phone (the exact pixels) and compares it with the video to\n"
                                  "pick the right colour conversion. Works best on a still screen such as the home screen.")
        self.match_btn.clicked.connect(self.matchRequested)
        self.match_btn.setEnabled(False)
        self.reset_btn = QPushButton("Reset picture look")
        self.reset_btn.clicked.connect(lambda: self.set_look(PictureLook(), emit=True))

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(note)
        layout.addWidget(self.preset_combo)
        layout.addLayout(grid)
        layout.addWidget(QLabel("Colour conversion"))
        layout.addWidget(self.color_combo)
        layout.addWidget(self.match_btn)
        layout.addWidget(self.reset_btn)
        self.set_look(PictureLook())

    # -- API ---------------------------------------------------------------------------------------
    def look(self) -> PictureLook:
        return self._look

    def set_connected(self, connected: bool) -> None:
        self.match_btn.setEnabled(connected)

    def set_look(self, look: PictureLook, emit: bool = False) -> None:
        """Show `look` in the controls. Only emits lookChanged when asked to (loading settings must not re-save)."""
        self._silent = True
        try:
            for key, _caption, _range, scale, fmt in self.ROWS:
                self.sliders[key].setValue(round(getattr(look, key) / scale))
                self.value_labels[key].setText(fmt(self.sliders[key].value()))
            self.color_combo.setCurrentIndex(max(0, self.color_combo.findData(look.color_mode)))
        finally:
            self._silent = False
        self._look = self._read()
        self._show_preset()
        if emit:
            self.lookChanged.emit(self._look)

    # -- internals ---------------------------------------------------------------------------------
    def _read(self) -> PictureLook:
        values = {key: self.sliders[key].value() * scale for key, _c, _r, scale, _f in self.ROWS}
        return PictureLook(color_mode=self.color_combo.currentData(), **values)

    def _show_preset(self) -> None:
        match = look_mod.matching_preset(self._look)
        self.preset_combo.setCurrentIndex(self.preset_combo.findData(match or "custom"))

    def _on_slider(self) -> None:
        if self._silent:
            return
        self._look = self._read()
        self._show_preset()
        self.lookChanged.emit(self._look)

    def _on_preset(self) -> None:
        key = self.preset_combo.currentData()
        if key in look_mod.PRESETS:
            preset = look_mod.PRESETS[key][1]
            self.set_look(preset.with_values(color_mode=self._look.color_mode), emit=True)
