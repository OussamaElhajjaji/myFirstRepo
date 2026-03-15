"""
Post videos to TikTok.

TikTok provides two upload methods:
  1. Content Posting API  — requires approved developer access (preferred)
  2. Direct share via session cookie — fallback, informal approach

This module implements the official Content Posting API approach.
Docs: https://developers.tiktok.com/doc/content-posting-api-get-started
"""

import logging
import time
from pathlib import Path
from typing import Optional

import requests

from config.settings import TIKTOK_SESSION_ID

logger = logging.getLogger(__name__)

# Replace with your approved app credentials
TIKTOK_CLIENT_KEY = ""      # set via env if needed
TIKTOK_CLIENT_SECRET = ""   # set via env if needed
TIKTOK_ACCESS_TOKEN = ""    # OAuth2 token obtained via auth flow


def _get_access_token() -> str:
    """Return a valid TikTok access token (reads from env/config)."""
    import os
    token = os.getenv("TIKTOK_ACCESS_TOKEN", TIKTOK_ACCESS_TOKEN)
    if not token:
        raise RuntimeError(
            "TIKTOK_ACCESS_TOKEN not set. Complete OAuth2 flow first.\n"
            "See: https://developers.tiktok.com/doc/oauth-user-access-token-management"
        )
    return token


def _init_video_upload(access_token: str, file_size: int) -> dict:
    """Call the TikTok init upload endpoint and return upload info."""
    url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    body = {
        "post_info": {
            "title": "",           # filled later
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": file_size,
            "chunk_size": file_size,
            "total_chunk_count": 1,
        },
    }
    resp = requests.post(url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _upload_video_chunk(upload_url: str, video_bytes: bytes, file_size: int) -> None:
    headers = {
        "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
        "Content-Type": "video/mp4",
    }
    resp = requests.put(upload_url, headers=headers, data=video_bytes, timeout=120)
    resp.raise_for_status()


def _publish_video(access_token: str, publish_id: str, title: str) -> dict:
    url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    # Title update is handled during init; this polls status
    status_url = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    for _ in range(10):
        resp = requests.post(status_url, headers=headers, json={"publish_id": publish_id}, timeout=15)
        data = resp.json()
        status = data.get("data", {}).get("status", "")
        if status in ("PUBLISH_COMPLETE", "FAILED"):
            return data
        time.sleep(3)
    return {}


def post_video(
    video_path: Path,
    caption: str,
    hashtags: Optional[list[str]] = None,
) -> Optional[str]:
    """Upload a video to TikTok. Returns publish_id on success."""
    try:
        access_token = _get_access_token()
    except RuntimeError as exc:
        logger.error("TikTok auth error: %s", exc)
        return None

    try:
        video_bytes = video_path.read_bytes()
        file_size = len(video_bytes)

        # Build title with hashtags
        tag_str = " ".join(f"#{h}" for h in (hashtags or [])[:5])
        title = f"{caption[:100]} {tag_str}".strip()[:150]

        init_resp = _init_video_upload(access_token, file_size)
        data = init_resp.get("data", {})
        upload_url = data.get("upload_url")
        publish_id = data.get("publish_id")

        if not upload_url or not publish_id:
            logger.error("TikTok init upload returned unexpected data: %s", init_resp)
            return None

        _upload_video_chunk(upload_url, video_bytes, file_size)
        result = _publish_video(access_token, publish_id, title)
        logger.info("TikTok video published: %s | result: %s", publish_id, result)
        return publish_id

    except Exception as exc:
        logger.error("TikTok upload failed: %s", exc)
        return None
