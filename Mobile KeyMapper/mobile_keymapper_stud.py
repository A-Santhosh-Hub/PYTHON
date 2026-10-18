#!/usr/bin/env python3
"""
Mobile Game USB Keymapper Studio (BlueStacks / GameLoop Style Overlay)
======================================================================
A visual drag-and-drop keyboard, mouse, and joystick/gamepad keymapper for
Android games mirrored over USB debugging (ADB + scrcpy).

New & Core Features:
1. USB Device List + "Allow USB Debugging" Popup Trigger:
   - Automatically locates `adb.exe` from Android Studio (`AppData\\Local\\Android\\Sdk\\platform-tools`),
     your `scrcpy` folder on `C:\\`, or system PATH.
   - Lists all connected USB devices (including `unauthorized` or `offline` states) in a dropdown.
   - Includes an "Authorize USB / Trigger Phone Popup" button (`adb reconnect` / `adb usb`) that
     forces the Android "Allow USB debugging?" authorization prompt on your phone screen just like Android Studio.
2. Select Path / Auto-Scan C:\\ Drive for `scrcpy` & `adb`:
   - Click "Select C:\\ Path (scrcpy/ADB)" to pick your `scrcpy` folder or `.exe` on `C:\\`.
   - Automatically finds `scrcpy.exe` and `adb.exe` inside the selected folder, saves the path for future
     launches, and immediately runs the screen mirror.
3. Input Mode Switch (Keyboard + Mouse vs. Controller Gamepad vs. Both):
   - One-click switch on the top bar to toggle between:
     * "KEYBOARD + MOUSE" (WASD + Mouse-Look + Key taps)
     * "CONTROLLER / GAMEPAD" (Left Stick + Right Stick + Triggers/Buttons)
     * "BOTH (HYBRID)"
4. Drag-and-Drop Visual Overlay (Edit Mode vs. Play Mode via F12):
   - Tap Key, WASD/Left-Stick Joystick, FPS Mouse-Look/Right-Stick Aim, Fire Button (with Rapid-Fire), and Swipe.
"""

from __future__ import annotations

import json
import math
import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field, asdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional, Tuple

# Optional third-party libraries for global low-level input & controller support
try:
    from pynput import keyboard as pynput_kb
    from pynput import mouse as pynput_mouse
    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False

try:
    import pygame
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False


CONFIG_FILE_PATH = Path.home() / ".mobile_keymapper_studio_config.json"


# ============================================================================
# DATA MODELS FOR DRAG-AND-DROP KEYMAPPING NODES
# ============================================================================

@dataclass
class KeyMapNode:
    """Represents a single draggable control widget on the overlay canvas."""
    id: str
    node_type: str  # "tap", "dpad", "aim", "fire", "swipe"
    label: str
    # Normalized coordinates (0.0 to 1.0) relative to the game mirror area
    norm_x: float
    norm_y: float
    # Secondary normalized coordinates (used for Swipe end-point)
    norm_x2: float = 0.0
    norm_y2: float = 0.0
    # Normalized radius (used for D-Pad / Joystick wheel size)
    norm_radius: float = 0.08
    # Bound keyboard key (e.g., "space", "r", "w", "MouseLeft")
    key_bind: str = ""
    # Bound controller button/axis (e.g., "BTN_0", "AXIS_RT", "LEFT_STICK", "RIGHT_STICK")
    pad_bind: str = ""
    # Additional keys for D-Pad (Up, Down, Left, Right)
    dpad_keys: Dict[str, str] = field(
        default_factory=lambda: {"up": "w", "down": "s", "left": "a", "right": "d"}
    )
    # Sensitivity & behavior settings
    sensitivity: float = 1.5
    rapid_fire: bool = False
    rapid_fire_cps: int = 12
    swipe_duration_ms: int = 90


# ============================================================================
# BUILT-IN STARTER PRESETS (FPS / BATTLE ROYALE & MOBA / ACTION)
# ============================================================================

def get_builtin_presets() -> Dict[str, List[KeyMapNode]]:
    """Returns ready-to-use drag-and-drop presets for popular mobile game genres."""
    fps_preset = [
        KeyMapNode(
            id="dpad_move",
            node_type="dpad",
            label="Move (WASD / L-Stick)",
            norm_x=0.18,
            norm_y=0.72,
            norm_radius=0.11,
            key_bind="WASD",
            pad_bind="LEFT_STICK",
            dpad_keys={"up": "w", "down": "s", "left": "a", "right": "d"},
        ),
        KeyMapNode(
            id="aim_camera",
            node_type="aim",
            label="Camera Look (Tab / R-Stick)",
            norm_x=0.68,
            norm_y=0.50,
            norm_radius=0.06,
            key_bind="tab",
            pad_bind="RIGHT_STICK",
            sensitivity=1.6,
        ),
        KeyMapNode(
            id="fire_main",
            node_type="fire",
            label="Fire (L-Click / RT)",
            norm_x=0.84,
            norm_y=0.68,
            norm_radius=0.045,
            key_bind="MouseLeft",
            pad_bind="AXIS_RT",
            rapid_fire=False,
        ),
        KeyMapNode(
            id="ads_scope",
            node_type="tap",
            label="Scope / ADS",
            norm_x=0.92,
            norm_y=0.58,
            key_bind="MouseRight",
            pad_bind="AXIS_LT",
        ),
        KeyMapNode(
            id="btn_jump",
            node_type="tap",
            label="Jump",
            norm_x=0.93,
            norm_y=0.76,
            key_bind="space",
            pad_bind="BTN_0",  # A / Cross
        ),
        KeyMapNode(
            id="btn_crouch",
            node_type="tap",
            label="Crouch",
            norm_x=0.88,
            norm_y=0.88,
            key_bind="c",
            pad_bind="BTN_1",  # B / Circle
        ),
        KeyMapNode(
            id="btn_prone",
            node_type="tap",
            label="Prone",
            norm_x=0.94,
            norm_y=0.88,
            key_bind="z",
            pad_bind="BTN_7",
        ),
        KeyMapNode(
            id="btn_reload",
            node_type="tap",
            label="Reload",
            norm_x=0.77,
            norm_y=0.86,
            key_bind="r",
            pad_bind="BTN_2",  # X / Square
        ),
        KeyMapNode(
            id="btn_interact",
            node_type="tap",
            label="Loot / Interact",
            norm_x=0.66,
            norm_y=0.68,
            key_bind="f",
            pad_bind="BTN_3",  # Y / Triangle
        ),
        KeyMapNode(
            id="btn_weapon1",
            node_type="tap",
            label="Weapon 1",
            norm_x=0.45,
            norm_y=0.88,
            key_bind="1",
            pad_bind="BTN_4",  # LB
        ),
        KeyMapNode(
            id="btn_weapon2",
            node_type="tap",
            label="Weapon 2",
            norm_x=0.55,
            norm_y=0.88,
            key_bind="2",
            pad_bind="BTN_5",  # RB
        ),
        KeyMapNode(
            id="btn_heal",
            node_type="tap",
            label="Heal / Medkit",
            norm_x=0.33,
            norm_y=0.88,
            key_bind="4",
            pad_bind="DPAD_UP",
        ),
        KeyMapNode(
            id="btn_map",
            node_type="tap",
            label="Map",
            norm_x=0.92,
            norm_y=0.14,
            key_bind="m",
            pad_bind="BTN_6",
        ),
    ]

    moba_preset = [
        KeyMapNode(
            id="dpad_move",
            node_type="dpad",
            label="Move (WASD / L-Stick)",
            norm_x=0.18,
            norm_y=0.74,
            norm_radius=0.11,
            key_bind="WASD",
            pad_bind="LEFT_STICK",
            dpad_keys={"up": "w", "down": "s", "left": "a", "right": "d"},
        ),
        KeyMapNode(
            id="atk_basic",
            node_type="tap",
            label="Basic Attack",
            norm_x=0.88,
            norm_y=0.82,
            key_bind="space",
            pad_bind="BTN_0",
        ),
        KeyMapNode(
            id="skill_1",
            node_type="tap",
            label="Skill 1",
            norm_x=0.74,
            norm_y=0.86,
            key_bind="q",
            pad_bind="BTN_2",
        ),
        KeyMapNode(
            id="skill_2",
            node_type="tap",
            label="Skill 2",
            norm_x=0.78,
            norm_y=0.68,
            key_bind="e",
            pad_bind="BTN_3",
        ),
        KeyMapNode(
            id="skill_ult",
            node_type="tap",
            label="Ultimate",
            norm_x=0.88,
            norm_y=0.56,
            key_bind="r",
            pad_bind="BTN_5",
        ),
        KeyMapNode(
            id="swipe_dash",
            node_type="swipe",
            label="Dash / Dodge Swipe",
            norm_x=0.50,
            norm_y=0.55,
            norm_x2=0.68,
            norm_y2=0.40,
            key_bind="shift_l",
            pad_bind="BTN_1",
            swipe_duration_ms=80,
        ),
    ]

    return {
        "FPS / Battle Royale (BGMI, Free Fire, CODM)": fps_preset,
        "MOBA / Action RPG": moba_preset,
    }


# ============================================================================
# AUTO-DISCOVERY FOR C:\ DRIVE SCRCPY & ANDROID STUDIO ADB
# ============================================================================

