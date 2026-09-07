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

function basename(path) {
  if (!path) return "";
  return path.split(/[\\/]/).pop();
}

function makeId(existing, prefix = "el") {
  let n = existing.length + 1;
  while (existing.some((el) => el.id === `${prefix}_${n}`)) n += 1;
  return `${prefix}_${n}`;
}

// Default field shapes for each element type ROADMAP.md Phase 6 adds
// (gauge -- and its optional gradient `color2` -- already existed).
// Every type shares `id`/`type`/`x`/`y`/`z`/`opacity`; the rest is
// exactly the shape dashboard_theme.py's element handlers expect, so
// there's nothing to translate on save -- same "no separate canvas
// format" reasoning as the gauge elements already worked this way.
function makeElement(type, elements, meta) {
  const maxZ = elements.reduce((m, el) => Math.max(m, el.z ?? 0), -1);
  const base = { x: 0.5, y: 0.5, z: maxZ + 1, opacity: 1.0 };
  const statKeys = Object.keys(meta.stats);
  if (type === "gauge") {
    const used = new Set(elements.filter((e) => e.type === "gauge").map((e) => e.stat));
    const stat = statKeys.find((k) => !used.has(k)) || statKeys[0];
    return { id: makeId(elements, "gauge"), type: "gauge", stat, radius: 0.09,
             rotation: 0, color: null, color2: null, ...base };
  }
  if (type === "text") {
    return { id: makeId(elements, "text"), type: "text", text: "Label",
             font_size: 0.05, color: [255, 255, 255], align: "center", ...base };
  }
  if (type === "graph") {
    return { id: makeId(elements, "graph"), type: "graph", stat: statKeys[0],
             style: "line", color: [0, 220, 255], width: 0.22, height: 0.14,
             history_seconds: 20, ...base };
  }
  if (type === "image") {
    // width/height here are just a placeholder box until a picture's
    // actually picked -- uploadImage() below replaces them with a box
    // that matches the picked image's own aspect ratio, since a
    // freshly-added element has no image yet to size itself from.
    return { id: makeId(elements, "image"), type: "image", image_path: "",
             width: 0.15, height: 0.15, fit: "contain", ...base };
  }
  if (type === "media") {
    // The Spotify now-playing widget (album art + track/artist +
    // progress bar) as a movable/resizable element -- see
    // dashboard_theme.py's _draw_media_element(). Generously sized by
    // default since it has to fit album art plus two lines of text
    // plus a progress bar stacked vertically. show_art/show_name/
    // show_time let each piece be switched off independently.
    return { id: makeId(elements, "media"), type: "media", width: 0.32, height: 0.52,
             show_art: true, show_name: true, show_time: true, ...base };
  }
  if (type === "clock") {
    return { id: makeId(elements, "clock"), type: "clock",
             font_size: 0.05, color: [235, 235, 242], show_seconds: true, ...base };
  }
  return null;
}

