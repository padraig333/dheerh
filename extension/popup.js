// popup.js — settings UI + recent downloads + live server status.

const SYNC_DEFAULTS = {
  enabled: true,
  instant: false,
  serverUrl: "http://127.0.0.1:8731",
  minWatchSeconds: 5,
  allowlist: [],
  blocklist: [],
};

const $ = (id) => document.getElementById(id);
const linesToList = (s) => s.split("\n").map((x) => x.trim()).filter(Boolean);

// The watch threshold is irrelevant when instant mode is on.
function syncInstantUI() {
  $("minWatchSeconds").disabled = $("instant").checked;
}

async function load() {
  const s = await chrome.storage.sync.get(SYNC_DEFAULTS);
  $("enabled").checked = s.enabled;
  $("instant").checked = s.instant;
  $("serverUrl").value = s.serverUrl;
  $("minWatchSeconds").value = s.minWatchSeconds;
  $("allowlist").value = (s.allowlist || []).join("\n");
  $("blocklist").value = (s.blocklist || []).join("\n");
  syncInstantUI();
  checkServer(s.serverUrl);
  renderHistory();
}

async function save() {
  const values = {
    enabled: $("enabled").checked,
    instant: $("instant").checked,
    serverUrl: $("serverUrl").value.trim() || SYNC_DEFAULTS.serverUrl,
    minWatchSeconds: Math.max(0, Number($("minWatchSeconds").value) || 0),
    allowlist: linesToList($("allowlist").value),
    blocklist: linesToList($("blocklist").value),
  };
  await chrome.storage.sync.set(values);
  $("save").textContent = "Saved ✓";
  setTimeout(() => ($("save").textContent = "Save settings"), 1500);
  checkServer(values.serverUrl);
}

async function checkServer(url) {
  const el = $("serverStatus");
  const base = url.replace(/\/+$/, "");
  try {
    const res = await fetch(`${base}/health`, { cache: "no-store" });
    if (!res.ok) throw new Error();
    const data = await res.json();
    el.textContent = `online · ${data.downloads ?? 0} done`;
    el.className = "status ok";
  } catch (_) {
    el.textContent = "offline";
    el.className = "status bad";
  }
}

async function renderHistory() {
  const { history = [] } = await chrome.storage.local.get("history");
  const ul = $("history");
  ul.innerHTML = "";
  if (!history.length) {
    ul.innerHTML = '<li class="muted">Nothing yet.</li>';
    return;
  }
  for (const h of history) {
    const li = document.createElement("li");
    const tag = document.createElement("span");
    const status = h.status === "error" ? "error" : "queued";
    tag.className = `tag ${status}`;
    tag.textContent = status;
    const a = document.createElement("a");
    a.href = h.url;
    a.target = "_blank";
    a.textContent = h.title || h.url;
    a.title = h.error ? h.error : h.url;
    li.appendChild(tag);
    li.appendChild(a);
    ul.appendChild(li);
  }
}

$("instant").addEventListener("change", syncInstantUI);
$("save").addEventListener("click", save);
$("clear").addEventListener("click", async () => {
  await chrome.storage.local.set({ history: [] });
  renderHistory();
});
chrome.storage.onChanged.addListener((c, area) => {
  if (area === "local" && c.history) renderHistory();
});

load();
