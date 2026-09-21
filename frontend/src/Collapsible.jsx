import React, { useEffect, useState } from "react";

// A collapsible section header -- wraps any block of settings behind a
// click-to-toggle <h2>, so a long settings page (Panel port, Preview,
// System, Controls, Dashboard layout's own Background/Middle content/
// placeholder sub-sections, Config, Log...) doesn't force scrolling
// past everything you're not currently touching just to reach the one
// thing you are. Open/closed state persists per-section across reloads
// (keyed by `id`, in localStorage) so a section you've collapsed once
// -- Log, say -- stays out of the way from then on, while one you
// habitually use stays exactly where you left it.
//
// `as`/`className` let this wrap either a top-level App.jsx section
// (<section className="panel">) or one of DashboardCanvas.jsx's nested
// sub-panels (<div className="canvas-props">) -- same collapse
// behavior either way, just a different outer tag/class to match
// whichever spot it's used from.
const STORAGE_PREFIX = "hongtai_collapsed:";

export default function Collapsible({ id, title, defaultOpen = true, as: As = "section", className = "panel", children }) {
  const [open, setOpen] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_PREFIX + id);
      if (stored !== null) return stored === "1";
    } catch {
      // localStorage can throw (private browsing, storage disabled) --
      // just fall back to defaultOpen every time, same as never having
      // a stored preference.
    }
    return defaultOpen;
  });

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_PREFIX + id, open ? "1" : "0");
    } catch {
      // Best-effort only -- losing the remembered state is harmless,
      // it just falls back to defaultOpen next time.
    }
  }, [id, open]);

  return (
    <As className={className}>
      <button
        type="button"
        className="collapsible-header"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <h2>{title}</h2>
        <span className={`collapsible-chevron${open ? " open" : ""}`}>▸</span>
      </button>
      <div hidden={!open}>{children}</div>
    </As>
  );
}