class PathResolver:
    """
    Finds `scrcpy.exe` and `adb.exe` across:
    1. User-selected custom paths (saved in ~/.mobile_keymapper_studio_config.json)
    2. Android Studio SDK default installation folders (`AppData\\Local\\Android\\Sdk\\platform-tools`)
    3. Common `C:\\` folders (`C:\\scrcpy*`, `C:\\Program Files\\scrcpy*`, Downloads, Desktop)
    4. System PATH environment variable
    """

    def __init__(self) -> None:
        self.scrcpy_path: str = ""
        self.adb_path: str = ""
        self.last_browse_dir: str = "C:\\" if platform.system() == "Windows" else str(Path.home())
        self.load_saved_config()
        self.auto_discover_binaries()

    def load_saved_config(self) -> None:
        if CONFIG_FILE_PATH.exists():
            try:
                data = json.loads(CONFIG_FILE_PATH.read_text(encoding="utf-8"))
                if data.get("scrcpy_path") and Path(data["scrcpy_path"]).is_file():
                    self.scrcpy_path = data["scrcpy_path"]
                if data.get("adb_path") and Path(data["adb_path"]).is_file():
                    self.adb_path = data["adb_path"]
                if data.get("last_browse_dir") and Path(data["last_browse_dir"]).exists():
                    self.last_browse_dir = data["last_browse_dir"]
            except Exception:
                pass

    def save_config(self) -> None:
        try:
            data = {
                "scrcpy_path": self.scrcpy_path,
                "adb_path": self.adb_path,
                "last_browse_dir": self.last_browse_dir,
            }
            CONFIG_FILE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def apply_user_selected_path(self, chosen_path: str) -> Tuple[bool, str]:
        """
        Accepts either a folder (e.g. `C:\\scrcpy-win64-v3.1`) or an executable file
        (`scrcpy.exe` / `adb.exe`) and automatically links both `scrcpy` and `adb`.
        """
        p = Path(chosen_path)
        if not p.exists():
            return False, f"Path does not exist: {chosen_path}"

        folder = p if p.is_dir() else p.parent
        self.last_browse_dir = str(folder)

        is_win = platform.system() == "Windows"
        scrcpy_exe_name = "scrcpy.exe" if is_win else "scrcpy"
        adb_exe_name = "adb.exe" if is_win else "adb"

        # If the user directly picked an executable, assign it first
        if p.is_file():
            low_name = p.name.lower()
            if "scrcpy" in low_name:
                self.scrcpy_path = str(p)
            elif "adb" in low_name:
                self.adb_path = str(p)

        # Search the chosen folder and immediate subfolders for scrcpy & adb
        candidate_dirs = [folder]
        try:
            candidate_dirs.extend([d for d in folder.iterdir() if d.is_dir()][:15])
        except Exception:
            pass

        for d in candidate_dirs:
            s_cand = d / scrcpy_exe_name
            if s_cand.is_file():
                self.scrcpy_path = str(s_cand)
            a_cand = d / adb_exe_name
            if a_cand.is_file():
                self.adb_path = str(a_cand)

        self.auto_discover_binaries()
        self.save_config()

        found_parts = []
        if self.scrcpy_path:
            found_parts.append(f"scrcpy: {self.scrcpy_path}")
        if self.adb_path:
            found_parts.append(f"adb: {self.adb_path}")

        if found_parts:
            return True, "Found & Saved:\n" + "\n".join(found_parts)
        return False, f"Could not find {scrcpy_exe_name} or {adb_exe_name} in {folder}"

    def auto_discover_binaries(self) -> None:
        """Automatically scans PATH, Android Studio SDK, and C:\\ drive folders."""
        is_win = platform.system() == "Windows"
        scrcpy_name = "scrcpy.exe" if is_win else "scrcpy"
        adb_name = "adb.exe" if is_win else "adb"

        # 1. If scrcpy_path is already known, check if adb.exe sits right next to it
        if self.scrcpy_path and Path(self.scrcpy_path).is_file() and not self.adb_path:
            sibling_adb = Path(self.scrcpy_path).parent / adb_name
            if sibling_adb.is_file():
                self.adb_path = str(sibling_adb)

        # 2. Check system PATH
        if not self.scrcpy_path:
            w_scrcpy = shutil.which("scrcpy")
            if w_scrcpy:
                self.scrcpy_path = w_scrcpy
        if not self.adb_path:
            w_adb = shutil.which("adb")
            if w_adb:
                self.adb_path = w_adb

        if not is_win:
            return

        # 3. Scan common Windows C:\ locations and Android Studio SDK paths
        home = Path.home()
        local_appdata = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        android_sdk_adb_candidates = [
            local_appdata / "Android" / "Sdk" / "platform-tools" / "adb.exe",
            Path("C:/Android/sdk/platform-tools/adb.exe"),
            Path("C:/Program Files (x86)/Android/android-sdk/platform-tools/adb.exe"),
            Path("C:/platform-tools/adb.exe"),
        ]
        for cand in android_sdk_adb_candidates:
            if not self.adb_path and cand.is_file():
                self.adb_path = str(cand)
                break

        # Scan C:\ root, Program Files, Downloads, Desktop for any folder starting with "scrcpy"
        search_roots = [
            Path("C:/"),
            Path("C:/Program Files"),
            Path("C:/Program Files (x86)"),
            home / "Downloads",
            home / "Desktop",
        ]
        for root_dir in search_roots:
            if not root_dir.exists():
                continue
            try:
                for item in root_dir.iterdir():
                    if item.is_dir() and ("scrcpy" in item.name.lower() or "platform-tools" in item.name.lower()):
                        s_exe = item / "scrcpy.exe"
                        a_exe = item / "adb.exe"
                        if not self.scrcpy_path and s_exe.is_file():
                            self.scrcpy_path = str(s_exe)
                        if not self.adb_path and a_exe.is_file():
                            self.adb_path = str(a_exe)
                        # Check one nested level (e.g., extracted zip folder)
                        for sub in item.iterdir():
                            if sub.is_dir():
                                if not self.scrcpy_path and (sub / "scrcpy.exe").is_file():
                                    self.scrcpy_path = str(sub / "scrcpy.exe")
                                if not self.adb_path and (sub / "adb.exe").is_file():
                                    self.adb_path = str(sub / "adb.exe")
            except Exception:
                continue


# ============================================================================
# LOW-LATENCY PERSISTENT ADB TOUCH & USB AUTHORIZATION ENGINE
# ============================================================================

@dataclass
class UsbDeviceEntry:
    serial: str
    state: str       # "device" (authorized), "unauthorized", "offline"
    model: str = ""

    @property
    def display_label(self) -> str:
        status_tag = {
            "device": "READY",
            "unauthorized": "ALLOW POPUP ON PHONE!",
            "offline": "OFFLINE",
        }.get(self.state, self.state.upper())
        model_Part = f" ({self.model})" if self.model else ""
        return f"{self.serial}{model_Part} [{status_tag}]"


