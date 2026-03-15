"""
YouTube Uploader Module
Handles authentication and video uploading to YouTube using
the YouTube Data API v3 with resumable uploads.
"""
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from youtube_cash_cow.config import (
    UPLOAD_ENABLED,
    YOUTUBE_CLIENT_SECRETS_FILE,
)
from youtube_cash_cow.modules.script_writer import VideoScript

logger = logging.getLogger(__name__)

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
TOKEN_FILE = "youtube_token.json"

# Resumable upload chunk size: 1MB
CHUNK_SIZE = 1024 * 1024

# Category IDs (YouTube)
CATEGORY_IDS = {
    "education": "27",
    "entertainment": "24",
    "science": "28",
    "howto": "26",
    "news": "25",
}


def _get_authenticated_service():
    """
    Authenticate with YouTube API using OAuth2.
    Returns authenticated service object.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        raise ImportError(
            "Google API libraries not installed. "
            "Run: pip install google-api-python-client google-auth-oauthlib"
        )

    creds = None

    # Load existing token
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(
            TOKEN_FILE, [YOUTUBE_UPLOAD_SCOPE]
        )

    # Refresh or re-authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(YOUTUBE_CLIENT_SECRETS_FILE):
                raise FileNotFoundError(
                    f"YouTube client secrets file not found: {YOUTUBE_CLIENT_SECRETS_FILE}\n"
                    "Download it from https://console.cloud.google.com"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                YOUTUBE_CLIENT_SECRETS_FILE, [YOUTUBE_UPLOAD_SCOPE]
            )
            creds = flow.run_local_server(port=0)

        # Save token for future use
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build(
        YOUTUBE_API_SERVICE_NAME,
        YOUTUBE_API_VERSION,
        credentials=creds,
    )


def _build_video_metadata(
    script: VideoScript,
    niche: str,
    privacy_status: str = "private",
) -> dict:
    """Build YouTube video metadata from script."""
    category_map = {
        "top10": CATEGORY_IDS["entertainment"],
        "facts": CATEGORY_IDS["education"],
        "educational": CATEGORY_IDS["education"],
        "motivational": CATEGORY_IDS["howto"],
        "mystery": CATEGORY_IDS["entertainment"],
    }

    return {
        "snippet": {
            "title": script.title[:100],  # YouTube max: 100 chars
            "description": script.description[:5000],  # YouTube max: 5000 chars
            "tags": script.tags[:500],  # YouTube max: 500 chars total
            "categoryId": category_map.get(niche, CATEGORY_IDS["entertainment"]),
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }


def upload_video(
    video_path: Path,
    script: VideoScript,
    thumbnail_path: Optional[Path] = None,
    privacy_status: str = "private",
    retry_count: int = 3,
) -> Optional[str]:
    """
    Upload a video to YouTube with metadata and optional thumbnail.

    Args:
        video_path: Path to the video file
        script: VideoScript with title, description, tags
        thumbnail_path: Optional path to thumbnail image
        privacy_status: "private", "unlisted", or "public"
        retry_count: Number of upload retry attempts

    Returns:
        YouTube video ID if successful, None otherwise
    """
    if not UPLOAD_ENABLED:
        logger.info(
            "YouTube upload disabled (UPLOAD_ENABLED=false). "
            f"Would upload: {video_path.name}"
        )
        return None

    if not video_path.exists():
        logger.error(f"Video file not found: {video_path}")
        return None

    try:
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        logger.error("Google API client not installed")
        return None

    logger.info(f"Uploading video: {script.title}")
    youtube = _get_authenticated_service()
    metadata = _build_video_metadata(script, script.niche, privacy_status)

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=CHUNK_SIZE,
    )

    for attempt in range(retry_count):
        try:
            request = youtube.videos().insert(
                part="snippet,status",
                body=metadata,
                media_body=media,
            )

            video_id = None
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    logger.info(f"Upload progress: {progress}%")

            video_id = response.get("id")
            logger.info(f"Video uploaded successfully! ID: {video_id}")
            logger.info(f"Watch at: https://www.youtube.com/watch?v={video_id}")

            # Upload thumbnail if provided
            if thumbnail_path and thumbnail_path.exists() and video_id:
                _upload_thumbnail(youtube, video_id, thumbnail_path)

            return video_id

        except Exception as e:
            logger.warning(f"Upload attempt {attempt + 1} failed: {e}")
            if attempt < retry_count - 1:
                wait = 2 ** attempt * 5  # Exponential backoff: 5s, 10s, 20s
                logger.info(f"Retrying in {wait} seconds...")
                time.sleep(wait)
            else:
                logger.error(f"Upload failed after {retry_count} attempts")
                return None

    return None


def _upload_thumbnail(youtube, video_id: str, thumbnail_path: Path) -> bool:
    """Upload a custom thumbnail for a video."""
    try:
        from googleapiclient.http import MediaFileUpload

        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/png"),
        ).execute()
        logger.info(f"Thumbnail uploaded for video {video_id}")
        return True
    except Exception as e:
        logger.warning(f"Failed to upload thumbnail: {e}")
        return False


def get_channel_stats(youtube=None) -> Optional[dict]:
    """Fetch basic channel statistics."""
    try:
        if youtube is None:
            youtube = _get_authenticated_service()

        response = youtube.channels().list(
            part="statistics,snippet",
            mine=True,
        ).execute()

        if response.get("items"):
            channel = response["items"][0]
            stats = channel.get("statistics", {})
            snippet = channel.get("snippet", {})
            return {
                "name": snippet.get("title"),
                "subscribers": int(stats.get("subscriberCount", 0)),
                "views": int(stats.get("viewCount", 0)),
                "videos": int(stats.get("videoCount", 0)),
            }
    except Exception as e:
        logger.error(f"Failed to get channel stats: {e}")
    return None


def save_upload_record(
    video_id: Optional[str],
    script: VideoScript,
    video_path: Path,
    thumbnail_path: Optional[Path],
) -> None:
    """Save upload metadata to a local JSON record."""
    record_path = Path("logs") / "uploads.jsonl"
    record_path.parent.mkdir(exist_ok=True)

    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "video_id": video_id,
        "title": script.title,
        "niche": script.niche,
        "video_file": str(video_path),
        "thumbnail_file": str(thumbnail_path) if thumbnail_path else None,
        "tags": script.tags,
        "uploaded": video_id is not None,
    }

    with open(record_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    logger.info(f"Upload record saved: {record_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if not UPLOAD_ENABLED:
        print("Upload is disabled. Set UPLOAD_ENABLED=true in .env to enable.")
    else:
        stats = get_channel_stats()
        if stats:
            print(f"Channel: {stats['name']}")
            print(f"Subscribers: {stats['subscribers']:,}")
            print(f"Total Views: {stats['views']:,}")
            print(f"Videos: {stats['videos']}")
