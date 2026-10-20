"""All the control widgets (profiles, editor palette, stick, mouse look, hotkeys, ...).

This class only creates and wires them; the windows that show them (the simple sidebar and the Settings
dialog) arrange them. Nothing here is laid out on the panel itself."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QMenu, QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout, QGroupBox,
                               QHBoxLayout, QHeaderView, QLabel, QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..game_names import friendly_name
from ..hotkeys import DEFAULT_HOTKEYS, HOTKEY_LABELS, pretty
from ..mapping.profile import DIRECTIONS, MODE_HELP, MODE_SHORT, MODES, STICK_EXTRAS, Look, Profile, Stick
from .binding_options import BindingOptionsDialog


CHIP_HEIGHT = 34          # palette buttons never shrink below this, so their text is not clipped

TIPS = {
    "next weapon": "Scroll the mouse wheel DOWN to tap this point (e.g. the next weapon slot).",
    "previous weapon": "Scroll the mouse wheel UP to tap this point (e.g. the previous weapon slot).",
    "custom": "Press any key, mouse button or wheel direction, then place it on the screen.",
    "stick": "Four keys (WASD) drag a virtual joystick. Drag its centre onto the game's joystick, drag a key to resize.",
    "look": "The mouse turns the camera inside this box. Drag its corners to resize.",
}


class ControlsPanel(QWidget):
    profileChosen = Signal(str)
    newProfileRequested = Signal()
    deleteProfileRequested = Signal()
    mappingToggled = Signal(bool)
    directTouchToggled = Signal(bool)
    addRequested = Signal()
    removeRequested = Signal(str)
    bindingsEdited = Signal()
    selectionChanged = Signal(int)
    stickPlaceRequested = Signal()
    stickRemoveRequested = Signal()
    stickKeyRequested = Signal(str)          # direction: up / left / down / right
    stickEdited = Signal()
    stickExtraRequested = Signal(str)        # sprint / walk / autorun
    stickExtraCleared = Signal(str)
    lookPlaceRequested = Signal()
    lookRemoveRequested = Signal()
    lookEdited = Signal()
    captureToggled = Signal(bool)
    editToggled = Signal(bool)
    saveRequested = Signal()
    undoRequested = Signal()
    resetRequested = Signal()
    stickResetRequested = Signal()
    lookResetRequested = Signal()
    hotkeyRebind = Signal(str)
    hotkeysResetRequested = Signal()
    resetAllRequested = Signal()
    addControl = Signal(str)
    linkRequested = Signal()
    unlinkRequested = Signal()
    autoLoadToggled = Signal(bool)
    autoMappingToggled = Signal(bool)
    smartToggled = Signal(bool)
    smartLearnRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._profile: Profile | None = None
        self._hk = dict(DEFAULT_HOTKEYS)

        self.profile_combo = QComboBox()
        self.profile_combo.setToolTip("The set of keys for one game or one game mode.")
        self.profile_combo.activated.connect(lambda _: self.profileChosen.emit(self.profile_combo.currentText()))
        self.new_btn = QPushButton("+ New")
        self.new_btn.setObjectName("tool")
        self.new_btn.setToolTip("Create controls for another game or mode, starting from a ready-made layout.")
        self.new_btn.clicked.connect(self.newProfileRequested)
        self.delete_btn = QPushButton("Delete this profile")
        self.delete_btn.clicked.connect(self.deleteProfileRequested)
        self.save_btn = QPushButton("Save")
        self.save_btn.setToolTip("Keep the current controls as a restore point. (Every change is already stored "
                                 "automatically - Save only marks a point you can go back to.)")
        self.save_btn.clicked.connect(self.saveRequested)
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.setToolTip("Go back to the controls as they were at the last Save.")
        self.undo_btn.clicked.connect(self.undoRequested)
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setToolTip("Replace this profile's controls with the standard shooter layout.")
        self.reset_btn.clicked.connect(self.resetRequested)
        for button in (self.save_btn, self.undo_btn, self.reset_btn):
            button.setObjectName("tool")
        self.save_label = QLabel("")
        self.save_label.setObjectName("muted")
        self.save_label.setWordWrap(True)

        self.game_line = QLabel("")
        self.game_line.setObjectName("muted")
        self.game_line.setWordWrap(True)
        self.quick_link_btn = QPushButton("Use these controls whenever this game opens")
        self.quick_link_btn.setObjectName("flat")
        self.quick_link_btn.setToolTip("Remember which game this profile is for. When that game opens on the phone,\n"
                                       "the profile loads by itself with the same keys and positions.")
        self.quick_link_btn.clicked.connect(self.linkRequested)
        self.quick_link_btn.setVisible(False)

        self.mapping_btn = QPushButton("Start playing")
        self.mapping_btn.setObjectName("play")
        self.mapping_btn.setCheckable(True)
        self.mapping_btn.setToolTip("Turn your keys and mouse on for the game. Esc stops.")
        self.mapping_btn.toggled.connect(self._on_mapping_toggled)
        self.play_label = QLabel("")
        self.play_label.setObjectName("muted")
        self.play_label.setWordWrap(True)
        self.smart_check = QCheckBox("Free the mouse and pause keys in menus")
        self.smart_check.setToolTip("While you play, the app watches the phone picture. When the game's own buttons are on\n"
                                    "screen it locks the mouse for aiming and runs your keys. In menus, lobbies and result\n"
                                    "screens it frees the mouse (it works like a finger) and pauses the keys.")
        self.smart_check.toggled.connect(self.smartToggled)
        self.smart_learn_btn = QPushButton("Learn the game screen")
        self.smart_learn_btn.setToolTip("Open a match so the game's buttons are showing, then press this. The app remembers\n"
                                        "what your controls look like, to tell the game from its menus.")
        self.smart_learn_btn.clicked.connect(self.smartLearnRequested)
        self.smart_status = QLabel("")
        self.smart_status.setObjectName("muted")
        self.smart_status.setWordWrap(True)
        self.direct_check = QCheckBox("Mouse works like a finger on the phone screen")
        self.direct_check.setChecked(True)
        self.direct_check.setToolTip("Left-drag touches and swipes. Wheel scrolls.\n"
                                     "Right-click = Back, middle-click = Home (when key mapping is off).")
        self.direct_check.toggled.connect(self.directTouchToggled)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Label", "Input", "Does", "X %", "Y %", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(170)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        for col, width in ((2, 104), (3, 58), (4, 58), (5, 44)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(col, width)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemSelectionChanged.connect(lambda: self.selectionChanged.emit(self.selected_row()))

        self.add_btn = QPushButton("Add key")
        self.add_btn.setToolTip("Click a spot on the phone screen, then press the key or mouse button for it.")
        self.add_btn.clicked.connect(self.addRequested)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._on_remove)
        self.hint = QLabel("")
        self.hint.setObjectName("tip")
        self.hint.setWordWrap(True)
        self.hint.setVisible(False)

        self.bind_box = bind_box = QGroupBox("All keys of this profile")
        bl = QVBoxLayout(bind_box)
        bl.addWidget(self.table)
        buttons = QHBoxLayout()
        buttons.addWidget(self.add_btn, 2)
        buttons.addWidget(self.remove_btn, 1)
        bl.addLayout(buttons)

        self.stick_keys: dict[str, QPushButton] = {}
        self.stick_box = stick_box = QGroupBox("Walking (WASD keys)")
        sl = QVBoxLayout(stick_box)
        grid = QGridLayout()
        for direction, (row, col) in {"up": (0, 1), "left": (1, 0), "down": (1, 1), "right": (1, 2)}.items():
            button = QPushButton("-")
            button.setToolTip(f"Click, then press the key for '{direction}'")
            button.clicked.connect(lambda _=False, d=direction: self.stickKeyRequested.emit(d))
            self.stick_keys[direction] = button
            grid.addWidget(button, row, col)
        sl.addLayout(grid)
        settings = QHBoxLayout()
        self.radius_spin = QDoubleSpinBox(minimum=1, maximum=50, decimals=1, singleStep=0.5, suffix=" %")
        self.radius_spin.setToolTip("How far the finger moves from the stick centre, as % of the shorter screen side.\n"
                                    "Match it to the game's joystick circle.")
        self.ramp_spin = QSpinBox(minimum=0, maximum=500, singleStep=10, suffix=" ms")
        self.ramp_spin.setToolTip("Time the finger takes to reach full deflection. 0 = instant.")
        self.radius_spin.valueChanged.connect(lambda _: self._on_stick_value())
        self.ramp_spin.valueChanged.connect(lambda _: self._on_stick_value())
        settings.addWidget(QLabel("Radius"))
        settings.addWidget(self.radius_spin)
        settings.addWidget(QLabel("Ramp"))
        settings.addWidget(self.ramp_spin)
        sl.addLayout(settings)
        extras = QGridLayout()
        self.stick_extra_btns: dict[str, QPushButton] = {}
        self.stick_extra_clear: dict[str, QPushButton] = {}
        extra_info = {
            "sprint": ("Sprint key", "While held, the stick is pushed further, which makes most games sprint."),
            "walk": ("Walk key", "While held, the stick is pushed only part of the way: slow, quiet walking."),
            "autorun": ("Auto-run key", "Press once to keep walking forward by itself. S or the key again stops it."),
        }
        for row_index, kind in enumerate(STICK_EXTRAS):
            title, tip = extra_info[kind]
            extras.addWidget(QLabel(title), row_index, 0)
            key_btn = QPushButton("not set")
            key_btn.setToolTip(tip + "\nClick, then press the key (a modifier like Shift works too).")
            key_btn.clicked.connect(lambda _=False, k=kind: self.stickExtraRequested.emit(k))
            clear_btn = QPushButton("\u2715")
            clear_btn.setObjectName("flat")
            clear_btn.setToolTip("Clear")
            clear_btn.clicked.connect(lambda _=False, k=kind: self.stickExtraCleared.emit(k))
            self.stick_extra_btns[kind] = key_btn
            self.stick_extra_clear[kind] = clear_btn
            extras.addWidget(key_btn, row_index, 1)
            extras.addWidget(clear_btn, row_index, 2)
        self.sprint_spin = QSpinBox(minimum=100, maximum=400, singleStep=5, suffix=" %")
        self.sprint_spin.setToolTip("How far the sprint key pushes the stick, compared with a normal run (100 %).")
        self.walk_spin = QSpinBox(minimum=10, maximum=95, singleStep=5, suffix=" %")
        self.walk_spin.setToolTip("How far the walk key pushes the stick, compared with a normal run.")
        self.sprint_spin.valueChanged.connect(lambda _: self._on_stick_value())
        self.walk_spin.valueChanged.connect(lambda _: self._on_stick_value())
        extras.addWidget(self.sprint_spin, 0, 3)
        extras.addWidget(self.walk_spin, 1, 3)
        extras.setColumnStretch(1, 1)
        sl.addLayout(extras)
        stick_buttons = QHBoxLayout()
        self.stick_place_btn = QPushButton("Place stick")
        self.stick_place_btn.setToolTip("Click the centre of the game's on-screen joystick.")
        self.stick_place_btn.clicked.connect(self.stickPlaceRequested)
        self.stick_remove_btn = QPushButton("Remove")
        self.stick_remove_btn.clicked.connect(self.stickRemoveRequested)
        stick_buttons.addWidget(self.stick_place_btn, 2)
        stick_buttons.addWidget(self.stick_remove_btn, 1)
        self.stick_reset_btn = QPushButton("Defaults")
        self.stick_reset_btn.setToolTip("Reset radius, ramp and keys to the defaults (WASD, 9 %, 50 ms).")
        self.stick_reset_btn.clicked.connect(self.stickResetRequested)
        stick_buttons.addWidget(self.stick_reset_btn, 1)
        sl.addLayout(stick_buttons)
        self._update_stick_widgets(None)

        self.look_box = look_box = QGroupBox("Looking around (mouse)")
        ll = QVBoxLayout(look_box)
        form = QGridLayout()
        self.look_sens_x = QDoubleSpinBox(minimum=0.05, maximum=20, decimals=2, singleStep=0.1)
        self.look_sens_y = QDoubleSpinBox(minimum=0.05, maximum=20, decimals=2, singleStep=0.1)
        self.look_accel = QSpinBox(minimum=0, maximum=100, singleStep=5, suffix=" %")
        self.look_invert = QCheckBox("Invert Y")
        sens_tip = "Phone-screen pixels the finger moves per mouse count. Raise it to turn faster."
        self.look_sens_x.setToolTip(sens_tip)
        self.look_sens_y.setToolTip(sens_tip)
        self.look_accel.setToolTip("Amplifies fast flicks. 0 = perfectly linear.")
        for widget, row, col, label in ((self.look_sens_x, 0, 0, "Sens X"), (self.look_sens_y, 0, 2, "Sens Y"),
                                        (self.look_accel, 1, 0, "Accel")):
            form.addWidget(QLabel(label), row, col)
            form.addWidget(widget, row, col + 1)
            widget.valueChanged.connect(lambda _: self._on_look_value())
        form.addWidget(self.look_invert, 1, 2, 1, 2)
        self.look_ads = QSpinBox(minimum=10, maximum=150, singleStep=5, suffix=" %")
        self.look_ads.setToolTip("Mouse sensitivity while the scope / aim button is on (100 % = unchanged).\n"
                                 "Mark a key as the scope button in its Options.")
        self.look_ads.valueChanged.connect(lambda _: self._on_look_value())
        form.addWidget(QLabel("While scoped in"), 2, 0)
        form.addWidget(self.look_ads, 2, 1)
        self.look_invert.toggled.connect(lambda _: self._on_look_value())
        ll.addLayout(form)
        look_buttons = QHBoxLayout()
        self.look_place_btn = QPushButton("Set area")
        self.look_place_btn.setToolTip("Click two opposite corners of an empty part of the game view\n"
                                       "(away from every on-screen button). Mouse movement turns the camera there.")
        self.look_place_btn.clicked.connect(self.lookPlaceRequested)
        self.look_remove_btn = QPushButton("Remove")
        self.look_remove_btn.clicked.connect(self.lookRemoveRequested)
        self.capture_btn = QPushButton("Mouse locked for aiming  (~ or F8)")
        self.capture_btn.setCheckable(True)
        self.capture_btn.setToolTip("While on, the cursor is hidden and the mouse aims. Turn off to use the cursor.")
        self.capture_btn.toggled.connect(self.captureToggled)
        look_buttons.addWidget(self.look_place_btn, 2)
        look_buttons.addWidget(self.look_remove_btn, 1)
        self.look_reset_btn = QPushButton("Defaults")
        self.look_reset_btn.setToolTip("Reset sensitivity, acceleration and invert to the defaults (1.00 / 1.00 / 0 % / off).")
        self.look_reset_btn.clicked.connect(self.lookResetRequested)
        look_buttons.addWidget(self.look_reset_btn, 1)
        ll.addLayout(look_buttons)
        self._update_look_widgets(None)

        self.game_box = game_box = QGroupBox("Games")
        gl = QVBoxLayout(game_box)
        self.running_label = QLabel("Phone app: -")
        self.running_label.setWordWrap(True)
        self.linked_label = QLabel("This profile is not linked to a game.")
        self.linked_label.setObjectName("muted")
        self.linked_label.setWordWrap(True)
        game_buttons = QHBoxLayout()
        self.link_btn = QPushButton("Link to running game")
        self.link_btn.setToolTip("Remember which game this profile is for. When that game opens on the phone,\n"
                                 "the profile loads by itself with the same keys and positions.")
        self.link_btn.clicked.connect(self.linkRequested)
        self.unlink_btn = QPushButton("Unlink")
        self.unlink_btn.clicked.connect(self.unlinkRequested)
        game_buttons.addWidget(self.link_btn, 2)
        game_buttons.addWidget(self.unlink_btn, 1)
        self.auto_load_check = QCheckBox("Load the profile automatically when its game opens")
        self.auto_load_check.setChecked(True)
        self.auto_load_check.toggled.connect(self.autoLoadToggled)
        self.auto_mapping_check = QCheckBox("...and turn key mapping on")
        self.auto_mapping_check.toggled.connect(self.autoMappingToggled)
        for widget in (self.running_label, self.linked_label):
            gl.addWidget(widget)
        gl.addLayout(game_buttons)
        gl.addWidget(self.auto_load_check)
        gl.addWidget(self.auto_mapping_check)

        self.edit_btn = QPushButton("Edit controls")
        self.edit_btn.setObjectName("editToggle")
        self.edit_btn.setCheckable(True)
        self.edit_btn.setToolTip("Move, add or change keys right on the phone picture.\n"
                                 "Drag a marker to move it, double-click to change its key, Delete removes it.")
        self.edit_btn.toggled.connect(self._on_edit_toggled)
        self.palette_widget = QWidget()
        palette = QGridLayout(self.palette_widget)
        palette.setContentsMargins(0, 0, 0, 0)
        palette.setSpacing(6)
        self.palette_buttons: list[QPushButton] = []
        items = [("fire", "Fire"), ("scope", "Aim (scope)"), ("reload", "Reload"), ("crouch", "Crouch"),
                 ("jump", "Jump"), ("sprint", "Sprint"), ("next weapon", "Next weapon \u25bc"),
                 ("previous weapon", "Prev. weapon \u25b2"), ("stick", "Walk (WASD)"),
                 ("look", "Look (mouse)"), ("custom", "Any other key")]
        for i, (kind, text) in enumerate(items):
            button = QPushButton(text)
            button.setObjectName("chip")
            button.setToolTip(TIPS.get(kind, "Adds this control in the middle of the screen. Drag it into place."))
            button.clicked.connect(lambda _=False, k=kind: self.addControl.emit(k))
            button.setMinimumHeight(CHIP_HEIGHT)
            palette.addWidget(button, i // 2, i % 2)
            self.palette_buttons.append(button)
        self.more_btn = QPushButton("More controls")
        self.more_btn.setObjectName("chip")
        self.more_btn.setMinimumHeight(CHIP_HEIGHT)
        self.more_btn.setToolTip("Swipe, zoom, multi-tap, repeat tap, toggle, double tap...")
        more_menu = QMenu(self.more_btn)
        for kind, text in (("swipe", "Swipe  (drag from A to B)"), ("drag", "Drag and hold  (A to B)"),
                           ("pinch-out", "Zoom in  (pinch out)"), ("pinch-in", "Zoom out  (pinch in)"),
                           ("sequence", "Multi-tap  (several spots in order)"),
                           ("repeat", "Repeat tap  (auto-click while held)"),
                           ("toggle", "Toggle key  (press on, press off)"), ("double", "Double tap")):
            action = more_menu.addAction(text)
            action.setToolTip(MODE_HELP[kind])
            action.triggered.connect(lambda _=False, k=kind: self.addControl.emit(k))
        self.more_btn.setMenu(more_menu)
        palette.addWidget(self.more_btn, len(items) // 2, len(items) % 2)      # fills the half-empty last row
        self.palette_buttons.append(self.more_btn)
        self.palette_widget.setVisible(False)

        self.hotkey_box = hotkey_box = QGroupBox("Keyboard shortcuts of the app")
        hl = QGridLayout(hotkey_box)
        self.hotkey_buttons: dict[str, QPushButton] = {}
        for row_index, action in enumerate(DEFAULT_HOTKEYS):
            hl.addWidget(QLabel(HOTKEY_LABELS[action]), row_index, 0)
            button = QPushButton(self._hk[action])
            button.setToolTip("Click, then press the new key (F1-F12, Pause, ScrollLock, Ins, Home, End, PgUp, PgDown).")
            button.clicked.connect(lambda _=False, a=action: self.hotkeyRebind.emit(a))
            self.hotkey_buttons[action] = button
            hl.addWidget(button, row_index, 1)
        self.hotkeys_reset_btn = QPushButton("Reset hotkeys")
        self.hotkeys_reset_btn.clicked.connect(self.hotkeysResetRequested)
        hl.addWidget(self.hotkeys_reset_btn, len(DEFAULT_HOTKEYS), 0, 1, 2)

        self.reset_box = reset_box = QGroupBox("Start over")
        rl = QVBoxLayout(reset_box)
        self.reset_all_btn = QPushButton("Reset all settings...")
        self.reset_all_btn.setToolTip("Video options, 'Mouse acts as a finger', auto-load options and hotkeys go back to\n"
                                      "how the app came. Your profiles are not touched.")
        self.reset_all_btn.clicked.connect(self.resetAllRequested)
        note = QLabel("Changed something by accident? Use Undo changes (controls) or this button (settings).")
        note.setObjectName("muted")
        note.setWordWrap(True)
        rl.addWidget(self.reset_all_btn)
        rl.addWidget(note)

    # -- API -------------------------------------------------------------------------------
    def set_profiles(self, names: list[str], current: str) -> None:
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItems(names)
        self.profile_combo.setCurrentText(current)
        self.profile_combo.blockSignals(False)
        self.delete_btn.setEnabled(len(names) > 1)

    def set_profile(self, profile: Profile | None) -> None:
        self._profile = profile
        self._rebuild()
        self._update_stick_widgets(profile.sticks[0] if profile and profile.sticks else None)
        self._update_look_widgets(profile.looks[0] if profile and profile.looks else None)
        self.set_linked(profile.package if profile else "")
        self.set_smart(profile)

    def set_smart(self, profile: Profile | None) -> None:
        """Show whether smart mode is on and whether the game screen has been learned for this profile."""
        from ..scene import SceneModel
        scene = profile.scene if profile else None
        model = SceneModel.from_dict(scene) if scene else None
        learned = model is not None and model.usable
        self.smart_check.blockSignals(True)
        self.smart_check.setChecked(bool(learned and scene.get("enabled")))
        self.smart_check.blockSignals(False)
        self.smart_learn_btn.setText("Learn again" if learned else "Learn the game screen")
        self.smart_learn_btn.setEnabled(profile is not None)
        self.smart_check.setEnabled(profile is not None)
        self.smart_status.setText(f"Learned from {len(model.anchors)} buttons of the game." if learned else
                                  "Not learned yet. Open a match, then press 'Learn the game screen'.")

    def set_smart_live(self, text: str) -> None:
        """What the app sees right now (only while playing); empty text puts the learned-info back."""
        if text:
            self.smart_status.setText(text)
        else:
            self.set_smart(self._profile)

    def set_edit_checked(self, on: bool) -> None:
        self.edit_btn.blockSignals(True)
        self.edit_btn.setChecked(on)
        self.edit_btn.blockSignals(False)
        self._edit_visuals(on)

    def _edit_visuals(self, on: bool) -> None:
        self.edit_btn.setText("Done editing" if on else "Edit controls")
        self.palette_widget.setVisible(on)

    def _on_edit_toggled(self, on: bool) -> None:
        self._edit_visuals(on)
        self.editToggled.emit(on)

    def set_running(self, package: str) -> None:
        self._running = package
        self.running_label.setText(f"Open on the phone: {friendly_name(package)}  ({package})" if package
                                   else "Open on the phone: nothing detected yet")
        self.link_btn.setEnabled(bool(package))
        self._refresh_game_line()

    def set_linked(self, package: str) -> None:
        self._linked = package
        self.linked_label.setText(f"This profile belongs to: {friendly_name(package)}  ({package})" if package
                                  else "This profile is not tied to a game.")
        self.unlink_btn.setEnabled(bool(package))
        self._refresh_game_line()

    def _refresh_game_line(self) -> None:
        running, linked = getattr(self, "_running", ""), getattr(self, "_linked", "")
        if linked and running == linked:
            self.game_line.setText(f"\u2714  Playing {friendly_name(linked)} - these controls load by themselves.")
        elif linked:
            self.game_line.setText(f"These controls belong to {friendly_name(linked)}.")
        elif running:
            self.game_line.setText(f"{friendly_name(running)} is open on your phone.")
        else:
            self.game_line.setText("Open your game on the phone.")
        self.quick_link_btn.setVisible(bool(running) and linked != running)

    def set_auto(self, auto_load: bool, auto_mapping: bool) -> None:
        for check, value in ((self.auto_load_check, auto_load), (self.auto_mapping_check, auto_mapping)):
            check.blockSignals(True)
            check.setChecked(value)
            check.blockSignals(False)

    def set_mapping_checked(self, on: bool) -> None:
        self.mapping_btn.blockSignals(True)
        self.mapping_btn.setChecked(on)
        self.mapping_btn.setText(self._mapping_text(on))
        self.play_label.setText(self._play_text(on))
        self.mapping_btn.blockSignals(False)

    def set_adding(self, adding: bool) -> None:
        self.add_btn.setText("Cancel" if adding else "Add binding")
        for widget in (self.table, self.remove_btn, self.profile_combo, self.new_btn, self.delete_btn,
                       self.mapping_btn, self.stick_place_btn, self.stick_remove_btn, self.radius_spin,
                       self.ramp_spin, self.look_place_btn, self.look_remove_btn, self.look_sens_x,
                       self.look_sens_y, self.look_accel, self.look_invert, self.capture_btn,
                       self.edit_btn, self.quick_link_btn, self.smart_check, self.smart_learn_btn, self.save_btn, self.undo_btn, self.reset_btn, self.stick_reset_btn,
                       self.look_reset_btn, self.reset_all_btn, self.hotkeys_reset_btn,
                       *self.hotkey_buttons.values(), *self.palette_buttons, *self.stick_keys.values()):
            widget.setEnabled(not adding)
        if not adding:                                   # restore the right enabled/disabled state of each control
            profile = self._profile
            self._update_stick_widgets(profile.sticks[0] if profile and profile.sticks else None)
            self._update_look_widgets(profile.looks[0] if profile and profile.looks else None)
            self.delete_btn.setEnabled(self.profile_combo.count() > 1)
            self.stick_reset_btn.setEnabled(bool(profile and profile.sticks))
            self.look_reset_btn.setEnabled(bool(profile and profile.looks))

    def set_hint(self, text: str) -> None:
        self.hint.setText(text)
        self.hint.setVisible(bool(text))

    def selected_row(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    # -- internals -------------------------------------------------------------------------
    def _mapping_text(self, on: bool) -> str:
        return f"\u25a0   Stop playing   ({self._hk['mapping']})" if on else f"\u25b6   Start playing   ({self._hk['mapping']})"

    def _play_text(self, on: bool) -> str:
        if on:
            return "Your keyboard and mouse now control the game. Press Esc to stop."
        return "Press the button, or the shortcut, when you are ready."

    def set_hotkeys(self, hotkeys: dict[str, str]) -> None:
        self._hk = dict(hotkeys)
        for action, button in self.hotkey_buttons.items():
            button.setText(pretty(self._hk[action]))
        self.mapping_btn.setText(self._mapping_text(self.mapping_btn.isChecked()))
        keys = " or ".join(dict.fromkeys(pretty(self._hk[a]) for a in ("cursor", "capture")))
        self.capture_btn.setText(f"Mouse locked for aiming  ({keys})")

    def set_save_status(self, text: str, dirty: bool) -> None:
        self.save_label.setText(text)
        self.save_label.setStyleSheet("color: #ffb020;" if dirty else "color: #35d07f;")

    def set_profile_actions_enabled(self, has_profile: bool, can_undo: bool) -> None:
        self.save_btn.setEnabled(has_profile)
        self.undo_btn.setEnabled(has_profile and can_undo)
        self.reset_btn.setEnabled(has_profile)

    def _on_mapping_toggled(self, on: bool) -> None:
        self.mapping_btn.setText(self._mapping_text(on))
        self.play_label.setText(self._play_text(on))
        self.mappingToggled.emit(on)

    def _rebuild(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        bindings = self._profile.bindings if self._profile else []
        for row, binding in enumerate(bindings):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(binding.label))
            key_item = QTableWidgetItem(binding.input)
            key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, key_item)
            mode = QComboBox()
            for name in MODES:
                mode.addItem(MODE_SHORT[name], name)
            mode.setCurrentIndex(mode.findData(binding.mode))
            mode.setToolTip(MODE_HELP[binding.mode])
            mode.currentIndexChanged.connect(lambda _i, b=binding, c=mode: self._set_mode(b, c.currentData()))
            self.table.setCellWidget(row, 2, mode)
            for col, value, attr in ((3, binding.x, "x"), (4, binding.y, "y")):
                spin = QDoubleSpinBox(minimum=0, maximum=100, decimals=1, singleStep=0.5)
                spin.setStyleSheet("QDoubleSpinBox { padding: 0px 3px; }"
                                   "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 0px; border: 0px; }")
                spin.setValue(value * 100)
                spin.valueChanged.connect(lambda v, b=binding, a=attr: self._set_coord(b, a, v))
                self.table.setCellWidget(row, col, spin)
            options = QPushButton("\u22ef")
            options.setObjectName("flat")
            options.setToolTip("More options for this key (speed, second point, multi-tap, scope button...)")
            options.clicked.connect(lambda _=False, b=binding: self.open_options(b))
            self.table.setCellWidget(row, 5, options)
        self.table.blockSignals(False)

    def _set_mode(self, binding, mode: str) -> None:
        binding.set_mode(mode)
        self.bindingsEdited.emit()
        if mode in ("swipe", "drag", "sequence"):
            self.set_hint("Set where it goes in 'Options' (the three dots), or drag its handle on the picture.")

    def open_options(self, binding) -> None:
        dialog = BindingOptionsDialog(binding, self.window())
        if dialog.exec() == dialog.DialogCode.Accepted:
            dialog.apply(binding)
            self._rebuild()
            self.bindingsEdited.emit()

    def _set_coord(self, binding, attr: str, percent: float) -> None:
        setattr(binding, attr, percent / 100)
        self.bindingsEdited.emit()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0 and self._profile and 0 <= item.row() < len(self._profile.bindings):
            self._profile.bindings[item.row()].label = item.text()
            self.bindingsEdited.emit()

    def _update_stick_widgets(self, stick: Stick | None) -> None:
        has = stick is not None
        for direction in DIRECTIONS:
            self.stick_keys[direction].setText(stick.keys[direction] if stick else "-")
            self.stick_keys[direction].setEnabled(has)
        spins = (self.radius_spin, self.ramp_spin, self.sprint_spin, self.walk_spin)
        for spin in spins:
            spin.blockSignals(True)
        self.radius_spin.setValue(stick.radius * 100 if stick else 9.0)
        self.ramp_spin.setValue(stick.ramp_ms if stick else 50)
        self.sprint_spin.setValue(round(stick.sprint_scale * 100) if stick else 135)
        self.walk_spin.setValue(round(stick.walk_scale * 100) if stick else 50)
        for spin in spins:
            spin.blockSignals(False)
        extra = stick.extra_keys() if stick else {}
        for kind in STICK_EXTRAS:
            self.stick_extra_btns[kind].setText(extra.get(kind, "not set"))
            self.stick_extra_btns[kind].setEnabled(has)
            self.stick_extra_clear[kind].setEnabled(has and kind in extra)
        for widget in (*spins, self.stick_remove_btn, self.stick_reset_btn):
            widget.setEnabled(has)
        self.stick_place_btn.setText("Move stick" if has else "Place stick")

    def set_capture_checked(self, on: bool) -> None:
        self.capture_btn.blockSignals(True)
        self.capture_btn.setChecked(on)
        self.capture_btn.blockSignals(False)

    def _update_look_widgets(self, look: Look | None) -> None:
        has = look is not None
        widgets = (self.look_sens_x, self.look_sens_y, self.look_accel, self.look_invert, self.look_ads)
        for widget in widgets:
            widget.blockSignals(True)
        self.look_sens_x.setValue(look.sens_x if look else 1.0)
        self.look_sens_y.setValue(look.sens_y if look else 1.0)
        self.look_accel.setValue(round(look.accel * 100) if look else 0)
        self.look_invert.setChecked(look.invert_y if look else False)
        self.look_ads.setValue(round(look.ads_scale * 100) if look else 100)
        for widget in widgets:
            widget.blockSignals(False)
            widget.setEnabled(has)
        self.look_remove_btn.setEnabled(has)
        self.capture_btn.setEnabled(has)
        if not has:
            self.capture_btn.setVisible(False)       # shown by the main window while playing
        self.look_reset_btn.setEnabled(has)
        self.look_place_btn.setText("Change area" if has else "Set area")

    def _on_look_value(self) -> None:
        if self._profile and self._profile.looks:
            look = self._profile.looks[0]
            look.sens_x = self.look_sens_x.value()
            look.sens_y = self.look_sens_y.value()
            look.accel = self.look_accel.value() / 100
            look.invert_y = self.look_invert.isChecked()
            look.ads_scale = self.look_ads.value() / 100
            self.lookEdited.emit()

    def _on_stick_value(self) -> None:
        if self._profile and self._profile.sticks:
            stick = self._profile.sticks[0]
            stick.radius = self.radius_spin.value() / 100
            stick.ramp_ms = self.ramp_spin.value()
            stick.sprint_scale = self.sprint_spin.value() / 100
            stick.walk_scale = self.walk_spin.value() / 100
            self.stickEdited.emit()

    def _on_remove(self) -> None:
        row = self.selected_row()
        if self._profile and 0 <= row < len(self._profile.bindings):
            self.removeRequested.emit(self._profile.bindings[row].input)
