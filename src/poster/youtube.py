"""Upload YouTube Shorts via the YouTube Data API v3."""

import logging
import os
from pathlib import Path
from typing import Optional

from config.settings import YOUTUBE_CLIENT_SECRETS_FILE, YOUTUBE_TOKEN_FILE

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
API_SERVICE = "youtube"
API_VERSION = "v3"


def _get_authenticated_service():
    """Return an authenticated YouTube service object."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError("Google API packages not installed. Run: pip install google-api-python-client google-auth-oauthlib")

    creds = None
    token_path = Path(YOUTUBE_TOKEN_FILE)
    secrets_path = Path(YOUTUBE_CLIENT_SECRETS_FILE)

    if not secrets_path.exists():
        raise FileNotFoundError(f"YouTube client secrets not found at {secrets_path}")

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return build(API_SERVICE, API_VERSION, credentials=creds)


def upload_short(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    thumbnail_path: Optional[Path] = None,
) -> Optional[str]:
    """Upload a YouTube Short. Returns the video ID on success."""
    try:
        from googleapiclient.http import MediaFileUpload
        youtube = _get_authenticated_service()

        body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": tags[:500],  # tag string has a 500-char limit
                "categoryId": "22",  # People & Blogs
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
        request = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)

        response = None
        while response is None:
            _, response = request.next_chunk()

        video_id = response.get("id")
        logger.info("YouTube Short uploaded: https://youtu.be/%s", video_id)

        if thumbnail_path and thumbnail_path.exists():
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_path)),
            ).execute()

        return video_id
    except Exception as exc:
        logger.error("YouTube upload failed: %s", exc)
        return None
