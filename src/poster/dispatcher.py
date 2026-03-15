"""Route a finished video to all enabled social platforms."""

import logging
from pathlib import Path
from typing import Optional

from config.settings import ENABLED_PLATFORMS

logger = logging.getLogger(__name__)


def post_to_all_platforms(
    video_path: Path,
    script_data: dict,
    meta: dict,
    thumbnail_path: Optional[Path] = None,
) -> dict[str, Optional[str]]:
    """
    Post *video_path* to every enabled platform.

    Returns a dict mapping platform name → post ID (or None on failure).
    """
    results: dict[str, Optional[str]] = {}
    caption = _build_caption(script_data, meta)

    if "instagram" in ENABLED_PLATFORMS:
        from src.poster.instagram import post_reel
        results["instagram"] = post_reel(video_path, caption, thumbnail_path)

    if "youtube" in ENABLED_PLATFORMS:
        from src.poster.youtube import upload_short
        results["youtube"] = upload_short(
            video_path,
            title=meta.get("title", script_data.get("topic", "Viral Short")),
            description=meta.get("description", caption),
            tags=meta.get("tags", script_data.get("hashtags", [])),
            thumbnail_path=thumbnail_path,
        )

    if "tiktok" in ENABLED_PLATFORMS:
        from src.poster.tiktok import post_video
        results["tiktok"] = post_video(
            video_path,
            caption=meta.get("title", script_data.get("hook", "")),
            hashtags=script_data.get("hashtags", []),
        )

    return results


def _build_caption(script_data: dict, meta: dict) -> str:
    hook = script_data.get("hook", "")
    cta = script_data.get("cta", "")
    tags = " ".join(f"#{h}" for h in script_data.get("hashtags", [])[:10])
    return f"{hook}\n\n{cta}\n\n{tags}"
