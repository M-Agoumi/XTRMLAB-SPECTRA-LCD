"""Tests for ui_window.py's load watchdog: the "WebView2 is installed but
broken" popup that fires when the window opens and its page never loads.
"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hongtai_screen_app import ui_window


class _Event:
    """Just enough of pywebview's Event: `+=` a handler, fire() it."""

    def __init__(self):
        self._handlers = []

    def __iadd__(self, handler):
        self._handlers.append(handler)
        return self

    def fire(self):
        for handler in self._handlers:
            handler()


class _FakeWindow:
    def __init__(self):
        self.events = type("Events", (), {})()
        self.events.loaded = _Event()
        self.destroyed = threading.Event()

    def destroy(self):
        self.destroyed.set()


def _record_messages(monkeypatch):
    shown = []
    monkeypatch.setattr(ui_window, "_show_webview2_missing_message", shown.append)
    return shown


def test_page_that_never_loads_shows_message_and_closes_window(monkeypatch):
    shown = _record_messages(monkeypatch)
    window = _FakeWindow()

    ui_window._start_load_watchdog(window, timeout=0.05)

    assert window.destroyed.wait(2)
    assert shown == [ui_window._WEBVIEW2_BROKEN_TEXT]


def test_page_that_loads_shows_nothing(monkeypatch):
    shown = _record_messages(monkeypatch)
    window = _FakeWindow()

    ui_window._start_load_watchdog(window, timeout=0.2)
    window.events.loaded.fire()

    assert not window.destroyed.wait(0.5)
    assert shown == []


def test_load_during_message_keeps_window_open(monkeypatch):
    window = _FakeWindow()
    shown = []

    def _message_then_late_load(text):
        shown.append(text)
        window.events.loaded.fire()

    monkeypatch.setattr(ui_window, "_show_webview2_missing_message", _message_then_late_load)

    ui_window._start_load_watchdog(window, timeout=0.05)

    assert not window.destroyed.wait(0.5)
    assert shown == [ui_window._WEBVIEW2_BROKEN_TEXT]


def test_pywebview_without_loaded_event_is_a_no_op(monkeypatch):
    shown = _record_messages(monkeypatch)
    window = _FakeWindow()
    del window.events.loaded

    ui_window._start_load_watchdog(window, timeout=0.05)

    assert not window.destroyed.wait(0.3)
    assert shown == []
