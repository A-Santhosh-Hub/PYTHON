"""Thin wrapper around adb.exe: device listing, properties, push, port forwarding."""
from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .. import paths

log = logging.getLogger(__name__)

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

STATE_HINTS = {
    "unauthorized": "Unlock the phone and tap 'Allow' on the USB debugging prompt "
                    "(tick 'Always allow from this computer').",
    "offline": "The device is offline. Unplug and replug the cable, or toggle USB debugging off and on.",
    "authorizing": "Waiting for you to accept the USB debugging prompt on the phone.",
    "recovery": "The device is in recovery mode.",
    "bootloader": "The device is in bootloader mode.",
    "no permissions": "Windows cannot access the device. Install the phone's USB driver.",
}


class AdbError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeviceInfo:
    serial: str
    state: str
    model: str = ""
    product: str = ""
    transport_id: str = ""

    @property
    def usable(self) -> bool:
        return self.state == "device"

    @property
    def label(self) -> str:
        name = self.model.replace("_", " ") or self.serial
        suffix = "" if self.usable else f" [{self.state}]"
        return f"{name} ({self.serial}){suffix}"

    @property
    def hint(self) -> str:
        return STATE_HINTS.get(self.state, "")


def parse_device_lines(text: str) -> list[DeviceInfo]:
    """Parse `adb devices -l` output or a `host:track-devices-l` payload."""
    devices: list[DeviceInfo] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("List of devices", "*")):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        props = dict(p.split(":", 1) for p in parts[2:] if ":" in p)
        devices.append(
            DeviceInfo(
                serial=serial,
                state=state,
                model=props.get("model", ""),
                product=props.get("product", ""),
                transport_id=props.get("transport_id", ""),
            )
        )
    return devices


class Adb:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = str(path or paths.adb_path())

    def _cmd(self, args: tuple[str, ...], serial: str | None) -> list[str]:
        cmd = [self.path]
        if serial:
            cmd += ["-s", serial]
        cmd += list(args)
        return cmd

    def run(self, *args: str, serial: str | None = None, timeout: float = 20,
            check: bool = True) -> subprocess.CompletedProcess:
        cmd = self._cmd(args, serial)
        log.debug("adb: %s", " ".join(cmd[1:]))
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=timeout, creationflags=CREATE_NO_WINDOW,
            )
        except FileNotFoundError as exc:
            raise AdbError(f"adb not found at {self.path}") from exc
        except subprocess.TimeoutExpired as exc:
            raise AdbError(f"adb {' '.join(args)} timed out after {timeout}s") from exc
        if check and proc.returncode != 0:
            raise AdbError((proc.stderr or proc.stdout).strip() or f"adb exited with {proc.returncode}")
        return proc

    def screencap(self, serial: str, timeout: float = 20) -> bytes:
        """A PNG screenshot of the phone's real screen (the exact pixels, before video compression)."""
        try:
            proc = subprocess.run(self._cmd(("exec-out", "screencap", "-p"), serial), capture_output=True,
                                  timeout=timeout, creationflags=CREATE_NO_WINDOW)
        except FileNotFoundError as exc:
            raise AdbError(f"adb not found at {self.path}") from exc
        except subprocess.TimeoutExpired as exc:
            raise AdbError(f"The phone did not answer the screenshot request within {timeout:.0f}s") from exc
        if proc.returncode != 0 or not proc.stdout.startswith(b"\x89PNG"):
            raise AdbError("Could not take a screenshot of the phone (some games block screenshots)")
        return proc.stdout

    def version(self) -> str:
        return self.run("version").stdout.strip().splitlines()[0]

    def start_server(self) -> None:
        self.run("start-server", timeout=30)

    def devices(self) -> list[DeviceInfo]:
        return parse_device_lines(self.run("devices", "-l").stdout)

    def getprop(self, serial: str, name: str) -> str:
        return self.run("shell", "getprop", name, serial=serial).stdout.strip()

    def device_details(self, serial: str) -> dict[str, str]:
        details = {
            "brand": self.getprop(serial, "ro.product.brand"),
            "model": self.getprop(serial, "ro.product.model"),
            "android": self.getprop(serial, "ro.build.version.release"),
            "sdk": self.getprop(serial, "ro.build.version.sdk"),
            "soc": self.getprop(serial, "ro.soc.model"),
        }
        size = self.run("shell", "wm", "size", serial=serial, check=False).stdout
        details["screen"] = size.strip().split(":")[-1].strip() if ":" in size else ""
        return details

    def push(self, serial: str, local: str | Path, remote: str) -> None:
        self.run("push", str(local), remote, serial=serial, timeout=60)

    def forward(self, serial: str, remote: str) -> int:
        """Forward a free local TCP port to `remote` and return the port."""
        out = self.run("forward", "tcp:0", remote, serial=serial).stdout.strip()
        try:
            return int(out.splitlines()[-1])
        except (ValueError, IndexError) as exc:
            raise AdbError(f"Unexpected output from adb forward: {out!r}") from exc

    def forward_remove(self, serial: str, port: int) -> None:
        self.run("forward", "--remove", f"tcp:{port}", serial=serial, check=False)

    def popen_shell(self, serial: str, command: str) -> subprocess.Popen:
        cmd = self._cmd(("shell", command), serial)
        log.debug("adb shell: %s", command)
        return subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )
