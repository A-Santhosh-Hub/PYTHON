"""Ready-made layouts for new profiles ("One-Click Setup") and the factory defaults used by Reset buttons.

The key choices follow what PC players of mobile shooters expect (and what the Tencent / BlueStacks style
emulators ship): WASD to move, Shift to sprint, Ctrl to walk, C crouch, Z prone, Space jump, Q / E lean,
R reload, F pick up, G grenade, Tab bag, M map, 1-3 weapons, mouse wheel to change weapon, left click fire,
right click scope. The screen positions are a starting point: the player drags each marker onto the real button.
"""
from __future__ import annotations

from .profile import Binding, Look, Profile, Stick

EMPTY = "empty"
STANDARD = "standard"
BATTLE_ROYALE = "battle_royale"

TEMPLATE_NAMES = {
    STANDARD: "Standard shooter  -  WASD, mouse aim, fire, scope, reload, crouch, jump, sprint, map, wheel weapons",
    BATTLE_ROYALE: "Battle royale (PC style)  -  adds Shift sprint, Ctrl walk, lean Q/E, prone, pick up, grenade, bag",
    EMPTY: "Empty  -  add every control yourself",
}

TEMPLATE_HELP = {
    STANDARD: "A typical shooter layout in landscape. The positions are a starting point: switch on 'Edit controls' "
              "and drag each marker onto the matching button of your game.",
    BATTLE_ROYALE: "Everything a PC battle-royale player expects: hold Shift to sprint (the stick is pushed further), "
                   "hold Ctrl to walk quietly, Q and E to lean, Z for prone, F to pick things up, G for a grenade, "
                   "Tab for the bag. Mouse sensitivity drops while you are scoped in. Drag the markers onto your "
                   "game's buttons.",
    EMPTY: "No controls. Use the palette in 'Edit controls' to add them one by one.",
}


def default_stick() -> Stick:
    return Stick(0.14, 0.70, radius=0.09, ramp_ms=50)


def default_look() -> Look:
    return Look(0.40, 0.12, 0.66, 0.50, sens_x=1.0, sens_y=1.0, accel=0.0, invert_y=False, ads_scale=0.75)


def standard_bindings() -> list[Binding]:
    return [
        Binding("LMB", 0.78, 0.68, "hold", "Fire"),
        Binding("RMB", 0.92, 0.48, "tap", "Scope", scope=True),
        Binding("R", 0.72, 0.88, "tap", "Reload"),
        Binding("C", 0.91, 0.68, "tap", "Crouch"),
        Binding("Space", 0.94, 0.86, "tap", "Jump"),
        Binding("Shift", 0.82, 0.32, "tap", "Sprint"),
        Binding("M", 0.86, 0.12, "tap", "Map"),
        Binding("WheelDown", 0.54, 0.88, "tap", "Next weapon"),
        Binding("WheelUp", 0.44, 0.88, "tap", "Previous weapon"),
    ]


def battle_royale_stick() -> Stick:
    return Stick(0.14, 0.70, radius=0.09, ramp_ms=50, sprint_key="Shift", sprint_scale=1.35, walk_key="Ctrl",
                 walk_scale=0.5)


def battle_royale_bindings() -> list[Binding]:
    return [
        Binding("LMB", 0.78, 0.68, "hold", "Fire"),
        Binding("RMB", 0.92, 0.48, "tap", "Scope", scope=True),
        Binding("R", 0.72, 0.88, "tap", "Reload"),
        Binding("C", 0.91, 0.64, "tap", "Crouch"),
        Binding("Z", 0.84, 0.84, "tap", "Prone"),
        Binding("Space", 0.95, 0.84, "tap", "Jump"),
        Binding("Q", 0.72, 0.32, "tap", "Lean left"),
        Binding("E", 0.80, 0.32, "tap", "Lean right"),
        Binding("F", 0.62, 0.55, "tap", "Pick up"),
        Binding("G", 0.80, 0.14, "tap", "Grenade"),
        Binding("Tab", 0.07, 0.40, "tap", "Bag"),
        Binding("M", 0.92, 0.12, "tap", "Map"),
        Binding("1", 0.44, 0.88, "tap", "Weapon 1"),
        Binding("2", 0.52, 0.88, "tap", "Weapon 2"),
        Binding("3", 0.60, 0.88, "tap", "Weapon 3"),
        Binding("WheelUp", 0.44, 0.72, "tap", "Wheel up"),
        Binding("WheelDown", 0.52, 0.72, "tap", "Wheel down"),
    ]


def apply_template(profile: Profile, template: str) -> None:
    """Replace the controls of `profile` with a template, keeping its name, orientation and linked game."""
    profile.bindings = []
    profile.sticks = []
    profile.looks = []
    if template == STANDARD:
        profile.sticks = [default_stick()]
        profile.looks = [default_look()]
        for binding in standard_bindings():
            profile.add(binding)
    elif template == BATTLE_ROYALE:
        profile.sticks = [battle_royale_stick()]
        profile.looks = [default_look()]
        for binding in battle_royale_bindings():
            profile.add(binding)


def build(template: str, name: str, orientation: str = "landscape", package: str = "") -> Profile:
    profile = Profile(name, orientation, package=package)
    apply_template(profile, template)
    return profile
