"""
image_store.py -- where a user-picked image (dashboard background,
the "nothing playing" placeholder, a Phase 6 image element) actually
lives once it's picked.

Every image setting used to just store whatever path the user typed or
browsed to, verbatim -- which is fragile in exactly the way a plain
path always is: move the file, rename it, delete it, or pick one off a
USB stick that isn't plugged in next time, and the feature silently
falls back to a placeholder with no obvious explanation why (see
dashboard_theme.py's _build_background_image()/_draw_image_element(),
which both catch-and-fall-back on any read error by design -- that
tolerance is exactly what was masking how easy this was to break).
Not everyone browsing to a file realizes they're handing the app a
*reference* to it rather than a copy either, so this isn't just an
edge case.

The fix: the moment an image is picked -- Tkinter's Browse dialog, or
the web UI's upload -- a copy lands in this app's own managed folder,
and it's THAT copy's path that ends up in app_config.json. The
original file can move, get renamed, or get deleted afterward with no
effect at all.
"""
import hashlib
import io
import os
import re

from PIL import Image

# %LOCALAPPDATA% (not %APPDATA%/Roaming) on purpose -- these are copies
# of binary image files, not small settings worth syncing across
# machines via a roaming profile. Falls back to the home directory on
# any other OS, or if LOCALAPPDATA isn't set (a stripped-down
# environment) -- still a writable, per-user location, just not the
# "proper" Windows spot.
USER_DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "HongtaiScreen")
IMAGES_DIR = os.path.join(USER_DATA_DIR, "images")

MAX_IMAGE_BYTES = 25 * 1024 * 1024  # 25MB -- generous for a photo/logo, not for an accidental video

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")


def _ensure_images_dir():
    os.makedirs(IMAGES_DIR, exist_ok=True)
    return IMAGES_DIR


def _sanitize_stem(name):
    stem = os.path.splitext(os.path.basename(name or "image"))[0]
    stem = _SAFE_CHARS.sub("_", stem).strip("_") or "image"
    return stem[:60]  # keep filenames sane even from a wildly long original name


def _stored_name(data, original_name, ext):
    # An 8-char content hash prefix so picking the exact same file
    # twice (the common "I clicked Browse again" case) reuses the one
    # copy already on disk instead of piling up duplicates -- and keeps
    # the sanitized original name alongside it so the file this app now
    # owns is still recognizable if the user goes looking for it in
    # IMAGES_DIR directly.
    digest = hashlib.sha1(data).hexdigest()[:8]
    return f"{digest}_{_sanitize_stem(original_name)}{ext}"


def _validate_image_bytes(data):
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f"image is too large ({len(data)} bytes, max {MAX_IMAGE_BYTES})")
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()  # cheap structural check -- doesn't decode full pixel data
    except Exception as e:  # noqa: BLE001 -- any of PIL's many "not an image" exceptions
        raise ValueError(f"doesn't look like a readable image: {e}")


def store_image_bytes(data, original_name):
    """Saves raw image bytes (the web UI's upload path -- a browser
    can't hand back a real filesystem path for a picked file, only its
    content) into IMAGES_DIR and returns the stored copy's absolute
    path. Raises ValueError on anything that isn't actually a readable
    image, or is implausibly large, rather than silently storing junk
    that only fails later, confusingly, at render time."""
    _validate_image_bytes(data)
    ext = os.path.splitext(original_name or "")[1].lower() or ".png"
    _ensure_images_dir()
    dest = os.path.join(IMAGES_DIR, _stored_name(data, original_name, ext))
    with open(dest, "wb") as f:
        f.write(data)
    return dest


def store_image_file(source_path):
    """Copies an image already on disk (Tkinter's Browse dialog gives a
    real path, unlike a browser) into IMAGES_DIR and returns the stored
    copy's absolute path -- same validation/dedup as store_image_bytes,
    just reading the source file first instead of taking bytes
    directly. Raises ValueError on a missing/unreadable/non-image file,
    or FileNotFoundError if `source_path` itself doesn't exist."""
    with open(source_path, "rb") as f:
        data = f.read()
    return store_image_bytes(data, os.path.basename(source_path))


def is_managed(path):
    """True if `path` already lives under IMAGES_DIR -- lets a caller
    skip re-copying an image that's already this app's own managed
    copy (e.g. re-saving a form without the user picking a new file)."""
    if not path:
        return False
    try:
        return os.path.commonpath([os.path.abspath(path), IMAGES_DIR]) == IMAGES_DIR
    except ValueError:  # different drives on Windows -- definitely not managed
        return False
