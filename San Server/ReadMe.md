# SanShare — share a whole folder over Wi-Fi, no pen drive

Solves exactly the problem you described: your friend has game folders
(not installers — full folders, hundreds of loose files, 90GB+ total).
Right now he copies it to a pen drive and walks it over to your laptop.
This replaces that with: he runs one command, you open one link in your
browser, you download it straight over your shared office Wi-Fi.

Only the **host** (whoever has the files) needs Python installed. The
other person just needs a browser — nothing to install on their side.

---

## 1. Setup (host machine only — whoever is sharing)

Requires Python 3.9+.

```bash
cd lan-file-share
pip install -r requirements.txt
```

## 2. Run it (host machine)

```bash
python server.py --folder "D:\Games" --port 5000
```

- `--folder` — the folder you want to share (any size, any mix of file types)
- `--port` — optional, defaults to 5000
- `--password` — optional, recommended since you're both on a shared
  office Wi-Fi and not just a private home network (see [Security](#security) below):

```bash
python server.py --folder "D:\Games" --password 1234
```

On Windows you can instead edit `start_windows.bat` (change the `FOLDER`
line to your path) and just double-click it going forward. Same idea for
Mac/Linux with `start_mac_linux.sh`.

On startup it prints something like:

```
Sharing:  D:\Games
Open on any device on this Wi-Fi:   http://192.168.1.14:5000
```

Send that `http://192.168.1.14:5000` address to whoever's downloading —
that's the only thing they need.

## 3. Download it (the other person)

Open that address in any browser (Chrome, Edge, Firefox — phone or
laptop, doesn't matter, as long as it's on the same Wi-Fi). You'll see
the shared folder:

- Click a **file** to download it directly.
- Click a **folder** to open it and browse inside.
- Tick the checkboxes next to whatever you want (files, folders, or a
  mix) and hit **Download as ZIP** at the bottom to get it all in one
  go, folder structure kept intact.

## Windows Firewall

The first time you run it, Windows will ask if Python should be allowed
through the firewall for private networks — click **Allow**. If it
doesn't ask and the other side can't connect, go to *Windows Defender
Firewall → Allow an app through firewall* and enable Python for
**Private** networks.

---

## What's actually happening (the core function you asked about)

- **Browsing**: Flask reads the folder with `os.scandir` and renders a
  listing — no database, no indexing step, so it opens instantly even
  on a 90GB tree, because it only ever looks at *one* folder level at a
  time, not the whole tree.
- **Single-file downloads are resumable.** Flask's `send_from_directory`
  handles HTTP `Range` requests automatically (confirmed in testing —
  a request for the middle bytes of a file gets exactly those bytes
  back with `206 Partial Content`). That matters at your scale: if the
  Wi-Fi drops mid-way through a 1GB file, a re-attempted download
  resumes instead of restarting from zero.
- **"Download as ZIP" streams on the fly** using `zipstream-ng` — it
  never builds a .zip on disk first. It reads each file and writes zip
  bytes straight to the response as they're requested, so there's no
  "please wait while I zip 90GB" delay before the download even starts,
  and no extra 90GB of temp space needed on the host.
- **No compression in that ZIP, on purpose.** Game files (textures,
  audio, packed assets) are already compressed, so running them through
  ZIP's Deflate again just burns CPU for a fraction of a percent of
  space saved — sometimes it even comes out slightly *larger*. Stored
  (uncompressed) mode is used instead, which is also what makes it
  possible to calculate the exact final ZIP size *before* streaming
  starts, so the browser shows a real progress bar instead of a
  spinning "unknown size" download.
- **Path safety**: every request is resolved and checked against the
  shared folder before touching disk, so `../../` style tricks in a
  URL can't walk outside the folder you chose to share (tested).

### Why Flask + waitress instead of Python's plain `http.server`

`python -m http.server` was the obvious "simplest possible" option and
is worth naming since you asked for the reasoning: it can share a
folder in one line, but it has no resume support for interrupted
downloads, no way to bundle a multi-file selection into one download,
and no login gate — all three matter once a single file is 1GB+ and
you're on a Wi-Fi that occasionally hiccups. Flask gives you those for
a small amount of extra code, and it's still one file.

Flask's own built-in dev server is fine for trying things out but isn't
meant to be lean on serving large files under real load. `waitress` is
a production-grade WSGI server that's pure Python (no compiler/build
tools needed, unlike `gunicorn`, which also doesn't run on Windows) —
it's used automatically if installed (it's in `requirements.txt`), and
the app quietly falls back to Flask's dev server if it isn't, so
nothing breaks either way.

---

## Security

This has **no encryption and, without `--password`, no login** — it's
built for a trusted local network, not the open internet. Since you
mentioned it's a shared office Wi-Fi (not just you two), that means
anyone else on that same Wi-Fi could technically browse the shared
folder while it's running unless you set `--password`. A few notes:

- Use `--password` when other people share that Wi-Fi.
- Only run it while you're actively transferring — it's not meant to
  stay on permanently in the background.
- Don't port-forward this on a router to expose it to the public
  internet; it's designed for LAN use only.

## Known limitation

Individual file downloads resume if interrupted. A ZIP download made
from multiple selected items does **not** — because its exact contents
depend on what you selected, so a browser can't "resume" one from a
random past request. For a handful of files this is a non-issue; for a
truly huge one-shot transfer, downloading the big files individually
(which do resume) is the safer bet on a flaky connection.

## Project layout

```
lan-file-share/
├── server.py            # Flask app — all backend logic
├── requirements.txt
├── start_windows.bat    # convenience launcher, edit the folder path
├── start_mac_linux.sh
├── templates/
│   ├── index.html       # folder browser
│   └── login.html       # password gate (only used with --password)
└── static/
    ├── style.css
    └── script.js         # selection state, live size total, filter box
```
