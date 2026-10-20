"""Window hotkeys (shooting mode, key mapping on/off, fullscreen) and the rules for choosing them."""
from __future__ import annotations

DEFAULT_HOTKEYS = {"capture": "F8", "cursor": "`", "mapping": "F9", "fullscreen": "F11",
                   "opacity_down": "F2", "opacity_up": "F3", "markers": "F4", "suspend": "Alt"}

HOTKEY_LABELS = {
    "capture": "Shooting mode (lock the mouse)",
    "cursor": "Free / lock the mouse (the ~ key, like GameLoop)",
    "mapping": "Key mapping on / off",
    "fullscreen": "Fullscreen",
    "opacity_down": "Key markers: more transparent",
    "opacity_up": "Key markers: more visible",
    "markers": "Key markers: hide / show",
    "suspend": "Hold to free the mouse (let go to aim again)",
}

# Only keys that never type text, so a hotkey cannot fire while you write a profile name.
ALLOWED_KEYS = frozenset({f"F{i}" for i in range(1, 13)} | {"Pause", "ScrollLock", "Ins", "Home", "End", "PgUp", "PgDown",
                                                              "`"})        # ` is the ~ key; typing it in a text box still works
# The hold-to-free key may also be a modifier, because it works while held, not as a one-shot hotkey.
HOLD_ACTIONS = frozenset({"suspend"})
HOLD_EXTRA_KEYS = frozenset({"Alt", "Ctrl", "Shift"})
ESCAPE_NAMES = frozenset({"Esc", "Escape"})
DIRECT_KEY = "`"       # the ~ key: handled by the input router, not by a window shortcut


def allowed_for(action: str) -> frozenset:
    return ALLOWED_KEYS | HOLD_EXTRA_KEYS if action in HOLD_ACTIONS else ALLOWED_KEYS


def pretty(key: str) -> str:
    """How a hotkey is shown to the user (the ` key is the ~ key)."""
    return "~" if key == "`" else key


def validate(hotkeys: dict[str, str], action: str, key: str, profile_inputs: set[str]) -> str | None:
    """Return why `key` cannot be the hotkey for `action`, or None if it is fine."""
    if action not in DEFAULT_HOTKEYS:
        return f"Unknown hotkey '{action}'."
    if key in ESCAPE_NAMES:
        return "Esc always releases the mouse and turns mapping off, so it cannot be a hotkey."
    if key not in allowed_for(action):
        extra = ", Alt, Ctrl or Shift" if action in HOLD_ACTIONS else ""
        return f"'{key}' cannot be a hotkey. Use F1-F12, ~, Pause, ScrollLock, Ins, Home, End, PgUp or PgDown{extra}."
    for other, current in hotkeys.items():
        if other != action and current == key:
            return f"'{key}' is already the hotkey for '{HOTKEY_LABELS[other]}'."
    if key in profile_inputs:
        return f"'{key}' is used by a control in this profile. Pick another key."
    return None


def load(settings) -> dict[str, str]:
    """Read the hotkeys from QSettings, falling back to the defaults for anything missing or invalid."""
    result = {}
    for action, default in DEFAULT_HOTKEYS.items():
        value = str(settings.value(f"hotkey_{action}", default))
        result[action] = value if value in allowed_for(action) else default
    if len(set(result.values())) != len(result):          # a corrupted settings file: do not keep duplicates
        return dict(DEFAULT_HOTKEYS)
    return result


def save(settings, hotkeys: dict[str, str]) -> None:
    for action, key in hotkeys.items():
        settings.setValue(f"hotkey_{action}", key)
