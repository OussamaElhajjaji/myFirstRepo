"""Fetch royalty-free videos and photos from Pixabay as a fallback source."""

import logging
import time
from pathlib import Path
from typing import Optional

import requests

from config.settings import PIXABAY_API_KEY, VIDEOS_DIR, IMAGES_DIR

logger = logging.getLogger(__name__)
BASE_URL = "https://pixabay.com/api"


def search_videos(query: str, count: int = 5) -> list[dict]:
    url = f"{BASE_URL}/videos/"
    params = {
        "key": PIXABAY_API_KEY,
        "q": query,
        "per_page": min(count * 2, 50),
        "video_type": "film",
        "safesearch": "true",
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Pixabay video search failed: %s", exc)
        return []

    results = []
    for hit in resp.json().get("hits", []):
        videos = hit.get("videos", {})
        src = videos.get("medium") or videos.get("small") or videos.get("large")
        if src:
            results.append({
                "id": hit["id"],
                "url": src["url"],
                "duration": hit.get("duration", 0),
            })
        if len(results) >= count:
            break
    return results


def search_photos(query: str, count: int = 5) -> list[dict]:
    url = f"{BASE_URL}/"
    params = {
        "key": PIXABAY_API_KEY,
        "q": query,
        "per_page": count,
        "image_type": "photo",
        "safesearch": "true",
        "orientation": "vertical",
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Pixabay photo search failed: %s", exc)
        return []

    return [{"id": h["id"], "url": h["largeImageURL"]} for h in resp.json().get("hits", [])[:count]]


def _download(url: str, dest: Path) -> Optional[Path]:
    if dest.exists():
        return dest
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
        return dest
    except requests.RequestException as exc:
        logger.error("Pixabay download failed: %s", exc)
        return None


def fetch_videos_for_topic(topic: str, count: int = 5) -> list[Path]:
    metas = search_videos(topic, count)
    return [p for m in metas if (p := _download(m["url"], VIDEOS_DIR / f"pixabay_{m['id']}.mp4"))]


def fetch_photos_for_topic(topic: str, count: int = 5) -> list[Path]:
    metas = search_photos(topic, count)
    return [p for m in metas if (p := _download(m["url"], IMAGES_DIR / f"pixabay_{m['id']}.jpg"))]
