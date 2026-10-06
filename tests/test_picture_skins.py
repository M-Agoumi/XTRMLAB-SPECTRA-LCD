"""Tests for picture skins (a bar's `skin`, a styled dial's `face_image`):
which files they may load, and how they travel through preset export/import.
"""
import base64
import io
import os
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
# controller.py imports video_theme, which imports cv2 unconditionally; see
# test_simulated_screen.py for why a stub is enough here.
sys.modules.setdefault("cv2", types.ModuleType("cv2"))

from PIL import Image, ImageChops

from hongtai_screen_app import image_store
from hongtai_screen_app.controller import AppController
from hongtai_screen_app.themes import dashboard_theme as dashboard
from hongtai_screen_app.themes import widget_styles


def _png_bytes():
    buf = io.BytesIO()
    Image.new("RGBA", (40, 8), (200, 200, 200, 255)).save(buf, "PNG")
    return buf.getvalue()


def test_skin_path_accepts_bundled_names_and_managed_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(image_store, "IMAGES_DIR", str(tmp_path))
    uploaded = tmp_path / "ab12cd34_saber.png"
    uploaded.write_bytes(_png_bytes())
    assert widget_styles.skin_path("katana.png").endswith(os.path.join("skins", "katana.png"))
    assert widget_styles.skin_path(str(uploaded)) == str(uploaded)


def test_skin_path_refuses_paths_outside_the_skins_and_image_store(tmp_path, monkeypatch):
    monkeypatch.setattr(image_store, "IMAGES_DIR", str(tmp_path / "store"))
    elsewhere = tmp_path / "private.png"
    elsewhere.write_bytes(_png_bytes())
    assert widget_styles.skin_path(str(elsewhere)) is None
    assert widget_styles.skin_path("../backgrounds/nebula.jpg") is None
    assert widget_styles.skin_path("") is None


def test_import_keeps_bundled_skins_stores_inlined_ones_and_drops_foreign_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(image_store, "IMAGES_DIR", str(tmp_path))
    saved = {}
    fake = types.SimpleNamespace(
        _PICTURE_FIELDS=AppController._PICTURE_FIELDS,
        _preset_image_slots=AppController._preset_image_slots,
        save_dashboard_preset=lambda name, elements, background: saved.update(elements=elements),
    )
    preset = {"elements": [
        {"id": "a", "type": "bar", "skin": "katana.png"},
        {"id": "b", "type": "bar", "skin": None,
         "skin_b64": base64.b64encode(_png_bytes()).decode(), "skin_name": "saber.png"},
        {"id": "c", "type": "gauge", "face_image": r"C:\Users\someone\secret.png"},
        {"id": "d", "type": "text"},
    ]}
    AppController.import_dashboard_preset(fake, "Shared", preset)
    a, b, c, d = saved["elements"]
    assert a["skin"] == "katana.png"
    assert image_store.is_managed(b["skin"]) and os.path.exists(b["skin"])
    assert "skin_b64" not in b and "skin_name" not in b
    assert c["face_image"] is None
    assert "skin" not in d and "face_image" not in d


def test_export_inlines_uploaded_skins_and_leaves_bundled_names(tmp_path, monkeypatch):
    monkeypatch.setattr(image_store, "IMAGES_DIR", str(tmp_path))
    uploaded = image_store.store_image_bytes(_png_bytes(), "saber.png")
    preset = {"elements": [{"id": "a", "type": "bar", "skin": uploaded},
                           {"id": "b", "type": "bar", "skin": "katana.png"}]}
    fake = types.SimpleNamespace(
        cfg={}, _PICTURE_FIELDS=AppController._PICTURE_FIELDS,
        _preset_image_slots=AppController._preset_image_slots,
    )
    monkeypatch.setattr("hongtai_screen_app.config_store.resolve_dashboard_presets", lambda cfg: {"Mine": preset})
    exported = AppController.export_dashboard_preset(fake, "Mine")["preset"]["elements"]
    assert exported[0]["skin"] is None and exported[0]["skin_name"] == "saber.png"
    assert base64.b64decode(exported[0]["skin_b64"]) == Path(uploaded).read_bytes()
    assert exported[1]["skin"] == "katana.png" and "skin_b64" not in exported[1]


def test_a_skin_replaces_the_meter_on_styled_bars_too():
    bar = {"id": "m", "type": "bar", "stat": "ram", "x": 0.5, "y": 0.5, "width": 0.4, "height": 0.08,
           "widget_style": "gothic", "show_title": False, "show_value": False}
    background = {"mode": "solid", "scheme": "mono"}
    plain = dashboard.render_preset_thumbnail([bar], background, 960, 480)
    skinned = dashboard.render_preset_thumbnail([{**bar, "skin": "katana.png"}], background, 960, 480)
    assert ImageChops.difference(plain.convert("RGB"), skinned.convert("RGB")).getbbox() is not None
