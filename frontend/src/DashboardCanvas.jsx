import React, { useCallback, useEffect, useRef, useState } from "react";
import * as api from "./api.js";

// The dashboard design canvas (ROADMAP.md Phase 5) -- drag/resize gauge
// elements over the live panel frame, edit their stat/color/opacity in a
// property panel, undo/redo, and save the result (or named presets of
// it) back to the backend. Built on top of Phase 4's element list
// (dashboard_theme.py's build_static_background()/render_frame()) --
// every element here is exactly the {id, type, stat, x, y, radius,
// rotation, color, opacity, z} shape that already round-trips through
// config, so there's no separate "canvas format" to convert to/from.
//
// Reference size matches dashboard_theme.py's REFERENCE_WIDTH/HEIGHT --
// x/y/radius are stored as fractions (of width/height/min(width,height))
// precisely so they scale to any panel resolution, but this canvas just
// needs *a* concrete size to draw an SVG viewBox in, and 960x480 is this
// panel's real resolution.
const REF_W = 960;
const REF_H = 480;

const ACCENT_CPU = "rgb(0, 220, 255)";
const ACCENT_GPU = "rgb(235, 45, 225)";

// Rotation is deliberately not exposed here -- dashboard_theme.py stores
// and migrates it but doesn't render it yet (see ROADMAP.md Phase 4's
// notes): a rotate handle in this canvas would visibly do nothing,
// which is worse than not offering it. It'll get a control once
// rendering support lands.

const SNAP_THRESHOLD = 0.018; // fraction-of-canvas distance to snap at
const MIN_RADIUS = 0.02;
const MAX_RADIUS = 0.45;

function rgbToHex([r, g, b]) {
  return "#" + [r, g, b].map((c) => c.toString(16).padStart(2, "0")).join("");
}

function hexToRgb(hex) {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!m) return [255, 255, 255];
  return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)];
}

function accentFor(el) {
  if (el.color) return `rgb(${el.color[0]}, ${el.color[1]}, ${el.color[2]})`;
  return el.x < 0.5 ? ACCENT_CPU : ACCENT_GPU;
}

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

function makeId(existing) {
  let n = existing.length + 1;
  while (existing.some((el) => el.id === `gauge_${n}`)) n += 1;
  return `gauge_${n}`;
}

