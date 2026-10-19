"""Locations of bundled tools and per-user data (works from source and from a frozen exe)."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# The scrcpy client and server must match exactly (the protocol has no compatibility).
SCRCPY_VERSION = "5.0.1"
DEVICE_SERVER_PATH = "/data/local/tmp/scrcpy-server.jar"


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def vendor_dir() -> Path:
    return app_root() / "vendor"


def adb_path() -> Path:
    bundled = vendor_dir() / "adb" / "adb.exe"
    if bundled.is_file():
        return bundled
    found = shutil.which("adb")
    return Path(found) if found else bundled


def server_jar() -> Path:
    return vendor_dir() / f"scrcpy-server-v{SCRCPY_VERSION}"


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    path = Path(base) / "MobileKeyOne"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path
