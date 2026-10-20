"""Stable, human-readable names for keyboard keys and mouse buttons."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QKeySequence

MOUSE_NAMES = {
    Qt.MouseButton.LeftButton: "LMB",
    Qt.MouseButton.RightButton: "RMB",
    Qt.MouseButton.MiddleButton: "MMB",
    Qt.MouseButton.BackButton: "Mouse4",
    Qt.MouseButton.ForwardButton: "Mouse5",
}

_MODIFIER_NAMES = {
    Qt.Key.Key_Shift: "Shift", Qt.Key.Key_Control: "Ctrl", Qt.Key.Key_Alt: "Alt", Qt.Key.Key_Meta: "Meta",
}


def mouse_name(button: Qt.MouseButton) -> str | None:
    return MOUSE_NAMES.get(button)


def key_name(event: QKeyEvent) -> str | None:
    """Name for a key press, independent of Shift (so Shift+1 is still "1") and of the keyboard layout
    for letters, digits, function keys and the numpad (taken from the Windows virtual-key code)."""
    key = event.key()
    if key in _MODIFIER_NAMES:
        return _MODIFIER_NAMES[key]
    vk = event.nativeVirtualKey()
    numpad = bool(event.modifiers() & Qt.KeyboardModifier.KeypadModifier)
    if vk == 0xC0:                                   # the key above Tab (~): the same name with or without Shift
        return "`"
    if key in (Qt.Key.Key_AsciiTilde, Qt.Key.Key_QuoteLeft):
        return "`"
    if 0x30 <= vk <= 0x39 and not numpad:
        return chr(vk)
    if 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return f"Num {vk - 0x60}"
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    if key in (0, Qt.Key.Key_unknown):
        return None
    text = QKeySequence(key).toString(QKeySequence.SequenceFormat.PortableText)
    if not text:
        return None
    return f"Num {text}" if numpad else text