// Reads a just-picked File's own pixel dimensions in the browser (no
// upload round-trip needed for this) -- used so a new image element
// starts out matching the picture's own aspect ratio instead of
// whatever generic default box was there before. Resolves null (never
// rejects) on anything that isn't decodable as an image, so a caller
// can just skip the auto-sizing rather than having to handle an error.
function readImageDimensions(file) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve({ width: img.naturalWidth, height: img.naturalHeight });
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(null);
    };
    img.src = url;
  });
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
  const [npDraft, setNpDraft] = useState(null);
  const [npStatus, setNpStatus] = useState(null);
  const [npError, setNpError] = useState(null);
  const [mcDraft, setMcDraft] = useState(null);
  const [mcStatus, setMcStatus] = useState(null);
  const [mcError, setMcError] = useState(null);
  const [uploadingId, setUploadingId] = useState(null); // "background" | "nowPlaying" | an element id, or null

  const historyRef = useRef([]);
  const futureRef = useRef([]);
  // What's currently saved on the backend, so the toolbar can show an
  // honest "you have unsaved changes" state instead of leaving it to
  // guesswork -- see the "Unsaved changes" hint below Save layout.
  // Reference equality is enough: commit()/undo()/redo()/load() always
  // hand back a *new* array, never mutate elements in place.
  const savedElementsRef = useRef(null);
  const dragRef = useRef(null); // {id, mode: 'move'|'resize', beforeElements}
  const svgRef = useRef(null);

  const load = useCallback(() => {
    setError(null);
    api.getDashboardMeta().then(
      (m) => {
        setMeta(m);
        setElements(m.elements);
        savedElementsRef.current = m.elements;
        setBgDraft(m.background);
        setNpDraft(m.nowPlaying);
        setMcDraft(m.middleContent);
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

  // `axis` picks which dimension(s) a given handle drags -- "both" (the
  // original corner handle, still there for a quick freeform resize),
  // "width", or "height". Only graph/image/media elements have
  // independent width/height to begin with (a gauge resizes via one
  // `radius`, text via one `font_size`), so this is a no-op for those.
  const onPointerDownHandle = (el, axis = "both") => (e) => {
    e.stopPropagation();
    e.target.setPointerCapture(e.pointerId);
    setSelectedId(el.id);
    dragRef.current = { id: el.id, mode: "resize", axis, beforeElements: elements };
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
      // resize: gauge is a circle so one radius (a fraction of
      // min(REF_W, REF_H), matching how dashboard_theme.py resolves
      // it) does it, from the pixel distance between the element's
      // center and the pointer -- computed in pixel space first since
      // x/y and radius are fractions of different bases (width vs.
      // min(width, height)). Graph/image are rectangles with their own
      // independent width/height instead, resized the same way but on
      // each axis separately; text has no box at all, so its "handle"
      // scales font_size off the vertical drag distance instead.
      const dxPx = px * REF_W - el.x * REF_W;
      const dyPx = py * REF_H - el.y * REF_H;
      if (el.type === "graph" || el.type === "image" || el.type === "media") {
        // `axis` (set by which handle was grabbed -- see
        // onPointerDownHandle) picks whether this drag touches width,
        // height, or both -- e.g. dragging the right-edge handle
        // straight up shouldn't also shrink the height.
        const axis = drag.axis || "both";
        const patch = {};
        if (axis !== "height") patch.width = clamp((Math.abs(dxPx) * 2) / REF_W, 0.04, 0.9);
        if (axis !== "width") patch.height = clamp((Math.abs(dyPx) * 2) / REF_H, 0.04, 0.9);
        return prev.map((it) => (it.id === drag.id ? { ...it, ...patch } : it));
      }
      if (el.type === "text" || el.type === "clock") {
        const font_size = clamp((Math.abs(dyPx) * 2) / REF_H, 0.02, 0.25);
        return prev.map((it) => (it.id === drag.id ? { ...it, font_size } : it));
      }
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

  const addElement = (type) => {
    if (!elements || !meta) return;
    const el = makeElement(type, elements, meta);
    if (!el) return;
    commit([...elements, el]);
    setSelectedId(el.id);
  };

  const deleteSelected = () => {
    if (!selectedId || !elements) return;
    commit(elements.filter((el) => el.id !== selectedId));
    setSelectedId(null);
  };

  const centerHorizontally = () => updateSelected({ x: 0.5 });
  const centerVertically = () => updateSelected({ y: 0.5 });

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
      () => {
        savedElementsRef.current = elements;
        setStatus("Layout saved -- takes effect on the next Start/Apply.");
      },
      (e) => setError(e.message)
    );

  // Shared by every "pick an image" field on this canvas (background,
  // now-playing placeholder, an image element) -- a browser file input
  // can only hand back the picked file's bytes, never a real
  // filesystem path, so this always goes through an actual upload:
  // the backend copies it into its own managed image folder
  // (image_store.py) and hands back that copy's path, which is what
  // actually gets saved. `uploadingId` just drives a "Uploading..."
  // label near whichever field is mid-upload.
  // `onStored` gets (path, dims) -- dims is the picked file's own
  // {width, height} in pixels (or null if it couldn't be read), read
  // client-side in parallel with the upload so the image element case
  // can size its box to match, see makeElement()'s comment.
  const uploadImage = (id, file, onStored, onError) => {
    if (!file) return;
    setUploadingId(id);
    Promise.all([api.uploadDashboardImage(file), readImageDimensions(file)]).then(
      ([r, dims]) => {
        setUploadingId(null);
        onStored(r.path, dims);
      },
      (e) => {
        setUploadingId(null);
        onError(e.message);
      }
    );
  };

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

  const updateNpDraft = (patch) => {
    setNpStatus(null);
    setNpDraft((prev) => ({ ...prev, ...patch }));
  };

  const saveNowPlaying = () => {
    if (!npDraft) return;
    setNpError(null);
    api.saveDashboardNowPlaying({
      default_art_path: npDraft.default_art_path || null,
      not_playing_message: npDraft.not_playing_message || null,
    }).then(
      (dashboardCfg) => {
        setNpDraft((prev) => ({ ...prev, default_art_path: dashboardCfg.default_art_path,
                                 not_playing_message: dashboardCfg.not_playing_message }));
        setNpStatus("Saved -- applies live, even while the dashboard is already running.");
      },
      (e) => setNpError(e.message)
    );
  };

  const updateMcDraft = (patch) => {
    setMcStatus(null);
    setMcDraft((prev) => ({ ...prev, ...patch }));
  };

  const saveMiddleContent = () => {
    if (!mcDraft) return;
    setMcError(null);
    api.saveDashboardMiddleContent({
      middle_content: mcDraft.value,
      weather_location: mcDraft.weather_location || "",
      weather_units: mcDraft.weather_units,
    }).then(
      (dashboardCfg) => {
        setMcDraft((prev) => ({ ...prev, value: dashboardCfg.middle_content || "spotify",
                                 weather_location: dashboardCfg.weather_location || "",
                                 weather_units: dashboardCfg.weather_units || "celsius" }));
        setMcStatus("Saved -- applies live, even while the dashboard is already running.");
      },
      (e) => setMcError(e.message)
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
  const dirty = elements !== savedElementsRef.current;

  return (
    <section className="panel">
      <h2>Dashboard layout</h2>
      <p className="hint">
        Drag an element to move it, click to select. A selected element with independent
        width/height (graph, image, now-playing) gets three resize handles: the one on its
        right edge changes width only, the one on its bottom edge changes height only, and
        the corner changes both. Everything below updates live in this box as you edit --
        no need to save just to see it.
        {connected ? " It's overlaid on the panel's live frame too." : " Start the Dashboard to also see it over the live frame."}
      </p>

      <div className="canvas-toolbar">
        <button onClick={() => addElement("gauge")}>+ Add gauge</button>
        <button onClick={() => addElement("text")}>+ Add text</button>
        <button onClick={() => addElement("graph")}>+ Add graph</button>
        <button onClick={() => addElement("image")}>+ Add image</button>
        <button onClick={() => addElement("media")}>+ Add now-playing</button>
        <button onClick={() => addElement("clock")}>+ Add clock</button>
        <button onClick={undo} disabled={historyRef.current.length === 0}>Undo</button>
        <button onClick={redo} disabled={futureRef.current.length === 0}>Redo</button>
        <button onClick={resetToDefaults}>Reset to defaults</button>
        <button onClick={saveLayout} className={dirty ? "btn-attention" : undefined}>
          {dirty ? "Save layout*" : "Save layout"}
        </button>
      </div>
      {dirty && (
        <p className="hint">
          * You have unsaved changes -- this preview is live, but Save layout is what keeps
          them (and Start/Apply is what pushes them to the physical panel).
        </p>
      )}

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
            const isSelected = el.id === selectedId;

            if (el.type === "text") {
              const x = el.x * REF_W;
              const y = el.y * REF_H;
              const fontSize = Math.max(8, (el.font_size ?? 0.05) * REF_H);
              const color = el.color ? `rgb(${el.color[0]}, ${el.color[1]}, ${el.color[2]})` : "#fff";
              const anchor = { left: "start", center: "middle", right: "end" }[el.align || "center"] || "middle";
              const halfW = Math.max(24, ((el.text || "").length * fontSize) / 3.2);
              return (
                <g key={el.id}>
                  {isSelected && (
                    <rect x={x - (anchor === "start" ? 4 : anchor === "end" ? halfW * 2 - 4 : halfW)}
                          y={y - fontSize * 0.8} width={halfW * 2} height={fontSize * 1.6}
                          fill="none" stroke="#ffd85e" strokeDasharray="4 3" />
                  )}
                  <text x={x} y={y} textAnchor={anchor} dominantBaseline="middle"
                        fontSize={fontSize} fill={color} opacity={el.opacity ?? 1}
                        onPointerDown={onPointerDownGauge(el)} style={{ cursor: "move", userSelect: "none" }}>
                    {el.text || "(empty text)"}
                  </text>
                  {isSelected && (
                    <rect x={x + halfW - 7} y={y + fontSize * 0.8 - 7} width={14} height={14}
                          fill="#ffd85e" stroke="#fff" strokeWidth={1}
                          onPointerDown={onPointerDownHandle(el)} style={{ cursor: "ns-resize" }} />
                  )}
                </g>
              );
            }

            if (el.type === "graph" || el.type === "image" || el.type === "media") {
              const w = (el.width ?? (el.type === "media" ? 0.32 : 0.2)) * REF_W;
              const h = (el.height ?? (el.type === "media" ? 0.52 : 0.14)) * REF_H;
              const x0 = el.x * REF_W - w / 2;
              const y0 = el.y * REF_H - h / 2;
              const accent = el.type === "graph" ? accentFor(el)
                : el.type === "media" ? ACCENT_GPU : "rgb(150, 170, 200)";
              const label = el.type === "graph" ? (meta.stats[el.stat]?.title || el.stat)
                : el.type === "media" ? "NOW PLAYING" : "PICK AN IMAGE BELOW";
              const imageUrl = el.type === "image" ? api.dashboardImageUrl(el.image_path) : null;
              const clipId = `clip_${el.id}`;
              // Mirrors dashboard_theme.py's _fit_into_box(): "contain"
              // (default) never crops, "cover" fills the box and crops
              // overflow, "stretch" ignores aspect ratio entirely --
              // same three SVG preserveAspectRatio values do the same
              // job here, so this preview matches what actually renders.
              const preserveAspectRatio =
                el.type === "image" && el.fit === "cover" ? "xMidYMid slice"
                : el.type === "image" && el.fit === "stretch" ? "none"
                : "xMidYMid meet";
              return (
                <g key={el.id}>
                  {imageUrl && (
                    <clipPath id={clipId}>
                      <rect x={x0} y={y0} width={w} height={h} rx={4} />
                    </clipPath>
                  )}
                  {imageUrl ? (
                    // The actual picked image, shown here the moment
                    // it's uploaded -- not just once Saved/Started, see
                    // uploadImage()'s comment on why this can render
                    // immediately.
                    <image href={imageUrl} x={x0} y={y0} width={w} height={h}
                           preserveAspectRatio={preserveAspectRatio} clipPath={`url(#${clipId})`}
                           opacity={el.opacity ?? 1}
                           onPointerDown={onPointerDownGauge(el)} style={{ cursor: "move" }} />
                  ) : (
                    <rect x={x0} y={y0} width={w} height={h}
                          fill={accent} fillOpacity={0.1 * (el.opacity ?? 1)}
                          stroke={accent} strokeOpacity={el.opacity ?? 1}
                          strokeWidth={isSelected ? 3 : 1.5}
                          strokeDasharray={isSelected ? "6 3" : undefined}
                          onPointerDown={onPointerDownGauge(el)} style={{ cursor: "move" }} />
                  )}
                  {imageUrl && (
                    <rect x={x0} y={y0} width={w} height={h} rx={4}
                          fill="none" stroke={isSelected ? "#ffd85e" : accent}
                          strokeOpacity={isSelected ? 1 : 0.6}
                          strokeWidth={isSelected ? 3 : 1.5}
                          strokeDasharray={isSelected ? "6 3" : undefined}
                          style={{ pointerEvents: "none" }} />
                  )}
                  {!imageUrl && (
                    <text x={x0 + w / 2} y={y0 + h / 2} textAnchor="middle" dominantBaseline="middle"
                          fill="#fff" fontSize={12} style={{ pointerEvents: "none" }}>
                      {label}
                    </text>
                  )}
                  {isSelected && (
                    <>
                      {/* Right-edge handle: width only. */}
                      <rect x={x0 + w - 5} y={y0 + h / 2 - 7} width={10} height={14} rx={2}
                            fill={accent} stroke="#fff" strokeWidth={1}
                            onPointerDown={onPointerDownHandle(el, "width")}
                            style={{ cursor: "ew-resize" }}>
                        <title>Drag to resize width only</title>
                      </rect>
                      {/* Bottom-edge handle: height only. */}
                      <rect x={x0 + w / 2 - 7} y={y0 + h - 5} width={14} height={10} rx={2}
                            fill={accent} stroke="#fff" strokeWidth={1}
                            onPointerDown={onPointerDownHandle(el, "height")}
                            style={{ cursor: "ns-resize" }}>
                        <title>Drag to resize height only</title>
                      </rect>
                      {/* Corner handle: both at once. */}
                      <rect x={x0 + w - 7} y={y0 + h - 7} width={14} height={14}
                            fill={accent} stroke="#fff" strokeWidth={1}
                            onPointerDown={onPointerDownHandle(el, "both")}
                            style={{ cursor: "nwse-resize" }}>
                        <title>Drag to resize width and height together</title>
                      </rect>
                    </>
                  )}
                </g>
              );
            }

            if (el.type === "clock") {
              const x = el.x * REF_W;
              const y = el.y * REF_H;
              const fontSize = Math.max(8, (el.font_size ?? 0.05) * REF_H);
              const color = el.color ? `rgb(${el.color[0]}, ${el.color[1]}, ${el.color[2]})` : "#fff";
              // A representative sample, not the actual current time --
              // this canvas is a layout editor, not a second clock to
              // keep in sync; what matters here is the size/position,
              // same as how a graph/gauge element shows placeholder
              // values rather than live stats.
              const sample = el.show_seconds ?? true ? "12:34:56" : "12:34";
              const halfW = Math.max(24, (sample.length * fontSize) / 3.4);
              return (
                <g key={el.id}>
                  {isSelected && (
                    <rect x={x - halfW} y={y - fontSize * 0.7} width={halfW * 2} height={fontSize * 1.4}
                          fill="none" stroke="#ffd85e" strokeDasharray="4 3" />
                  )}
                  <text x={x} y={y} textAnchor="middle" dominantBaseline="middle"
                        fontSize={fontSize} fill={color} opacity={el.opacity ?? 1}
                        onPointerDown={onPointerDownGauge(el)} style={{ cursor: "move", userSelect: "none" }}>
                    {sample}
                  </text>
                  {isSelected && (
                    <rect x={x + halfW - 7} y={y + fontSize * 0.7 - 7} width={14} height={14}
                          fill="#ffd85e" stroke="#fff" strokeWidth={1}
                          onPointerDown={onPointerDownHandle(el)} style={{ cursor: "ns-resize" }} />
                  )}
                </g>
              );
            }

            // gauge (the original element type)
            const cx = el.x * REF_W;
            const cy = el.y * REF_H;
            const r = el.radius * Math.min(REF_W, REF_H);
            const accent = accentFor(el);
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
          {selected.type === "text" && (
            <>
              <div className="row">
                <label className="grow">
                  Text
                  <input type="text" value={selected.text || ""}
                         onChange={(e) => updateSelected({ text: e.target.value })} />
                </label>
                <label>
                  Align
                  <select value={selected.align || "center"} onChange={(e) => updateSelected({ align: e.target.value })}>
                    <option value="left">Left</option>
                    <option value="center">Center</option>
                    <option value="right">Right</option>
                  </select>
                </label>
              </div>
              <div className="row">
                <label>
                  Color
                  <input type="color" value={rgbToHex(selected.color || [255, 255, 255])}
                         onChange={(e) => updateSelected({ color: hexToRgb(e.target.value) })} />
                </label>
                <label>
                  Font size %
                  <input type="number" min={2} max={25} style={{ width: "5em" }}
                         value={Math.round((selected.font_size ?? 0.05) * 100)}
                         onChange={(e) => updateSelected({ font_size: clamp(Number(e.target.value) / 100, 0.02, 0.25) })} />
                </label>
                <label>
                  Opacity
                  <input type="range" min={20} max={100}
                         value={Math.round((selected.opacity ?? 1) * 100)}
                         onChange={(e) => updateSelected({ opacity: Number(e.target.value) / 100 })} />
                </label>
              </div>
            </>
          )}

          {selected.type === "graph" && (
            <>
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
                  Style
                  <select value={selected.style || "line"} onChange={(e) => updateSelected({ style: e.target.value })}>
                    <option value="line">Line</option>
                    <option value="bar">Bar</option>
                  </select>
                </label>
                <label>
                  History (seconds)
                  <input type="number" min={2} max={120} style={{ width: "5em" }}
                         value={selected.history_seconds ?? 20}
                         onChange={(e) => updateSelected({ history_seconds: Math.max(2, Number(e.target.value)) })} />
                </label>
              </div>
              <div className="row">
                <label>
                  Color
                  <input type="color" value={rgbToHex(selected.color || [0, 220, 255])}
                         onChange={(e) => updateSelected({ color: hexToRgb(e.target.value) })} />
                </label>
                <label>
                  Opacity
                  <input type="range" min={20} max={100}
                         value={Math.round((selected.opacity ?? 1) * 100)}
                         onChange={(e) => updateSelected({ opacity: Number(e.target.value) / 100 })} />
                </label>
              </div>
            </>
          )}

          {selected.type === "image" && (
            <div className="row">
              <label className="grow">
                Image
                <input type="file" accept="image/*"
                       onChange={(e) => uploadImage(selected.id, e.target.files[0],
                         (path, dims) => {
                           const patch = { image_path: path };
                           if (dims && dims.width && dims.height) {
                             // Box the new picture at roughly its own on-screen
                             // footprint, matching ITS aspect ratio -- not the
                             // small square default (or whatever box a
                             // previous picture left behind), so a freshly
                             // picked image doesn't start out looking
                             // squished/cropped before anyone's touched the
                             // resize handles.
                             const target = 0.28;
                             const ratio = dims.width / dims.height;
                             if (ratio >= 1) {
                               patch.width = target;
                               patch.height = clamp((target * REF_W) / ratio / REF_H, 0.02, 0.9);
                             } else {
                               patch.height = target;
                               patch.width = clamp((target * REF_H) * ratio / REF_W, 0.02, 0.9);
                             }
                           }
                           updateSelected(patch);
                         }, setError)} />
              </label>
              <label>
                Fit
                <select value={selected.fit || "contain"} onChange={(e) => updateSelected({ fit: e.target.value })}>
                  <option value="contain">Contain (show the whole image)</option>
                  <option value="cover">Cover (fill the box, may crop)</option>
                  <option value="stretch">Stretch (fill exactly, may distort)</option>
                </select>
              </label>
              <label>
                Opacity
                <input type="range" min={20} max={100}
                       value={Math.round((selected.opacity ?? 1) * 100)}
                       onChange={(e) => updateSelected({ opacity: Number(e.target.value) / 100 })} />
              </label>
              {selected.image_path && (
                <>
                  <img className="file-thumb" src={api.dashboardImageUrl(selected.image_path)} alt="" />
                  <span className="hint">{basename(selected.image_path)}</span>
                </>
              )}
              {uploadingId === selected.id && <span className="hint">Uploading…</span>}
            </div>
          )}

          {selected.type === "media" && (
            <>
              <div className="row">
                <label className="row-inline">
                  <input type="checkbox" checked={selected.show_art ?? true}
                         onChange={(e) => updateSelected({ show_art: e.target.checked })} />
                  Cover art
                </label>
                <label className="row-inline">
                  <input type="checkbox" checked={selected.show_name ?? true}
                         onChange={(e) => updateSelected({ show_name: e.target.checked })} />
                  Track/artist name
                </label>
                <label className="row-inline">
                  <input type="checkbox" checked={selected.show_time ?? true}
                         onChange={(e) => updateSelected({ show_time: e.target.checked })} />
                  Progress/time
                </label>
              </div>
              <div className="row">
                <label>
                  Opacity
                  <input type="range" min={20} max={100}
                         value={Math.round((selected.opacity ?? 1) * 100)}
                         onChange={(e) => updateSelected({ opacity: Number(e.target.value) / 100 })} />
                </label>
                <span className="hint">
                  Shows the same Spotify now-playing display as the "Middle content" section below,
                  but positioned/sized here instead of locked to the middle column. Turn off
                  whichever pieces you don't want -- e.g. just the cover art, or just the time.
                </span>
              </div>
            </>
          )}

          {selected.type === "clock" && (
            <div className="row">
              <label className="row-inline">
                <input type="checkbox" checked={selected.show_seconds ?? true}
                       onChange={(e) => updateSelected({ show_seconds: e.target.checked })} />
                Show seconds
              </label>
              <label>
                Color
                <input type="color" value={rgbToHex(selected.color || [235, 235, 242])}
                       onChange={(e) => updateSelected({ color: hexToRgb(e.target.value) })} />
              </label>
              <label>
                Font size %
                <input type="number" min={2} max={25} style={{ width: "5em" }}
                       value={Math.round((selected.font_size ?? 0.05) * 100)}
                       onChange={(e) => updateSelected({ font_size: clamp(Number(e.target.value) / 100, 0.02, 0.25) })} />
              </label>
              <label>
                Opacity
                <input type="range" min={20} max={100}
                       value={Math.round((selected.opacity ?? 1) * 100)}
                       onChange={(e) => updateSelected({ opacity: Number(e.target.value) / 100 })} />
              </label>
            </div>
          )}

          {(!selected.type || selected.type === "gauge") && (
            <>
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
                <label className="row-inline">
                  <input
                    type="checkbox"
                    checked={!!selected.color2}
                    onChange={(e) => updateSelected({ color2: e.target.checked ? hexToRgb("#ff2ee0") : null })}
                  />
                  Gradient (2nd color)
                </label>
                {selected.color2 && (
                  <input
                    type="color"
                    value={rgbToHex(selected.color2)}
                    onChange={(e) => updateSelected({ color2: hexToRgb(e.target.value) })}
                  />
                )}
              </div>
              <div className="row">
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
            </>
          )}

          {selected.type && selected.type !== "gauge" && (
            <div className="row">
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
              {(selected.type === "graph" || selected.type === "image" || selected.type === "media") && (
                <>
                  <label>
                    Width %
                    <input type="number" min={4} max={90} style={{ width: "5em" }}
                           value={Math.round((selected.width ?? (selected.type === "media" ? 0.32 : 0.2)) * 100)}
                           onChange={(e) => updateSelected({ width: clamp(Number(e.target.value) / 100, 0.04, 0.9) })} />
                  </label>
                  <label>
                    Height %
                    <input type="number" min={4} max={90} style={{ width: "5em" }}
                           value={Math.round((selected.height ?? (selected.type === "media" ? 0.52 : 0.14)) * 100)}
                           onChange={(e) => updateSelected({ height: clamp(Number(e.target.value) / 100, 0.04, 0.9) })} />
                  </label>
                </>
              )}
            </div>
          )}

          <div className="row">
            <button onClick={centerHorizontally} title="Set X to 50% -- centers it left/right">Center horizontally</button>
            <button onClick={centerVertically} title="Set Y to 50% -- centers it top/bottom">Center vertically</button>
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
                Image
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => uploadImage("background", e.target.files[0],
                    (path) => updateBgDraft({ image_path: path }), setBgError)}
                />
              </label>
              {bgDraft.image_path && (
                <>
                  <img className="file-thumb" src={api.dashboardImageUrl(bgDraft.image_path)} alt="" />
                  <span className="hint">{basename(bgDraft.image_path)}</span>
                </>
              )}
              {uploadingId === "background" && <span className="hint">Uploading…</span>}
            </div>
          )}
          <p className="hint">
            {bgDraft.mode === "image"
              ? "Pick an image on this PC -- it's copied into this app's own folder, so moving or deleting the original afterward won't break it. Falls back to the default background if none is set."
              : "The color scheme tints the gradient and, for Grid/Starfield/Radial, the whole background."}
          </p>
          <div className="row">
            <button onClick={saveBackground}>Save background</button>
          </div>
          {bgStatus && <p className="hint settings-saved">{bgStatus}</p>}
          {bgError && <p className="error">{bgError}</p>}
        </div>
      )}

      {mcDraft && (
        <div className="canvas-props">
          <h2>Middle content</h2>
          <div className="row">
            <label className="grow">
              Show
              <select value={mcDraft.value} onChange={(e) => updateMcDraft({ value: e.target.value })}>
                {Object.entries(mcDraft.options).map(([key, label]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </select>
            </label>
          </div>
          {mcDraft.value === "weather" && (
            <div className="row">
              <label className="grow">
                Location
                <input
                  type="text"
                  value={mcDraft.weather_location || ""}
                  onChange={(e) => updateMcDraft({ weather_location: e.target.value })}
                  placeholder="City, address, or lat,lon"
                />
              </label>
              <label>
                Units
                <select value={mcDraft.weather_units}
                        onChange={(e) => updateMcDraft({ weather_units: e.target.value })}>
                  {Object.entries(mcDraft.weather_unit_options).map(([key, label]) => (
                    <option key={key} value={key}>{label}</option>
                  ))}
                </select>
              </label>
            </div>
          )}
          <p className="hint">
            {mcDraft.value === "weather"
              ? "Looked up via Open-Meteo -- a free weather service, no account or API key needed."
              : mcDraft.value === "none"
              ? "Nothing is drawn between the two gauge columns -- just the background shows through."
              : "The Spotify now-playing display below (album art, track/artist, progress)."}
            {" "}Applies live, even while the dashboard is already running -- no need to Stop/Start.
          </p>
          <div className="row">
            <button onClick={saveMiddleContent}>Save</button>
          </div>
          {mcStatus && <p className="hint settings-saved">{mcStatus}</p>}
          {mcError && <p className="error">{mcError}</p>}
        </div>
      )}

      {npDraft && mcDraft && mcDraft.value === "spotify" && (
        <div className="canvas-props">
          <h2>"Nothing playing" placeholder</h2>
          <div className="row">
            <label className="grow">
              Placeholder image
              <input
                type="file"
                accept="image/*"
                onChange={(e) => uploadImage("nowPlaying", e.target.files[0],
                  (path) => updateNpDraft({ default_art_path: path }), setNpError)}
              />
            </label>
            {npDraft.default_art_path && (
              <>
                <img className="file-thumb" src={api.dashboardImageUrl(npDraft.default_art_path)} alt="" />
                <span className="hint">{basename(npDraft.default_art_path)}</span>
                <button type="button" onClick={() => updateNpDraft({ default_art_path: "" })}>Clear</button>
              </>
            )}
            {uploadingId === "nowPlaying" && <span className="hint">Uploading…</span>}
          </div>
          <div className="row">
            <label className="grow">
              Message
              <input
                type="text"
                value={npDraft.not_playing_message || ""}
                onChange={(e) => updateNpDraft({ not_playing_message: e.target.value })}
                placeholder={npDraft.default_message}
              />
            </label>
          </div>
          <p className="hint">
            Shown in place of the album art/track title whenever nothing is playing.
            Leave either blank to fall back to the default. Both apply live, even while
            the dashboard is already running -- no need to Stop/Start or Save layout.
          </p>
          <div className="row">
            <button onClick={saveNowPlaying}>Save</button>
          </div>
          {npStatus && <p className="hint settings-saved">{npStatus}</p>}
          {npError && <p className="error">{npError}</p>}
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
