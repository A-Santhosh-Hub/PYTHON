"""Dialog for creating a profile: a name, a ready-made layout, and optionally a link to the running game."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout)

from ..mapping import templates

COPY = "copy"


class NewProfileDialog(QDialog):
    def __init__(self, parent, current_name: str | None, running_package: str, existing: list[str]) -> None:
        super().__init__(parent)
        self.setWindowTitle("New profile")
        self.setMinimumWidth(460)
        self._existing = {n.lower() for n in existing}

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. COD Mobile - Battle Royale")
        self.name_edit.textChanged.connect(self._validate)

        self.template_combo = QComboBox()
        self.template_combo.addItem(templates.TEMPLATE_NAMES[templates.STANDARD], templates.STANDARD)
        self.template_combo.addItem(templates.TEMPLATE_NAMES[templates.BATTLE_ROYALE], templates.BATTLE_ROYALE)
        self.template_combo.addItem(templates.TEMPLATE_NAMES[templates.EMPTY], templates.EMPTY)
        if current_name:
            self.template_combo.addItem(f"Copy of '{current_name}'  -  start from the layout you have now", COPY)
        self.template_combo.currentIndexChanged.connect(self._update_help)

        self.help_label = QLabel("")
        self.help_label.setWordWrap(True)
        self.help_label.setObjectName("muted")

        self.link_check = QCheckBox("Link to the game open on the phone")
        self.link_check.setToolTip("The profile then loads by itself when that game opens.")
        self.link_check.setVisible(bool(running_package))
        self.link_check.setChecked(False)
        self.package_label = QLabel(running_package)
        self.package_label.setObjectName("muted")
        self.package_label.setVisible(bool(running_package))

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #ff5c6c;")

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Name (for example the game or the mode):"))
        layout.addWidget(self.name_edit)
        layout.addWidget(QLabel("Start with:"))
        layout.addWidget(self.template_combo)
        layout.addWidget(self.help_label)
        layout.addWidget(self.link_check)
        layout.addWidget(self.package_label)
        layout.addWidget(self.error_label)
        layout.addWidget(self.buttons)
        self._update_help()
        self._validate()

    def _update_help(self) -> None:
        kind = self.template_combo.currentData()
        self.help_label.setText(templates.TEMPLATE_HELP.get(kind, "A copy of the layout you are using now, under a new name."))

    def _validate(self) -> None:
        name = self.name_edit.text().strip()
        problem = ""
        if not name:
            problem = "Type a name."
        elif name.lower() in self._existing:
            problem = f"A profile named '{name}' already exists."
        self.error_label.setText(problem if name or self.name_edit.hasFocus() else "")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not problem)

    def result_values(self) -> tuple[str, str, bool]:
        return self.name_edit.text().strip(), self.template_combo.currentData(), self.link_check.isChecked()
