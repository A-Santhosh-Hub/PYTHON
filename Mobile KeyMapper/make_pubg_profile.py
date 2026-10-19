"""Creates (or resets) the 'PUBG Battle Royale' profile, linked to PUBG Mobile so it loads automatically.

Positions are pixels read from a screenshot (1608x720) of the live in-match HUD on the user's phone, turned into
fractions of the landscape screen. Only buttons that were visible on that HUD are included. PUBG shows more
buttons only in some situations (vehicle: Drive / Get in / Exit; Open door; Rescue; Carry; Shop; Parachute; heal;
grenade; fire mode; switch shoulder): add those from the in-game screen when they appear (Edit controls ->
Any other key -> click the button -> press a key).

The in-match HUD differs from PUBG's layout-editor screen, so always take positions from a real match.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import paths  # noqa: E402
from app.mapping.profile import Binding, Look, Profile, ProfileStore, Stick  # noqa: E402

PUBG_PACKAGE = "com.pubg.imobile"
NAME = "PUBG Battle Royale"

W, H = 1608.0, 720.0          # size of the screenshot the pixel positions below were read from


def at(px: float, py: float) -> tuple[float, float]:
    return round(px / W, 4), round(py / H, 4)


def build() -> Profile:
    profile = Profile(NAME, "landscape", package=PUBG_PACKAGE)
    # Joystick ring centre. Sprint (Shift) pushes the finger 3.8x the radius (about 274 px). Measured live: PUBG shows
    # its "Sprint" lock icon at the top-left (about 308,155) once the stick is pushed 216 px, and locks at about 274 px;
    # a push of only 158 px did nothing. Ctrl walks. The camera only turns from the right of centre (0.62-0.76), not from
    # the middle-left.
    sx, sy = at(310, 497)
    profile.set_stick(Stick(sx, sy, radius=0.10, ramp_ms=50, sprint_key="Shift", sprint_scale=3.8,
                            walk_key="Ctrl", walk_scale=0.5))
    profile.looks.append(Look(0.62, 0.12, 0.76, 0.40, sens_x=1.0, sens_y=1.0, ads_scale=0.75))
    controls = [
        # key, pixel position, mode, label, scope?
        ("LMB", (1360, 540), "hold", "Fire", False),
        ("J", (143, 367), "hold", "Fire (left side)", False),
        ("RMB", (1500, 376), "tap", "Scope", True),
        ("Space", (1498, 493), "tap", "Jump", False),
        ("C", (1352, 670), "tap", "Crouch", False),
        ("Z", (1452, 665), "tap", "Prone", False),
        ("R", (1247, 675), "tap", "Reload", False),
        ("X", (1048, 675), "tap", "Melee", False),
        ("V", (390, 612), "tap", "FPP / TPP", False),
        ("Tab", (150, 655), "tap", "Backpack", False),
        ("M", (1463, 90), "tap", "Map", False),
        ("1", (700, 655), "tap", "Weapon 1", False),
        ("2", (890, 650), "tap", "Weapon 2", False),
        ("3", (948, 603), "tap", "Pistol", False),
        ("WheelUp", (700, 655), "tap", "Wheel up: weapon 1", False),
        ("WheelDown", (890, 650), "tap", "Wheel down: weapon 2", False),
    ]
    for key, (px, py), mode, label, scope in controls:
        x, y = at(px, py)
        profile.add(Binding(key, x, y, mode, label, scope=scope))
    return profile


if __name__ == "__main__":
    store = ProfileStore(paths.data_dir() / "profiles")
    profile = build()
    unlinked = store.link_package(profile, PUBG_PACKAGE)
    print(f"saved '{NAME}' with {len(profile.bindings)} keys, 1 stick, 1 look zone, linked to {PUBG_PACKAGE}"
          + (f"; unlinked from: {', '.join(unlinked)}" if unlinked else ""))
