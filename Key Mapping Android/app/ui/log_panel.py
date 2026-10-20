from __future__ import annotations

import logging
import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from .. import paths


class QtLogHandler(logging.Handler, QObject):
    """Forwards log records to the GUI thread."""

    message = Signal(str)

    def __init__(self) -> None:
        logging.Handler.__init__(self)
        QObject.__init__(self)
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.message.emit(self.format(record))
        except RuntimeError:
            pass        # the widget was destroyed during shutdown


class LogPanel(QWidget):
    def __init__(self, diagnostics_provider, parent=None) -> None:
        super().__init__(parent)
        self._diagnostics = diagnostics_provider
        self.text = QPlainTextEdit(readOnly=True, maximumBlockCount=3000)

        clear = QPushButton("Clear")
        clear.clicked.connect(self.text.clear)
        folder = QPushButton("Open log folder")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.log_dir()))))
        copy = QPushButton("Copy diagnostics")
        copy.clicked.connect(self._copy_diagnostics)

        buttons = QHBoxLayout()
        for button in (clear, folder, copy):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(buttons)
        layout.addWidget(self.text)

        self.handler = QtLogHandler()
        self.handler.message.connect(self.text.appendPlainText)
        logging.getLogger().addHandler(self.handler)

    def _copy_diagnostics(self) -> None:
        QApplication.clipboard().setText(self._diagnostics())
        logging.getLogger(__name__).info("Diagnostics copied to the clipboard")

    def detach(self) -> None:
        logging.getLogger().removeHandler(self.handler)
