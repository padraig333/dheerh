# Auto Video Archiver

A browser extension that **automatically downloads videos you watch** using
[`yt-dlp`](https://github.com/yt-dlp/yt-dlp).

When a video actually plays in your browser for a few seconds (not just a hover
preview or a muted autoplay banner), the extension sends that page's URL to a
small local helper server, which runs `yt-dlp` to save a copy to your disk.

```
┌──────────────┐   page URL    ┌──────────────────┐   runs    ┌─────────┐
│  Browser     │ ───────────►  │  Local helper     │ ───────►  │ yt-dlp  │
│  extension   │  POST /download│  (server.py)      │           └─────────┘
└──────────────┘               └──────────────────┘
   detects real                  queues + dedupes
   video playback                downloads to ~/Videos/Archive
```

A browser extension can't run a native binary like `yt-dlp` directly (the
sandbox forbids it), so the work is split in two: the extension does the
*detection*, and the local helper does the *downloading*.

---

## Why a local helper instead of native messaging?

A plain HTTP helper is simpler to install, works identically across Chrome,
Edge, Brave and Firefox, and is easy to inspect/curl. It only listens on
`127.0.0.1` by default, so it isn't reachable from the network.

---

## Setup

### 1. Install yt-dlp

```bash
# pick one
pipx install yt-dlp           # recommended
pip install -U yt-dlp
brew install yt-dlp           # macOS
winget install yt-dlp.yt-dlp  # Windows
```

`ffmpeg` is recommended too, so `yt-dlp` can merge the best video+audio streams:

```bash
brew install ffmpeg           # macOS
sudo apt install ffmpeg       # Debian/Ubuntu
winget install Gyan.FFmpeg    # Windows
```

### 2. Start the helper server

```bash
cd server
python3 server.py --dir ~/Videos/Archive --port 8731
```

On **Windows** use `python` (or `py`) and a Windows path:

```powershell
cd server
python server.py --dir "$env:USERPROFILE\Videos\Archive" --port 8731
```

> The default `--dir` (`~/Videos/Archive`) already resolves to
> `C:\Users\<you>\Videos\Archive` on Windows, so you can omit `--dir` entirely.

Useful flags:

| Flag        | Default            | Meaning                                  |
|-------------|--------------------|------------------------------------------|
| `--dir`     | `~/Videos/Archive` | where videos are saved                   |
| `--port`    | `8731`             | port the extension talks to              |
| `--host`    | `127.0.0.1`        | bind address (keep on localhost)         |
| `--ytdlp`   | `yt-dlp`           | path to the yt-dlp executable            |

Anything after `--` is passed straight through to `yt-dlp`, e.g. to cap quality:

```bash
python3 server.py -- -f "bestvideo[height<=1080]+bestaudio/best"
```

Leave this running while you browse. To run it in the background as a service,
see [Running as a service](#running-as-a-service).

### 3. Load the extension

**Chrome / Edge / Brave**

1. Visit `chrome://extensions`
2. Enable **Developer mode** (top-right)
3. Click **Load unpacked** and select the `extension/` folder

**Firefox**

1. Visit `about:debugging#/runtime/this-firefox`
2. Click **Load Temporary Add-on…** and pick `extension/manifest.json`

Click the toolbar icon to open the popup. It shows whether the helper is online,
lets you toggle the extension on/off, set the watch threshold, and restrict it
to (or block it from) specific sites.

---

## How "watching" is detected

The content script watches every `<video>` element on the page and counts only
**genuine, forward playback time**. Once a video has played for the configured
threshold (default **5 seconds**), the page URL is reported once. Seeks, pauses,
and large time jumps are ignored, so scrubbing doesn't inflate the count and
brief autoplay previews don't trigger a download.

The helper keeps a `yt-dlp` download archive, so re-watching a video never
downloads it twice, and concurrent tabs are processed one at a time through a
queue.

---

## Configuration (popup)

- **Enabled** — master on/off switch.
- **Helper server URL** — defaults to `http://127.0.0.1:8731`.
- **Watch threshold** — seconds of real playback before a download is triggered.
- **Only on these sites** — allowlist (blank = every site).
- **Never on these sites** — blocklist (e.g. internal/sensitive sites).
- **Recent** — the last downloads with status, links, and any errors.

---

## Running as a service

**Linux (systemd, user service)** — `~/.config/systemd/user/video-archiver.service`:

```ini
[Unit]
Description=Auto Video Archiver helper

[Service]
ExecStart=%h/.local/bin/python3 %h/path/to/server/server.py --dir %h/Videos/Archive
Restart=on-failure

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable --now video-archiver
```

**macOS (launchd)** — create a `~/Library/LaunchAgents/com.local.videoarchiver.plist`
that runs `python3 .../server/server.py` with `RunAtLoad`.

**Windows (Task Scheduler)** — run it at logon, hidden, with no console window.
Use `pythonw.exe` (the windowless interpreter) so no terminal pops up:

```powershell
$py  = (Get-Command pythonw).Source
$arg = "`"$PWD\server\server.py`" --dir `"$env:USERPROFILE\Videos\Archive`""
$action  = New-ScheduledTaskAction -Execute $py -Argument $arg
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "VideoArchiver" -Action $action -Trigger $trigger
```

Alternatively, drop a shortcut to `pythonw.exe "...\server.py"` in your Startup
folder (`shell:startup`). To run it as a true background service, wrap it with
[NSSM](https://nssm.cc/).

---

## Troubleshooting

- **Popup says "offline"** — the helper isn't running, or the URL/port in the
  popup doesn't match how you launched `server.py`.
- **Downloads fail** — run `yt-dlp <url>` manually to see the real error;
  `yt-dlp` may need updating (`yt-dlp -U`) or `ffmpeg` may be missing.
- **Nothing triggers** — confirm the site isn't blocklisted, that the video
  actually plays for longer than the threshold, and that the extension is enabled.

---

## Legal / responsible use

Download only content you have the right to save — your own uploads, content
under a permissive licence, or where the platform's terms permit personal
archiving. You are responsible for complying with the terms of service of the
sites you use and with applicable copyright law.
