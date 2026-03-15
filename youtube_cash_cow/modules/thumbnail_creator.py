"""
Thumbnail Creator Module
Creates eye-catching YouTube thumbnails using Pillow.
Thumbnails are critical for CTR (Click-Through Rate) in cash cow channels.
Uses bold text, high-contrast colors, and engaging visual design.
"""
import logging
import os
import textwrap
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from youtube_cash_cow.config import ASSETS_DIR, THUMBNAILS_DIR
from youtube_cash_cow.modules.video_creator import COLOR_SCHEMES

logger = logging.getLogger(__name__)

THUMBNAIL_WIDTH = 1280
THUMBNAIL_HEIGHT = 720


def _get_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    """Load a font, falling back to default if not found."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        str(ASSETS_DIR / "fonts" / "Roboto-Bold.ttf"),
    ]
    if not bold:
        font_paths = [p.replace("Bold", "").replace("-B.", ".") for p in font_paths]

    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_outlined_text(
    draw: ImageDraw.ImageDraw,
    position: tuple,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill_color: tuple,
    outline_color: tuple = (0, 0, 0),
    outline_width: int = 4,
) -> None:
    """Draw text with a solid outline for better readability."""
    x, y = position
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
    draw.text((x, y), text, font=font, fill=fill_color)


def _draw_badge(
    draw: ImageDraw.ImageDraw,
    text: str,
    position: tuple,
    font: ImageFont.FreeTypeFont,
    bg_color: tuple,
    text_color: tuple = (255, 255, 255),
    padding: int = 15,
) -> None:
    """Draw a colored badge/pill with text."""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x, y = position
    rect = [
        x - padding,
        y - padding,
        x + text_w + padding,
        y + text_h + padding,
    ]
    draw.rounded_rectangle(rect, radius=10, fill=bg_color)
    draw.text((x, y), text, font=font, fill=text_color)


def create_thumbnail(
    title: str,
    niche: str,
    thumbnail_text: str,
    output_filename: Optional[str] = None,
    section_number: Optional[int] = None,
) -> Path:
    """
    Create an eye-catching YouTube thumbnail.

    Args:
        title: Full video title
        niche: Channel niche (determines color scheme)
        thumbnail_text: Short punchy text for overlay (e.g., "TOP 10 SHOCKING")
        output_filename: Custom output filename (auto-generated if None)
        section_number: For numbered list videos (e.g., Top 10)

    Returns:
        Path to the saved thumbnail PNG file.
    """
    colors = COLOR_SCHEMES.get(niche, COLOR_SCHEMES["facts"])
    bg_color = colors["background"]
    primary = colors["primary"]
    secondary = colors["secondary"]
    accent = colors["accent"]

    # Create base image
    img = Image.new("RGB", (THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), color=bg_color)
    draw = ImageDraw.Draw(img)

    # --- Background: diagonal gradient stripes ---
    for i in range(0, THUMBNAIL_WIDTH + THUMBNAIL_HEIGHT, 40):
        alpha = 0.05
        r = int(bg_color[0] + (primary[0] - bg_color[0]) * alpha)
        g = int(bg_color[1] + (primary[1] - bg_color[1]) * alpha)
        b = int(bg_color[2] + (primary[2] - bg_color[2]) * alpha)
        draw.line(
            [(i, 0), (0, i)],
            fill=(r, g, b),
            width=2,
        )

    # --- Left accent bar ---
    draw.rectangle([0, 0, 18, THUMBNAIL_HEIGHT], fill=primary)

    # --- Large number or emoji area (left side) ---
    if section_number is not None:
        num_font = _get_font(220)
        num_text = str(section_number)
        bbox = draw.textbbox((0, 0), num_text, font=num_font)
        num_w = bbox[2] - bbox[0]
        num_x = 80
        num_y = (THUMBNAIL_HEIGHT - (bbox[3] - bbox[1])) // 2
        # Number shadow
        draw.text((num_x + 8, num_y + 8), num_text, font=num_font, fill=(0, 0, 0))
        draw.text((num_x, num_y), num_text, font=num_font, fill=primary)
        text_start_x = num_x + num_w + 40
    else:
        text_start_x = 80

    # --- Main thumbnail text (large, centered vertically) ---
    main_font = _get_font(90)
    lines = textwrap.wrap(thumbnail_text.upper(), width=18)[:3]

    total_text_height = len(lines) * 110
    text_y = (THUMBNAIL_HEIGHT - total_text_height) // 2

    text_area_width = THUMBNAIL_WIDTH - text_start_x - 40
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=main_font)
        line_w = bbox[2] - bbox[0]
        x = text_start_x + (text_area_width - line_w) // 2
        _draw_outlined_text(
            draw,
            (x, text_y),
            line,
            font=main_font,
            fill_color=(255, 255, 255),
            outline_color=(0, 0, 0),
            outline_width=5,
        )
        text_y += 110

    # --- Subtitle (shorter title excerpt) ---
    subtitle_font = _get_font(38, bold=False)
    subtitle = title[:60] + ("..." if len(title) > 60 else "")
    sub_lines = textwrap.wrap(subtitle, width=45)[:2]
    sub_y = THUMBNAIL_HEIGHT - 120
    for line in sub_lines:
        bbox = draw.textbbox((0, 0), line, font=subtitle_font)
        line_w = bbox[2] - bbox[0]
        x = (THUMBNAIL_WIDTH - line_w) // 2
        _draw_outlined_text(
            draw,
            (x, sub_y),
            line,
            font=subtitle_font,
            fill_color=(220, 220, 220),
            outline_color=(0, 0, 0),
            outline_width=3,
        )
        sub_y += 50

    # --- Top-right badge ---
    badge_font = _get_font(32)
    niche_labels = {
        "top10": "TOP 10",
        "facts": "FACTS",
        "educational": "LEARN",
        "motivational": "MINDSET",
        "mystery": "MYSTERY",
    }
    badge_text = niche_labels.get(niche, "WATCH")
    bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    badge_x = THUMBNAIL_WIDTH - (bbox[2] - bbox[0]) - 60
    _draw_badge(
        draw,
        badge_text,
        (badge_x, 30),
        font=badge_font,
        bg_color=accent,
        text_color=(0, 0, 0),
        padding=12,
    )

    # --- Bottom accent line ---
    draw.rectangle(
        [0, THUMBNAIL_HEIGHT - 12, THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT],
        fill=primary,
    )

    # Apply slight blur to background (keeps text sharp via layer approach)
    # This is done by blurring a copy and compositing
    blurred = img.filter(ImageFilter.GaussianBlur(radius=1))
    img = Image.blend(img, blurred, alpha=0.1)

    # Save thumbnail
    if output_filename is None:
        safe_title = "".join(
            c if c.isalnum() or c in (" ", "-", "_") else "" for c in title
        )[:50]
        output_filename = f"{safe_title}_thumb.png"

    output_path = THUMBNAILS_DIR / output_filename
    img.save(str(output_path), "PNG", quality=95)
    logger.info(f"Thumbnail saved: {output_path} ({THUMBNAIL_WIDTH}x{THUMBNAIL_HEIGHT})")
    return output_path


def create_thumbnail_variants(
    title: str,
    niche: str,
    thumbnail_text: str,
    count: int = 3,
) -> list[Path]:
    """
    Create multiple thumbnail variants for A/B testing.
    Returns list of thumbnail paths.
    """
    paths = []
    safe_title = "".join(
        c if c.isalnum() or c in (" ", "-", "_") else "" for c in title
    )[:40]

    for i in range(count):
        filename = f"{safe_title}_thumb_v{i + 1}.png"
        # Rotate through section numbers for visual variety
        section_num = i + 1 if i < 9 else None
        path = create_thumbnail(
            title=title,
            niche=niche,
            thumbnail_text=thumbnail_text,
            output_filename=filename,
            section_number=section_num,
        )
        paths.append(path)

    logger.info(f"Created {len(paths)} thumbnail variants")
    return paths


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    path = create_thumbnail(
        title="Top 10 Most Dangerous Animals in the World",
        niche="top10",
        thumbnail_text="MOST DANGEROUS",
        section_number=10,
    )
    print(f"Thumbnail saved: {path}")
