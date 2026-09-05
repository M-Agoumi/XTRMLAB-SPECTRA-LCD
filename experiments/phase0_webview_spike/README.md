# Phase 0 spike

Throwaway code answering ROADMAP.md's Phase 0 question: does a
pywebview/WebView2 window's memory actually come back when destroyed
(not hidden) on minimize-to-tray, and how long does re-opening take?

Not part of the shipped app -- safe to delete once Phase 0's numbers
are in and the go/no-go call is made.

## Setup (once)

```
pip install pywebview pystray psutil pillow
```

## Run it

Double-click, in this order:

1. **`RUN_SPIKE.bat`** -- interactive. A window opens; click
   "Minimize to tray" in it, watch the console, then right-click the
   tray icon (cyan dot) -> Show, and repeat a couple times, then Quit.
   Output is mirrored to `spike_output.log` next to this file.

2. **`RUN_FOLLOWUP_CYCLES.bat`** -- fully automated, no clicking. Runs
   12 open/destroy cycles back to back (each window auto-closes after
   1s) and prints a verdict on whether RAM is still climbing after a
   dozen cycles or has flattened out. Takes a couple minutes. Output
   goes to `cycles_output.log`.

3. **`RUN_FOLLOWUP_CONTROL.bat`** -- fully automated. Opens one window
   and never destroys it, sampling RAM every 5s for a minute, to see
   what "just leave it open" settles at for comparison. Output goes to
   `control_output.log`.

Send me whichever `.log` file(s) you end up with -- that's simpler than
copy-pasting console output.

These are written against pywebview's documented APIs but only the
first one (`spike.py`, via `RUN_SPIKE.bat`) has actually been run so
far. If `RUN_FOLLOWUP_*` errors out or behaves oddly, paste the log and
it'll get fixed the same way every other Windows-only issue in this
project has been.

## What the first run already showed

`RUN_SPIKE.bat`'s first run: the giant "1153MB across 13
msedgewebview2.exe processes" is pre-existing background noise from
something else on the machine (almost certainly Windows 11's Widgets/
Search integration) -- it never moved, whether our window was open,
destroyed, or hadn't been created yet. The number that's actually ours
("this process") jumped once on first window creation and then stayed
flat around ~101-102MB regardless of window state, which looks more
like a one-time WebView2-runtime-loading cost than a per-window leak.

`RUN_FOLLOWUP_CYCLES.bat` and `RUN_FOLLOWUP_CONTROL.bat` exist to
confirm that read: cycles checks whether RAM keeps climbing over many
more cycles (a real leak) or plateaus (a one-time cost, as suspected);
control checks whether a window that's never destroyed at all settles
at roughly the same number, which would confirm the cost is about
loading the runtime, not about specific windows piling up.

## What "done" looks like

If both follow-ups confirm the plateau theory, the practical takeaway
for ROADMAP.md changes in a good way: destroying the window on minimize
isn't worth the reopen-delay cost, since it doesn't reclaim anything --
just **hide** it instead (instant reopen), and plan around a steady
~100MB footprint for the app's whole lifetime once WebView2 has been
used at all, rather than the original "84MB in tray, more only while
the window's open" hope. Not as good as the original hope, but a small,
bounded, one-time cost rather than the runaway-multi-process scenario
that would have actually killed this approach.
