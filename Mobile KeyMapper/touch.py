"""Turns 'finger down / move / up' calls into scrcpy touch messages, one pointer id per finger."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Hashable

from ..stream import protocol

log = logging.getLogger(__name__)


@dataclass
class _Finger:
    pointer_id: int
    x: float
    y: float
    size: tuple[int, int]


class TouchInjector:
    """`get_control()` returns an object with send(bytes) (or None); `get_size()` the current video size.

    Positions are normalized (0..1). Each finger is owned by a hashable key (e.g. a key name), so a
    key can only ever hold one finger, and up to MAX_POINTERS fingers can be down at once.
    """

    def __init__(self, get_control: Callable[[], object | None], get_size: Callable[[], tuple[int, int]]) -> None:
        self._get_control = get_control
        self._get_size = get_size
        self._fingers: dict[Hashable, _Finger] = {}

    def size(self) -> tuple[int, int]:
        return self._get_size()

    @property
    def active_count(self) -> int:
        return len(self._fingers)

    def is_down(self, owner: Hashable) -> bool:
        return owner in self._fingers

    def _send(self, data: bytes) -> bool:
        control = self._get_control()
        return bool(control and control.send(data))

    def _free_pointer_id(self) -> int | None:
        used = {f.pointer_id for f in self._fingers.values()}
        return next((i for i in range(protocol.MAX_POINTERS) if i not in used), None)

    def _pixels(self, nx: float, ny: float, size: tuple[int, int]) -> tuple[int, int]:
        w, h = size
        return (min(w - 1, max(0, int(nx * w + 1e-6))), min(h - 1, max(0, int(ny * h + 1e-6))))

    def _drop_if_resized(self) -> None:
        size = self._get_size()
        if any(f.size != size for f in self._fingers.values()):
            # The screen rotated: the server would ignore these fingers anyway. Forget them.
            log.info("Video size changed; releasing %d touches", len(self._fingers))
            self._fingers.clear()

    def down(self, owner: Hashable, nx: float, ny: float) -> bool:
        self._drop_if_resized()
        size = self._get_size()
        if owner in self._fingers or size[0] <= 0 or size[1] <= 0:
            return False
        pointer_id = self._free_pointer_id()
        if pointer_id is None:
            log.warning("All %d touch pointers are in use", protocol.MAX_POINTERS)
            return False
        x, y = self._pixels(nx, ny, size)
        if not self._send(protocol.encode_touch(protocol.TOUCH_DOWN, pointer_id, x, y, *size, pressure=1.0)):
            return False
        self._fingers[owner] = _Finger(pointer_id, nx, ny, size)
        return True

    def move(self, owner: Hashable, nx: float, ny: float) -> bool:
        finger = self._fingers.get(owner)
        if finger is None:
            return False
        self._drop_if_resized()
        if owner not in self._fingers:
            return False
        x, y = self._pixels(nx, ny, finger.size)
        finger.x, finger.y = nx, ny
        return self._send(protocol.encode_touch(protocol.TOUCH_MOVE, finger.pointer_id, x, y, *finger.size))

    def up(self, owner: Hashable) -> bool:
        finger = self._fingers.pop(owner, None)
        if finger is None:
            return False
        x, y = self._pixels(finger.x, finger.y, finger.size)
        return self._send(protocol.encode_touch(protocol.TOUCH_UP, finger.pointer_id, x, y, *finger.size,
                                                pressure=0.0))

    def release_all(self) -> None:
        for owner in list(self._fingers):
            self.up(owner)

    def scroll(self, nx: float, ny: float, hscroll: float, vscroll: float) -> bool:
        size = self._get_size()
        if size[0] <= 0:
            return False
        x, y = self._pixels(nx, ny, size)
        return self._send(protocol.encode_scroll(x, y, *size, hscroll, vscroll))

    def key(self, keycode: int, pressed: bool) -> bool:
        action = protocol.KEY_DOWN if pressed else protocol.KEY_UP
        return self._send(protocol.encode_keycode(action, keycode))

    def back_or_screen_on(self, pressed: bool) -> bool:
        action = protocol.KEY_DOWN if pressed else protocol.KEY_UP
        return self._send(protocol.encode_back_or_screen_on(action))
