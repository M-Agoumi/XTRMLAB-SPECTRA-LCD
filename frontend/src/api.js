// api.js -- the only file that knows the backend's actual endpoint
// shapes (control_server.py). Everything else in the app just calls
// these functions. Paths are relative ("/api/state", not a full
// origin) on purpose: in dev, Vite's proxy (vite.config.js) forwards
// them to the backend; in production, the backend serves this app's
// own build output, so "relative" already means "same origin, same
// port" with nothing to configure.

async function asJson(res) {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body.error || `${res.status} ${res.statusText}`);
  }
  return body;
}

export function getState() {
  return fetch("/api/state").then(asJson);
}

export function getConfig() {
  return fetch("/api/config").then(asJson);
}

export function updateConfig(patch) {
  return fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  }).then(asJson);
}

// Brightness is split out from updateConfig() on purpose: the backend
// applies it live (no restart needed) the same way app.py's slider
// does, by pushing straight to the connected screen if one's running.
export function setBrightness(value) {
  return fetch("/api/brightness", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  }).then(asJson);
}

export function getSystem() {
  return fetch("/api/system").then(asJson);
}

export function setStartup(enabled) {
  return fetch("/api/startup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  }).then(asJson);
}

export function createShortcut() {
  return fetch("/api/shortcut", { method: "POST" }).then(asJson);
}

export function start(theme) {
  return fetch("/api/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(theme ? { theme } : {}),
  }).then(asJson);
}

export function stop() {
  return fetch("/api/stop", { method: "POST" }).then(asJson);
}

export function apply() {
  return fetch("/api/apply", { method: "POST" }).then(asJson);
}

// EventSource handles SSE reconnection itself; the caller just gets a
// stream of log lines and an unsubscribe function.
export function subscribeLogs(onLine) {
  const source = new EventSource("/api/logs/stream");
  source.onmessage = (ev) => onLine(ev.data);
  return () => source.close();
}

export const THEMES = ["dashboard", "video", "webpage", "clock"];
