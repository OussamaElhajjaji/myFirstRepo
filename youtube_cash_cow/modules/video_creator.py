"""
Video Creator Module
Creates YouTube-ready videos by combining:
- Background images/solid colors
- Text overlays (section titles, facts)
- TTS audio narration
- Optional background music
- Transitions and animations
Uses MoviePy for video composition.
"""
import logging
import os
import random
import textwrap
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from youtube_cash_cow.config import (
    ASSETS_DIR,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
    VIDEOS_DIR,
)
from youtube_cash_cow.modules.script_writer import VideoScript
from youtube_cash_cow.modules.tts_generator import get_audio_duration

logger = logging.getLogger(__name__)

# Color schemes for different niches
COLOR_SCHEMES = {
    "top10": {
        "background": (10, 10, 30),
        "primary": (255, 200, 0),
        "secondary": (255, 100, 0),
        "text": (255, 255, 255),
        "accent": (255, 50, 50),
    },
    "facts": {
        "background": (5, 20, 40),
        "primary": (0, 200, 255),
        "secondary": (0, 100, 200),
        "text": (255, 255, 255),
        "accent": (0, 255, 200),
    },
    "educational": {
        "background": (15, 25, 15),
        "primary": (50, 200, 50),
        "secondary": (20, 150, 20),
        "text": (255, 255, 255),
        "accent": (150, 255, 150),
    },
    "motivational": {
        "background": (30, 10, 10),
        "primary": (255, 80, 0),
        "secondary": (200, 50, 0),
        "text": (255, 255, 255),
        "accent": (255, 200, 0),
    },
    "mystery": {
        "background": (5, 5, 15),
        "primary": (150, 0, 255),
        "secondary": (80, 0, 200),
        "text": (220, 220, 220),
        "accent": (200, 100, 255),
    },
}


def _get_color_scheme(niche: str) -> dict:
    return COLOR_SCHEMES.get(niche, COLOR_SCHEMES["facts"])


