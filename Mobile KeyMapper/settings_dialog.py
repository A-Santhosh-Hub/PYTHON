"""The Settings window: everything technical, in plain-language tabs, out of the way of the main screen."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QGroupBox, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QSlider, QTabWidget, QVBoxLayout, QWidget)


def _page(*widgets: QWidget, stretch: bool = True) -> QScrollArea:
    """A scrolling page holding the given widgets one under the other."""
    holder = QWidget()
    layout = QVBoxLayout(holder)
    layout.setContentsMargins(4, 8, 8, 8)
    layout.setSpacing(12)
    for widget in widgets:
        layout.addWidget(widget)
    if stretch:
        layout.addStretch(1)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(holder)
    return scroll


def _note(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(True)
    return label


class SettingsDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.setWindowTitle("Settings")
        self.resize(620, 700)
        self.setModal(False)
        c = window.controls

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        # Video ----------------------------------------------------------------------------
        quality = QGroupBox("Picture quality")
        ql = QVBoxLayout(quality)
        ql.addWidget(_note("Pick how clear and how smooth the phone picture is on your PC. 'Sharp' suits most people. 'Ultra' and 'Max' give the clearest, smoothest picture if your PC and USB cable can keep up. Press 'Apply now' below to use a change."))
        ql.addWidget(window.quality_combo)
        markers = QGroupBox("Key markers (the circles drawn on the picture)")
        kl = QVBoxLayout(markers)
        kl.addWidget(_note("While you play, the circles and labels can fade away so the picture is clean. 0 % is "
                           "invisible; the keys still work. Change it any time with the shortcuts (see 'Shortcuts')."))
        row = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setSingleStep(5)
        self.opacity_slider.setPageStep(10)
        self.opacity_value = QLabel("100 %")
        self.opacity_value.setMinimumWidth(48)
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_value.setText(f"{v} %"))
        row.addWidget(self.opacity_slider, 1)
        row.addWidget(self.opacity_value)
        kl.addLayout(row)
        self.tabs.addTab(_page(quality, window.stream_box, window.look_panel, markers,
                               _note("Size, smoothness and quality change the stream: press 'Apply now' (or connect again) to use "
                                     "them. Picture look changes apply at once.")),
                         "Picture")

        # Mouse & walking -----------------------------------------------------------------------
        mouse = QGroupBox("Mouse")
        ml = QVBoxLayout(mouse)
        ml.addWidget(c.direct_check)
        ml.addWidget(_note("When this is on, a left click or drag on the picture touches the phone screen, the wheel "
                           "scrolls, a right click goes Back and a middle click goes Home (not while playing)."))
        self.tabs.addTab(_page(mouse, c.stick_box, c.look_box), "Mouse and walking")

        # All keys ------------------------------------------------------------------------------
        self.tabs.addTab(_page(_note("Every key of the current profile. You can also change them by dragging on the "
                                     "picture (Edit controls)."), c.bind_box, stretch=False), "All keys")

        # Games ---------------------------------------------------------------------------------
        profile_box = QGroupBox("This profile")
        pl = QVBoxLayout(profile_box)
        pl.addWidget(c.delete_btn)
        self.tabs.addTab(_page(c.game_box, profile_box), "Games and profiles")

        # Shortcuts -----------------------------------------------------------------------------
        self.tabs.addTab(_page(c.hotkey_box), "Shortcuts")

        # Help ----------------------------------------------------------------------------------
        help_box = QGroupBox("Phone not found?")
        hl = QVBoxLayout(help_box)
        hl.addWidget(_note("1. Use a USB cable that carries data (not a charge-only cable).\n"
                           "2. On the phone: Settings > Developer options > USB debugging: ON.\n"
                           "3. When the phone asks 'Allow USB debugging?', tap Allow."))
        hl.addWidget(window.refresh_btn)
        info_box = QGroupBox("Information")
        il = QVBoxLayout(info_box)
        il.addWidget(window.show_stats_check)
        log_box = QGroupBox("Activity log (for support)")
        ll = QVBoxLayout(log_box)
        ll.addWidget(window.log_panel)
        self.tabs.addTab(_page(help_box, info_box, c.reset_box, log_box, stretch=False), "Help and reset")

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.addWidget(self.tabs)
        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("primary")
        close.clicked.connect(self.close)
        close_row.addWidget(close)
        root.addLayout(close_row)

    def set_opacity_value(self, percent: int) -> None:
        self.opacity_slider.blockSignals(True)
        self.opacity_slider.setValue(percent)
        self.opacity_slider.blockSignals(False)
        self.opacity_value.setText(f"{percent} %")

    def show_tab(self, index: int = 0) -> None:
        self.tabs.setCurrentIndex(index)
        self.show()
        self.raise_()
        self.activateWindow()
