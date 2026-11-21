"""Tests for startup_registration.py's run level: the logon task only
starts the app elevated when it was registered from an elevated app AND
the exe it launches can't be modified without admin rights.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hongtai_screen_app import startup_registration


def _registered_run_level(monkeypatch, tmp_path, elevated, exe_under_program_files):
    program_files = tmp_path / "Program Files"
    local_programs = tmp_path / "AppData" / "Local" / "Programs"
    exe_dir = (program_files if exe_under_program_files else local_programs) / "Rigvue"
    exe_dir.mkdir(parents=True)
    exe = exe_dir / "Hongtai Screen.exe"
    exe.touch()

    calls = []

    def _fake_schtasks(*args, log=None):
        calls.append(args)
        return startup_registration._Result(0, "SUCCESS", "")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    for var in ("ProgramFiles(x86)", "ProgramW6432"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ProgramFiles", str(program_files))
    monkeypatch.setattr(startup_registration, "_is_elevated", lambda: elevated)
    monkeypatch.setattr(startup_registration, "_run_schtasks", _fake_schtasks)
    monkeypatch.setattr(startup_registration, "_legacy_startup_script_path", lambda: None)

    startup_registration.enable_startup()

    (create,) = [c for c in calls if c[0] == "/create"]
    return create[create.index("/rl") + 1]


def test_elevated_all_users_install_registers_highest(monkeypatch, tmp_path):
    assert _registered_run_level(monkeypatch, tmp_path, elevated=True, exe_under_program_files=True) == "highest"


def test_elevated_per_user_install_stays_limited(monkeypatch, tmp_path):
    assert _registered_run_level(monkeypatch, tmp_path, elevated=True, exe_under_program_files=False) == "limited"


def test_not_elevated_stays_limited(monkeypatch, tmp_path):
    assert _registered_run_level(monkeypatch, tmp_path, elevated=False, exe_under_program_files=True) == "limited"


def test_source_run_stays_limited(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(startup_registration, "_is_elevated", lambda: True)
    assert startup_registration._run_level() == "limited"
