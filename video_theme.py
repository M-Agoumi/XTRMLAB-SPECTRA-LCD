"""
video_theme.py -- stream any video file to the panel as a "theme".

Works great for Bad Apple specifically (it's a classic stress-test video
for exactly this kind of thing -- flat black/white silhouette animation
compresses to tiny JPEGs, so it can actually keep up with the panel's
2 Mbaud link) but it's fully generic: point it at any video file you
already have.

    python video_theme.py bad_apple.mp4
    python video_theme.py bad_apple.mp4 --fps 20
    python video_theme.py bad_apple.mp4 --bw           # force black & white
    python video_theme.py bad_apple.mp4 --audio        # also play the audio
    python video_theme.py bad_apple.mp4 COM5           # explicit port

NOTE: this does not fetch, download, or include any video content --
supply your own file. Nothing here is specific to any one video; it
just decodes whatever file you point it at and streams the frames.

Requires:
    pip install opencv-python-headless pyserial pillow
    pip install pygame                # only needed for --audio
    ffmpeg on PATH                    # only needed for --audio (extracts sound)
"""

import argparse
import subprocess
import sys
import time
import shutil
import tempfile
import os

import cv2
from PIL import Image

from hongtai_screen import HongtaiScreen


def fit_frame(frame_bgr, target_w, target_h, bw=False):
    """Resize+letterbox a BGR OpenCV frame to (target_w, target_h),
    preserving aspect ratio with black bars, returned as a PIL Image."""
    img = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    if bw:
        img = img.convert("L").convert("RGB")

    src_w, src_h = img.size
    scale = min(target_w / src_w, target_h / src_h)
    new_w, new_h = max(1, int(src_w * scale)), max(1, int(src_h * scale))
    img = img.resize((new_w, new_h))

    canvas = Image.new("RGB", (target_w, target_h), (0, 0, 0))
    canvas.paste(img, ((target_w - new_w) // 2, (target_h - new_h) // 2))
    return canvas


def extract_audio(video_path, out_wav):
    """Best-effort audio extraction via ffmpeg. Returns True on success."""
    if shutil.which("ffmpeg") is None:
        print("  (ffmpeg not found on PATH -- skipping audio)")
        return False
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-vn",
             "-ar", "44100", "-ac", "2", out_wav],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  (audio extraction failed: {e} -- continuing without audio)")
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video", help="path to a video file you already have")
    ap.add_argument("port", nargs="?", default=None, help="COM port (auto-detected if omitted)")
    ap.add_argument("--fps", type=float, default=None,
                     help="override playback rate (default: the video's own fps, "
                          "capped to what the panel can realistically keep up with)")
    ap.add_argument("--bw", action="store_true", help="force black & white")
    ap.add_argument("--audio", action="store_true",
                     help="also play the audio track through the PC's speakers, "
                          "roughly synced (best-effort, needs ffmpeg + pygame)")
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"Could not open video file: {args.video}")
        sys.exit(1)

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    target_fps = args.fps or min(src_fps, 24.0)  # 24fps is already plenty for silhouette content
    print(f"Video: {args.video}  ({frame_count} frames @ {src_fps:.1f}fps source, "
          f"playing at {target_fps:.1f}fps)")

    screen = HongtaiScreen(args.port)
    info = screen.connect()
    print(f"Connected: {info.width}x{info.height}, firmware {info.version}")
    screen.set_brightness(90)

    audio_tmp = None
    if args.audio:
        try:
            import pygame  # noqa: F401
        except ImportError:
            print("  --audio needs pygame (pip install pygame) -- skipping audio")
            args.audio = False

    if args.audio:
        audio_tmp = os.path.join(tempfile.gettempdir(), "video_theme_audio.wav")
        if extract_audio(args.video, audio_tmp):
            import pygame
            pygame.mixer.init()
            pygame.mixer.music.load(audio_tmp)
            pygame.mixer.music.play()
        else:
            args.audio = False

    period = 1.0 / target_fps
    frame_idx = 0
    start = time.time()

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            # keep roughly in sync with wall-clock time, dropping frames
            # if we've fallen behind rather than letting playback lag
            target_time = start + frame_idx / target_fps
            now = time.time()
            if now < target_time:
                time.sleep(target_time - now)
            elif now > target_time + period:
                frame_idx += 1
                continue  # we're behind -- skip this frame instead of queueing up

            img = fit_frame(frame, info.width, info.height, bw=args.bw)
            screen.show(img)
            frame_idx += 1

            if frame_count and frame_idx % 100 == 0:
                pct = 100 * frame_idx / frame_count
                print(f"  {frame_idx}/{frame_count} ({pct:.0f}%)")

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        if args.audio:
            try:
                import pygame
                pygame.mixer.music.stop()
            except Exception:  # noqa: BLE001
                pass
        screen.close()
        print("Done, disconnected cleanly.")


if __name__ == "__main__":
    main()
