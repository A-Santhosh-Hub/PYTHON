"""Step-2 test 1: list devices, authorization state and basic properties."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import paths  # noqa: E402
from app.device.adb import Adb  # noqa: E402


def main() -> int:
    adb = Adb()
    print("adb      :", adb.path)
    print("version  :", adb.version())
    print("server   :", paths.server_jar(), "exists" if paths.server_jar().is_file() else "MISSING")
    adb.start_server()
    devices = adb.devices()
    if not devices:
        print("No devices. Check cable (data, not charge-only), USB mode 'File transfer', USB debugging.")
        return 1
    for d in devices:
        print(f"\n{d.label}  state={d.state}")
        if d.hint:
            print("  ->", d.hint)
        if d.usable:
            for key, value in adb.device_details(d.serial).items():
                print(f"  {key:8}: {value}")
    return 0 if any(d.usable for d in devices) else 1


if __name__ == "__main__":
    raise SystemExit(main())
