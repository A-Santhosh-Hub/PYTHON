"""Dialog with every option of one key: what it does (mode) and the settings of that mode."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
                               QTableWidget, QVBoxLayout, QWidget)

from ..mapping.layout_edit import DEFAULT_STEP_DELAY_MS
from ..mapping.profile import MODE_HELP, MODE_SHORT, MODES, PINCH_MODES, TWO_POINT_MODES, Binding


def _percent(value: float = 0.0) -> QDoubleSpinBox:
    spin = QDoubleSpinBox(minimum=0, maximum=100, decimals=1, singleStep=0.5, suffix=" %")
    spin.setValue(value * 100)
    return spin


class BindingOptionsDialog(QDialog):
    def __init__(self, binding: Binding, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Options for '{binding.input}'")
        self.setMinimumWidth(470)
        self._binding = binding

        self.label_edit = QLineEdit(binding.label)
        self.label_edit.setPlaceholderText("Name shown on the screen, e.g. Reload")
        self.mode_combo = QComboBox()
        for mode in MODES:
            self.mode_combo.addItem(MODE_SHORT[mode].capitalize(), mode)
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(binding.mode))
        self.help_label = QLabel("")
        self.help_label.setWordWrap(True)
        self.help_label.setObjectName("muted")
        self.scope_check = QCheckBox("This is the scope / aim button (mouse sensitivity drops while it is on)")
        self.scope_check.setChecked(binding.scope)
        self.scope_check.setToolTip("Set 'While scoped in' under Settings > Mouse and walking to choose how much slower.")

        # repeat -----------------------------------------------------------------------------
        self.rate_spin = QDoubleSpinBox(minimum=1, maximum=30, decimals=0, suffix=" taps / second")
        self.rate_spin.setValue(binding.rate_hz)
        self.repeat_box = QGroupBox("Repeat tap")
        QFormLayout(self.repeat_box).addRow("Speed", self.rate_spin)
        self.repeat_note = QLabel("Online games may treat auto-clicking as cheating. Use it where that is allowed.")
        self.repeat_note.setObjectName("muted")
        self.repeat_note.setWordWrap(True)
        self.repeat_box.layout().addRow(self.repeat_note)

        # swipe / drag -----------------------------------------------------------------------------
        self.end_x = _percent(binding.x2 if binding.x2 is not None else binding.x + 0.15)
        self.end_y = _percent(binding.y2 if binding.y2 is not None else binding.y)
        self.swipe_ms = QSpinBox(minimum=40, maximum=3000, singleStep=20, suffix=" ms")
        self.swipe_ms.setValue(binding.duration_ms)
        self.swipe_box = QGroupBox("Swipe / drag")
        sw = QFormLayout(self.swipe_box)
        sw.addRow("Ends at X", self.end_x)
        sw.addRow("Ends at Y", self.end_y)
        sw.addRow("Takes", self.swipe_ms)

        # pinch ------------------------------------------------------------------------------------
        self.span_spin = _percent(binding.span)
        self.span_spin.setMaximum(40)
        self.pinch_ms = QSpinBox(minimum=40, maximum=3000, singleStep=20, suffix=" ms")
        self.pinch_ms.setValue(binding.duration_ms)
        self.pinch_box = QGroupBox("Zoom (pinch)")
        pb = QFormLayout(self.pinch_box)
        pb.addRow("Finger distance", self.span_spin)
        pb.addRow("Takes", self.pinch_ms)

        # multi-tap ------------------------------------------------------------------------------------
        self.steps_table = QTableWidget(0, 3)
        self.steps_table.setHorizontalHeaderLabels(["X", "Y", "Wait before (ms)"])
        self.steps_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.steps_table.setMinimumHeight(140)
        self.steps_table.horizontalHeader().setStretchLastSection(True)
        for sx, sy, delay in (binding.steps or [(binding.x, binding.y, 0)]):
            self._add_step_row(sx, sy, delay)
        add = QPushButton("Add point")
        add.clicked.connect(lambda: self._add_step_row(0.5, 0.5, DEFAULT_STEP_DELAY_MS))
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self._remove_step_row)
        buttons = QHBoxLayout()
        buttons.addWidget(add)
        buttons.addWidget(remove)
        self.seq_box = QGroupBox("Multi-tap (touches each point in order)")
        sb = QVBoxLayout(self.seq_box)
        sb.addWidget(self.steps_table)
        sb.addLayout(buttons)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("Name", self.label_edit)
        form.addRow("What it does", self.mode_combo)
        root.addLayout(form)
        root.addWidget(self.help_label)
        root.addWidget(self.scope_check)
        for box in (self.repeat_box, self.swipe_box, self.pinch_box, self.seq_box):
            root.addWidget(box)
        root.addWidget(self.buttons)
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        self._mode_changed()

    # -- helpers -----------------------------------------------------------------------------
    def _add_step_row(self, x: float, y: float, delay: int) -> None:
        row = self.steps_table.rowCount()
        self.steps_table.insertRow(row)
        for col, value in ((0, x), (1, y)):
            self.steps_table.setCellWidget(row, col, _percent(value))
        wait = QSpinBox(minimum=0, maximum=5000, singleStep=50)
        wait.setValue(delay)
        wait.setEnabled(row > 0)
        self.steps_table.setCellWidget(row, 2, wait)

    def _remove_step_row(self) -> None:
        row = self.steps_table.currentRow()
        if self.steps_table.rowCount() > 1 and row >= 0:
            self.steps_table.removeRow(row)
            first_wait = self.steps_table.cellWidget(0, 2)
            first_wait.setValue(0)
            first_wait.setEnabled(False)

    def selected_mode(self) -> str:
        return self.mode_combo.currentData()

    def _mode_changed(self) -> None:
        mode = self.selected_mode()
        self.help_label.setText(MODE_HELP[mode])
        self.repeat_box.setVisible(mode == "repeat")
        self.swipe_box.setVisible(mode in TWO_POINT_MODES)
        self.pinch_box.setVisible(mode in PINCH_MODES)
        self.seq_box.setVisible(mode == "sequence")
        self.adjustSize()

    # -- result --------------------------------------------------------------------------------
    def apply(self, binding: Binding) -> None:
        """Write the dialog's values into `binding`."""
        binding.label = self.label_edit.text().strip()
        binding.scope = self.scope_check.isChecked()
        mode = self.selected_mode()
        binding.set_mode(mode)
        binding.rate_hz = self.rate_spin.value()
        if mode in TWO_POINT_MODES:
            binding.x2, binding.y2 = self.end_x.value() / 100, self.end_y.value() / 100
            binding.duration_ms = self.swipe_ms.value()
        if mode in PINCH_MODES:
            binding.span = self.span_spin.value() / 100
            binding.duration_ms = self.pinch_ms.value()
        if mode == "sequence":
            steps = []
            for row in range(self.steps_table.rowCount()):
                steps.append((self.steps_table.cellWidget(row, 0).value() / 100,
                              self.steps_table.cellWidget(row, 1).value() / 100,
                              0 if row == 0 else self.steps_table.cellWidget(row, 2).value()))
            if steps:
                binding.steps = steps
                binding.x, binding.y = steps[0][0], steps[0][1]
        # re-run the model's own validation / clamping
        binding.__post_init__()
