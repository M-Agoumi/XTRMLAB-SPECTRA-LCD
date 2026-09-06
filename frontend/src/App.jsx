import React, { useCallback, useEffect, useRef, useState } from "react";
import * as api from "./api.js";
import DashboardCanvas from "./DashboardCanvas.jsx";

const STATE_POLL_MS = 1500;
const FRAME_POLL_MS = 400; // control_server.py serves one JPEG per
                            // request (no multipart stream), so the
                            // "live" preview is really a fast poll --
                            // matches what the old web-mirror page did.

const BRIGHTNESS_DEBOUNCE_MS = 120; // set_brightness() is a live, no-restart
                                     // push straight to the connected screen
                                     // (see api.js) -- debounced just enough
                                     // that dragging the slider doesn't fire
                                     // an HTTP request on every pixel.

export default function App() {
  const [state, setState] = useState(null);
  const [stateError, setStateError] = useState(null);
  const [config, setConfig] = useState(null);
  const [system, setSystem] = useState(null);
  const [portDraft, setPortDraft] = useState("");
  const [brightnessDraft, setBrightnessDraft] = useState(90);
  const [theme, setTheme] = useState("clock");
  const [logs, setLogs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [systemError, setSystemError] = useState(null);
  const [shortcutMsg, setShortcutMsg] = useState(null);
  const [videoDraft, setVideoDraft] = useState({ path: "", loop: true, bw: false, audio: false, fps: "" });
  const [webpageDraft, setWebpageDraft] = useState({ url: "", interval: "0.1", reloadEvery: "" });
  const [settingsSaved, setSettingsSaved] = useState(null);
  const logBoxRef = useRef(null);
  const brightnessTimer = useRef(null);

  // -- state polling -----------------------------------------------
  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      api.getState().then(
        (s) => {
          if (!cancelled) {
            setState(s);
            setStateError(null);
          }
        },
        (e) => {
          if (!cancelled) setStateError(e.message);
        }
      );
    };
    tick();
    const id = setInterval(tick, STATE_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // -- config: loaded once, then edited locally until Save ---------
  useEffect(() => {
    api.getConfig().then((c) => {
      setConfig(c);
      setPortDraft(c.port || "");
      setBrightnessDraft(c.brightness ?? 90);
      const v = c.video || {};
      setVideoDraft({
        path: v.path || "",
        loop: v.loop ?? true,
        bw: v.bw ?? false,
        audio: v.audio ?? false,
        fps: v.fps ? String(v.fps) : "",
      });
      const w = c.webpage || {};
      setWebpageDraft({
        url: w.url || "",
        interval: w.interval ? String(w.interval) : "0.1",
        reloadEvery: w.reload_every ? String(w.reload_every) : "",
      });
    });
  }, []);

  // -- system info: Windows-startup / desktop-shortcut status --------
  useEffect(() => {
    api.getSystem().then(setSystem, (e) => setSystemError(e.message));
  }, []);

  // -- live log stream -----------------------------------------------
  useEffect(() => {
    const unsubscribe = api.subscribeLogs((line) => {
      setLogs((prev) => {
        const next = prev.length > 500 ? prev.slice(prev.length - 500) : prev;
        return [...next, line];
      });
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    const el = logBoxRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logs]);

  // -- keep the theme picker in sync with whatever's ACTUALLY running --
  // covers both a theme resumed automatically on launch (backend_app.py
  // resumes the last-running theme before this page ever loads -- see
  // ROADMAP.md Phase 2c) and Start/Stop/switch from another tab/device.
  // The picker is never locked (see the live-switching note by
  // handleStart below), so this is just about not leaving it pointed at
  // the wrong theme after an out-of-band change, not about working
  // around a lock.
  useEffect(() => {
    if (!state?.running_theme) return;
    const key = Object.entries(api.THEME_LABELS).find(
      ([, label]) => label === state.running_theme
    )?.[0];
    if (key) setTheme(key);
  }, [state?.running_theme]);

  // -- live preview: poll /frame.jpg only while a theme is connected --
  const [frameUrl, setFrameUrl] = useState(null);
  useEffect(() => {
    if (!state?.connected) {
      setFrameUrl(null);
      return;
    }
    let cancelled = false;
    const tick = () => {
      if (cancelled) return;
      setFrameUrl(`/frame.jpg?t=${Date.now()}`);
    };
    tick();
    const id = setInterval(tick, FRAME_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [state?.connected]);

  const runAction = useCallback(async (fn) => {
    setBusy(true);
    setActionError(null);
    try {
      await fn();
    } catch (e) {
      setActionError(e.message);
    } finally {
      setBusy(false);
    }
  }, []);

  // Start doubles as "switch": calling it while a different theme is
  // already running just live-switches to the selected one instead of
  // erroring -- the backend reuses the existing panel connection
  // rather than reconnecting (see screen_engine.py). No need to Stop
  // first any more, so the theme picker and this button are never
  // locked while something's running.
  const handleStart = () => runAction(() => api.start(theme));
  const handleStop = () => runAction(() => api.stop());
  // Apply restarts whatever theme is CURRENTLY running with the
  // latest saved settings (port, and anything theme-specific) -- it
  // does not switch to a different theme (use the picker + Start for
  // that). Also connection-preserving under the hood, same as a
  // switch.
  const handleApply = () => runAction(() => api.apply());

  const handleSaveConfig = () =>
    runAction(async () => {
      const saved = await api.updateConfig({ port: portDraft || null });
      setConfig(saved);
    });

  // Brightness is applied live (see api.setBrightness's docstring) --
  // no Save button needed for it, just a short debounce on drag.
  const handleBrightnessChange = (value) => {
    setBrightnessDraft(value);
    if (brightnessTimer.current) clearTimeout(brightnessTimer.current);
    brightnessTimer.current = setTimeout(() => {
      api.setBrightness(Number(value)).catch((e) => setActionError(e.message));
    }, BRIGHTNESS_DEBOUNCE_MS);
  };

  // Video/Webpage settings -- ROADMAP.md Phase 3. Same shape app.py's
  // own _save_current_config() persists (see its "video"/"webpage"
  // dict comments): path/fps as a string or null, url/interval as
  // strings, reload_every as a string or null. theme_kwargs.py already
  // parses these straight out of app_config.json (it's what the
  // headless controller was built to read from Phase 2a onward), so
  // nothing on the backend needed to change for this -- these just
  // fill in the two settings forms Phase 2b's minimal shell skipped.
  const handleSaveVideo = () =>
    runAction(async () => {
      setSettingsSaved(null);
      const saved = await api.updateConfig({
        video: {
          path: videoDraft.path.trim() || null,
          loop: videoDraft.loop,
          bw: videoDraft.bw,
          audio: videoDraft.audio,
          fps: videoDraft.fps.trim() || null,
        },
      });
      setConfig(saved);
      setSettingsSaved("Video settings saved -- takes effect on the next Start/Apply.");
    });

  const handleSaveWebpage = () =>
    runAction(async () => {
      setSettingsSaved(null);
      const saved = await api.updateConfig({
        webpage: {
          url: webpageDraft.url.trim(),
          interval: webpageDraft.interval.trim() || "0.1",
          reload_every: webpageDraft.reloadEvery.trim() || null,
        },
      });
      setConfig(saved);
      setSettingsSaved("Webpage settings saved -- takes effect on the next Start/Apply.");
    });

  const handleToggleStartup = (enabled) =>
    runAction(async () => {
      setSystem(await api.setStartup(enabled));
    });

  const handleCreateShortcut = () =>
    runAction(async () => {
      setShortcutMsg(null);
      const { path } = await api.createShortcut();
      setShortcutMsg(`Created: ${path}`);
    });

  const running = !!state?.worker_alive;

  return (
    <div className="app">
      <header>
        <h1>Hongtai Screen</h1>
        <span className={`dot ${state?.connected ? "dot-ok" : "dot-off"}`} />
        <span className="status-text">
          {stateError
            ? `backend unreachable: ${stateError}`
            : state?.connected
            ? `connected${state.screen_info ? ` -- ${state.screen_info.model}` : ""}`
            : "no screen connected"}
        </span>
      </header>

      <section className="panel">
        <h2>Preview</h2>
        <div className="preview-box">
          {frameUrl ? (
            <img className="preview-img" src={frameUrl} alt="Live panel preview" />
          ) : (
            <div className="preview-placeholder">
              {running ? "waiting for first frame..." : "start a theme to see a preview"}
            </div>
          )}
        </div>
      </section>

      <section className="panel">
        <h2>System</h2>
        {system?.startup_supported === false ? (
          <p className="hint">
            Launch-at-startup and desktop shortcuts are Windows-only.
          </p>
        ) : (
          <>
            <div className="row">
              <label className="row-inline">
                <input
                  type="checkbox"
                  checked={!!system?.startup_enabled}
                  disabled={busy || !system}
                  onChange={(e) => handleToggleStartup(e.target.checked)}
                />
                Launch at Windows startup
              </label>
              <button onClick={handleCreateShortcut} disabled={busy}>
                Create Desktop Shortcut
              </button>
            </div>
            {shortcutMsg && <p className="hint">{shortcutMsg}</p>}
          </>
        )}
        {systemError && <p className="error">{systemError}</p>}
      </section>

      <section className="panel controls">
        <h2>Controls</h2>
        <div className="row">
          <label>
            Theme
            <select
              value={theme}
              onChange={(e) => setTheme(e.target.value)}
              disabled={busy}
            >
              {api.THEMES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={handleStart}
            disabled={busy}
            title={running ? "Switch live to the selected theme -- no reconnect" : undefined}
          >
            {running ? "Switch" : "Start"}
          </button>
          <button onClick={handleStop} disabled={busy || !running}>
            Stop
          </button>
          <button onClick={handleApply} disabled={busy || !running} title="Restart the running theme with the latest saved settings">
            Apply (restart)
          </button>
        </div>
        {state?.running_theme && (
          <p className="hint">Running: {state.running_theme}</p>
        )}
        {actionError && <p className="error">{actionError}</p>}
      </section>

      {theme === "video" && (
        <section className="panel">
          <h2>Video settings</h2>
          <div className="row">
            <label className="grow">
              Video file (full path)
              <input
                type="text"
                value={videoDraft.path}
                onChange={(e) => setVideoDraft({ ...videoDraft, path: e.target.value })}
                placeholder="C:\path\to\video.mp4"
              />
            </label>
          </div>
          <div className="row">
            <label className="row-inline">
              <input
                type="checkbox"
                checked={videoDraft.loop}
                onChange={(e) => setVideoDraft({ ...videoDraft, loop: e.target.checked })}
              />
              Loop when it ends
            </label>
            <label className="row-inline">
              <input
                type="checkbox"
                checked={videoDraft.bw}
                onChange={(e) => setVideoDraft({ ...videoDraft, bw: e.target.checked })}
              />
              Force black &amp; white
            </label>
            <label className="row-inline">
              <input
                type="checkbox"
                checked={videoDraft.audio}
                onChange={(e) => setVideoDraft({ ...videoDraft, audio: e.target.checked })}
              />
              Also play audio (needs ffmpeg + pygame)
            </label>
          </div>
          <div className="row">
            <label>
              FPS override (blank = the video's own rate)
              <input
                type="text"
                value={videoDraft.fps}
                onChange={(e) => setVideoDraft({ ...videoDraft, fps: e.target.value })}
                placeholder="auto"
                style={{ width: "6em" }}
              />
            </label>
            <button onClick={handleSaveVideo} disabled={busy}>
              Save
            </button>
          </div>
          <p className="hint">No video is bundled with this app -- point it at any file on this machine.</p>
        </section>
      )}

      {theme === "webpage" && (
        <section className="panel">
          <h2>Webpage settings</h2>
          <div className="row">
            <label className="grow">
              URL
              <input
                type="text"
                value={webpageDraft.url}
                onChange={(e) => setWebpageDraft({ ...webpageDraft, url: e.target.value })}
                placeholder="https://..."
              />
            </label>
          </div>
          <div className="row">
            <label>
              Screenshot interval (seconds)
              <input
                type="text"
                value={webpageDraft.interval}
                onChange={(e) => setWebpageDraft({ ...webpageDraft, interval: e.target.value })}
                style={{ width: "6em" }}
              />
            </label>
            <label>
              Full reload every N seconds (blank = never)
              <input
                type="text"
                value={webpageDraft.reloadEvery}
                onChange={(e) => setWebpageDraft({ ...webpageDraft, reloadEvery: e.target.value })}
                placeholder="never"
                style={{ width: "6em" }}
              />
            </label>
            <button onClick={handleSaveWebpage} disabled={busy}>
              Save
            </button>
          </div>
          <p className="hint">
            Needs Playwright on the backend (pip install playwright, then playwright
            install chromium) -- best kept simple and landscape.
          </p>
        </section>
      )}

      {theme === "clock" && (
        <section className="panel">
          <h2>Clock settings</h2>
          <p className="hint">A live clock with CPU/RAM bars -- no settings beyond port and brightness below.</p>
        </section>
      )}

      {theme === "dashboard" && (
        <DashboardCanvas frameUrl={frameUrl} connected={!!state?.connected} />
      )}

      {settingsSaved && <p className="hint settings-saved">{settingsSaved}</p>}

      <section className="panel">
        <h2>Config</h2>
        <div className="row">
          <label className="grow">
            Port (blank = auto-detect)
            <input
              type="text"
              value={portDraft}
              onChange={(e) => setPortDraft(e.target.value)}
              placeholder="auto-detect"
            />
          </label>
        </div>
        <div className="row">
          <label className="grow">
            Brightness: {brightnessDraft}
            <input
              type="range"
              min="0"
              max="100"
              value={brightnessDraft}
              onChange={(e) => handleBrightnessChange(e.target.value)}
            />
          </label>
        </div>
        <p className="hint">
          Brightness applies immediately, running or not. Port needs
          Save, and takes effect on the next Start/Apply.
        </p>
      </section>

      <section className="panel">
        <h2>Log</h2>
        <div className="log-box" ref={logBoxRef}>
          {logs.length === 0 ? (
            <div className="log-placeholder">(no log lines yet)</div>
          ) : (
            logs.map((line, i) => <div key={i}>{line}</div>)
          )}
        </div>
      </section>
    </div>
  );
}
