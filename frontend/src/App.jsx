import React, { useCallback, useEffect, useRef, useState } from "react";
import * as api from "./api.js";

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

  const handleStart = () => runAction(() => api.start(theme));
  const handleStop = () => runAction(() => api.stop());
  // Apply restarts whatever theme is CURRENTLY running with the
  // latest saved settings (port, and anything theme-specific) -- it
  // does not switch to a different theme. That's not a limitation of
  // this button specifically: app.py's own "Apply (restart)" button
  // works the same way, which is also why the theme picker below is
  // locked while something's running -- Stop first to pick a
  // different one, same as the old app's tabs being locked mid-run.
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

      <section className="panel controls">
        <h2>Controls</h2>
        <div className="row">
          <label>
            Theme
            <select
              value={theme}
              onChange={(e) => setTheme(e.target.value)}
              disabled={busy || running}
              title={running ? "Stop the running theme to pick a different one" : undefined}
            >
              {api.THEMES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <button onClick={handleStart} disabled={busy || running}>
            Start
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
