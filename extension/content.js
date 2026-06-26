// content.js — runs on every page (and frame). Detects genuine video playback
// and reports the page URL to the background service worker, which forwards it
// to the local yt-dlp helper.
//
// "Watching" is defined conservatively to avoid grabbing hover-previews, muted
// autoplay banners, ads, etc.: a <video> must accumulate a configurable amount
// of actual playback time before we consider it watched.

(() => {
  "use strict";

  const DEFAULTS = {
    enabled: true,
    // Fire the download the moment playback starts, ignoring the threshold.
    instant: false,
    // Seconds of real playback before a video counts as "watched".
    minWatchSeconds: 5,
    // Empty list = run everywhere. Otherwise only these hostnames (suffix match).
    allowlist: [],
    // Hostnames to always ignore (suffix match).
    blocklist: [],
  };

  let settings = { ...DEFAULTS };

  // URLs already reported from this frame, so we don't spam the helper.
  const reported = new Set();
  // Per-video accumulated playback time.
  const watched = new WeakMap();

  chrome.storage?.sync.get(DEFAULTS, (stored) => {
    settings = { ...DEFAULTS, ...stored };
  });

  chrome.storage?.onChanged.addListener((changes, area) => {
    if (area !== "sync") return;
    for (const [key, { newValue }] of Object.entries(changes)) {
      if (key in settings) settings[key] = newValue;
    }
  });

  function hostnameMatches(list) {
    const host = location.hostname;
    return list.some((entry) => {
      const e = entry.trim().toLowerCase();
      if (!e) return false;
      return host === e || host.endsWith("." + e);
    });
  }

  function siteEnabled() {
    if (!settings.enabled) return false;
    if (settings.blocklist.length && hostnameMatches(settings.blocklist)) return false;
    if (settings.allowlist.length && !hostnameMatches(settings.allowlist)) return false;
    return true;
  }

  // Use the top-level document URL even when running inside an iframe, because
  // that's the page the user is actually watching (e.g. an embedded player).
  function pageUrl() {
    try {
      return window.top.location.href;
    } catch (_) {
      // Cross-origin frame: fall back to the referrer or this frame's URL.
      return document.referrer || location.href;
    }
  }

  function report(video) {
    if (!siteEnabled()) return;
    const url = pageUrl();
    if (!url || reported.has(url)) return;
    reported.add(url);

    const title =
      (() => {
        try {
          return window.top.document.title;
        } catch (_) {
          return document.title;
        }
      })() || url;

    chrome.runtime.sendMessage({ type: "watched-video", url, title }, () => {
      // Swallow "receiving end does not exist" errors during reloads.
      void chrome.runtime.lastError;
    });
  }

  function trackProgress(video) {
    if (video.dataset.avaTracked) return;
    video.dataset.avaTracked = "1";

    // Instant mode: report as soon as the video actually starts playing.
    video.addEventListener("playing", () => {
      if (settings.instant) report(video);
    });

    let last = null;

    const onTimeUpdate = () => {
      if (settings.instant) return; // handled by the "playing" listener
      const now = video.currentTime;
      if (last !== null && !video.paused && !video.seeking) {
        const delta = now - last;
        // Ignore big jumps from seeking; count only natural progression.
        if (delta > 0 && delta < 1.5) {
          const total = (watched.get(video) || 0) + delta;
          watched.set(video, total);
          if (total >= settings.minWatchSeconds) {
            report(video);
            video.removeEventListener("timeupdate", onTimeUpdate);
          }
        }
      }
      last = now;
    };

    video.addEventListener("timeupdate", onTimeUpdate);
  }

  function scan() {
    document.querySelectorAll("video").forEach(trackProgress);
  }

  // Catch videos added later (SPA navigation, lazy players).
  const observer = new MutationObserver(scan);
  observer.observe(document.documentElement, { childList: true, subtree: true });

  // On SPA navigations the URL changes without reload; allow re-reporting the
  // new URL. We clear nothing from `reported` (it dedupes by full URL anyway).
  scan();
})();
