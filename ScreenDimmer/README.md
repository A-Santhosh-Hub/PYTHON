# Screen Dimmer

Makes your screen darker than the lowest Windows brightness setting.

Useful at night, when 0% brightness is still too bright. Set your normal brightness
as low as it goes, then add extra dimming from 0% to 100%:

- **0%:** no extra dimming
- **100%:** completely black

Windows 8 or later. Nothing to install, and no admin rights needed.

## Start it

Double-click `ScreenDimmer.exe`.

No window opens. The screen darkens and a small circle icon appears in the tray. It
may be hidden under the `^` arrow next to the clock. Double-click the exe again to
open the slider.

Windows may show a "Windows protected your PC" message, because the exe is not
digitally signed. Choose **More info**, then **Run anyway**, or build it yourself
from the source (see below).

## Controls

| Action | How |
|---|---|
| Open the slider | Left-click the tray icon |
| Pick a level, mode or Exit | Right-click the tray icon |
| Darker | `Ctrl+Alt+Page Down` |
| Brighter | `Ctrl+Alt+Page Up` |
| Dimming off, or back on | `Ctrl+Alt+Home` |

**If the screen goes black, press `Ctrl+Alt+Home`.**

## Commands

Run these from a terminal in the same folder:

```bat
ScreenDimmer.exe 70
ScreenDimmer.exe off
ScreenDimmer.exe overlay
ScreenDimmer.exe filter
ScreenDimmer.exe exit
```

- `70` is any level from 0 to 100.
- `off` turns dimming off and keeps the tray icon.
- `overlay` and `filter` switch modes.
- `exit` closes the program and restores the screen.

## Modes

- **Full-screen filter (default):** uses the Windows Magnification color effect.
  It darkens the whole desktop, including the Start menu and taskbar.
- **Overlay window:** a click-through black window on top of the screen. Try this
  if the filter conflicts with something, such as the color features in Windows
  Magnifier.

If the filter isn't available, the tool switches to overlay mode by itself.

## Good to know

- Your last level is remembered. It is capped at 90% when the tool starts, so it
  can never open on a black screen.
- The percentage scales the picture's color values, so the screen looks darker
  than the number suggests. Small steps near the top of the range make a big
  difference, which is why the hotkeys use smaller steps from 90%.
- This darkens the picture and does not lower the backlight further, so it won't
  save extra battery on an LCD panel.
- It may not darken games in exclusive full-screen mode or Windows security
  screens, such as the UAC prompt.
- "Start with Windows" remembers where the program is, so turn it off before you
  move the file.

## Privacy and what it changes

Screen Dimmer has no network code, so it doesn't send anything anywhere. It writes
only to your own user section of the Windows registry:

| Registry key | What it holds |
|---|---|
| `HKCU\Software\ScreenDimmer` | Your dimming level and mode |
| `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` | A `ScreenDimmer` value, only if you turn on "Start with Windows" |

## Uninstall

1. Right-click the tray icon and turn off "Start with Windows" if it is on.
2. Choose **Exit**, then delete `ScreenDimmer.exe`.
3. Optional: delete the `HKCU\Software\ScreenDimmer` registry key to clear your
   saved settings.

## Build from source

Run `build.bat`. It creates `ScreenDimmer.exe` using the C# compiler included with
Windows, so there is nothing to install. Close the program first if it is running.

## Files

| File | Purpose |
|---|---|
| `ScreenDimmer.exe` | The program |
| `src\ScreenDimmer.cs` | Source code |
| `build.bat` | Builds `ScreenDimmer.exe` |
| `LICENSE` | MIT License |

## License

[MIT](LICENSE)
