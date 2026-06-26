// background.js — service worker. Receives "watched-video" messages from
// content scripts and forwards them to the local yt-dlp helper server. Keeps a
// small history and a session-level dedupe set, and reflects status on the
// toolbar badge.

const DEFAULTS = {
  enabled: true,
  serverUrl: "http://127.0.0.1:8731",
  historyLimit: 100,
};

// URLs sent during this worker's lifetime, to avoid duplicate posts.
const sentThisSession = new Set();

async function getSettings() {
  const stored = await chrome.storage.sync.get(DEFAULTS);
  return { ...DEFAULTS, ...stored };
}

async function pushHistory(entry) {
  const { history = [] } = await chrome.storage.local.get("history");
  history.unshift(entry);
  const { historyLimit } = await getSettings();
  history.length = Math.min(history.length, historyLimit);
  await chrome.storage.local.set({ history });
}

function flashBadge(text, color) {
  chrome.action.setBadgeBackgroundColor({ color });
  chrome.action.setBadgeText({ text });
  setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);
}

async function queueDownload(url, title) {
  const settings = await getSettings();
  if (!settings.enabled) return;
  if (sentThisSession.has(url)) return;
  sentThisSession.add(url);

  const base = settings.serverUrl.replace(/\/+$/, "");
  try {
    const res = await fetch(`${base}/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, title }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      flashBadge("✓", "#2e7d32");
      await pushHistory({
        url,
        title,
        status: data.status || "queued",
        time: Date.now(),
      });
    } else {
      throw new Error(data.error || `HTTP ${res.status}`);
    }
  } catch (err) {
    // Allow a retry later if the server was simply unreachable.
    sentThisSession.delete(url);
    flashBadge("!", "#c62828");
    await pushHistory({
      url,
      title,
      status: "error",
      error: String(err.message || err),
      time: Date.now(),
    });
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "watched-video" && msg.url) {
    queueDownload(msg.url, msg.title).then(() => sendResponse({ ok: true }));
    return true; // async response
  }
});
