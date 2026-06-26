#!/usr/bin/env python3
"""Local yt-dlp helper for the Auto Video Archiver browser extension.

The extension can't run native binaries, so it POSTs the page URLs you watch to
this small server, which runs ``yt-dlp`` for each one. A download archive keeps
track of what's already been fetched so nothing is downloaded twice, and a
single background worker thread processes a queue so concurrent tabs don't spawn
a flood of yt-dlp processes.

Endpoints
---------
GET  /health    -> {"ok": true, "queued": N, "downloads": M}
POST /download  -> body {"url": "...", "title": "..."} -> {"status": "queued"}

Usage
-----
    python3 server.py --dir ~/Videos/Archive --port 8731

Requires yt-dlp on PATH (https://github.com/yt-dlp/yt-dlp).
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Populated from CLI args in main().
CONFIG = {
    "download_dir": os.path.expanduser("~/Videos/Archive"),
    "ytdlp": "yt-dlp",
    "extra_args": [],
}

job_queue: "queue.Queue[dict]" = queue.Queue()
seen_urls: set[str] = set()
seen_lock = threading.Lock()
stats = {"downloads": 0, "errors": 0}


def log(*args) -> None:
    print(datetime.now().strftime("[%H:%M:%S]"), *args, flush=True)


def archive_path() -> str:
    return os.path.join(CONFIG["download_dir"], ".download-archive.txt")


def worker() -> None:
    """Single consumer: runs yt-dlp for each queued URL, one at a time."""
    while True:
        job = job_queue.get()
        url = job["url"]
        title = job.get("title") or url
        try:
            os.makedirs(CONFIG["download_dir"], exist_ok=True)
            cmd = [
                CONFIG["ytdlp"],
                "--no-overwrites",
                "--download-archive", archive_path(),
                "--no-playlist",
                "--restrict-filenames",
                "-o", os.path.join(CONFIG["download_dir"], "%(title)s [%(id)s].%(ext)s"),
                *CONFIG["extra_args"],
                url,
            ]
            log(f"downloading: {title}")
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode == 0:
                stats["downloads"] += 1
                log(f"done: {title}")
            else:
                stats["errors"] += 1
                tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
                log(f"FAILED ({proc.returncode}): {title}\n  " + "\n  ".join(tail))
                # Let a future watch retry a transient failure.
                with seen_lock:
                    seen_urls.discard(url)
        except Exception as exc:  # noqa: BLE001
            stats["errors"] += 1
            log(f"ERROR: {exc}")
            with seen_lock:
                seen_urls.discard(url)
        finally:
            job_queue.task_done()


class Handler(BaseHTTPRequestHandler):
    server_version = "AutoVideoArchiver/1.0"

    # --- helpers -----------------------------------------------------------
    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # The extension's service worker fetches cross-origin; allow it.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.body_sent = True
        self.wfile.write(body)

    def log_message(self, *_args) -> None:  # silence default noisy logging
        pass

    # --- routes ------------------------------------------------------------
    def do_OPTIONS(self) -> None:  # CORS preflight
        self._send(204, {})

    def do_GET(self) -> None:
        if self.path.split("?")[0] == "/health":
            self._send(200, {
                "ok": True,
                "queued": job_queue.qsize(),
                "downloads": stats["downloads"],
                "errors": stats["errors"],
                "dir": CONFIG["download_dir"],
            })
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path.split("?")[0] != "/download":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"error": "invalid JSON"})
            return

        url = (data.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            self._send(400, {"error": "missing or invalid url"})
            return

        with seen_lock:
            if url in seen_urls:
                self._send(200, {"status": "duplicate"})
                return
            seen_urls.add(url)

        job_queue.put({"url": url, "title": data.get("title")})
        log(f"queued: {data.get('title') or url}")
        self._send(200, {"status": "queued", "queued": job_queue.qsize()})


def main() -> int:
    parser = argparse.ArgumentParser(description="Local yt-dlp helper server.")
    parser.add_argument("--dir", default=CONFIG["download_dir"],
                        help="download directory (default: %(default)s)")
    parser.add_argument("--port", type=int, default=8731, help="listen port")
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address (default: localhost only)")
    parser.add_argument("--ytdlp", default="yt-dlp", help="yt-dlp executable")
    parser.add_argument("ytdlp_args", nargs=argparse.REMAINDER,
                        help="extra args passed to yt-dlp after '--'")
    args = parser.parse_args()

    CONFIG["download_dir"] = os.path.expanduser(args.dir)
    CONFIG["ytdlp"] = args.ytdlp
    # Strip a leading '--' separator if present.
    extra = args.ytdlp_args
    if extra and extra[0] == "--":
        extra = extra[1:]
    CONFIG["extra_args"] = extra

    if not shutil.which(CONFIG["ytdlp"]):
        log(f"WARNING: '{CONFIG['ytdlp']}' not found on PATH. "
            "Install it from https://github.com/yt-dlp/yt-dlp")

    os.makedirs(CONFIG["download_dir"], exist_ok=True)

    threading.Thread(target=worker, daemon=True).start()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    log(f"listening on http://{args.host}:{args.port}")
    log(f"saving videos to {CONFIG['download_dir']}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log("shutting down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