class FastAdbTouchEngine:
    """
    High-speed ADB touch dispatcher + USB Device Manager.
    - Supports listing all connected USB devices (including `unauthorized` phones waiting
      for the user to tap "Allow USB debugging" on their mobile screen).
    - Provides `trigger_usb_authorization_popup()` which restarts the ADB handshake
      (`adb start-server`, `adb reconnect`, `adb usb`) so the phone displays the
      "Allow USB debugging?" dialog just like Android Studio.
    - Keeps a persistent `adb shell` pipe open for ~5-15ms gaming touch response.
    """

    def __init__(self, resolver: PathResolver) -> None:
        self.resolver = resolver
        self.devices: List[UsbDeviceEntry] = []
        self.device_serial: Optional[str] = None
        self.device_width: int = 2400   # Default landscape width
        self.device_height: int = 1080  # Default landscape height
        self.connected: bool = False
        self.supports_motionevent: bool = True

        self._shell_proc: Optional[subprocess.Popen] = None
        self._cmd_queue: "queue.Queue[str]" = queue.Queue(maxsize=400)
        self._running: bool = True
        self._lock = threading.Lock()

        self._pointer_down: bool = False
        self._active_owner: Optional[str] = None

        self._worker_thread = threading.Thread(target=self._shell_worker, daemon=True)
        self._worker_thread.start()

    def _get_creation_flags(self) -> int:
        if platform.system() == "Windows":
            return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        return 0

    def list_usb_devices(self) -> Tuple[List[UsbDeviceEntry], str]:
        """Scans `adb devices -l` and returns all connected USB devices and their auth status."""
        self.resolver.auto_discover_binaries()
        adb_bin = self.resolver.adb_path
        if not adb_bin or not Path(adb_bin).is_file():
            self.connected = False
            self.devices = []
            return (
                [],
                "ADB not found! Click 'Select C:\\ Path' to select your scrcpy or Android SDK folder.",
            )

        try:
            # Ensure ADB server is running
            subprocess.run(
                [adb_bin, "start-server"],
                capture_output=True,
                text=True,
                timeout=4.0,
                creationflags=self._get_creation_flags(),
            )
            res = subprocess.run(
                [adb_bin, "devices", "-l"],
                capture_output=True,
                text=True,
                timeout=4.0,
                creationflags=self._get_creation_flags(),
            )
            found: List[UsbDeviceEntry] = []
            for raw_line in res.stdout.splitlines()[1:]:
                line = raw_line.strip()
                if not line or line.startswith("*"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    serial = parts[0]
                    state = parts[1]
                    model = ""
                    for token in parts[2:]:
                        if token.startswith("model:"):
                            model = token.split(":", 1)[1]
                    found.append(UsbDeviceEntry(serial=serial, state=state, model=model))

            self.devices = found
            if not found:
                self.connected = False
                return (
                    [],
                    "No USB phone detected. Plug in USB cable, set USB mode to File Transfer/PTP, and click 'Allow USB Popup'.",
                )

            # Prefer an authorized device, otherwise select the first device
            chosen = next((d for d in found if d.state == "device"), found[0])
            return self.select_device(chosen.serial)

        except Exception as exc:
            self.connected = False
            return [], f"ADB scan error: {exc}"

    def select_device(self, serial: str) -> Tuple[List[UsbDeviceEntry], str]:
        """Selects a specific device from the USB list and queries its resolution if authorized."""
        adb_bin = self.resolver.adb_path
        target = next((d for d in self.devices if d.serial == serial), None)
        self.device_serial = serial

        if target and target.state == "unauthorized":
            self.connected = False
            return (
                self.devices,
                f"Phone '{serial}' is UNAUTHORIZED! Unlock your phone screen and tap 'Allow' on the 'Allow USB debugging?' popup (or click 'Allow USB Popup').",
            )

        if target and target.state != "device":
            self.connected = False
            return self.devices, f"Phone '{serial}' is currently in '{target.state}' state."

        self._restart_persistent_shell()

        # Query physical size & orientation
        try:
            wm_res = subprocess.run(
                [adb_bin, "-s", serial, "shell", "wm", "size"],
                capture_output=True,
                text=True,
                timeout=3.0,
                creationflags=self._get_creation_flags(),
            )
            w, h = 1080, 2400
            for line in wm_res.stdout.splitlines():
                if "Override size:" in line or "Physical size:" in line:
                    dims = line.split(":")[-1].strip().split("x")
                    if len(dims) == 2 and dims[0].isdigit() and dims[1].isdigit():
                        w, h = int(dims[0]), int(dims[1])

            rot_res = subprocess.run(
                [adb_bin, "-s", serial, "shell", "dumpsys", "input"],
                capture_output=True,
                text=True,
                timeout=3.0,
                creationflags=self._get_creation_flags(),
            )
            is_landscape = True
            if "SurfaceOrientation: 0" in rot_res.stdout or "SurfaceOrientation: 2" in rot_res.stdout:
                is_landscape = False

            if is_landscape:
                self.device_width = max(w, h)
                self.device_height = min(w, h)
            else:
                self.device_width = min(w, h)
                self.device_height = max(w, h)

            self.connected = True
            return (
                self.devices,
                f"Connected: {serial} ({self.device_width}x{self.device_height})",
            )
        except Exception as exc:
            self.connected = False
            return self.devices, f"Connected to {serial}, but resolution query failed: {exc}"

    def trigger_usb_authorization_popup(self) -> Tuple[List[UsbDeviceEntry], str]:
        """
        Forces ADB to reset the USB connection and re-request RSA authorization from the phone.
        This triggers the 'Allow USB debugging?' popup on the phone screen just like Android Studio.
        """
        self.resolver.auto_discover_binaries()
        adb_bin = self.resolver.adb_path
        if not adb_bin or not Path(adb_bin).is_file():
            return (
                [],
                "Cannot find adb.exe! Please click 'Select C:\\ Path' and choose your scrcpy folder first.",
            )

        flags = self._get_creation_flags()
        try:
            # Step 1: Try `adb reconnect` and `adb reconnect offline`
            subprocess.run([adb_bin, "start-server"], capture_output=True, timeout=4.0, creationflags=flags)
            subprocess.run([adb_bin, "reconnect"], capture_output=True, timeout=3.0, creationflags=flags)
            subprocess.run([adb_bin, "reconnect", "offline"], capture_output=True, timeout=3.0, creationflags=flags)

            # Step 2: Restart ADB server if no devices or unauthorized to force a fresh RSA handshake popup
            devices, msg = self.list_usb_devices()
            if not devices or any(d.state != "device" for d in devices):
                subprocess.run([adb_bin, "kill-server"], capture_output=True, timeout=3.0, creationflags=flags)
                time.sleep(0.4)
                subprocess.run([adb_bin, "start-server"], capture_output=True, timeout=4.0, creationflags=flags)
                subprocess.run([adb_bin, "usb"], capture_output=True, timeout=3.0, creationflags=flags)
                time.sleep(0.5)
                devices, msg = self.list_usb_devices()

            return devices, msg
        except Exception as exc:
            return [], f"USB Auth Request Error: {exc}"

    def set_orientation_mode(self, landscape: bool) -> None:
        w, h = self.device_width, self.device_height
        if landscape:
            self.device_width = max(w, h)
            self.device_height = min(w, h)
        else:
            self.device_width = min(w, h)
            self.device_height = max(w, h)

    def _restart_persistent_shell(self) -> None:
        with self._lock:
            if self._shell_proc is not None:
                try:
                    self._shell_proc.terminate()
                except Exception:
                    pass
                self._shell_proc = None

            adb_bin = self.resolver.adb_path
            if not adb_bin or not Path(adb_bin).is_file() or not self.device_serial:
                return

            try:
                cmd = [adb_bin, "-s", self.device_serial, "shell"]
                self._shell_proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                    creationflags=self._get_creation_flags(),
                )
            except Exception:
                self._shell_proc = None

    def _shell_worker(self) -> None:
        while self._running:
            try:
                cmd_line = self._cmd_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            with self._lock:
                proc = self._shell_proc
                if proc is None or proc.poll() is not None:
                    self._restart_persistent_shell()
                    proc = self._shell_proc

                if proc is not None and proc.stdin is not None:
                    try:
                        proc.stdin.write(cmd_line + "\n")
                        proc.stdin.flush()
                    except Exception:
                        self._restart_persistent_shell()

    def _enqueue(self, shell_cmd: str) -> None:
        if not self.connected:
            return
        try:
            self._cmd_queue.put_nowait(shell_cmd)
        except queue.Full:
            pass

    def norm_to_device(self, norm_x: float, norm_y: float) -> Tuple[int, int]:
        x = int(max(0.0, min(1.0, norm_x)) * self.device_width)
        y = int(max(0.0, min(1.0, norm_y)) * self.device_height)
        return x, y

    def send_tap(self, norm_x: float, norm_y: float) -> None:
        x, y = self.norm_to_device(norm_x, norm_y)
        self._enqueue(f"input tap {x} {y} &")

    def send_swipe(
        self,
        norm_x1: float,
        norm_y1: float,
        norm_x2: float,
        norm_y2: float,
        duration_ms: int = 90,
    ) -> None:
        x1, y1 = self.norm_to_device(norm_x1, norm_y1)
        x2, y2 = self.norm_to_device(norm_x2, norm_y2)
        self._enqueue(f"input swipe {x1} {y1} {x2} {y2} {max(20, int(duration_ms))} &")

    def send_touch_down(self, owner: str, norm_x: float, norm_y: float) -> None:
        x, y = self.norm_to_device(norm_x, norm_y)
        if self.supports_motionevent:
            if self._pointer_down and self._active_owner != owner:
                self._enqueue(f"input motionevent UP {x} {y}")
            self._pointer_down = True
            self._active_owner = owner
            self._enqueue(f"input motionevent DOWN {x} {y}")
        else:
            self._enqueue(f"input swipe {x} {y} {x} {y} 350 &")

    def send_touch_move(self, owner: str, norm_x: float, norm_y: float) -> None:
        if not self._pointer_down or self._active_owner != owner:
            self.send_touch_down(owner, norm_x, norm_y)
            return
        x, y = self.norm_to_device(norm_x, norm_y)
        if self.supports_motionevent:
            self._enqueue(f"input motionevent MOVE {x} {y}")

    def send_touch_up(self, owner: str, norm_x: float, norm_y: float) -> None:
        if not self._pointer_down or self._active_owner != owner:
            return
        x, y = self.norm_to_device(norm_x, norm_y)
        self._pointer_down = False
        self._active_owner = None
        if self.supports_motionevent:
            self._enqueue(f"input motionevent UP {x} {y}")

    def shutdown(self) -> None:
        self._running = False
        with self._lock:
            if self._shell_proc is not None:
                try:
                    self._shell_proc.terminate()
                except Exception:
                    pass


# ============================================================================
# CONTROLLER / JOYSTICK POLLING MANAGER (PYGAME)
# ============================================================================

class GamepadManager:
    """
    Polls connected USB or Bluetooth controllers (Xbox, PlayStation, Generic USB)
    and fires callbacks for button presses, triggers, and analog stick motion.
    """

    def __init__(
        self,
        on_button_down: Callable[[str], None],
        on_button_up: Callable[[str], None],
        on_sticks_update: Callable[[float, float, float, float], None],
    ) -> None:
        self.on_button_down = on_button_down
        self.on_button_up = on_button_up
        self.on_sticks_update = on_sticks_update

        self.joystick: Optional["pygame.joystick.Joystick"] = None
        self.controller_name: str = "No Controller Detected"
        self._running: bool = False
        self._button_states: Dict[str, bool] = {}
        self.deadzone: float = 0.16

        if HAS_PYGAME:
            try:
                pygame.init()
                pygame.joystick.init()
                self.refresh_controllers()
                self._running = True
                threading.Thread(target=self._poll_loop, daemon=True).start()
            except Exception:
                pass

    def refresh_controllers(self) -> str:
        if not HAS_PYGAME:
            self.controller_name = "Install 'pygame' for Joystick support"
            return self.controller_name

        try:
            pygame.joystick.quit()
            pygame.joystick.init()
            count = pygame.joystick.get_count()
            if count > 0:
                self.joystick = pygame.joystick.Joystick(0)
                self.joystick.init()
                self.controller_name = self.joystick.get_name()
            else:
                self.joystick = None
                self.controller_name = "No USB/BT Joystick Connected"
        except Exception as exc:
            self.controller_name = f"Joystick Error: {exc}"
        return self.controller_name

    def _apply_deadzone(self, val: float) -> float:
        return 0.0 if abs(val) < self.deadzone else val

    def _poll_loop(self) -> None:
        while self._running:
            if not HAS_PYGAME or self.joystick is None:
                time.sleep(0.5)
                continue

            try:
                pygame.event.pump()
                js = self.joystick

                for idx in range(js.get_numbuttons()):
                    b_name = f"BTN_{idx}"
                    pressed = bool(js.get_button(idx))
                    prev = self._button_states.get(b_name, False)
                    if pressed and not prev:
                        self._button_states[b_name] = True
                        self.on_button_down(b_name)
                    elif not pressed and prev:
                        self._button_states[b_name] = False
                        self.on_button_up(b_name)

                if js.get_numhats() > 0:
                    hx, hy = js.get_hat(0)
                    hat_map = {
                        "DPAD_LEFT": hx < 0,
                        "DPAD_RIGHT": hx > 0,
                        "DPAD_UP": hy > 0,
                        "DPAD_DOWN": hy < 0,
                    }
                    for h_name, active in hat_map.items():
                        prev = self._button_states.get(h_name, False)
                        if active and not prev:
                            self._button_states[h_name] = True
                            self.on_button_down(h_name)
                        elif not active and prev:
                            self._button_states[h_name] = False
                            self.on_button_up(h_name)

                num_axes = js.get_numaxes()
                lx = self._apply_deadzone(js.get_axis(0)) if num_axes > 0 else 0.0
                ly = self._apply_deadzone(js.get_axis(1)) if num_axes > 1 else 0.0
                rx = self._apply_deadzone(js.get_axis(2)) if num_axes > 2 else 0.0
                ry = self._apply_deadzone(js.get_axis(3)) if num_axes > 3 else 0.0

                if num_axes >= 6:
                    lt_val = js.get_axis(4)
                    rt_val = js.get_axis(5)
                    for t_name, t_val in [("AXIS_LT", lt_val), ("AXIS_RT", rt_val)]:
                        active = t_val > 0.3
                        prev = self._button_states.get(t_name, False)
                        if active and not prev:
                            self._button_states[t_name] = True
                            self.on_button_down(t_name)
                        elif not active and prev:
                            self._button_states[t_name] = False
                            self.on_button_up(t_name)

                self.on_sticks_update(lx, ly, rx, ry)
            except Exception:
                pass

            time.sleep(0.016)


# ============================================================================
# VISUAL DRAG-AND-DROP OVERLAY STUDIO GUI (TKINTER)
# ============================================================================