def _create_gradient_frame(
    width: int,
    height: int,
    color1: tuple,
    color2: tuple,
) -> np.ndarray:
    """Create a vertical gradient background frame."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(height):
        ratio = y / height
        r = int(color1[0] * (1 - ratio) + color2[0] * ratio)
        g = int(color1[1] * (1 - ratio) + color2[1] * ratio)
        b = int(color1[2] * (1 - ratio) + color2[2] * ratio)
        frame[y, :] = [r, g, b]
    return frame


def _add_particle_effect(
    frame: np.ndarray,
    accent_color: tuple,
    seed: int = 42,
) -> np.ndarray:
    """Add subtle particle/star effect to background."""
    rng = np.random.RandomState(seed)
    height, width = frame.shape[:2]
    n_particles = 80
    xs = rng.randint(0, width, n_particles)
    ys = rng.randint(0, height, n_particles)
    sizes = rng.randint(1, 4, n_particles)
    alphas = rng.uniform(0.2, 0.8, n_particles)

    result = frame.copy()
    for x, y, size, alpha in zip(xs, ys, sizes, alphas):
        for dy in range(-size, size + 1):
            for dx in range(-size, size + 1):
                ny, nx = y + dy, x + dx
                if 0 <= ny < height and 0 <= nx < width:
                    for c in range(3):
                        result[ny, nx, c] = min(
                            255,
                            int(
                                result[ny, nx, c] * (1 - alpha)
                                + accent_color[c] * alpha
                            ),
                        )
    return result


def _render_text_on_frame(
    frame: np.ndarray,
    title: str,
    section_title: Optional[str],
    section_number: Optional[int],
    total_sections: Optional[int],
    colors: dict,
    progress: float = 0.0,
) -> np.ndarray:
    """
    Render text overlays on a video frame using Pillow.
    Returns modified numpy array.
    """
    img = Image.fromarray(frame)
    draw = ImageDraw.Draw(img)
    width, height = img.size

    # Try to load a font, fall back to default
    font_large = None
    font_medium = None
    font_small = None

    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        str(ASSETS_DIR / "fonts" / "Roboto-Bold.ttf"),
    ]

    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                font_large = ImageFont.truetype(font_path, 72)
                font_medium = ImageFont.truetype(font_path, 48)
                font_small = ImageFont.truetype(font_path, 32)
                break
            except Exception:
                continue

    if font_large is None:
        font_large = ImageFont.load_default()
        font_medium = font_large
        font_small = font_large

    primary = colors["primary"]
    accent = colors["accent"]
    text_color = colors["text"]

    # Draw video title at top (wrapped)
    title_lines = textwrap.wrap(title, width=40)
    y_offset = 60
    for line in title_lines[:2]:
        bbox = draw.textbbox((0, 0), line, font=font_medium)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2
        # Shadow
        draw.text((x + 3, y_offset + 3), line, fill=(0, 0, 0, 180), font=font_medium)
        draw.text((x, y_offset), line, fill=primary, font=font_medium)
        y_offset += 60

    # Draw section title in center
    if section_title:
        section_lines = textwrap.wrap(section_title, width=35)
        center_y = height // 2 - len(section_lines) * 45
        for line in section_lines:
            bbox = draw.textbbox((0, 0), line, font=font_large)
            text_w = bbox[2] - bbox[0]
            x = (width - text_w) // 2
            # Glow effect
            for offset in [(4, 4), (-4, -4), (4, -4), (-4, 4)]:
                draw.text(
                    (x + offset[0], center_y + offset[1]),
                    line,
                    fill=(*accent, 100),
                    font=font_large,
                )
            draw.text((x + 2, center_y + 2), line, fill=(0, 0, 0), font=font_large)
            draw.text((x, center_y), line, fill=text_color, font=font_large)
            center_y += 90

    # Draw section progress indicator
    if section_number is not None and total_sections is not None:
        progress_text = f"Part {section_number} of {total_sections}"
        bbox = draw.textbbox((0, 0), progress_text, font=font_small)
        text_w = bbox[2] - bbox[0]
        x = width - text_w - 40
        draw.text(
            (x, height - 70),
            progress_text,
            fill=(*primary, 200),
            font=font_small,
        )

    # Draw progress bar at bottom
    bar_height = 8
    bar_y = height - bar_height
    draw.rectangle([0, bar_y, width, height], fill=(30, 30, 30))
    bar_width = int(width * progress)
    if bar_width > 0:
        draw.rectangle([0, bar_y, bar_width, height], fill=primary)

    return np.array(img)


def create_video_from_script(
    script: VideoScript,
    audio_path: Path,
    background_music_path: Optional[Path] = None,
) -> Path:
    """
    Create a complete YouTube video from script and audio.
    Returns path to the output video file.
    """
    try:
        from moviepy import (
            AudioFileClip,
            CompositeAudioClip,
            CompositeVideoClip,
            ImageClip,
            concatenate_videoclips,
        )
    except ImportError:
        logger.error("MoviePy not installed. Run: pip install moviepy")
        raise

    logger.info(f"Creating video for: {script.title}")

    safe_title = "".join(
        c if c.isalnum() or c in (" ", "-", "_") else "" for c in script.title
    )[:50]
    output_path = VIDEOS_DIR / f"{safe_title}.mp4"

    if output_path.exists():
        logger.info(f"Video already exists: {output_path}")
        return output_path

    colors = _get_color_scheme(script.niche)
    audio_duration = get_audio_duration(audio_path)

    if audio_duration <= 0:
        raise ValueError(f"Invalid audio duration: {audio_duration}")

    # Build a list of image clips, one per section
    clips = []
    n_sections = len(script.sections)
    section_duration = audio_duration / max(n_sections, 1)

    # Intro/hook clip
    hook_frame = _create_gradient_frame(
        VIDEO_WIDTH,
        VIDEO_HEIGHT,
        colors["background"],
        tuple(max(0, c + 20) for c in colors["background"]),
    )
    hook_frame = _add_particle_effect(hook_frame, colors["accent"], seed=0)
    hook_frame = _render_text_on_frame(
        hook_frame,
        script.title,
        section_title=None,
        section_number=None,
        total_sections=None,
        colors=colors,
        progress=0.0,
    )
    hook_clip = ImageClip(hook_frame, duration=section_duration * 0.5)
    clips.append(hook_clip)

    for idx, section in enumerate(script.sections):
        progress = (idx + 1) / n_sections

        # Vary gradient slightly per section
        bg1 = tuple(
            max(0, min(255, c + random.randint(-10, 10)))
            for c in colors["background"]
        )
        bg2 = tuple(
            max(0, min(255, c + random.randint(5, 30)))
            for c in colors["background"]
        )
        frame = _create_gradient_frame(VIDEO_WIDTH, VIDEO_HEIGHT, bg1, bg2)
        frame = _add_particle_effect(frame, colors["accent"], seed=idx)
        frame = _render_text_on_frame(
            frame,
            script.title,
            section_title=section.get("section_title", ""),
            section_number=idx + 1,
            total_sections=n_sections,
            colors=colors,
            progress=progress,
        )

        clip = ImageClip(frame, duration=section_duration)
        clips.append(clip)

    # Outro clip
    outro_frame = _create_gradient_frame(
        VIDEO_WIDTH,
        VIDEO_HEIGHT,
        colors["background"],
        tuple(max(0, c - 10) for c in colors["background"]),
    )
    outro_frame = _render_text_on_frame(
        outro_frame,
        script.title,
        section_title="Subscribe for more!",
        section_number=None,
        total_sections=None,
        colors=colors,
        progress=1.0,
    )
    outro_clip = ImageClip(outro_frame, duration=section_duration * 0.5)
    clips.append(outro_clip)

    # Concatenate all clips
    video = concatenate_videoclips(clips, method="compose")
    video = video.with_fps(VIDEO_FPS)

    # Add narration audio
    narration_audio = AudioFileClip(str(audio_path))

    # Trim video to match audio if needed
    if video.duration > narration_audio.duration:
        video = video.subclipped(0, narration_audio.duration)
    elif narration_audio.duration > video.duration:
        narration_audio = narration_audio.subclipped(0, video.duration)

    # Mix with background music if provided
    if background_music_path and background_music_path.exists():
        bg_music = AudioFileClip(str(background_music_path))
        bg_music = bg_music.with_volume_scaled(0.08)
        if bg_music.duration < narration_audio.duration:
            # Loop the music
            loops = int(narration_audio.duration / bg_music.duration) + 1
            bg_segments = [bg_music] * loops
            from moviepy import concatenate_audioclips
            bg_music = concatenate_audioclips(bg_segments).subclipped(
                0, narration_audio.duration
            )
        else:
            bg_music = bg_music.subclipped(0, narration_audio.duration)
        final_audio = CompositeAudioClip([narration_audio, bg_music])
    else:
        final_audio = narration_audio

    video = video.with_audio(final_audio)

    # Export
    logger.info(f"Rendering video: {output_path}")
    video.write_videofile(
        str(output_path),
        fps=VIDEO_FPS,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        preset="fast",
        logger=None,
    )

    logger.info(f"Video created: {output_path}")
    return output_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"Video creator ready. Output dir: {VIDEOS_DIR}")
    print(f"Available color schemes: {list(COLOR_SCHEMES.keys())}")
