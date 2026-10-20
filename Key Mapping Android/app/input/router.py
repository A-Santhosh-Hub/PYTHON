"""Qt glue: captures keyboard/mouse events and feeds the InputEngine.

An application-wide event filter sees every key press first, so mapped keys never reach buttons or
text fields while key mapping is active. Mouse events are taken from the video widget only.
"""
from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QWidget

from ..mapping.profile import MODIFIERS, make_combo
from ..video.widget import VideoWidget
from .engine import InputEngine
from .keys import key_name, mouse_name

log = logging.getLogger(__name__)

# Keys the main window keeps for itself (toggle mapping, fullscreen, release).
RESERVED_KEYS = {Qt.Key.Key_F8, Qt.Key.Key_F9, Qt.Key.Key_F11, Qt.Key.Key_Escape}


class InputRouter(QObject):
    def __init__(self, engine: InputEngine, video: VideoWidget, window: QWidget, parent=None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.video = video
        self.window = window
        self.connected = lambda: False                       # set by the main window
        self._wheel_accum = 0
        self.escape_callback: Callable[[], None] | None = None   # set by the main window
        # Hotkeys the router runs itself (the ~ key): a window shortcut cannot match it while Shift is held.
        self.direct_hotkeys: dict[str, Callable[[], None]] = {}
        # Keys that act while held (hold-to-free-the-mouse). Called with True on press and False on release; the key
        # still reaches the engine afterwards, so combinations like Alt+X keep working.
        self.hold_hotkeys: dict[str, Callable[[bool], None]] = {}
        self.reserved_names: set[str] = {"F2", "F3", "F4", "F8", "`", "F9", "F11"}   # window hotkeys (set by the main window)
        # Binding editor hooks: when set, the next click / key is delivered here instead of the phone.
        self.place_callback: Callable[[tuple[float, float]], None] | None = None
        self.capture_callback: Callable[[str], None] | None = None
        self._cap_alone: str | None = None       # a modifier pressed while capturing; a lone modifier is taken on release
        QApplication.instance().installEventFilter(self)

    @property
    def editing(self) -> bool:
        return self.place_callback is not None or self.capture_callback is not None

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        kind = event.type()
        if kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return self._on_key(event)
        if obj is self.video:
            if kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
                        QEvent.Type.MouseButtonDblClick):
                return self._on_mouse_button(event, kind != QEvent.Type.MouseButtonRelease)
            if kind == QEvent.Type.MouseMove:
                return self._on_mouse_move(event)
            if kind == QEvent.Type.Wheel:
                return self._on_wheel(event)
        return False

    # -- keyboard --------------------------------------------------------------------------
    def _on_key(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape:
            # Esc is handled here, not by a window shortcut: a shortcut stops working when the button you just
            # clicked still has keyboard focus but has been disabled. Dialogs and open drop-downs keep their Esc.
            if (self.escape_callback is None or not self.window.isActiveWindow()
                    or QApplication.activeModalWidget() is not None or QApplication.activePopupWidget() is not None):
                return False
            if event.type() == QEvent.Type.KeyPress and not event.isAutoRepeat():
                self.escape_callback()
            return True
        if not self.window.isActiveWindow():
            return False
        if not (self.engine.mapping_active or self.capture_callback):
            return False
        name = key_name(event)
        if name in self.direct_hotkeys and not self.capture_callback:
            if event.type() == QEvent.Type.KeyPress and not event.isAutoRepeat():
                self.direct_hotkeys[name]()
            return True
        if name in self.reserved_names and not self.capture_callback:
            return False                                  # a window hotkey: the shortcut handles it
        if event.isAutoRepeat():
            return True
        if name is None:
            return True
        pressed = event.type() == QEvent.Type.KeyPress
        if self.capture_callback:
            self._capture_key(name, pressed, event)
            return True
        hold = self.hold_hotkeys.get(name)
        if hold is not None:
            hold(pressed)
        self.engine.key_event(name, pressed)
        return True

    @staticmethod
    def _modifier_names(event) -> set[str]:
        flags = event.modifiers()
        names = set()
        if flags & Qt.KeyboardModifier.ControlModifier:
            names.add("Ctrl")
        if flags & Qt.KeyboardModifier.ShiftModifier:
            names.add("Shift")
        if flags & Qt.KeyboardModifier.AltModifier:
            names.add("Alt")
        return names

    def _capture_key(self, name: str, pressed: bool, event: QKeyEvent) -> None:
        """Key capture for the editor. A normal key with modifiers held gives a combination ("Shift+W"); a
        modifier pressed and released on its own is captured as that modifier ("Shift")."""
        if name in MODIFIERS:
            if pressed:
                self._cap_alone = name                    # wait: maybe a second key follows
            elif self._cap_alone == name:
                self._cap_alone = None
                self.capture_callback(name)
            return
        if not pressed:
            return
        self._cap_alone = None
        self.capture_callback(make_combo(self._modifier_names(event), name))

    # -- mouse -----------------------------------------------------------------------------
    def _on_mouse_button(self, event: QMouseEvent, pressed: bool) -> bool:
        name = mouse_name(event.button())
        if name is None:
            return False
        pos = self.video.map_to_device(event.position())
        if pressed and self.place_callback and name == "LMB":
            if pos is not None:
                self.place_callback(pos)
            return True
        if pressed and self.capture_callback:
            self._cap_alone = None
            self.capture_callback(make_combo(self._modifier_names(event), name))
            return True
        if self.editing or not self.connected():
            return False
        return self.engine.mouse_button(name, pressed, pos)

    def _on_mouse_move(self, event: QMouseEvent) -> bool:
        if self.editing or not self.connected():
            return False
        pos = self.video.map_to_device(event.position(), clamp=True)
        if pos is not None:
            self.engine.mouse_move(pos)
        return False

    def _on_wheel(self, event: QWheelEvent) -> bool:
        delta = event.angleDelta()
        if delta.y() == 0:
            return False
        self._wheel_accum += delta.y()
        if abs(self._wheel_accum) < 120:                  # smooth-scroll wheels send many small steps
            return bool(self.capture_callback or self.engine.has_wheel_binding())
        notches = 1 if self._wheel_accum > 0 else -1
        self._wheel_accum = 0
        if self.capture_callback:                         # binding editor: scrolling assigns WheelUp / WheelDown
            self._cap_alone = None
            self.capture_callback(make_combo(self._modifier_names(event), "WheelUp" if notches > 0 else "WheelDown"))
            return True
        if not self.connected() or self.place_callback:
            return False
        if self.engine.wheel_binding(notches):
            return True
        pos = self.video.map_to_device(event.position())
        if pos is None:
            return False
        return self.engine.wheel(pos, delta.x() / 120.0, delta.y() / 120.0)