class MobileKeymapperStudio:
    """
    Main application window that acts as a transparent drag-and-drop overlay
    directly over the mirrored mobile screen (`scrcpy` or Android Studio mirror).
    """

    NODE_COLORS = {
        "tap": ("#00E5FF", "#004D61"),     # Cyan
        "dpad": ("#00E676", "#004D25"),    # Emerald Green
        "aim": ("#FFEA00", "#5C5300"),     # Amber Gold
        "fire": ("#FF3D00", "#661800"),    # Crimson Orange
        "swipe": ("#D500F9", "#4A0057"),   # Neon Purple
    }

    INPUT_MODES = [
        "KEYBOARD + MOUSE",
        "CONTROLLER / GAMEPAD",
        "BOTH (KB/M + GAMEPAD)",
    ]

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Mobile Game USB Keymapper Studio (Edit & Play)")
        self.root.geometry("1220x700+80+60")
        self.root.configure(bg="#121418")

        self.root.attributes("-topmost", True)
        self.overlay_alpha: float = 0.78
        self._apply_window_transparency(self.overlay_alpha)

        # Core path & ADB engines
        self.path_resolver = PathResolver()
        self.adb_engine = FastAdbTouchEngine(self.path_resolver)
        self.scrcpy_proc: Optional[subprocess.Popen] = None

        # State flags
        self.mode: str = "EDIT"  # "EDIT" or "PLAY"
        self.input_device_mode: str = "BOTH (KB/M + GAMEPAD)"
        self.landscape_mode: bool = True
        self.fps_aim_locked: bool = False

        # Active nodes list
        presets = get_builtin_presets()
        self.nodes: List[KeyMapNode] = list(
            presets["FPS / Battle Royale (BGMI, Free Fire, CODM)"]
        )
        self.selected_node: Optional[KeyMapNode] = None
        self.waiting_for_bind_node: Optional[KeyMapNode] = None
        self._drag_data: Dict[str, object] = {"node": None, "handle": "main"}

        # Runtime play-mode state tracking
        self._pressed_keys: set[str] = set()
        self._dpad_touch_active: bool = False
        self._dpad_curr_norm: Tuple[float, float] = (0.0, 0.0)
        self._aim_curr_norm: Tuple[float, float] = (0.68, 0.50)
        self._last_mouse_pos: Optional[Tuple[int, int]] = None
        self._rapid_fire_active: bool = False

        # Build UI
        self._build_top_toolbar()
        self._build_usb_and_mode_bar()
        self._build_canvas_and_sidebar()

        # Start controller manager
        self.gamepad = GamepadManager(
            on_button_down=self._on_gamepad_button_down,
            on_button_up=self._on_gamepad_button_up,
            on_sticks_update=self._on_gamepad_sticks_update,
        )

        # Bind keyboard & mouse events
        self._setup_input_listeners()

        # Initial ADB scan & render
        self._refresh_adb_status()
        self.root.after(100, self.redraw_canvas)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------------
    # WINDOW TRANSPARENCY & UI BARS
    # ------------------------------------------------------------------------

    def _apply_window_transparency(self, alpha: float) -> None:
        try:
            self.root.attributes("-alpha", alpha)
        except Exception:
            pass

    def _build_top_toolbar(self) -> None:
        """Top Row 1: Play/Edit Mode, Add Drag-and-Drop Widgets, Presets, Save/Load JSON."""
        self.toolbar = tk.Frame(self.root, bg="#1B1F27", height=44, padx=8, pady=5)
        self.toolbar.pack(side=tk.TOP, fill=tk.X)

        btn_style = {
            "bg": "#29303D",
            "fg": "#F0F4F8",
            "activebackground": "#3B4659",
            "activeforeground": "#FFFFFF",
            "relief": tk.FLAT,
            "font": ("Segoe UI", 9, "bold"),
            "padx": 8,
            "pady": 4,
            "cursor": "hand2",
        }

        self.btn_mode = tk.Button(
            self.toolbar,
            text="MODE: EDIT OVERLAY (F12)",
            bg="#00C853",
            fg="#0A0E14",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=10,
            pady=4,
            command=self.toggle_play_edit_mode,
        )
        self.btn_mode.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(
            self.toolbar,
            text="Drag & Drop Widgets:",
            bg="#1B1F27",
            fg="#9FB3C8",
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT, padx=(2, 4))

        tk.Button(
            self.toolbar,
            text="+ Tap Key",
            command=lambda: self.add_node("tap"),
            **btn_style,
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            self.toolbar,
            text="+ WASD / Stick",
            command=lambda: self.add_node("dpad"),
            **btn_style,
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            self.toolbar,
            text="+ Mouse Look",
            command=lambda: self.add_node("aim"),
            **btn_style,
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            self.toolbar,
            text="+ Fire Button",
            command=lambda: self.add_node("fire"),
            **btn_style,
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            self.toolbar,
            text="+ Swipe",
            command=lambda: self.add_node("swipe"),
            **btn_style,
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            self.toolbar,
            text="Load JSON",
            command=self.load_profile_dialog,
            **btn_style,
        ).pack(side=tk.RIGHT, padx=2)

        tk.Button(
            self.toolbar,
            text="Save JSON",
            command=self.save_profile_dialog,
            **btn_style,
        ).pack(side=tk.RIGHT, padx=2)

        self.preset_var = tk.StringVar(
            value="FPS / Battle Royale (BGMI, Free Fire, CODM)"
        )
        preset_menu = ttk.Combobox(
            self.toolbar,
            textvariable=self.preset_var,
            values=list(get_builtin_presets().keys()),
            state="readonly",
            width=30,
        )
        preset_menu.pack(side=tk.RIGHT, padx=6)
        preset_menu.bind("<<ComboboxSelected>>", self._on_preset_selected)

    def _build_usb_and_mode_bar(self) -> None:
        """
        Top Row 2: Dedicated bar for:
        1) USB Device List Dropdown + 'Allow USB Popup' button (Android Studio style)
        2) 'Select C:\\ Path (scrcpy/ADB)' + 'Launch Mirror (scrcpy)'
        3) Input Switch: Keyboard & Mouse vs. Controller Gamepad vs. Both
        """
        self.usb_bar = tk.Frame(self.root, bg="#222834", height=44, padx=8, pady=5)
        self.usb_bar.pack(side=tk.TOP, fill=tk.X)

        # 1. USB Device List & Allow USB Debugging Popup Trigger
        tk.Label(
            self.usb_bar,
            text="USB Mobile:",
            bg="#222834",
            fg="#00E5FF",
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 4))

        self.device_var = tk.StringVar(value="Scanning USB...")
        self.device_combo = ttk.Combobox(
            self.usb_bar,
            textvariable=self.device_var,
            values=["No USB Devices"],
            state="readonly",
            width=27,
        )
        self.device_combo.pack(side=tk.LEFT, padx=3)
        self.device_combo.bind("<<ComboboxSelected>>", self._on_device_combo_selected)

        tk.Button(
            self.usb_bar,
            text="Refresh List",
            bg="#2D3748",
            fg="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            padx=7,
            pady=3,
            cursor="hand2",
            command=self._refresh_adb_status,
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            self.usb_bar,
            text="Allow USB Debugging Popup",
            bg="#F59E0B",
            fg="#0F172A",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=3,
            cursor="hand2",
            command=self.request_usb_debugging_popup,
        ).pack(side=tk.LEFT, padx=3)

        tk.Frame(self.usb_bar, bg="#3E4859", width=2, height=24).pack(
            side=tk.LEFT, padx=8
        )

        # 2. C:\ Path Selector & scrcpy Mirror Launcher
        tk.Button(
            self.usb_bar,
            text="Select C:\\ Path (scrcpy / ADB)",
            bg="#3B82F6",
            fg="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=3,
            cursor="hand2",
            command=self.select_c_drive_path_dialog,
        ).pack(side=tk.LEFT, padx=3)

        tk.Button(
            self.usb_bar,
            text="Launch Mirror (scrcpy)",
            bg="#10B981",
            fg="#06281E",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            padx=9,
            pady=3,
            cursor="hand2",
            command=self.launch_scrcpy_mirror,
        ).pack(side=tk.LEFT, padx=3)

        # 3. Input Control Switch (Keyboard + Mouse vs. Controller Gamepad vs. Both)
        self.btn_input_switch = tk.Button(
            self.usb_bar,
            text=f"INPUT: {self.input_device_mode}",
            bg="#8B5CF6",
            fg="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.cycle_input_device_mode,
        )
        self.btn_input_switch.pack(side=tk.RIGHT, padx=4)

        tk.Label(
            self.usb_bar,
            text="Control Switch:",
            bg="#222834",
            fg="#CBD5E1",
            font=("Segoe UI", 8, "bold"),
        ).pack(side=tk.RIGHT, padx=2)

    def _build_canvas_and_sidebar(self) -> None:
        """Builds the main draggable keymapping canvas and the right-hand inspector sidebar."""
        self.main_container = tk.Frame(self.root, bg="#121418")
        self.main_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(
            self.main_container,
            bg="#161920",
            highlightthickness=2,
            highlightbackground="#00E5FF",
            cursor="crosshair",
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas.bind("<Configure>", lambda e: self.redraw_canvas())
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_left_down)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_left_up)
        self.canvas.bind("<ButtonPress-3>", self._on_canvas_right_click)
        self.canvas.bind("<Motion>", self._on_canvas_mouse_move)

        self.sidebar = tk.Frame(
            self.main_container, bg="#1B1F27", width=290, padx=12, pady=8
        )
        self.sidebar.pack(side=tk.RIGHT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        # USB & Tool Paths Status Box
        tk.Label(
            self.sidebar,
            text="USB & C:\\ TOOL PATH STATUS",
            bg="#1B1F27",
            fg="#00E5FF",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 3))

        self.lbl_adb_status = tk.Label(
            self.sidebar,
            text="Checking USB devices...",
            bg="#232936",
            fg="#E2E8F0",
            font=("Segoe UI", 8),
            wraplength=260,
            justify=tk.LEFT,
            padx=8,
            pady=5,
        )
        self.lbl_adb_status.pack(fill=tk.X, pady=2)

        self.lbl_paths_status = tk.Label(
            self.sidebar,
            text="Scanning C:\\ for scrcpy & adb...",
            bg="#232936",
            fg="#94A3B8",
            font=("Segoe UI", 7),
            wraplength=260,
            justify=tk.LEFT,
            padx=8,
            pady=5,
        )
        self.lbl_paths_status.pack(fill=tk.X, pady=2)

        self.lbl_pad_status = tk.Label(
            self.sidebar,
            text="Joystick: Scanning...",
            bg="#232936",
            fg="#A3B8CC",
            font=("Segoe UI", 8),
            wraplength=260,
            justify=tk.LEFT,
            padx=8,
            pady=5,
        )
        self.lbl_pad_status.pack(fill=tk.X, pady=2)

        # Input Mode Radio/Quick Switch in Sidebar
        tk.Frame(self.sidebar, bg="#334155", height=1).pack(fill=tk.X, pady=5)
        tk.Label(
            self.sidebar,
            text="ACTIVE INPUT MODE SWITCH",
            bg="#1B1F27",
            fg="#C084FC",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 3))

        mode_btn_frame = tk.Frame(self.sidebar, bg="#1B1F27")
        mode_btn_frame.pack(fill=tk.X, pady=2)

        self.btn_mode_kbm = tk.Button(
            mode_btn_frame,
            text="Keyboard+Mouse",
            bg="#2D3748",
            fg="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            command=lambda: self.set_input_device_mode("KEYBOARD + MOUSE"),
        )
        self.btn_mode_kbm.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))

        self.btn_mode_pad = tk.Button(
            mode_btn_frame,
            text="Gamepad",
            bg="#2D3748",
            fg="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            command=lambda: self.set_input_device_mode("CONTROLLER / GAMEPAD"),
        )
        self.btn_mode_pad.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        self.btn_mode_both = tk.Button(
            mode_btn_frame,
            text="Both",
            bg="#8B5CF6",
            fg="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            command=lambda: self.set_input_device_mode("BOTH (KB/M + GAMEPAD)"),
        )
        self.btn_mode_both.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        # Orientation Toggle & Overlay Opacity Slider
        orient_frame = tk.Frame(self.sidebar, bg="#1B1F27")
        orient_frame.pack(fill=tk.X, pady=5)
        tk.Label(
            orient_frame,
            text="Phone Orientation:",
            bg="#1B1F27",
            fg="#CBD5E1",
            font=("Segoe UI", 8),
        ).pack(side=tk.LEFT)
        self.btn_orient = tk.Button(
            orient_frame,
            text="Landscape (Games)",
            bg="#2D3748",
            fg="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 8),
            command=self._toggle_orientation,
        )
        self.btn_orient.pack(side=tk.RIGHT)

        tk.Label(
            self.sidebar,
            text="Overlay Transparency:",
            bg="#1B1F27",
            fg="#CBD5E1",
            font=("Segoe UI", 8),
            anchor="w",
        ).pack(fill=tk.X)

        self.alpha_scale = tk.Scale(
            self.sidebar,
            from_=0.25,
            to=0.95,
            resolution=0.05,
            orient=tk.HORIZONTAL,
            bg="#1B1F27",
            fg="#E2E8F0",
            highlightthickness=0,
            troughcolor="#2D3748",
            command=self._on_alpha_slider,
        )
        self.alpha_scale.set(self.overlay_alpha)
        self.alpha_scale.pack(fill=tk.X, pady=(0, 4))

        # Selected Control Node Inspector
        tk.Frame(self.sidebar, bg="#334155", height=1).pack(fill=tk.X, pady=5)
        tk.Label(
            self.sidebar,
            text="SELECTED WIDGET INSPECTOR",
            bg="#1B1F27",
            fg="#00E676",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 4))

        self.lbl_selected_info = tk.Label(
            self.sidebar,
            text="Click any node on the canvas to edit its key or controller binding.\nRight-click empty space to quick-add a Tap Key.",
            bg="#232936",
            fg="#E2E8F0",
            font=("Segoe UI", 8),
            wraplength=260,
            justify=tk.LEFT,
            padx=8,
            pady=6,
        )
        self.lbl_selected_info.pack(fill=tk.X, pady=3)

        self.btn_rebind = tk.Button(
            self.sidebar,
            text="Bind Keyboard / Controller Key",
            bg="#3B82F6",
            fg="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 9, "bold"),
            pady=4,
            state=tk.DISABLED,
            command=self.start_binding_capture,
        )
        self.btn_rebind.pack(fill=tk.X, pady=3)

        self.btn_rapid_toggle = tk.Button(
            self.sidebar,
            text="Rapid-Fire Turbo: OFF",
            bg="#2D3748",
            fg="#E2E8F0",
            relief=tk.FLAT,
            font=("Segoe UI", 8),
            state=tk.DISABLED,
            command=self._toggle_selected_rapid_fire,
        )
        self.btn_rapid_toggle.pack(fill=tk.X, pady=2)

        self.btn_delete_node = tk.Button(
            self.sidebar,
            text="Delete Selected Widget (Del)",
            bg="#991B1B",
            fg="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            pady=4,
            state=tk.DISABLED,
            command=self.delete_selected_node,
        )
        self.btn_delete_node.pack(fill=tk.X, pady=4)

    # ------------------------------------------------------------------------
    # FEATURE 1: USB DEVICE LIST & "ALLOW USB DEBUGGING POPUP"
    # ------------------------------------------------------------------------

    def _refresh_adb_status(self) -> None:
        devices, msg = self.adb_engine.list_usb_devices()
        ok = self.adb_engine.connected

        self.lbl_adb_status.configure(
            text=msg,
            fg="#4ADE80" if ok else "#FBBF24" if devices else "#F87171",
        )

        # Populate USB Device Dropdown List
        if devices:
            labels = [d.display_label for d in devices]
            self.device_combo.configure(values=labels)
            active_serial = self.adb_engine.device_serial
            matched_label = next(
                (d.display_label for d in devices if d.serial == active_serial),
                labels[0],
            )
            self.device_var.set(matched_label)
        else:
            self.device_combo.configure(values=["No USB Phone Listed"])
            self.device_var.set("No USB Phone Listed")

        # Update discovered C:\ paths display
        scrcpy_disp = self.path_resolver.scrcpy_path or "Not Found (Click 'Select C:\\ Path')"
        adb_disp = self.path_resolver.adb_path or "Not Found (Click 'Select C:\\ Path')"
        self.lbl_paths_status.configure(
            text=f"scrcpy: {scrcpy_disp}\nadb: {adb_disp}"
        )

        pad_msg = self.gamepad.refresh_controllers()
        self.lbl_pad_status.configure(text=f"Joystick: {pad_msg}")
        self.redraw_canvas()

    def _on_device_combo_selected(self, _event: Optional[tk.Event] = None) -> None:
        chosen_label = self.device_var.get()
        for dev in self.adb_engine.devices:
            if dev.display_label == chosen_label:
                _, msg = self.adb_engine.select_device(dev.serial)
                self.lbl_adb_status.configure(
                    text=msg,
                    fg="#4ADE80" if self.adb_engine.connected else "#FBBF24",
                )
                self.redraw_canvas()
                break

    def request_usb_debugging_popup(self) -> None:
        """
        Triggers the Android 'Allow USB debugging?' authorization popup on the connected
        mobile phone (just like Android Studio) and refreshes the USB device dropdown list.
        """
        self.lbl_adb_status.configure(
            text="Restarting USB handshake... Look at your phone screen to tap 'Allow USB debugging'!",
            fg="#FBBF24",
        )
        self.root.update_idletasks()

        devices, msg = self.adb_engine.trigger_usb_authorization_popup()
        self._refresh_adb_status()

        if any(d.state == "unauthorized" for d in devices):
            messagebox.showinfo(
                "Allow USB Debugging on Phone",
                "A popup has been triggered on your mobile phone!\n\n"
                "1. Unlock your phone screen.\n"
                "2. Check 'Always allow from this computer' and tap 'Allow'.\n"
                "3. Click 'Refresh List' on the toolbar.",
            )
        elif self.adb_engine.connected:
            messagebox.showinfo(
                "USB Mobile Connected",
                f"Your mobile is authorized and ready!\n\n{msg}",
            )
        else:
            messagebox.showwarning(
                "USB Device Not Detected Yet",
                f"{msg}\n\n"
                "Tips:\n"
                "• Make sure USB Debugging is ON in Developer Options.\n"
                "• Change USB mode on your phone notification bar from 'Charging Only' to 'File Transfer (MTP)' or 'PTP'.\n"
                "• If adb.exe was not found, click 'Select C:\\ Path (scrcpy / ADB)' to point to your scrcpy or Android SDK folder.",
            )

    # ------------------------------------------------------------------------
    # FEATURE 2: SELECT C:\ PATH (SCRCPY / ADB) & AUTO-RUN
    # ------------------------------------------------------------------------

    def select_c_drive_path_dialog(self) -> None:
        """
        Opens a dialog starting on C:\\ so the user can pick their `scrcpy.exe`, `adb.exe`,
        or the folder where scrcpy is installed, then automatically runs the mirror if desired.
        """
        initial_dir = self.path_resolver.last_browse_dir
        if not Path(initial_dir).exists():
            initial_dir = "C:\\" if platform.system() == "Windows" else str(Path.home())

        chosen_file = filedialog.askopenfilename(
            title="Select scrcpy.exe or adb.exe from your C:\\ Drive (or Cancel to pick a Folder)",
            initialdir=initial_dir,
            filetypes=[
                ("Executable Files", "*.exe"),
                ("All Files", "*.*"),
            ],
        )

        target_path = chosen_file
        if not target_path:
            # Allow picking a directory if the user prefers selecting the C:\scrcpy folder
            chosen_dir = filedialog.askdirectory(
                title="Select your scrcpy or Android SDK Platform-Tools Folder on C:\\",
                initialdir=initial_dir,
            )
            target_path = chosen_dir

        if not target_path:
            return

        ok, summary = self.path_resolver.apply_user_selected_path(target_path)
        self._refresh_adb_status()

        if ok:
            if self.path_resolver.scrcpy_path:
                run_now = messagebox.askyesno(
                    "Path Saved — Launch Screen Mirror?",
                    f"{summary}\n\nWould you like to automatically launch scrcpy now?",
                )
                if run_now:
                    self.launch_scrcpy_mirror()
            else:
                messagebox.showinfo("ADB Path Saved", summary)
        else:
            messagebox.showwarning("Executable Not Found in Selected Path", summary)

    def launch_scrcpy_mirror(self) -> None:
        """Launches `scrcpy` from the discovered or selected C:\\ path right beneath the overlay."""
        self.path_resolver.auto_discover_binaries()
        scrcpy_bin = self.path_resolver.scrcpy_path

        if not scrcpy_bin or not Path(scrcpy_bin).is_file():
            ask = messagebox.askyesno(
                "Select scrcpy Path on C:\\ Drive",
                "Could not find 'scrcpy.exe' automatically.\n\n"
                "Click YES to browse your C:\\ drive and select your scrcpy folder or scrcpy.exe!",
            )
            if ask:
                self.select_c_drive_path_dialog()
            return

        self.root.update_idletasks()
        cx = self.canvas.winfo_rootx()
        cy = self.canvas.winfo_rooty()
        cw = max(400, self.canvas.winfo_width())
        ch = max(300, self.canvas.winfo_height())

        cmd = [
            scrcpy_bin,
            "--max-fps=60",
            "--stay-awake",
            "--window-title=USB_Game_Mirror",
            f"--window-x={cx}",
            f"--window-y={cy}",
            f"--window-width={cw}",
            f"--window-height={ch}",
        ]
        if self.adb_engine.device_serial:
            cmd.extend(["-s", self.adb_engine.device_serial])

        # Ensure scrcpy uses the same adb.exe if found
        env = os.environ.copy()
        if self.path_resolver.adb_path:
            env["ADB"] = self.path_resolver.adb_path

        try:
            self.scrcpy_proc = subprocess.Popen(cmd, cwd=str(Path(scrcpy_bin).parent), env=env)
        except Exception as exc:
            messagebox.showerror("scrcpy Launch Error", str(exc))

    # ------------------------------------------------------------------------
    # FEATURE 3: INPUT DEVICE MODE SWITCH (KEYBOARD+MOUSE vs. GAMEPAD vs. BOTH)
    # ------------------------------------------------------------------------

    def cycle_input_device_mode(self) -> None:
        idx = self.INPUT_MODES.index(self.input_device_mode)
        next_mode = self.INPUT_MODES[(idx + 1) % len(self.INPUT_MODES)]
        self.set_input_device_mode(next_mode)

    def set_input_device_mode(self, mode_name: str) -> None:
        if mode_name not in self.INPUT_MODES:
            return
        self.input_device_mode = mode_name
        self._release_all_active_touches()

        # Update top toolbar button and sidebar buttons
        self.btn_input_switch.configure(text=f"INPUT: {self.input_device_mode}")
        self.btn_mode_kbm.configure(
            bg="#8B5CF6" if mode_name == "KEYBOARD + MOUSE" else "#2D3748"
        )
        self.btn_mode_pad.configure(
            bg="#8B5CF6" if mode_name == "CONTROLLER / GAMEPAD" else "#2D3748"
        )
        self.btn_mode_both.configure(
            bg="#8B5CF6" if mode_name == "BOTH (KB/M + GAMEPAD)" else "#2D3748"
        )
        self._update_inspector_panel()
        self.redraw_canvas()

    def _is_kbm_enabled(self) -> bool:
        return self.input_device_mode in ("KEYBOARD + MOUSE", "BOTH (KB/M + GAMEPAD)")

    def _is_gamepad_enabled(self) -> bool:
        return self.input_device_mode in ("CONTROLLER / GAMEPAD", "BOTH (KB/M + GAMEPAD)")

    # ------------------------------------------------------------------------
    # ORIENTATION & TRANSPARENCY HELPERS
    # ------------------------------------------------------------------------

    def _toggle_orientation(self) -> None:
        self.landscape_mode = not self.landscape_mode
        self.adb_engine.set_orientation_mode(self.landscape_mode)
        mode_str = "Landscape (Games)" if self.landscape_mode else "Portrait (Apps)"
        self.btn_orient.configure(text=mode_str)
        self._refresh_adb_status()

    def _on_alpha_slider(self, val: str) -> None:
        self.overlay_alpha = float(val)
        self._apply_window_transparency(self.overlay_alpha)

    # ------------------------------------------------------------------------
    # CANVAS RENDERING OF DRAG-AND-DROP WIDGETS
    # ------------------------------------------------------------------------

    def redraw_canvas(self) -> None:
        self.canvas.delete("all")
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())

        if self.mode == "EDIT":
            step = 60
            for x in range(0, cw, step):
                self.canvas.create_line(x, 0, x, ch, fill="#1E2430", dash=(2, 4))
            for y in range(0, ch, step):
                self.canvas.create_line(0, y, cw, y, fill="#1E2430", dash=(2, 4))

            self.canvas.create_text(
                14,
                14,
                anchor="nw",
                text=(
                    f"EDIT MODE — Drag widgets over game buttons | "
                    f"Active Input: {self.input_device_mode} | "
                    f"Phone Target: {self.adb_engine.device_width}x{self.adb_engine.device_height} | "
                    f"Press F12 for Play Mode"
                ),
                fill="#94A3B8",
                font=("Segoe UI", 9, "bold"),
            )
        else:
            aim_status = "LOCKED (Move Mouse to Aim)" if self.fps_aim_locked else "UNLOCKED (Press TAB)"
            self.canvas.create_text(
                14,
                14,
                anchor="nw",
                text=(
                    f"PLAY MODE ACTIVE (F12 to Edit) | "
                    f"Input: {self.input_device_mode} | "
                    f"FPS Mouse-Look: {aim_status}"
                ),
                fill="#00E676",
                font=("Segoe UI", 9, "bold"),
            )

        for node in self.nodes:
            is_sel = node is self.selected_node
            stroke_col, fill_col = self.NODE_COLORS.get(
                node.node_type, ("#00E5FF", "#004D61")
            )
            outline_width = 3 if is_sel else 2
            if is_sel:
                stroke_col = "#FFFFFF"

            x = int(node.norm_x * cw)
            y = int(node.norm_y * ch)

            if node.node_type == "dpad":
                r = int(node.norm_radius * min(cw, ch))
                self.canvas.create_oval(
                    x - r,
                    y - r,
                    x + r,
                    y + r,
                    outline=stroke_col,
                    fill=fill_col if self.mode == "EDIT" else "",
                    width=outline_width,
                )
                self.canvas.create_line(x - r, y, x + r, y, fill=stroke_col, dash=(3, 3))
                self.canvas.create_line(x, y - r, x, y + r, fill=stroke_col, dash=(3, 3))
                if self._is_kbm_enabled():
                    self.canvas.create_text(
                        x, y - r + 14, text=node.dpad_keys.get("up", "W").upper(),
                        fill="#FFFFFF", font=("Segoe UI", 9, "bold")
                    )
                    self.canvas.create_text(
                        x, y + r - 14, text=node.dpad_keys.get("down", "S").upper(),
                        fill="#FFFFFF", font=("Segoe UI", 9, "bold")
                    )
                    self.canvas.create_text(
                        x - r + 14, y, text=node.dpad_keys.get("left", "A").upper(),
                        fill="#FFFFFF", font=("Segoe UI", 9, "bold")
                    )
                    self.canvas.create_text(
                        x + r - 14, y, text=node.dpad_keys.get("right", "D").upper(),
                        fill="#FFFFFF", font=("Segoe UI", 9, "bold")
                    )
                center_tag = "L-STICK" if self._is_gamepad_enabled() else "WASD"
                self.canvas.create_text(
                    x, y, text=center_tag, fill="#A7F3D0", font=("Segoe UI", 8, "bold")
                )

            elif node.node_type == "swipe":
                x2 = int(node.norm_x2 * cw)
                y2 = int(node.norm_y2 * ch)
                self.canvas.create_line(
                    x, y, x2, y2,
                    fill=stroke_col,
                    width=3,
                    arrow=tk.LAST,
                    arrowshape=(12, 15, 6),
                )
                self.canvas.create_oval(
                    x - 18, y - 18, x + 18, y + 18,
                    outline=stroke_col, fill=fill_col, width=outline_width
                )
                self.canvas.create_oval(
                    x2 - 10, y2 - 10, x2 + 10, y2 + 10,
                    outline=stroke_col, fill="#FFFFFF", width=2
                )
                bind_txt = self._format_node_badge(node)
                self.canvas.create_text(
                    x, y, text=bind_txt, fill="#FFFFFF", font=("Segoe UI", 8, "bold")
                )

            elif node.node_type == "aim":
                r = 32
                self.canvas.create_oval(
                    x - r, y - r, x + r, y + r,
                    outline=stroke_col,
                    fill=fill_col if self.mode == "EDIT" else "",
                    width=outline_width,
                )
                self.canvas.create_line(x - r - 8, y, x + r + 8, y, fill=stroke_col, width=2)
                self.canvas.create_line(x, y - r - 8, x, y + r + 8, fill=stroke_col, width=2)
                self.canvas.create_text(
                    x, y - r - 12,
                    text=f"AIM ({self._format_node_badge(node)})",
                    fill=stroke_col,
                    font=("Segoe UI", 8, "bold"),
                )

            else:
                r = 24 if node.node_type == "tap" else 28
                self.canvas.create_oval(
                    x - r,
                    y - r,
                    x + r,
                    y + r,
                    outline=stroke_col,
                    fill=fill_col if self.mode == "EDIT" else "",
                    width=outline_width,
                )
                badge = self._format_node_badge(node)
                self.canvas.create_text(
                    x, y - 4, text=badge, fill="#FFFFFF", font=("Segoe UI", 8, "bold")
                )
                self.canvas.create_text(
                    x,
                    y + 10,
                    text=node.label[:10],
                    fill="#CBD5E1",
                    font=("Segoe UI", 7),
                )

    def _format_node_badge(self, node: KeyMapNode) -> str:
        """Formats the node badge based on the currently selected Input Mode switch."""
        parts = []
        if self._is_kbm_enabled() and node.key_bind:
            parts.append(node.key_bind.strip().upper())
        if self._is_gamepad_enabled() and node.pad_bind:
            parts.append(node.pad_bind.replace("BTN_", "B").replace("AXIS_", ""))
        return " / ".join(parts) if parts else "UNBOUND"

    # ------------------------------------------------------------------------
    # EDIT MODE: DRAG-AND-DROP & INSPECTOR INTERACTION
    # ------------------------------------------------------------------------

    def _hit_test_node(self, px: int, py: int) -> Tuple[Optional[KeyMapNode], str]:
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())

        for node in reversed(self.nodes):
            if node.node_type == "swipe":
                x2 = int(node.norm_x2 * cw)
                y2 = int(node.norm_y2 * ch)
                if math.hypot(px - x2, py - y2) <= 16:
                    return node, "end"

            x = int(node.norm_x * cw)
            y = int(node.norm_y * ch)
            hit_r = (
                int(node.norm_radius * min(cw, ch))
                if node.node_type == "dpad"
                else 30
            )
            if math.hypot(px - x, py - y) <= hit_r:
                return node, "main"

        return None, "main"

    def _on_canvas_left_down(self, event: tk.Event) -> None:
        if self.mode == "PLAY":
            if self._is_kbm_enabled():
                self._handle_key_or_mouse_press("MouseLeft")
            return

        node, handle = self._hit_test_node(event.x, event.y)
        self.selected_node = node
        self._drag_data["node"] = node
        self._drag_data["handle"] = handle
        self._update_inspector_panel()
        self.redraw_canvas()

    def _on_canvas_drag(self, event: tk.Event) -> None:
        if self.mode != "EDIT":
            return
        node = self._drag_data.get("node")
        if not isinstance(node, KeyMapNode):
            return

        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        nx = max(0.02, min(0.98, event.x / cw))
        ny = max(0.02, min(0.98, event.y / ch))

        if self._drag_data.get("handle") == "end" and node.node_type == "swipe":
            node.norm_x2 = nx
            node.norm_y2 = ny
        else:
            dx = nx - node.norm_x
            dy = ny - node.norm_y
            node.norm_x = nx
            node.norm_y = ny
            if node.node_type == "swipe":
                node.norm_x2 = max(0.02, min(0.98, node.norm_x2 + dx))
                node.norm_y2 = max(0.02, min(0.98, node.norm_y2 + dy))

        self._update_inspector_panel()
        self.redraw_canvas()

    def _on_canvas_left_up(self, event: tk.Event) -> None:
        if self.mode == "PLAY":
            if self._is_kbm_enabled():
                self._handle_key_or_mouse_release("MouseLeft")
            return
        self._drag_data["node"] = None

    def _on_canvas_right_click(self, event: tk.Event) -> None:
        if self.mode == "PLAY":
            if self._is_kbm_enabled():
                self._handle_key_or_mouse_press("MouseRight")
                self.root.after(60, lambda: self._handle_key_or_mouse_release("MouseRight"))
            return

        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        new_node = KeyMapNode(
            id=f"tap_{int(time.time() * 1000) % 100000}",
            node_type="tap",
            label="Custom Key",
            norm_x=max(0.03, min(0.97, event.x / cw)),
            norm_y=max(0.03, min(0.97, event.y / ch)),
            key_bind="",
        )
        self.nodes.append(new_node)
        self.selected_node = new_node
        self.start_binding_capture()
        self.redraw_canvas()

    def add_node(self, node_type: str) -> None:
        if self.mode != "EDIT":
            self.toggle_play_edit_mode()

        uid = f"{node_type}_{int(time.time() * 1000) % 100000}"
        if node_type == "dpad":
            node = KeyMapNode(
                id=uid,
                node_type="dpad",
                label="Move Stick",
                norm_x=0.22,
                norm_y=0.70,
                norm_radius=0.10,
                key_bind="WASD",
                pad_bind="LEFT_STICK",
            )
        elif node_type == "aim":
            node = KeyMapNode(
                id=uid,
                node_type="aim",
                label="Camera Look",
                norm_x=0.65,
                norm_y=0.50,
                key_bind="tab",
                pad_bind="RIGHT_STICK",
            )
        elif node_type == "fire":
            node = KeyMapNode(
                id=uid,
                node_type="fire",
                label="Fire / Attack",
                norm_x=0.82,
                norm_y=0.68,
                key_bind="MouseLeft",
                pad_bind="AXIS_RT",
            )
        elif node_type == "swipe":
            node = KeyMapNode(
                id=uid,
                node_type="swipe",
                label="Swipe Action",
                norm_x=0.45,
                norm_y=0.55,
                norm_x2=0.62,
                norm_y2=0.38,
                key_bind="e",
                pad_bind="BTN_1",
            )
        else:
            node = KeyMapNode(
                id=uid,
                node_type="tap",
                label="Tap Button",
                norm_x=0.50,
                norm_y=0.50,
                key_bind="",
            )

        self.nodes.append(node)
        self.selected_node = node
        self._update_inspector_panel()
        self.redraw_canvas()

    def _update_inspector_panel(self) -> None:
        node = self.selected_node
        if node is None:
            self.lbl_selected_info.configure(
                text="No widget selected.\nClick any node on the canvas to inspect or rebind it."
            )
            self.btn_rebind.configure(state=tk.DISABLED, text="Bind Keyboard / Controller Key")
            self.btn_rapid_toggle.configure(state=tk.DISABLED)
            self.btn_delete_node.configure(state=tk.DISABLED)
            return

        dev_x, dev_y = self.adb_engine.norm_to_device(node.norm_x, node.norm_y)
        info = (
            f"Label: {node.label}\n"
            f"Type: {node.node_type.upper()}\n"
            f"Keyboard Bind: {node.key_bind or 'None'}\n"
            f"Controller Bind: {node.pad_bind or 'None'}\n"
            f"Target Phone XY: ({dev_x}, {dev_y})"
        )
        self.lbl_selected_info.configure(text=info)
        self.btn_rebind.configure(state=tk.NORMAL, text="Press to Rebind Key / Button")
        self.btn_delete_node.configure(state=tk.NORMAL)

        if node.node_type in ("tap", "fire"):
            self.btn_rapid_toggle.configure(
                state=tk.NORMAL,
                text=f"Rapid-Fire Turbo: {'ON (12 CPS)' if node.rapid_fire else 'OFF'}",
                bg="#059669" if node.rapid_fire else "#2D3748",
            )
        else:
            self.btn_rapid_toggle.configure(state=tk.DISABLED, text="Rapid-Fire: N/A")

    def start_binding_capture(self) -> None:
        if self.selected_node is None:
            return
        self.waiting_for_bind_node = self.selected_node
        prompt_txt = (
            "Press a Gamepad Button!"
            if self.input_device_mode == "CONTROLLER / GAMEPAD"
            else "Press a Keyboard Key!"
            if self.input_device_mode == "KEYBOARD + MOUSE"
            else "Press any Key or Pad Button!"
        )
        self.btn_rebind.configure(text=prompt_txt, bg="#F59E0B")

    def _toggle_selected_rapid_fire(self) -> None:
        if self.selected_node and self.selected_node.node_type in ("tap", "fire"):
            self.selected_node.rapid_fire = not self.selected_node.rapid_fire
            self._update_inspector_panel()

    def delete_selected_node(self) -> None:
        if self.selected_node and self.selected_node in self.nodes:
            self.nodes.remove(self.selected_node)
            self.selected_node = None
            self._update_inspector_panel()
            self.redraw_canvas()

    # ------------------------------------------------------------------------
    # PLAY MODE VS. EDIT MODE & INPUT DISPATCHING
    # ------------------------------------------------------------------------

    def toggle_play_edit_mode(self) -> None:
        if self.mode == "EDIT":
            self.mode = "PLAY"
            self.selected_node = None
            self.waiting_for_bind_node = None
            self.btn_mode.configure(
                text="MODE: PLAY ACTIVE (F12 to Edit)", bg="#FF3D00", fg="#FFFFFF"
            )
            self.sidebar.pack_forget()
            self._apply_window_transparency(max(0.25, min(0.55, self.overlay_alpha)))
        else:
            self.mode = "EDIT"
            self.fps_aim_locked = False
            self._release_all_active_touches()
            self.btn_mode.configure(
                text="MODE: EDIT OVERLAY (F12)", bg="#00C853", fg="#0A0E14"
            )
            self.sidebar.pack(side=tk.RIGHT, fill=tk.Y)
            self._apply_window_transparency(self.overlay_alpha)

        self.redraw_canvas()

    def _setup_input_listeners(self) -> None:
        self.root.bind("<KeyPress>", self._on_tk_key_press)
        self.root.bind("<KeyRelease>", self._on_tk_key_release)

        if HAS_PYNPUT:
            try:
                self._kb_listener = pynput_kb.Listener(
                    on_press=self._on_pynput_key_press,
                    on_release=self._on_pynput_key_release,
                )
                self._kb_listener.daemon = True
                self._kb_listener.start()
            except Exception:
                pass

    def _normalize_key_name(self, raw_key: str) -> str:
        k = raw_key.lower().replace("key.", "").strip()
        aliases = {
            "return": "enter",
            "escape": "esc",
            "control_l": "ctrl",
            "control_r": "ctrl",
            "alt_l": "alt",
            "alt_r": "alt",
        }
        return aliases.get(k, k)

    def _on_tk_key_press(self, event: tk.Event) -> None:
        key_name = self._normalize_key_name(event.keysym)
        if key_name == "f12":
            self.toggle_play_edit_mode()
            return
        if self.mode == "EDIT" and key_name == "delete":
            self.delete_selected_node()
            return
        if not HAS_PYNPUT:
            self._handle_key_or_mouse_press(key_name)

    def _on_tk_key_release(self, event: tk.Event) -> None:
        if not HAS_PYNPUT:
            key_name = self._normalize_key_name(event.keysym)
            self._handle_key_or_mouse_release(key_name)

    def _on_pynput_key_press(self, key: object) -> None:
        try:
            k_str = getattr(key, "char", None) or getattr(key, "name", str(key))
            k_norm = self._normalize_key_name(str(k_str))
            if k_norm == "f12":
                self.root.after(0, self.toggle_play_edit_mode)
                return
            self._handle_key_or_mouse_press(k_norm)
        except Exception:
            pass

    def _on_pynput_key_release(self, key: object) -> None:
        try:
            k_str = getattr(key, "char", None) or getattr(key, "name", str(key))
            k_norm = self._normalize_key_name(str(k_str))
            self._handle_key_or_mouse_release(k_norm)
        except Exception:
            pass

    def _handle_key_or_mouse_press(self, key_name: str) -> None:
        # 1. If waiting to bind a key in Edit Mode (when KB/M is allowed), capture it
        if self.waiting_for_bind_node is not None and self._is_kbm_enabled():
            self.waiting_for_bind_node.key_bind = key_name
            self.waiting_for_bind_node = None
            self.root.after(0, self._finish_bind_ui)
            return

        if self.mode != "PLAY" or not self._is_kbm_enabled():
            return

        # 2. Check FPS Aim Lock toggle (default: Tab)
        if key_name == "tab":
            self.fps_aim_locked = not self.fps_aim_locked
            if not self.fps_aim_locked:
                self.adb_engine.send_touch_up("aim", *self._aim_curr_norm)
            self.root.after(0, self.redraw_canvas)
            return

        if key_name in self._pressed_keys:
            return
        self._pressed_keys.add(key_name)

        # 3. Check WASD Virtual D-Pad updates
        self._update_wasd_dpad_vector()

        # 4. Trigger matching Tap, Fire, or Swipe nodes
        for node in self.nodes:
            if node.key_bind.strip().lower() == key_name.lower():
                self._activate_node_action(node, is_down=True)

    def _handle_key_or_mouse_release(self, key_name: str) -> None:
        if key_name in self._pressed_keys:
            self._pressed_keys.remove(key_name)

        if self.mode != "PLAY" or not self._is_kbm_enabled():
            return

        self._update_wasd_dpad_vector()

        for node in self.nodes:
            if node.key_bind.strip().lower() == key_name.lower():
                self._activate_node_action(node, is_down=False)

    def _finish_bind_ui(self) -> None:
        self.btn_rebind.configure(bg="#3B82F6")
        self._update_inspector_panel()
        self.redraw_canvas()

    def _activate_node_action(self, node: KeyMapNode, is_down: bool) -> None:
        if node.node_type == "swipe":
            if is_down:
                self.adb_engine.send_swipe(
                    node.norm_x,
                    node.norm_y,
                    node.norm_x2,
                    node.norm_y2,
                    node.swipe_duration_ms,
                )
        elif node.node_type in ("tap", "fire"):
            if is_down:
                if node.rapid_fire:
                    self._start_rapid_fire_loop(node)
                else:
                    self.adb_engine.send_tap(node.norm_x, node.norm_y)
            else:
                self._rapid_fire_active = False

    def _start_rapid_fire_loop(self, node: KeyMapNode) -> None:
        if self._rapid_fire_active:
            return
        self._rapid_fire_active = True

        def _loop() -> None:
            interval = 1.0 / max(1, node.rapid_fire_cps)
            while self._rapid_fire_active and self.mode == "PLAY":
                self.adb_engine.send_tap(node.norm_x, node.norm_y)
                time.sleep(interval)

        threading.Thread(target=_loop, daemon=True).start()

    # ------------------------------------------------------------------------
    # WASD & CONTROLLER LEFT-STICK VIRTUAL JOYSTICK (8-DIRECTION DRAG)
    # ------------------------------------------------------------------------

    def _update_wasd_dpad_vector(self) -> None:
        if not self._is_kbm_enabled():
            return
        dpad_node = next((n for n in self.nodes if n.node_type == "dpad"), None)
        if dpad_node is None:
            return

        up_k = dpad_node.dpad_keys.get("up", "w").lower()
        down_k = dpad_node.dpad_keys.get("down", "s").lower()
        left_k = dpad_node.dpad_keys.get("left", "a").lower()
        right_k = dpad_node.dpad_keys.get("right", "d").lower()

        vx = 0.0
        vy = 0.0
        if left_k in self._pressed_keys:
            vx -= 1.0
        if right_k in self._pressed_keys:
            vx += 1.0
        if up_k in self._pressed_keys:
            vy -= 1.0
        if down_k in self._pressed_keys:
            vy += 1.0

        self._apply_dpad_vector(dpad_node, vx, vy)

    def _apply_dpad_vector(self, dpad_node: KeyMapNode, vx: float, vy: float) -> None:
        mag = math.hypot(vx, vy)
        if mag < 0.05:
            if self._dpad_touch_active:
                self._dpad_touch_active = False
                self.adb_engine.send_touch_up("dpad", *self._dpad_curr_norm)
            return

        nx = dpad_node.norm_x + (vx / max(1.0, mag)) * dpad_node.norm_radius
        ny = dpad_node.norm_y + (vy / max(1.0, mag)) * dpad_node.norm_radius
        self._dpad_curr_norm = (nx, ny)

        if not self._dpad_touch_active:
            self._dpad_touch_active = True
            self.adb_engine.send_touch_down("dpad", dpad_node.norm_x, dpad_node.norm_y)
        self.adb_engine.send_touch_move("dpad", nx, ny)

    # ------------------------------------------------------------------------
    # FPS MOUSE-LOOK & CONTROLLER RIGHT-STICK CAMERA AIM
    # ------------------------------------------------------------------------

    def _on_canvas_mouse_move(self, event: tk.Event) -> None:
        if self.mode != "PLAY" or not self.fps_aim_locked or not self._is_kbm_enabled():
            self._last_mouse_pos = (event.x, event.y)
            return

        aim_node = next((n for n in self.nodes if n.node_type == "aim"), None)
        if aim_node is None:
            return

        if self._last_mouse_pos is None:
            self._last_mouse_pos = (event.x, event.y)
            self._aim_curr_norm = (aim_node.norm_x, aim_node.norm_y)
            self.adb_engine.send_touch_down("aim", *self._aim_curr_norm)
            return

        dx = event.x - self._last_mouse_pos[0]
        dy = event.y - self._last_mouse_pos[1]
        self._last_mouse_pos = (event.x, event.y)

        if dx == 0 and dy == 0:
            return

        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        sens = aim_node.sensitivity

        nx = self._aim_curr_norm[0] + (dx / cw) * sens
        ny = self._aim_curr_norm[1] + (dy / ch) * sens

        if nx < 0.35 or nx > 0.94 or ny < 0.12 or ny > 0.88:
            self.adb_engine.send_touch_up("aim", *self._aim_curr_norm)
            self._aim_curr_norm = (aim_node.norm_x, aim_node.norm_y)
            self.adb_engine.send_touch_down("aim", *self._aim_curr_norm)
        else:
            self._aim_curr_norm = (nx, ny)
            self.adb_engine.send_touch_move("aim", nx, ny)

    # ------------------------------------------------------------------------
    # GAMEPAD / JOYSTICK CALLBACKS
    # ------------------------------------------------------------------------

    def _on_gamepad_button_down(self, pad_btn: str) -> None:
        if self.waiting_for_bind_node is not None and self._is_gamepad_enabled():
            self.waiting_for_bind_node.pad_bind = pad_btn
            self.waiting_for_bind_node = None
            self.root.after(0, self._finish_bind_ui)
            return

        if self.mode != "PLAY" or not self._is_gamepad_enabled():
            return

        for node in self.nodes:
            if node.pad_bind.strip().upper() == pad_btn.upper():
                self._activate_node_action(node, is_down=True)

    def _on_gamepad_button_up(self, pad_btn: str) -> None:
        if self.mode != "PLAY" or not self._is_gamepad_enabled():
            return
        for node in self.nodes:
            if node.pad_bind.strip().upper() == pad_btn.upper():
                self._activate_node_action(node, is_down=False)

    def _on_gamepad_sticks_update(
        self, lx: float, ly: float, rx: float, ry: float
    ) -> None:
        if self.mode != "PLAY" or not self._is_gamepad_enabled():
            return

        # 1. Left Stick -> Virtual D-Pad
        if not any(k in self._pressed_keys for k in ("w", "a", "s", "d")):
            dpad_node = next((n for n in self.nodes if n.node_type == "dpad"), None)
            if dpad_node is not None:
                self._apply_dpad_vector(dpad_node, lx, ly)

        # 2. Right Stick -> Camera Aim pan
        aim_node = next((n for n in self.nodes if n.node_type == "aim"), None)
        if aim_node is not None and math.hypot(rx, ry) > 0.05:
            step = 0.018 * aim_node.sensitivity
            nx = self._aim_curr_norm[0] + rx * step
            ny = self._aim_curr_norm[1] + ry * step
            if nx < 0.35 or nx > 0.94 or ny < 0.12 or ny > 0.88:
                self.adb_engine.send_touch_up("aim", *self._aim_curr_norm)
                self._aim_curr_norm = (aim_node.norm_x, aim_node.norm_y)
                self.adb_engine.send_touch_down("aim", *self._aim_curr_norm)
            else:
                self._aim_curr_norm = (nx, ny)
                self.adb_engine.send_touch_move("aim", nx, ny)

    def _release_all_active_touches(self) -> None:
        self._rapid_fire_active = False
        self._dpad_touch_active = False
        self.adb_engine.send_touch_up("dpad", *self._dpad_curr_norm)
        self.adb_engine.send_touch_up("aim", *self._aim_curr_norm)

    # ------------------------------------------------------------------------
    # PROFILE MANAGEMENT (SAVE / LOAD JSON & PRESETS)
    # ------------------------------------------------------------------------

    def _on_preset_selected(self, _event: Optional[tk.Event] = None) -> None:
        presets = get_builtin_presets()
        choice = self.preset_var.get()
        if choice in presets:
            self.nodes = [KeyMapNode(**asdict(n)) for n in presets[choice]]
            self.selected_node = None
            self._update_inspector_panel()
            self.redraw_canvas()

    def save_profile_dialog(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save Keymapping Profile",
            defaultextension=".json",
            filetypes=[("JSON Keymap Profile", "*.json")],
            initialfile="my_game_keymap.json",
        )
        if not path:
            return
        data = {
            "landscape_mode": self.landscape_mode,
            "input_device_mode": self.input_device_mode,
            "nodes": [asdict(n) for n in self.nodes],
        }
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
        messagebox.showinfo("Profile Saved", f"Saved keymapping profile to:\n{path}")

    def load_profile_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Load Keymapping Profile",
            filetypes=[("JSON Keymap Profile", "*.json")],
        )
        if not path:
            return
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            self.landscape_mode = bool(raw.get("landscape_mode", True))
            self.adb_engine.set_orientation_mode(self.landscape_mode)
            if raw.get("input_device_mode") in self.INPUT_MODES:
                self.set_input_device_mode(raw["input_device_mode"])
            self.nodes = [KeyMapNode(**item) for item in raw.get("nodes", [])]
            self.selected_node = None
            self._update_inspector_panel()
            self.redraw_canvas()
        except Exception as exc:
            messagebox.showerror("Load Error", f"Failed to load profile:\n{exc}")

    def on_close(self) -> None:
        self._release_all_active_touches()
        self.adb_engine.shutdown()
        if self.scrcpy_proc is not None:
            try:
                self.scrcpy_proc.terminate()
            except Exception:
                pass
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = MobileKeymapperStudio(root)
    root.mainloop()


if __name__ == "__main__":
    main()
