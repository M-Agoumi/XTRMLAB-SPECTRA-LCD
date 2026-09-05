# Phase 0 spike

Throwaway code answering ROADMAP.md's Phase 0 question: does a
pywebview/WebView2 window's memory actually come back when destroyed
(not hidden) on minimize-to-tray, and how long does re-opening take?

Not part of the shipped app -- safe to delete once Phase 0's numbers
are in and the go/no-go call is made.

## Run it

```
pip install pywebview pystray psutil pillow
python spike.py
```

See the docstring at the top of `spike.py` for what to click and what
to report back. This is written against pywebview's documented APIs
but hasn't actually been run anywhere but here -- there's no way to
test WebView2 behavior outside a real Windows machine, so if it errors
out or the "Show" cycle doesn't work right, paste the console output
back and it'll get fixed, the same way every other Windows-only issue
in this project has been.

## What "done" looks like

Four sets of RAM numbers (baseline / window open / just after destroy
/ 10s after destroy) plus reopen timing, ideally across 2-3 open/close
cycles. That's enough to answer whether "destroy on minimize" actually
delivers on the RAM story, before any real UI code gets built on top
of the assumption.
