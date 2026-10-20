"""Human names for Android app ids, so the UI can say 'Call of Duty: Mobile' instead of a package name."""
from __future__ import annotations

KNOWN = {
    "com.activision.callofduty.shooter": "Call of Duty: Mobile",
    "com.blitzteam.battleprime": "Battle Prime",
    "com.tencent.ig": "PUBG Mobile",
    "com.pubg.imobile": "BGMI",
    "com.dts.freefireth": "Free Fire",
    "com.dts.freefiremax": "Free Fire MAX",
    "com.miHoYo.GenshinImpact": "Genshin Impact",
    "com.mojang.minecraftpe": "Minecraft",
    "com.supercell.clashofclans": "Clash of Clans",
    "com.android.settings": "Android Settings",
    "com.android.launcher3": "Home screen",
    "com.bbk.launcher2": "Home screen",
}

_SKIP = {"com", "org", "net", "io", "android", "app", "apps", "mobile", "game", "games", "gp", "google"}


def friendly_name(package: str) -> str:
    if not package:
        return ""
    if package in KNOWN:
        return KNOWN[package]
    parts = [p for p in package.split(".") if p and p.lower() not in _SKIP]
    if not parts:
        return package
    words = " ".join(parts[-2:] if len(parts) >= 2 else parts).replace("_", " ")     # e.g. horus.beach.head -> Beach Head
    return " ".join(w[:1].upper() + w[1:] for w in words.split())
