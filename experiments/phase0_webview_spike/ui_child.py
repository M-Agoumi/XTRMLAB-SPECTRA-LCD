"""
Phase 0b: the "UI process" side. Not part of the shipped app.

A single pywebview window, nothing else -- no tray icon, no
orchestration logic. Meant to be spawned as a subprocess by
spike_process_split.py, which is what actually tests the interesting
question: when THIS process's PID is killed from outside, do the
msedgewebview2.exe helper processes it spawned die with it, or do they
survive as orphans?

Can also be run standalone (`python ui_child.py`) to just look at it --
closing the window normally (the X button) exits cleanly either way.
"""
import webview

HTML = """
<!doctype html>
<html><body style="background:#111;color:#0ff;font-family:sans-serif;
             text-align:center;padding-top:60px;margin:0">
  <h2>Phase 0b UI child</h2>
  <p>This window's process gets killed from outside during the spike --
     if you're just running this standalone, close it with the X.</p>
</body></html>
"""

if __name__ == "__main__":
    webview.create_window("Phase 0b UI child", html=HTML, width=420, height=240)
    webview.start()
