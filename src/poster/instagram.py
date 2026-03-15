"""Post Reels to Instagram via instagrapi."""

import logging
from pathlib import Path
from typing import Optional

from config.settings import INSTAGRAM_PASSWORD, INSTAGRAM_USERNAME

logger = logging.getLogger(__name__)
_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    try:
        from instagrapi import Client
    except ImportError:
        raise RuntimeError("instagrapi not installed. Run: pip install instagrapi")

    if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
        raise RuntimeError("Instagram credentials not set in .env")

    cl = Client()
    session_file = Path("config/instagram_session.json")
    if session_file.exists():
        try:
            cl.load_settings(session_file)
            cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            logger.info("Instagram: reused saved session")
        except Exception:
            logger.warning("Instagram: saved session invalid, re-logging in")
            cl = Client()
            cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
    else:
        cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
        cl.dump_settings(session_file)
        logger.info("Instagram: logged in and saved session")
    _client = cl
    return _client


def post_reel(
    video_path: Path,
    caption: str,
    thumbnail_path: Optional[Path] = None,
) -> Optional[str]:
    """Upload a Reel. Returns the media ID on success."""
    try:
        cl = _get_client()
        media = cl.clip_upload(
            path=video_path,
            caption=caption,
            thumbnail=thumbnail_path,
        )
        media_id = media.pk
        logger.info("Instagram Reel posted: %s", media_id)
        return str(media_id)
    except Exception as exc:
        logger.error("Instagram post failed: %s", exc)
        return None
