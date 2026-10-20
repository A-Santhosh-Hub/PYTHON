# Third-party software

Mobile Key One uses and ships the following. Each keeps its own licence.

| Component | Where | Licence |
|---|---|---|
| **scrcpy server v5.0.1** (Genymobile) - runs on the phone, sends the picture and receives touches | `vendor/scrcpy-server-v5.0.1` | Apache License 2.0, see `vendor/scrcpy-server-LICENSE.txt`. Source: https://github.com/Genymobile/scrcpy |
| **adb** (Android SDK Platform-Tools, Google) - talks to the phone over USB | `vendor/adb/` (`adb.exe`, `AdbWinApi.dll`, `AdbWinUsbApi.dll`) | Apache License 2.0. Source and notices: https://developer.android.com/tools/releases/platform-tools |
| **PySide6 / Qt for Python** | installed with pip | LGPL-3.0 / GPL / commercial (Qt Company) |
| **PyAV** (bindings to FFmpeg) | installed with pip | BSD-3-Clause; the bundled FFmpeg libraries are LGPL / GPL |
| **NumPy**, **psutil** | installed with pip | BSD-3-Clause |

The client in this project is a separate Python implementation of the scrcpy protocol; the official scrcpy source was
used as a reference for the protocol. Client and server versions must match exactly, so the server is pinned to v5.0.1.

Mobile Key One is an independent project. It is not affiliated with or endorsed by Genymobile, Google, Tencent,
Activision, Krafton or any game publisher. Game and product names belong to their owners.
