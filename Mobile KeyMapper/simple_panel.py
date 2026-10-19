"""The sidebar a first-time player sees: connect, choose controls, set up keys, start playing.

Layout: a fixed header, a scrolling middle (the three step cards), and a pinned footer (message, Start playing).
When the window is short, or the key palette is open, the middle scrolls instead of squeezing the buttons, and
Start playing never leaves the screen.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget


MIN_WIDTH = 340
MAX_WIDTH = 420
WIDTH_FRACTION = 0.26          # of the window width


def sidebar_width(window_width: int) -> int:
    return max(MIN_WIDTH, min(MAX_WIDTH, int(window_width * WIDTH_FRACTION)))


def make_card(number: int | None, title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 16)
    layout.setSpacing(10)
    header = QHBoxLayout()
    header.setSpacing(10)
    if number is not None:
        badge = QLabel(str(number))
        badge.setObjectName("stepBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(badge)
    label = QLabel(title)
    label.setObjectName("cardTitle")
    header.addWidget(label)
    header.addStretch(1)
    layout.addLayout(header)
    return card, layout


class SimplePanel(QWidget):
    """Arranges widgets that already exist on the main window / controls panel into calm cards."""

    def __init__(self, window, settings_button: QPushButton) -> None:
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(sidebar_width(window.width()))
        c = window.controls

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # header (fixed) ----------------------------------------------------------------------
        header = QWidget()
        top = QHBoxLayout(header)
        top.setContentsMargins(16, 16, 16, 10)
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel("Mobile Key One")
        title.setObjectName("appTitle")
        subtitle = QLabel("Phone games on your PC")
        subtitle.setObjectName("muted")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        top.addLayout(title_box, 1)
        top.addWidget(settings_button, 0, Qt.AlignmentFlag.AlignTop)
        outer.addWidget(header)

        # cards (scroll) ----------------------------------------------------------------------
        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(16, 4, 10, 12)
        root.setSpacing(12)

        card, lay = make_card(1, "Connect your phone")
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        status_row.addWidget(window.status_dot, 0, Qt.AlignmentFlag.AlignTop)
        status_row.addWidget(window.status_label, 1)
        lay.addLayout(status_row)
        lay.addWidget(window.device_combo)
        lay.addWidget(window.connect_btn)
        root.addWidget(card)

        card, lay = make_card(2, "Choose your controls")
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(c.profile_combo, 1)
        row.addWidget(c.new_btn)
        lay.addLayout(row)
        lay.addWidget(c.game_line)
        lay.addWidget(c.quick_link_btn, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(c.save_label)
        root.addWidget(card)

        card, lay = make_card(3, "Set up your keys")
        lay.addWidget(c.edit_btn)
        lay.addWidget(c.palette_widget)
        small = QHBoxLayout()
        small.setSpacing(6)
        for button in (c.save_btn, c.undo_btn, c.reset_btn):
            small.addWidget(button)
        lay.addLayout(small)
        root.addWidget(card)

        card, lay = make_card(None, "Smart mode  (optional)")
        note = QLabel("Lets the app tell the game from its menus: in a match your mouse aims, in a menu it is a finger.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addWidget(c.smart_check)
        lay.addWidget(c.smart_learn_btn)
        lay.addWidget(c.smart_status)
        root.addWidget(card)
        root.addStretch(1)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(body)
        outer.addWidget(self.scroll, 1)

        # footer (pinned) ---------------------------------------------------------------------
        footer = QWidget()
        footer.setObjectName("sidebarFooter")
        fl = QVBoxLayout(footer)
        fl.setContentsMargins(16, 10, 16, 10)
        fl.setSpacing(8)
        fl.addWidget(c.hint)
        fl.addWidget(c.mapping_btn)
        fl.addWidget(c.play_label)
        fl.addWidget(c.capture_btn)
        outer.addWidget(footer)

    def ensure_visible(self, widget: QWidget) -> None:
        self.scroll.ensureWidgetVisible(widget)
