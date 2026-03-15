"""Fetch royalty-free videos and photos from Pexels."""

import logging
import time
from pathlib import Path
from typing import Optional

import requests

from config.settings import PEXELS_API_KEY, VIDEOS_DIR, IMAGES_DIR

logger = logging.getLogger(__name__)

BASE_URL = "https://api.pexels.com"
HEADERS = {"Authorization": PEXELS_API_KEY}


def search_videos(query: str, count: int = 5, min_duration: int = 5, max_duration: int = 30) -> list[dict]:
    """Return up to *count* video metadata dicts matching the query."""
    url = f"{BASE_URL}/videos/search"
    params = {
        "query": query,
        "per_page": min(count * 2, 40),   # fetch more, filter later
        "orientation": "portrait",
        "size": "medium",
    }
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Pexels video search failed: %s", exc)
        return []

    videos = []
    for item in resp.json().get("videos", []):
        duration = item.get("duration", 0)
        if min_duration <= duration <= max_duration:
            # Pick the smallest HD file available
            files = sorted(
                [f for f in item.get("video_files", []) if f.get("quality") in ("hd", "sd")],
                key=lambda f: f.get("width", 0),
            )
            if files:
                videos.append({
                    "id": item["id"],
                    "url": files[0]["link"],
                    "width": files[0]["width"],
                    "height": files[0]["height"],
                    "duration": duration,
                    "photographer": item.get("user", {}).get("name", "Unknown"),
                })
        if len(videos) >= count:
            break
    return videos


def search_photos(query: str, count: int = 5) -> list[dict]:
    """Return up to *count* photo metadata dicts."""
    url = f"{BASE_URL}/v1/search"
    params = {"query": query, "per_page": count, "orientation": "portrait"}
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Pexels photo search failed: %s", exc)
        return []

    photos = []
    for item in resp.json().get("photos", []):
        photos.append({
            "id": item["id"],
            "url": item["src"]["large"],
            "photographer": item.get("photographer", "Unknown"),
        })
    return photos


def download_file(url: str, dest: Path, retries: int = 3) -> Optional[Path]:
    """Download *url* to *dest*, return path on success."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    for attempt in range(retries):
        try:
            with requests.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            logger.info("Downloaded %s", dest.name)
            return dest
        except requests.RequestException as exc:
            logger.warning("Download attempt %d failed: %s", attempt + 1, exc)
            time.sleep(2 ** attempt)
    return None


def fetch_videos_for_topic(topic: str, count: int = 5) -> list[Path]:
    """Fetch and cache videos for a topic; return local paths."""
    metas = search_videos(topic, count=count)
    paths = []
    for m in metas:
        ext = "mp4"
        dest = VIDEOS_DIR / f"pexels_{m['id']}.{ext}"
        path = download_file(m["url"], dest)
        if path:
            paths.append(path)
    return paths


def fetch_photos_for_topic(topic: str, count: int = 5) -> list[Path]:
    """Fetch and cache photos for a topic; return local paths."""
    metas = search_photos(topic, count=count)
    paths = []
    for m in metas:
        dest = IMAGES_DIR / f"pexels_{m['id']}.jpg"
        path = download_file(m["url"], dest)
        if path:
            paths.append(path)
    return paths
