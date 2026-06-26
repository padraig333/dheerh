#!/usr/bin/env python3
"""Package the extension into installable browsers builds.

Reads the shared sources in ``extension/`` and writes, per target, both an
unpacked directory and a zipped package into ``dist/``:

    dist/chrome/                 unpacked (Load unpacked)
    dist/firefox/                unpacked (Load Temporary Add-on)
    dist/auto-video-archiver-chrome.zip
    dist/auto-video-archiver-firefox.xpi

The two targets need different manifests:

* Chrome/Edge/Brave (MV3) require ``background.service_worker``.
* Firefox is happiest with a ``background.scripts`` event page and *requires*
  an explicit add-on id under ``browser_specific_settings.gecko`` for signing
  and for ``storage.sync`` to work.

Standard library only — no build tooling required:

    python3 build.py
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "extension")
DIST = os.path.join(ROOT, "dist")

# Stable add-on id for Firefox. Change the domain part if you fork this.
GECKO_ID = "auto-video-archiver@dheerh"
FIREFOX_MIN_VERSION = "115.0"  # first ESR with stable MV3 support

# Files/dirs (relative to extension/) shipped in every build.
ASSETS = ["background.js", "content.js", "popup.html", "popup.js", "icons"]


def load_base_manifest() -> dict:
    with open(os.path.join(SRC, "manifest.json"), encoding="utf-8") as f:
        return json.load(f)


def chrome_manifest(base: dict) -> dict:
    m = copy.deepcopy(base)
    m["background"] = {"service_worker": "background.js"}
    return m


def firefox_manifest(base: dict) -> dict:
    m = copy.deepcopy(base)
    # Firefox uses a non-persistent event page rather than a service worker.
    m["background"] = {"scripts": ["background.js"]}
    m["browser_specific_settings"] = {
        "gecko": {
            "id": GECKO_ID,
            "strict_min_version": FIREFOX_MIN_VERSION,
        }
    }
    return m


def stage(target: str, manifest: dict) -> str:
    out_dir = os.path.join(DIST, target)
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)

    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    for asset in ASSETS:
        src = os.path.join(SRC, asset)
        dst = os.path.join(out_dir, asset)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    return out_dir


def zip_dir(src_dir: str, archive_path: str) -> None:
    if os.path.exists(archive_path):
        os.remove(archive_path)
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(src_dir):
            for name in sorted(files):
                full = os.path.join(root, name)
                # Store paths relative to src_dir so manifest.json sits at the root.
                zf.write(full, os.path.relpath(full, src_dir))


def build() -> None:
    base = load_base_manifest()
    os.makedirs(DIST, exist_ok=True)

    targets = {
        "chrome": (chrome_manifest(base), "auto-video-archiver-chrome.zip"),
        "firefox": (firefox_manifest(base), "auto-video-archiver-firefox.xpi"),
    }

    for target, (manifest, archive_name) in targets.items():
        out_dir = stage(target, manifest)
        archive = os.path.join(DIST, archive_name)
        zip_dir(out_dir, archive)
        size_kb = os.path.getsize(archive) / 1024
        print(f"{target:8} -> {os.path.relpath(out_dir, ROOT)}/  "
              f"and {os.path.relpath(archive, ROOT)} ({size_kb:.1f} KB)")

    print("\nDone. See the README 'Building packaged extensions' section "
          "for how to load/sign each build.")


if __name__ == "__main__":
    build()
