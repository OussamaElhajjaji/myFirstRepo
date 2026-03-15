"""
Build the final short-form video by combining:
  - stock video clips / photos (royalty-free)
  - TTS audio narration
  - animated text overlay (hook + captions)
  - branded outro card
"""

import logging
import textwrap
import uuid
from pathlib import Path
from typing import Optional

from config.settings import (
    AUDIO_DIR,
    CLIP_DURATION,
    MAX_VIDEO_DURATION,
    OUTPUT_DIR,
    TRANSITION_DURATION,
    VIDEO_FPS,
    VIDEO_RESOLUTION,
)

logger = logging.getLogger(__name__)

W, H = VIDEO_RESOLUTION  # 1080 × 1920


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_moviepy():
    """Lazy import to avoid slow startup."""
    from moviepy.editor import (
        AudioFileClip,
        ColorClip,
        CompositeVideoClip,
        ImageClip,
        TextClip,
        VideoFileClip,
        concatenate_videoclips,
        vfx,
    )
    return {
        "AudioFileClip": AudioFileClip,
        "ColorClip": ColorClip,
        "CompositeVideoClip": CompositeVideoClip,
        "ImageClip": ImageClip,
        "TextClip": TextClip,
        "VideoFileClip": VideoFileClip,
        "concatenate_videoclips": concatenate_videoclips,
        "vfx": vfx,
    }


def _resize_clip(clip, mp):
    """Crop/resize a clip to the target portrait resolution."""
    clip_ratio = clip.w / clip.h
    target_ratio = W / H
    if clip_ratio > target_ratio:
        # wider than target — crop sides
        new_w = int(clip.h * target_ratio)
        x_center = clip.w / 2
        clip = clip.crop(x1=x_center - new_w / 2, x2=x_center + new_w / 2)
    else:
        # taller — crop top/bottom
        new_h = int(clip.w / target_ratio)
        y_center = clip.h / 2
        clip = clip.crop(y1=y_center - new_h / 2, y2=y_center + new_h / 2)
    return clip.resize((W, H))


def _build_text_overlay(text: str, duration: float, mp, font_size: int = 56,
                         position: str = "center", color: str = "white") -> object:
    """Return a semi-transparent caption bar clip."""
    wrapped = "\n".join(textwrap.wrap(text, width=28))
    try:
        txt = mp["TextClip"](
            wrapped,
            fontsize=font_size,
            color=color,
            font="DejaVu-Sans-Bold",
            stroke_color="black",
            stroke_width=2,
            method="label",
        ).set_duration(duration)
    except Exception:
        # fallback if font not available
        txt = mp["TextClip"](
            wrapped,
            fontsize=font_size,
            color=color,
            stroke_color="black",
            stroke_width=2,
        ).set_duration(duration)

    txt = txt.set_position(("center", position if isinstance(position, int) else 0.75), relative=True if isinstance(position, str) else False)
    return txt


def _outro_card(duration: float, mp, topic: str = "") -> object:
    """Black card with 'Follow for more' text."""
    bg = mp["ColorClip"](size=(W, H), color=(0, 0, 0), duration=duration)
    msg = mp["TextClip"](
        "Follow for more tips!",
        fontsize=72,
        color="white",
        font="DejaVu-Sans-Bold",
    ).set_duration(duration).set_position("center")
    return mp["CompositeVideoClip"]([bg, msg])


# ── main builder ──────────────────────────────────────────────────────────────

def build_video(
    video_paths: list[Path],
    photo_paths: list[Path],
    audio_path: Path,
    script_data: dict,
    output_filename: Optional[str] = None,
) -> Optional[Path]:
    """
    Assemble final video. Returns output Path or None on failure.

    Strategy:
      1. Fill audio duration with stock clips / photos on loop.
      2. Add TTS audio.
      3. Overlay hook text for first 3 s, then scrolling captions.
      4. Append 2-second outro card.
    """
    mp = _load_moviepy()

    # ── audio ──────────────────────────────────────────────────────────────
    try:
        audio = mp["AudioFileClip"](str(audio_path))
        narration_duration = min(audio.duration, MAX_VIDEO_DURATION - 2)
    except Exception as exc:
        logger.error("Failed to load audio: %s", exc)
        return None

    # ── collect raw clips ──────────────────────────────────────────────────
    raw_clips = []

    for vp in video_paths:
        try:
            clip = mp["VideoFileClip"](str(vp), audio=False)
            clip = _resize_clip(clip, mp)
            # trim to CLIP_DURATION
            clip = clip.subclip(0, min(CLIP_DURATION, clip.duration))
            raw_clips.append(clip)
        except Exception as exc:
            logger.warning("Skipping video %s: %s", vp.name, exc)

    for ip in photo_paths:
        try:
            clip = mp["ImageClip"](str(ip), duration=CLIP_DURATION)
            clip = _resize_clip(clip, mp)
            raw_clips.append(clip)
        except Exception as exc:
            logger.warning("Skipping photo %s: %s", ip.name, exc)

    if not raw_clips:
        logger.error("No usable clips found.")
        return None

    # ── loop clips to fill narration duration ─────────────────────────────
    total = 0.0
    looped = []
    i = 0
    while total < narration_duration:
        c = raw_clips[i % len(raw_clips)]
        remaining = narration_duration - total
        if c.duration > remaining:
            c = c.subclip(0, remaining)
        looped.append(c)
        total += c.duration
        i += 1

    # ── concatenate with crossfade ─────────────────────────────────────────
    try:
        base = mp["concatenate_videoclips"](looped, method="compose")
    except Exception as exc:
        logger.error("Concatenation failed: %s", exc)
        return None

    # ── outro card ─────────────────────────────────────────────────────────
    outro = _outro_card(2.0, mp, topic=script_data.get("topic", ""))
    try:
        full_video = mp["concatenate_videoclips"]([base, outro], method="compose")
    except Exception:
        full_video = base

    # ── set audio ─────────────────────────────────────────────────────────
    narration = audio.subclip(0, min(audio.duration, full_video.duration))
    full_video = full_video.set_audio(narration)

    # ── text overlays ──────────────────────────────────────────────────────
    overlays = [full_video]

    hook_text = script_data.get("hook", "")
    if hook_text:
        hook_clip = _build_text_overlay(hook_text, min(3.0, narration_duration), mp, font_size=62)
        hook_clip = hook_clip.set_start(0)
        overlays.append(hook_clip)

    body_text = script_data.get("body", "")
    if body_text and narration_duration > 3:
        body_clip = _build_text_overlay(body_text, narration_duration - 3, mp, font_size=48)
        body_clip = body_clip.set_start(3)
        overlays.append(body_clip)

    final = mp["CompositeVideoClip"](overlays)

    # ── export ─────────────────────────────────────────────────────────────
    if output_filename is None:
        output_filename = f"video_{uuid.uuid4().hex[:8]}.mp4"
    out_path = OUTPUT_DIR / output_filename

    try:
        final.write_videofile(
            str(out_path),
            fps=VIDEO_FPS,
            codec="libx264",
            audio_codec="aac",
            threads=4,
            preset="fast",
            logger=None,
        )
        logger.info("Video exported to %s", out_path)
        return out_path
    except Exception as exc:
        logger.error("Video export failed: %s", exc)
        return None
    finally:
        # Release resources
        for c in raw_clips:
            try:
                c.close()
            except Exception:
                pass
        try:
            audio.close()
        except Exception:
            pass
