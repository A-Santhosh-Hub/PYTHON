# Lightweight Zero-Overhead FPS & System Overlay

A tiny, zero-install FPS and hardware monitoring overlay for Windows games. Runs directly from a single `.bat` and `.ps1` script using native Windows components—no third-party bloatware, no background services, and **zero game performance loss**.

---

## Why Use This Instead of Third-Party Apps?

Most popular FPS counters and overlays (like MSI Afterburner/RivaTuner, GeForce Experience, or Discord) work by **injecting DLLs directly into your game's process** and hooking into the rendering pipeline. That approach comes with downsides:
* **Reduced Game Performance:** Heavy background launchers and rendering hooks eat up CPU cycles, RAM, and frame time.
* **Game Crashes & Stutters:** Hooking into DirectX/Vulkan can cause instability, micro-stutters, or crashes on launch.
* **Anti-Cheat Conflicts:** Aggressive kernel anti-cheat systems often block or flag third-party DLL injectors.

### How This Project Preserves Your Performance
1. **Zero Game Injection:** Your game is never touched or modified. Windows naturally logs an **ETW (Event Tracing for Windows)** event every time an application presents a frame (the exact same mechanism Microsoft's *PresentMon* uses). This tool passively listens to those native Windows events from the outside.
2. **Ultra-Lightweight Native Execution:** Powered by a tiny Batch launcher and a self-contained PowerShell/C# script, it only counts frame events and updates a simple click-through label twice a second (every 500ms). 
3. **Nothing Installed:** No installers, no registry clutter, and no background telemetry running when you aren't gaming.

---

## Features

* **Real-Time Frame Metrics:** Displays current **FPS**, **Frame Time (ms)**, and **1% Low FPS** (calculated over a rolling 10-second window).
* **Multi-API Support:** Works automatically with **DirectX 10/11/12** (`DXGI`), **DirectX 9** (`D3D9`), and falls back to kernel tracking (`DxgKrnl`) for **Vulkan and OpenGL** games.
* **Smart Swap-Chain Filtering:** Tracks frames per swap chain and ignores `DXGI_PRESENT_TEST` calls so in-game sub-overlays don't double-count your FPS.
* **Live Hardware Telemetry:** 
  * **All Systems:** CPU Usage %, GPU Usage %, RAM Used/Total, and VRAM Usage.
  * **NVIDIA GPUs (via `nvml.dll`):** Automatically unlocks GPU Temperature (°C), Core Clock (MHz), and Power Draw (W).
* **100% Click-Through:** The overlay never steals window focus or blocks mouse clicks in your game.
* **On-the-Fly Repositioning:** Move the overlay to any corner or center edge using keyboard shortcuts while playing.

---

## Requirements

* **OS:** Windows 10 or Windows 11 (64-bit)
* **Display Mode:** Set your game to **Borderless Windowed** or **Windowed** mode. *(Because this tool does not inject itself into the game engine, Exclusive Fullscreen games will draw over the overlay).*
* **Permissions:** Administrator privileges (requested automatically once at startup via Windows UAC, which is required by Windows to listen to ETW frame events).

---

## Quick Start

1. Download or clone this repository and keep both files (`FpsOverlay.ps1` and the `.bat` launcher) in the **same folder**.
2. Double-click the **`.bat` file** to launch the overlay.
3. Click **Yes** on the Windows UAC Administrator prompt.
4. Launch your game and play!

*(Alternatively, you can right-click `FpsOverlay.ps1` and select **Run with PowerShell**).*

---

## Hotkeys & Controls

You can control the overlay at any time while in-game or from the system tray icon:

| Shortcut | Action |
| :--- | :--- |
| **`Ctrl + Shift + F12`** | **Exit** the FPS overlay completely |
| **`Ctrl + Shift + F11`** | **Hide / Show** the entire overlay |
| **`Ctrl + Shift + F10`** | **Hide / Show** extra hardware stats (CPU, GPU, RAM, VRAM, Temps) |
| **`Ctrl + Shift + Left`** | Move overlay to the **Left** side |
| **`Ctrl + Shift + Right`** | Move overlay to the **Right** side |
| **`Ctrl + Shift + C`** | Move overlay to the **Horizontal Center** |
| **`Ctrl + Shift + Up`** | Move overlay to the **Top** edge |
| **`Ctrl + Shift + Down`** | Move overlay to the **Bottom** edge |

> **Tip:** Horizontal and vertical positions work independently. For example, press `Ctrl + Shift + Down` followed by `Ctrl + Shift + C` to place the overlay at the **Bottom Center** of your screen.

---

## Advanced Command-Line Options

If you run `FpsOverlay.ps1` from a PowerShell terminal, you can pass optional flags:

* **Start in a Specific Position:**
  ```powershell
  .\FpsOverlay.ps1 -Corner TopRight
