"""
Core pipeline: topic → script → TTS → assets → video → post.

Usage:
    from src.pipeline import run_pipeline
    run_pipeline(topic="passive income ideas")
"""

import logging
import random
import uuid
from pathlib import Path
from typing import Optional

from config.settings import NICHE_TOPICS

logger = logging.getLogger(__name__)


def run_pipeline(topic: Optional[str] = None, dry_run: bool = False) -> dict:
    """
    Execute the full funnel for a single video.

    Parameters
    ----------
    topic   : content topic (random niche if None)
    dry_run : if True, skip the actual social-media posting step

    Returns a result dict with keys: topic, video_path, post_results, success
    """
    if topic is None:
        topic = random.choice(NICHE_TOPICS)

    logger.info("=" * 60)
    logger.info("Starting pipeline | topic: %s", topic)
    result = {"topic": topic, "video_path": None, "post_results": {}, "success": False}

    # ── 1. Generate script ────────────────────────────────────────────────
    logger.info("[1/5] Generating script...")
    from src.generator.script_writer import generate_script, generate_title_and_description
    script_data = generate_script(topic)
    meta = generate_title_and_description(script_data)
    logger.info("Script: %s", script_data.get("hook"))

    # ── 2. Convert script to audio ────────────────────────────────────────
    logger.info("[2/5] Converting script to audio (TTS)...")
    from src.generator.tts import text_to_speech, get_audio_duration
    audio_path = text_to_speech(script_data["full_script"])
    if audio_path is None:
        logger.error("TTS failed — aborting pipeline")
        return result
    audio_duration = get_audio_duration(audio_path)
    logger.info("Audio duration: %.1fs", audio_duration)

    # ── 3. Fetch royalty-free media ───────────────────────────────────────
    logger.info("[3/5] Fetching royalty-free media from Pexels/Pixabay...")
    from src.fetcher.media_pool import get_videos, get_photos
    video_paths = get_videos(topic, count=6)
    photo_paths = get_photos(topic, count=4)
    logger.info("Got %d video clips and %d photos", len(video_paths), len(photo_paths))

    if not video_paths and not photo_paths:
        logger.error("No media assets fetched — aborting pipeline")
        return result

    # ── 4. Build the video ────────────────────────────────────────────────
    logger.info("[4/5] Assembling video...")
    from src.editor.video_builder import build_video
    output_name = f"{topic.replace(' ', '_')}_{uuid.uuid4().hex[:6]}.mp4"
    video_path = build_video(
        video_paths=video_paths,
        photo_paths=photo_paths,
        audio_path=audio_path,
        script_data=script_data,
        output_filename=output_name,
    )
    if video_path is None:
        logger.error("Video build failed — aborting pipeline")
        return result

    result["video_path"] = str(video_path)
    logger.info("Video ready: %s", video_path)

    # ── 5. Post to social media ───────────────────────────────────────────
    if dry_run:
        logger.info("[5/5] DRY RUN — skipping social-media posting")
        result["success"] = True
        return result

    logger.info("[5/5] Posting to social media...")
    from src.poster.dispatcher import post_to_all_platforms
    post_results = post_to_all_platforms(
        video_path=video_path,
        script_data=script_data,
        meta=meta,
    )
    result["post_results"] = post_results
    result["success"] = any(v is not None for v in post_results.values())

    logger.info("Post results: %s", post_results)
    logger.info("Pipeline complete | success=%s", result["success"])
    return result
