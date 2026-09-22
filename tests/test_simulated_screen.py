"""Tests for driver/simulated_screen.py and the Controller wiring that
picks it -- simulation mode (ROADMAP: run without a physical panel).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image

from hongtai_screen_app.driver.hongtai_screen import HongtaiScreen
from hongtai_screen_app.driver.simulated_screen import (
    DEFAULT_ANGLE,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    SimulatedHongtaiScreen,
)


def test_connect_uses_defaults_with_no_hardware():
    screen = SimulatedHongtaiScreen()
    info = screen.connect()
    assert info.width == DEFAULT_WIDTH
    assert info.height == DEFAULT_HEIGHT
    assert info.angle == DEFAULT_ANGLE
    assert info.panel_width == DEFAULT_WIDTH
    assert info.panel_height == DEFAULT_HEIGHT


def test_connect_swaps_canvas_axes_at_90_and_270_like_a_real_panel():
    for angle, expect_swapped in [(0, False), (90, True), (180, False), (270, True)]:
        screen = SimulatedHongtaiScreen(width=960, height=480, angle=angle)
        info = screen.connect()
        assert info.panel_width == 960 and info.panel_height == 480
        if expect_swapped:
            assert (info.width, info.height) == (480, 960)
        else:
            assert (info.width, info.height) == (960, 480)


def test_show_never_touches_real_serial_and_still_feeds_the_mirror():
    screen = SimulatedHongtaiScreen(width=100, height=60)
    info = screen.connect()
    screen.enable_frame_capture()
    screen.set_brightness(40)  # exercises _send_noreply() against the fake serial
    img = Image.new("RGB", (info.width, info.height), "blue")
    screen.show(img)  # would raise/hang against a real closed port
    jpeg = screen.get_mirror_frame_jpeg()
    assert jpeg and jpeg[:2] == b"\xff\xd8"  # JPEG SOI marker
    screen.close()


def test_blind_restart_is_a_fast_noop():
    screen = SimulatedHongtaiScreen()
    logged = []
    screen.blind_restart(settle_time=0.01, log=logged.append)
    assert any("nothing to restart" in m for m in logged)


def test_simulated_screen_is_still_a_hongtaiscreen_for_duck_typing():
    # screen_engine.py and every theme's run() only care that this has
    # the same interface -- isinstance is what makes controller.py's
    # `screen_factory(port)` call sites (ScreenEngine._ensure_connected)
    # not need any special-casing for which one they got back.
    assert issubclass(SimulatedHongtaiScreen, HongtaiScreen)


def test_controller_desired_screen_factory_defaults_to_real_hongtaiscreen():
    from hongtai_screen_app.controller import AppController

    factory, descriptor = AppController._desired_screen_factory(
        _FakeSelf(cfg={})
    )
    assert factory is HongtaiScreen
    assert descriptor == ("real",)


def test_controller_desired_screen_factory_picks_simulated_when_enabled():
    from hongtai_screen_app.controller import AppController

    cfg = {"simulate": {"enabled": True, "width": 320, "height": 240, "angle": 0}}
    factory, descriptor = AppController._desired_screen_factory(_FakeSelf(cfg=cfg))
    assert descriptor == ("simulate", 320, 240, 0)
    screen = factory(port="COM3")  # port must be accepted-and-ignored
    assert isinstance(screen, SimulatedHongtaiScreen)
    info = screen.connect()
    assert (info.width, info.height) == (320, 240)


def test_controller_desired_screen_factory_descriptor_is_stable_across_calls():
    # Regression guard: start() compares descriptors (not factory
    # identity) precisely so an unchanged "simulate" setting never
    # forces a reconnect on every ordinary start()/apply() call -- see
    # _desired_screen_factory()'s docstring.
    from hongtai_screen_app.controller import AppController

    cfg = {"simulate": {"enabled": True, "width": 640, "height": 400, "angle": 180}}
    _, d1 = AppController._desired_screen_factory(_FakeSelf(cfg=cfg))
    _, d2 = AppController._desired_screen_factory(_FakeSelf(cfg=cfg))
    assert d1 == d2


class _FakeSelf:
    """Just enough of an AppController for the unbound-method calls
    above -- _desired_screen_factory() only ever reads self.cfg."""

    def __init__(self, cfg):
        self.cfg = cfg
