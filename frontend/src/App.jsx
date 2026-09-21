import React, { useCallback, useEffect, useRef, useState } from "react";
import * as api from "./api.js";
import DashboardCanvas from "./DashboardCanvas.jsx";
import Collapsible from "./Collapsible.jsx";

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
  const [portsList, setPortsList] = useState([]);
  const [autoDetectValue, setAutoDetectValue] = useState(null);
  const [portsStatus, setPortsStatus] = useState(null);
  const [portsError, setPortsError] = useState(null);
  const [brightnessDraft, setBrightnessDraft] = useState(90);
  const [theme, setTheme] = useState("clock");
  const [logs, setLogs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [systemError, setSystemError] = useState(null);
  const [shortcutMsg, setShortcutMsg] = useState(null);
  const [relaunchMsg, setRelaunchMsg] = useState(null);
  const [videoDraft, setVideoDraft] = useState({ path: "", loop: true, bw: false, audio: false, fps: "" });
  const [webpageDraft, setWebpageDraft] = useState({ url: "", interval: "0.1", reloadEvery: "" });
  const [settingsSaved, setSettingsSaved] = useState(null);
  const [copyLogsMsg, setCopyLogsMsg] = useState(null);
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

  // -- panel port: the one setting everything else depends on --------
  // Scans right away on load (so there's already something useful in
  // the dropdown before anyone touches the "Detect screens" button),
  // and again whenever that button is clicked (e.g. after plugging the
  // panel in). If nothing's been picked yet and the scan finds exactly
  // one candidate, it's the obvious choice -- select and save it
  // automatically rather than making that a mandatory extra click.
  const detectPorts = useCallback(() => {
    setPortsError(null);
    return api.listPorts().then(
      ({ ports, auto_detect }) => {
        setPortsList(ports);
        setAutoDetectValue(auto_detect);
        if (ports.length === 0) {
          setPortsStatus("No Hongtai-family screen found -- check the USB connection, then click Detect screens again.");
        } else if (ports.length === 1) {
          setPortsStatus(`Found 1 screen on ${ports[0].device}.`);
        } else {
          setPortsStatus(`Found ${ports.length} screens -- pick the right one below.`);
        }
        return { ports, auto_detect };
      },
      (e) => {
        setPortsError(e.message);
        return { ports: [], auto_detect: null };
      }
    );
  }, []);

  useEffect(() => {
    detectPorts();
  }, [detectPorts]);

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

  const handleDetectClick = () => runAction(() => detectPorts());

  // Applies (and saves) the moment it's picked -- no separate Save step,
  // since nothing else in this app can usefully be touched before a
  // port is chosen anyway (see `portSelected` below).
  const handlePortChange = (value) =>
    runAction(async () => {
      setPortDraft(value);
      const saved = await api.updateConfig({ port: value || null });
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

  const handleToggleKeepActive = (value) =>
    runAction(async () => {
      const { keep_active_when_locked } = await api.setKeepActiveWhenLocked(value);
      setSystem((prev) => ({ ...prev, keep_active_when_locked }));
    });

  const handleCreateShortcut = () =>
    runAction(async () => {
      setShortcutMsg(null);
      const { path } = await api.createShortcut();
      setShortcutMsg(`Created: ${path}`);
    });

  const handleRelaunchElevated = () =>
    runAction(async () => {
      setRelaunchMsg(null);
      await api.relaunchElevated();
      setRelaunchMsg("Approve the prompt that just opened -- this window will close on its own.");
    });

  // Copies the log panel's own text, not a fresh fetch -- what's
  // currently on screen is exactly what someone reporting a bug wants
  // to paste, "sensors_output.txt"-style copy/paste from a terminal was
  // the whole workaround this replaces (see the CPU Temp debugging
  // session that kept running into "i can't copy the logs").
  //
  // navigator.clipboard needs a secure context; pywebview's WebView2
  // window (see ui_window.py) serves this over http://127.0.0.1, which
  // Chromium/Edge treats as secure same as localhost, so this is
  // expected to work there -- but a plain browser tab pointed at this
  // same backend over a non-localhost http:// URL would find
  // navigator.clipboard undefined, hence the execCommand("copy")
  // fallback below rather than just letting that throw.
  const handleCopyLogs = async () => {
    const text = logs.length ? logs.join("\n") : "(no log lines yet)";
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      setCopyLogsMsg(`Copied ${logs.length} log line${logs.length === 1 ? "" : "s"} to the clipboard.`);
    } catch (e) {
      setCopyLogsMsg(`Couldn't copy: ${e.message}`);
    }
  };

  // Self-clearing, same reasoning as any other one-shot status line
  // here (relaunchMsg, shortcutMsg) -- "Copied" is only useful for a
  // few seconds, not as a permanent fixture next to the button.
  useEffect(() => {
    if (!copyLogsMsg) return;
    const t = setTimeout(() => setCopyLogsMsg(null), 4000);
    return () => clearTimeout(t);
  }, [copyLogsMsg]);

  const running = !!state?.worker_alive;
  // Everything past this point needs to know which physical port to
  // talk to -- there's no sensible "Start" or theme setting without
  // one, so it's the first thing on the page, and nothing else here is
  // usable until it's set. `config` (not `portDraft`) is the source of
  // truth for this gate: portDraft changes the instant the dropdown is
  // touched, but handlePortChange saves it immediately too (no separate
  // Save step -- see its own comment), so the two are never out of sync
  // for more than one request.
  const portSelected = !!config?.port;

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

      {/* `actionError` is shared across every button that goes through
          runAction() -- Start/Stop/Apply, the Windows-startup and
          keep-active-when-locked toggles, desktop shortcut creation,
          every dashboard action -- not just the ones in the Controls
          section below. It used to be rendered *inside* that one
          Collapsible, which meant an error from, say, the System
          section's "Launch at Windows startup" checkbox (its own
          section, closed by default) landed in a completely different,
          easy-to-miss part of the page instead of anywhere near the
          control that actually failed -- reported as "the checkbox
          doesn't work and no error shows anywhere," when an error was
          in fact being set, just not somewhere the person was looking.
          Rendered here instead, right under the header, it's visible
          regardless of which section below happens to be open. */}
      {actionError && <p className="error app-error">{actionError}</p>}

      {/* Full-width rows, top to bottom, per the layout the user asked
          for directly: controls/panel-select on top, the selected
          theme's own config next to the live preview right below that
          (the one place two things genuinely need to sit side by
          side), then brightness, system, and the log each getting
          their own full-width row rather than being crammed into a
          narrow sidebar column. No more left/right page columns --
          that layout kept the app-level settings and the live preview/
          config visually split apart into two independent-height
          columns, which is what produced the empty gap under the
          shorter column previously. */}
      <Collapsible id="controls" title="Controls -- panel &amp; theme" defaultOpen={true}>
        <p className="hint">
          Pick which serial port your screen is connected on -- everything else on this
          page needs this set first.
        </p>
        <div className="row">
          <label className="grow">
            Port
            <select value={portDraft} onChange={(e) => handlePortChange(e.target.value)} disabled={busy}>
              <option value="" disabled>
                {portsList.length || autoDetectValue ? "Select a port…" : "Click Detect screens ->"}
              </option>
              {autoDetectValue && (
                <option value={autoDetectValue}>Auto-detect (only works with exactly one screen plugged in)</option>
              )}
              {portsList.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.device} -- {p.description || "USB serial device"}
                </option>
              ))}
            </select>
          </label>
          <button onClick={handleDetectClick} disabled={busy}>
            Detect screens
          </button>
        </div>
        {portsStatus && <p className="hint">{portsStatus}</p>}
        {portsError && <p className="error">Couldn't scan for screens: {portsError}</p>}
        {!portSelected && (
          <p className="error">
            No port selected -- the rest of this app stays disabled until you pick one above.
          </p>
        )}

        {portSelected && (
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
        )}
        {state?.running_theme && <p className="hint">Running: {state.running_theme}</p>}
      </Collapsible>

      {/* Selected panel's own config next to the live preview -- side
          by side, not stacked, since these two are what's actually
          being looked at and worked on together while a theme runs.
          Dashboard is the one exception: DashboardCanvas already draws
          the live frame inside its own canvas box (see its "It's
          overlaid on the panel's live frame too" hint below), so a
          second, separate Preview box next to it would just be the
          same image polled and shown twice -- it's skipped there and
          DashboardCanvas gets the full row's width instead, where it
          does its own side-by-side split of canvas vs. element list/
          properties (see DashboardCanvas.jsx). */}
      <div className="config-and-preview">
        <div className="config-pane">
          {portSelected && theme === "video" && (
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

          {portSelected && theme === "webpage" && (
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

          {portSelected && theme === "clock" && (
            <section className="panel">
              <h2>Clock settings</h2>
              <p className="hint">A live clock with CPU/RAM bars -- no settings beyond port and brightness.</p>
            </section>
          )}

          {portSelected && theme === "dashboard" && (
            <DashboardCanvas frameUrl={frameUrl} connected={!!state?.connected}
                              dashboardRunning={!!state?.worker_alive && state?.running_theme === "Dashboard"} />
          )}
        </div>

        {theme !== "dashboard" && (
          <div className="preview-pane">
            <Collapsible id="preview" title="Preview" defaultOpen={true}>
              <div className="preview-box">
                {frameUrl ? (
                  <img className="preview-img" src={frameUrl} alt="Live panel preview" />
                ) : (
                  <div className="preview-placeholder">
                    {running ? "waiting for first frame..." : "start a theme to see a preview"}
                  </div>
                )}
              </div>
            </Collapsible>
          </div>
        )}
      </div>

      {settingsSaved && <p className="hint settings-saved">{settingsSaved}</p>}

      <Collapsible id="brightness" title="Brightness" defaultOpen={true}>
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
        <p className="hint">Applies immediately, running or not.</p>
      </Collapsible>

      <Collapsible id="system" title="System" defaultOpen={false}>
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
        <div className="row">
          <label className="row-inline">
            <input
              type="checkbox"
              checked={!!system?.keep_active_when_locked}
              disabled={busy || !system || system?.keep_active_supported === false}
              onChange={(e) => handleToggleKeepActive(e.target.checked)}
            />
            Keep the panel updating while Windows is locked
          </label>
          {system?.keep_active_supported === false && (
            <span className="hint">(Windows only)</span>
          )}
        </div>
        {system?.platform === "win32" && system?.elevated === false && (
          <div className="row">
            <p className="hint">
              CPU Temp reads "--" without Administrator (its sensor driver needs
              it) -- restart elevated to fix it.
            </p>
            <button onClick={handleRelaunchElevated} disabled={busy}>
              Restart as Administrator
            </button>
          </div>
        )}
        {relaunchMsg && <p className="hint">{relaunchMsg}</p>}
        {systemError && <p className="error">{systemError}</p>}
      </Collapsible>

      <Collapsible id="log" title="Log" defaultOpen={false}>
        <div className="row">
          <button type="button" onClick={handleCopyLogs} disabled={logs.length === 0}>
            Copy logs
          </button>
          {copyLogsMsg && <p className="hint">{copyLogsMsg}</p>}
        </div>
        <div className="log-box" ref={logBoxRef}>
          {logs.length === 0 ? (
            <div className="log-placeholder">(no log lines yet)</div>
          ) : (
            logs.map((line, i) => <div key={i}>{line}</div>)
          )}
        </div>
      </Collapsible>
    </div>
  );
}
