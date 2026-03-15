"""Unified media pool — tries Pexels first, falls back to Pixabay."""

import logging
from pathlib import Path

from src.fetcher import pexels, pixabay

logger = logging.getLogger(__name__)


def get_videos(topic: str, count: int = 6) -> list[Path]:
    paths = pexels.fetch_videos_for_topic(topic, count)
    if len(paths) < count:
        logger.info("Pexels returned %d/%d videos, supplementing from Pixabay", len(paths), count)
        extra = pixabay.fetch_videos_for_topic(topic, count - len(paths))
        paths.extend(extra)
    return paths[:count]


def get_photos(topic: str, count: int = 6) -> list[Path]:
    paths = pexels.fetch_photos_for_topic(topic, count)
    if len(paths) < count:
        extra = pixabay.fetch_photos_for_topic(topic, count - len(paths))
        paths.extend(extra)
    return paths[:count]
