# ▶ SanWatch - Ad-free YouTube for slow internet

Search or paste YouTube videos, see them as thumbnail cards, and watch **without ads**.

## Tabs
- **📚 Library** - your saved videos. Paste links with **Ctrl+V / Paste & Add**. Type in the box to filter.
- **🔍 Discover** - type a topic (e.g. `car`) + Enter to search YouTube inside the app. **Load more** for more results.
- **📰 My Feed** - latest videos from topics and channels you choose (**⚙ Manage feed**). Saved on your PC, so it shows offline; **🔄 Refresh feed** when you have data.

## Playing
- **▶ Watch** - downloads once (resumes if the network drops), then plays with your PC player. Rewatch = 0 data.
- **📡 Stream** - ad-free direct play in mpv or VLC, up to 4K.
- **⬇ Save** - download for offline. **＋ Library** - keep a search result in your library.
- **🦁 Brave** - opens the video in Brave (Shields blocks YouTube ads).
- **Auto-play next** - plays the next video in the list automatically (6-second "Up next" popup; Stop any time). **▶ Play all** starts the whole list. **⏹ Stop** ends the queue.

## Quality
Default is **Best (original)**, up to 4K. Click **🎞 Get ffmpeg (4K)** once for 1080p+ downloads.

## Run / Build
```bat
pip install -U yt-dlp pillow
python SanWatch.py
```
Or double-click `build_exe.bat` -> `dist\SanWatch.exe`.

## Notes
- Needs VLC or mpv for Stream / auto-play.
- If search or play breaks after a YouTube change: `pip install -U yt-dlp`, rebuild.
- Errors are saved to `%APPDATA%\SanWatch\error.log`.
- Personal offline viewing only; respect creators and YouTube's terms.
