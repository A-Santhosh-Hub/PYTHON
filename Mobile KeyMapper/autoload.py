"""Decisions for switching profiles automatically when a different game comes to the foreground."""
from __future__ import annotations

from .profile import Profile, ProfileStore


def profile_to_load(store: ProfileStore, package: str, current: Profile | None) -> str | None:
    """Name of the profile to switch to for `package`, or None if there is none / it is already loaded."""
    name = store.find_by_package(package)
    if name and (current is None or name != current.name):
        return name
    return None


def should_stop_mapping(profile: Profile | None, package: str) -> bool:
    """Key mapping must stop when the user leaves the game the profile is linked to."""
    return bool(profile and profile.package and package and package != profile.package)
