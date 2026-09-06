import React, { useCallback, useEffect, useRef, useState } from "react";
import * as api from "./api.js";

const STATE_POLL_MS = 1500;
const FRAME_POLL_MS = 400; // control_server.py serves one JPEG per
                            // request (no multipart stream), so the
                            // "live" preview is really a fast poll --
                            // matches what the old web-mirror page did.

export default function App() {
  const [state, setState] = useState(null);
  const [stateError, setStateError] = useState(null);
  const [config, setConfig] = useState(null);
  const [portDraft, setPortDraft] = useState("");
  const [brightnessDraft, setBrightnessDraft] = useState(90);
  const [theme, setTheme] = useState("clock");
  const [logs, setLogs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  const logBoxRef = useRef(null);

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
  const handleApply = () => runAction(() => api.apply());

  const handleSaveConfig = () =>
    runAction(async () => {
      const patch = { port: portDraft || null, brightness: Number(brightnessDraft) };
      const saved = await api.updateConfig(patch);
      setConfig(saved);
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
            <select value={theme} onChange={(e) => setTheme(e.target.value)} disabled={busy}>
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
          <button onClick={handleApply} disabled={busy || !running}>
            Apply
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
              onChange={(e) => setBrightnessDraft(e.target.value)}
            />
          </label>
          <button onClick={handleSaveConfig} disabled={busy}>
            Save
          </button>
        </div>
        <p className="hint">
          Saving takes effect on the next Start/Apply, same as editing
          app_config.json directly.
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
