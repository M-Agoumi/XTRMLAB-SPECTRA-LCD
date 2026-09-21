# Phase 0 spike

Throwaway code answering ROADMAP.md's Phase 0 question. Not part of
the shipped app -- safe to delete once Phase 0's numbers are in and
the go/no-go call is made.

## Setup (once)

```
pip install pywebview pystray psutil pillow
```

(the `.bat` wrappers below also do this automatically, so this is only
needed if you want to run the `.py` files directly instead)

## Round 1: does destroy() reclaim memory? (answered: no)

Double-click, in this order:

1. **`RUN_SPIKE.bat`** -- interactive. A window opens; click
   "Minimize to tray", watch the console, then Show/Quit from the tray
   icon (cyan dot). Output -> `spike_output.log`.
2. **`RUN_FOLLOWUP_CYCLES.bat`** -- automated, 12 open/destroy cycles,
   watches for continued growth vs. a plateau. Output -> `cycles_output.log`.
3. **`RUN_FOLLOWUP_CONTROL.bat`** -- automated, opens one window and
   never destroys it, for comparison. Output -> `control_output.log`.

**Result:** confirmed across all three runs. Loading WebView2 into a
process costs ~65-90MB, once -- and that memory does not come back
when the window is destroyed, hidden, or left alone. It's a one-time
runtime-load cost tied to the *process*, not something tied to a
specific window instance. A small (~1MB/cycle) creep showed up across
repeated cycles, but it flattens rather than accelerating -- not a
leak, just allocator noise.

**Consequence:** since the app needs a hard <100MB background/idle
budget, and WebView2 alone already costs ~90MB once loaded, it can't
share a process with the always-on backend (the thing that keeps the
LCD panel actually displaying content, which has to run continuously
regardless of whether any UI is open). The plan changed from
"destroy the window on minimize" to a full **two-process split**:

- **Backend process** -- always running, never imports pywebview/
  WebView2 at all. Panel connection, render loop, local HTTP API.
  Expected to cost about what today's app already costs (~84MB).
- **UI process** -- a completely separate process, spawned only when
  the window is opened, pointed at the backend's local HTTP API, and
  **killed outright** (not just closed) when the window closes.

## Round 2: does killing the UI process actually clean up everything?

Killing a whole process should be a much stronger guarantee than
`destroy()` inside a shared process -- but one thing is genuinely
unknown until tested: when the UI process itself is killed, do the
`msedgewebview2.exe` helper processes *it* spawned die with it, or do
they survive as orphans?

4. **`RUN_PROCESS_SPLIT.bat`** -- automated, no clicking. Spawns and
   kills a separate UI process (`ui_child.py`) 4 times, alternating
   between killing just its PID and killing its whole process tree
   explicitly, checking for orphaned survivors after each. Output ->
   `process_split_output.log`. Takes under a minute.

Not yet run anywhere but here -- written against psutil/subprocess/
pywebview's documented behavior. If it errors out, paste the log back.

## What "done" looks like

If `RUN_PROCESS_SPLIT.bat` shows `tracked-child-tree alive=0/Y` after
every kill (both PID-only and whole-tree cycles), killing just the
child PID is enough -- WebView2's own process-lifetime management
handles the rest, and the real app can do the same. If PID-only cycles
leave survivors but whole-tree cycles don't, the real app needs to
explicitly walk and kill the UI process's full descendant tree, not
just the immediate PID -- a straightforward fix, just one that needs
to be known about rather than assumed.

Either way, this closes out Phase 0: a two-process design where the
backend stays comfortably under budget by never touching WebView2 at
all, and the UI's cost exists only while it's actually open.