export default function DashboardCanvas({ frameUrl, connected }) {
  const [meta, setMeta] = useState(null);
  const [elements, setElements] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [presetName, setPresetName] = useState("");
  const [presetToLoad, setPresetToLoad] = useState("");
  const [guides, setGuides] = useState({ x: null, y: null });
  const [bgDraft, setBgDraft] = useState(null);
  const [bgStatus, setBgStatus] = useState(null);
  const [bgError, setBgError] = useState(null);

  const historyRef = useRef([]);
  const futureRef = useRef([]);
  const dragRef = useRef(null); // {id, mode: 'move'|'resize', beforeElements}
  const svgRef = useRef(null);

  const load = useCallback(() => {
    setError(null);
    api.getDashboardMeta().then(
      (m) => {
        setMeta(m);
        setElements(m.elements);
        setBgDraft(m.background);
        historyRef.current = [];
        futureRef.current = [];
        setSelectedId(null);
      },
      (e) => setError(e.message)
    );
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const commit = useCallback((next) => {
    setElements((prev) => {
      historyRef.current = [...historyRef.current, prev];
      if (historyRef.current.length > 100) historyRef.current.shift();
      return next;
    });
    futureRef.current = [];
  }, []);

  const undo = useCallback(() => {
    setElements((prev) => {
      const h = historyRef.current;
      if (h.length === 0) return prev;
      const previous = h[h.length - 1];
      historyRef.current = h.slice(0, -1);
      futureRef.current = [...futureRef.current, prev];
      return previous;
    });
  }, []);

  const redo = useCallback(() => {
    setElements((prev) => {
      const f = futureRef.current;
      if (f.length === 0) return prev;
      const next = f[f.length - 1];
      futureRef.current = f.slice(0, -1);
      historyRef.current = [...historyRef.current, prev];
      return next;
    });
  }, []);

  // Keyboard undo/redo -- only while this panel is mounted (the
  // Dashboard tab is selected), same scoping as everything else here.
  useEffect(() => {
    const onKey = (e) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      const key = e.key.toLowerCase();
      if (key === "z" && !e.shiftKey) {
        e.preventDefault();
        undo();
      } else if (key === "y" || (key === "z" && e.shiftKey)) {
        e.preventDefault();
        redo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo]);

  const pointerToFraction = (e) => {
    const svg = svgRef.current;
    const rect = svg.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    return { x: clamp(x, 0, 1), y: clamp(y, 0, 1) };
  };

  const onPointerDownGauge = (el) => (e) => {
    e.stopPropagation();
    e.target.setPointerCapture(e.pointerId);
    setSelectedId(el.id);
    dragRef.current = { id: el.id, mode: "move", beforeElements: elements };
  };

  const onPointerDownHandle = (el) => (e) => {
    e.stopPropagation();
    e.target.setPointerCapture(e.pointerId);
    setSelectedId(el.id);
    dragRef.current = { id: el.id, mode: "resize", beforeElements: elements };
  };

  const onPointerMove = (e) => {
    const drag = dragRef.current;
    if (!drag) return;
    const { x: px, y: py } = pointerToFraction(e);
    setElements((prev) => {
      const el = prev.find((it) => it.id === drag.id);
      if (!el) return prev;
      if (drag.mode === "move") {
        let nx = px;
        let ny = py;
        const others = prev.filter((it) => it.id !== drag.id);
        let snapX = null;
        let snapY = null;
        const xCandidates = [0.5, ...others.map((o) => o.x)];
        const yCandidates = [0.5, ...others.map((o) => o.y)];
        for (const c of xCandidates) {
          if (Math.abs(nx - c) < SNAP_THRESHOLD) {
            nx = c;
            snapX = c;
            break;
          }
        }
        for (const c of yCandidates) {
          if (Math.abs(ny - c) < SNAP_THRESHOLD) {
            ny = c;
            snapY = c;
            break;
          }
        }
        setGuides({ x: snapX, y: snapY });
        return prev.map((it) => (it.id === drag.id ? { ...it, x: nx, y: ny } : it));
      }
      // resize: radius (a fraction of min(REF_W, REF_H), matching how
      // dashboard_theme.py resolves it) from the pixel distance between
      // the element's center and the pointer -- computed in pixel space
      // first since x/y and radius are fractions of different bases
      // (width vs. min(width, height)).
      const dxPx = px * REF_W - el.x * REF_W;
      const dyPx = py * REF_H - el.y * REF_H;
      const distPx = Math.sqrt(dxPx * dxPx + dyPx * dyPx);
      const radius = clamp(distPx / Math.min(REF_W, REF_H), MIN_RADIUS, MAX_RADIUS);
      return prev.map((it) => (it.id === drag.id ? { ...it, radius } : it));
    });
  };

  const endDrag = () => {
    const drag = dragRef.current;
    if (!drag) return;
    dragRef.current = null;
    setGuides({ x: null, y: null });
    setElements((current) => {
      historyRef.current = [...historyRef.current, drag.beforeElements];
      if (historyRef.current.length > 100) historyRef.current.shift();
      futureRef.current = [];
      return current;
    });
  };

  const updateSelected = (patch) => {
    if (!selectedId || !elements) return;
    commit(elements.map((el) => (el.id === selectedId ? { ...el, ...patch } : el)));
  };

  const addGauge = () => {
    if (!elements || !meta) return;
    const statKeys = Object.keys(meta.stats);
    const used = new Set(elements.map((el) => el.stat));
    const stat = statKeys.find((k) => !used.has(k)) || statKeys[0];
    const maxZ = elements.reduce((m, el) => Math.max(m, el.z ?? 0), -1);
    const el = {
      id: makeId(elements), type: "gauge", stat, x: 0.5, y: 0.5, radius: 0.09,
      rotation: 0, color: null, opacity: 1.0, z: maxZ + 1,
    };
    commit([...elements, el]);
    setSelectedId(el.id);
  };

  const deleteSelected = () => {
    if (!selectedId || !elements) return;
    commit(elements.filter((el) => el.id !== selectedId));
    setSelectedId(null);
  };

  const bringToFront = () => {
    if (!selectedId || !elements) return;
    const maxZ = elements.reduce((m, el) => Math.max(m, el.z ?? 0), -1);
    updateSelected({ z: maxZ + 1 });
  };

  const sendToBack = () => {
    if (!selectedId || !elements) return;
    const minZ = elements.reduce((m, el) => Math.min(m, el.z ?? 0), 0);
    updateSelected({ z: minZ - 1 });
  };

  const resetToDefaults = () => {
    if (!meta) return;
    commit(meta.defaults);
    setSelectedId(null);
  };

  const saveLayout = () =>
    api.saveDashboardElements(elements).then(
      () => setStatus("Layout saved -- takes effect on the next Start/Apply."),
      (e) => setError(e.message)
    );

  const updateBgDraft = (patch) => {
    setBgStatus(null);
    setBgDraft((prev) => ({ ...prev, ...patch }));
  };

  const saveBackground = () => {
    if (!bgDraft) return;
    setBgError(null);
    api.saveDashboardBackground(bgDraft).then(
      (bg) => {
        setBgDraft(bg);
        setBgStatus("Background saved -- takes effect on the next Start/Apply.");
      },
      (e) => setBgError(e.message)
    );
  };

  const saveAsPreset = () => {
    const name = presetName.trim();
    if (!name) return;
    api.saveDashboardPreset(name, elements).then(
      (r) => {
        setMeta((m) => ({ ...m, presets: r.presets }));
        setPresetName("");
        setStatus(`Saved preset "${name}".`);
      },
      (e) => setError(e.message)
    );
  };

  const loadPreset = () => {
    if (!presetToLoad || !meta?.presets?.[presetToLoad]) return;
    commit(meta.presets[presetToLoad]);
    setSelectedId(null);
    setStatus(`Loaded preset "${presetToLoad}".`);
  };

  const deletePreset = () => {
    if (!presetToLoad) return;
    api.deleteDashboardPreset(presetToLoad).then(
      (r) => {
        setMeta((m) => ({ ...m, presets: r.presets }));
        setPresetToLoad("");
      },
      (e) => setError(e.message)
    );
  };

  if (!elements || !meta) {
    return (
      <section className="panel">
        <h2>Dashboard layout</h2>
        {error ? <p className="error">{error}</p> : <p className="hint">Loading layout…</p>}
      </section>
    );
  }

  const selected = elements.find((el) => el.id === selectedId) || null;
  const ordered = [...elements].sort((a, b) => (a.z ?? 0) - (b.z ?? 0));

  return (
    <section className="panel">
      <h2>Dashboard layout</h2>
      <p className="hint">
        Drag a gauge to move it, drag its bottom-right handle to resize, click to select.
        {connected ? " Shown over the panel's live frame." : " Start the Dashboard to see it over the live frame."}
      </p>

      <div className="canvas-toolbar">
        <button onClick={addGauge}>+ Add gauge</button>
        <button onClick={undo} disabled={historyRef.current.length === 0}>Undo</button>
        <button onClick={redo} disabled={futureRef.current.length === 0}>Redo</button>
        <button onClick={resetToDefaults}>Reset to defaults</button>
        <button onClick={saveLayout}>Save layout</button>
      </div>

      <div
        className="canvas-box"
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerLeave={endDrag}
      >
        {frameUrl && connected && (
          <img className="canvas-frame" src={frameUrl} alt="Live panel frame" />
        )}
        <svg
          ref={svgRef}
          className="canvas-svg"
          viewBox={`0 0 ${REF_W} ${REF_H}`}
          onPointerDown={() => setSelectedId(null)}
        >
          {guides.x !== null && (
            <line x1={guides.x * REF_W} y1={0} x2={guides.x * REF_W} y2={REF_H} className="canvas-guide" />
          )}
          {guides.y !== null && (
            <line x1={0} y1={guides.y * REF_H} x2={REF_W} y2={guides.y * REF_H} className="canvas-guide" />
          )}
          {ordered.map((el) => {
            const cx = el.x * REF_W;
            const cy = el.y * REF_H;
            const r = el.radius * Math.min(REF_W, REF_H);
            const accent = accentFor(el);
            const isSelected = el.id === selectedId;
            const title = meta.stats[el.stat]?.title || el.stat;
            return (
              <g key={el.id}>
                <circle
                  cx={cx}
                  cy={cy}
                  r={r}
                  fill={accent}
                  fillOpacity={0.12 * (el.opacity ?? 1)}
                  stroke={accent}
                  strokeOpacity={el.opacity ?? 1}
                  strokeWidth={isSelected ? 3 : 1.5}
                  strokeDasharray={isSelected ? "6 3" : undefined}
                  onPointerDown={onPointerDownGauge(el)}
                  style={{ cursor: "move" }}
                />
                <text x={cx} y={cy} textAnchor="middle" dominantBaseline="middle"
                      fill="#fff" fontSize={Math.max(10, r * 0.28)} style={{ pointerEvents: "none" }}>
                  {title}
                </text>
                <rect
                  x={cx + r * 0.707 - 7} y={cy + r * 0.707 - 7} width={14} height={14}
                  fill={accent} stroke="#fff" strokeWidth={1}
                  onPointerDown={onPointerDownHandle(el)}
                  style={{ cursor: "nwse-resize" }}
                />
              </g>
            );
          })}
        </svg>
      </div>

      {selected && (
        <div className="canvas-props">
          <div className="row">
            <label>
              Stat
              <select value={selected.stat} onChange={(e) => updateSelected({ stat: e.target.value })}>
                {Object.entries(meta.stats).map(([key, s]) => (
                  <option key={key} value={key}>{s.label}</option>
                ))}
              </select>
            </label>
            <label>
              Opacity
              <input
                type="range" min={20} max={100}
                value={Math.round((selected.opacity ?? 1) * 100)}
                onChange={(e) => updateSelected({ opacity: Number(e.target.value) / 100 })}
              />
            </label>
          </div>
          <div className="row">
            <label className="row-inline">
              <input
                type="checkbox"
                checked={selected.color !== null}
                onChange={(e) => updateSelected({ color: e.target.checked ? hexToRgb("#ffffff") : null })}
              />
              Custom color
            </label>
            {selected.color !== null && (
              <input
                type="color"
                value={rgbToHex(selected.color)}
                onChange={(e) => updateSelected({ color: hexToRgb(e.target.value) })}
              />
            )}
            <label>
              X %
              <input type="number" min={0} max={100} style={{ width: "5em" }}
                     value={Math.round(selected.x * 100)}
                     onChange={(e) => updateSelected({ x: clamp(Number(e.target.value) / 100, 0, 1) })} />
            </label>
            <label>
              Y %
              <input type="number" min={0} max={100} style={{ width: "5em" }}
                     value={Math.round(selected.y * 100)}
                     onChange={(e) => updateSelected({ y: clamp(Number(e.target.value) / 100, 0, 1) })} />
            </label>
            <label>
              Radius %
              <input type="number" min={2} max={45} style={{ width: "5em" }}
                     value={Math.round(selected.radius * 100)}
                     onChange={(e) => updateSelected({ radius: clamp(Number(e.target.value) / 100, MIN_RADIUS, MAX_RADIUS) })} />
            </label>
          </div>
          <div className="row">
            <button onClick={bringToFront}>Bring to front</button>
            <button onClick={sendToBack}>Send to back</button>
            <button onClick={deleteSelected}>Delete</button>
          </div>
        </div>
      )}

      {bgDraft && (
        <div className="canvas-props">
          <h2>Background</h2>
          <div className="row">
            <label>
              Style
              <select
                value={bgDraft.mode}
                onChange={(e) => updateBgDraft({ mode: e.target.value })}
              >
                {Object.entries(meta.backgroundPresets).map(([key, label]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </select>
            </label>
            {bgDraft.mode !== "image" && (
              <label>
                Color scheme
                <select
                  value={bgDraft.scheme}
                  onChange={(e) => updateBgDraft({ scheme: e.target.value })}
                >
                  {Object.entries(meta.backgroundSchemes).map(([key, s]) => (
                    <option key={key} value={key}>{s.label}</option>
                  ))}
                </select>
              </label>
            )}
          </div>
          {bgDraft.mode === "image" && (
            <div className="row">
              <label className="grow">
                Image path
                <input
                  type="text"
                  value={bgDraft.image_path || ""}
                  onChange={(e) => updateBgDraft({ image_path: e.target.value })}
                  placeholder="C:\Users\you\Pictures\background.jpg"
                />
              </label>
            </div>
          )}
          <p className="hint">
            {bgDraft.mode === "image"
              ? "Full path to an image file on this PC -- falls back to the default background if it can't be opened."
              : "The color scheme tints the gradient and, for Grid/Starfield/Radial, the whole background."}
          </p>
          <div className="row">
            <button onClick={saveBackground}>Save background</button>
          </div>
          {bgStatus && <p className="hint settings-saved">{bgStatus}</p>}
          {bgError && <p className="error">{bgError}</p>}
        </div>
      )}

      <div className="row">
        <label className="grow">
          Presets
          <select value={presetToLoad} onChange={(e) => setPresetToLoad(e.target.value)}>
            <option value="">Choose a saved preset…</option>
            {Object.keys(meta.presets || {}).map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </label>
        <button onClick={loadPreset} disabled={!presetToLoad}>Load</button>
        <button onClick={deletePreset} disabled={!presetToLoad}>Delete</button>
      </div>
      <div className="row">
        <label className="grow">
          Save current layout as preset
          <input type="text" value={presetName} onChange={(e) => setPresetName(e.target.value)}
                 placeholder="e.g. Streaming layout" />
        </label>
        <button onClick={saveAsPreset} disabled={!presetName.trim()}>Save as preset</button>
      </div>

      {status && <p className="hint settings-saved">{status}</p>}
      {error && <p className="error">{error}</p>}
    </section>
  );
}
