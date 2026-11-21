"""Tests for startup_registration.py's run level: the logon task only
starts the app elevated when it was registered from an elevated app.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hongtai_screen_app import startup_registration


def _registered_run_level(monkeypatch, elevated):
    calls = []

    def _fake_schtasks(*args, log=None):
        calls.append(args)
        return startup_registration._Result(0, "SUCCESS", "")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(startup_registration, "_is_elevated", lambda: elevated)
    monkeypatch.setattr(startup_registration, "_run_schtasks", _fake_schtasks)
    monkeypatch.setattr(startup_registration, "_legacy_startup_script_path", lambda: None)

    startup_registration.enable_startup()

    (create,) = [c for c in calls if c[0] == "/create"]
    return create[create.index("/rl") + 1]


def test_enabled_from_elevated_app_registers_highest(monkeypatch):
    assert _registered_run_level(monkeypatch, elevated=True) == "highest"


def test_enabled_from_normal_app_stays_limited(monkeypatch):
    assert _registered_run_level(monkeypatch, elevated=False) == "limited"
