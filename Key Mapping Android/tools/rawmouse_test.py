"""Checks the Windows raw-mouse path with real injected mouse movement (SendInput), no phone needed.

  1. raw counts arrive exactly as sent (independent of pointer acceleration)
  2. the cursor can be confined to a rectangle, and is free again after release
Needs the test window to get focus (Raw Input is only delivered to the focused window).
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from app.input.rawmouse import RawMouse, clip_cursor, release_cursor  # noqa: E402

user32 = ctypes.windll.user32
user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def move_mouse(dx: int, dy: int) -> None:
    event = INPUT(0, INPUT._U(MOUSEINPUT(dx, dy, 0, 0x0001, 0, 0)))     # MOUSEEVENTF_MOVE = relative
    user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))


def cursor_pos() -> tuple[int, int]:
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def main() -> int:
    app = QApplication([])
    window = QLabel("raw mouse test")
    window.resize(500, 400)
    window.show()
    window.raise_()
    window.activateWindow()
    end = time.time() + 3
    while not window.isActiveWindow() and time.time() < end:
        app.processEvents()
        time.sleep(0.05)
    if not window.isActiveWindow():
        print("SKIP: Windows did not give the test window focus (foreground lock). Click the window and rerun.")
        return 2

    got: list[tuple[int, int]] = []
    raw = RawMouse(lambda dx, dy: got.append((dx, dy)))
    ok = True

    def check(name: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= passed
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}  {detail}")

    check("raw input registered", raw.start(int(window.winId())))
    saved = cursor_pos()
    moves = [(10, 0), (10, 0), (-7, 12), (3, -4), (0, 25)]
    expected = (sum(m[0] for m in moves), sum(m[1] for m in moves))
    total, exact = (0, 0), False
    for attempt in range(8):                    # a hand on the real mouse adds counts: retry until a clean run
        got.clear()
        for dx, dy in moves:
            move_mouse(dx, dy)
            app.processEvents()
            time.sleep(0.01)
        for _ in range(6):
            app.processEvents()
            time.sleep(0.01)
        total = (sum(d[0] for d in got), sum(d[1] for d in got))
        if total == expected and len(got) == len(moves):
            exact = True
            break
    check("injected movement arrives as exact raw counts", exact,
          f"expected {expected}, got {total} from {len(got)} events (attempt {attempt + 1})"
          + ("" if exact else "  - your physical mouse was probably moving"))

    # confinement: move far beyond the rectangle
    got.clear()
    box = (300, 300, 700, 600)                    # a small rectangle, well inside the screen
    user32.SetCursorPos(500, 450)
    check("cursor confined", clip_cursor(*box))
    for _ in range(20):
        move_mouse(400, 300)
        app.processEvents()
        time.sleep(0.01)
    x, y = cursor_pos()
    check("cursor stays inside the rectangle", box[0] <= x <= box[2] and box[1] <= y <= box[3],
          f"cursor {x},{y} box {box}")
    check("raw counts keep flowing at the edge", sum(d[0] for d in got) >= 20 * 400 * 0.9,
          f"sum dx {sum(d[0] for d in got)}")
    release_cursor()
    move_mouse(-3000, -3000)
    for _ in range(5):
        app.processEvents()
        time.sleep(0.02)
    x2, y2 = cursor_pos()
    check("cursor free again after release", x2 < box[0] and y2 < box[1], f"cursor {x2},{y2}")

    raw.stop()
    got.clear()
    move_mouse(50, 50)
    for _ in range(5):
        app.processEvents()
        time.sleep(0.02)
    check("no events after stop()", not got)
    user32.SetCursorPos(*saved)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
