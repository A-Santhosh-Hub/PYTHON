# 🛡️ SanDen — Private Vault & Phone ↔ PC Continuity Hub

**SanDen** is a zero-cloud, privacy-first Android file vault and Phone ↔ PC Continuity Hub.

- **Private File Vault:** Drop images, videos, audio, documents, or any file into `/storage/emulated/0/SanDen/` (or use **Private Import** mode in Settings) — files are organized automatically and **never appear in Gallery, Google Photos, or music/video players** (`.nomedia` + app-private isolation).
- **Phone ↔ PC Continuity Hub:** Share text notes, links, code snippets, clipboard contents, and multi-GB files directly between your Android phone and Windows PC over your own Wi-Fi (or USB) — no WhatsApp, no cloud, no account needed.

---

## 📦 What's Included
1. **`SanDen-v2.0.0-arm-release.apk`** — Signed ARM release APK for Android 8.0+ (API 26+).
2. **`SanDen-PC.exe`** — Standalone Windows desktop companion app (no Python installation required).

---

## 📱 How to Install & Run (Android)
1. Transfer **`SanDen-v2.0.0-arm-release.apk`** to your Android phone and tap to install *(allow "Install unknown apps" if prompted)*.
2. Open **SanDen** and grant **"All files access"** so it can create and protect your `/storage/emulated/0/SanDen/` vault folder.
3. Tap **Phone ↔ Laptop Sync** (or the Laptop icon at the top) to start the Wi-Fi Continuity Hub.

---

## 💻 How to Run on Windows (`SanDen-PC.exe`)
1. Make sure your Android phone and Windows PC are on the **same Wi-Fi network** (or mobile hotspot).
2. Double-click **`SanDen-PC.exe`** *(if Windows SmartScreen appears, click **More info → Run anyway**)*.
3. Open **Phone ↔ Laptop Sync** on your phone — `SanDen-PC.exe` will **automatically discover your phone** and connect!
   - *Tip:* If your office/public Wi-Fi blocks device-to-device connections, connect via USB cable (with USB Debugging on) and click **USB Bridge (ADB)**.
4. **Where files are saved:**
   - **PC → Phone:** Saved directly into your phone's **SanDen Vault**.
   - **Phone → PC:** Auto-saved to `Downloads\SanDen\` on your PC — click **Open** next to any file in the chat stream to open it immediately!
