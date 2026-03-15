"""
YouTube Cash Cow Channel Automation — Main Orchestrator
Runs the full pipeline:
  1. Generate trending topic
  2. Write video script (Claude API)
  3. Generate TTS narration audio
  4. Create video with text overlays
  5. Create thumbnail
  6. Upload to YouTube
  7. Log results
"""
import argparse
import json
import logging
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import schedule

from youtube_cash_cow.config import (
    ASSETS_DIR,
    CHANNEL_NICHE,
    LOGS_DIR,
    UPLOAD_ENABLED,
    UPLOAD_HOUR,
    VIDEOS_PER_DAY,
)
from youtube_cash_cow.modules.script_writer import VideoScript, generate_script
from youtube_cash_cow.modules.thumbnail_creator import create_thumbnail
from youtube_cash_cow.modules.topic_generator import select_best_topic
from youtube_cash_cow.modules.tts_generator import generate_audio_for_script
from youtube_cash_cow.modules.video_creator import create_video_from_script
from youtube_cash_cow.modules.youtube_uploader import save_upload_record, upload_video

# Configure logging
log_file = LOGS_DIR / f"automation_{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def run_pipeline(
    topic_override: dict | None = None,
    privacy_status: str = "private",
    skip_upload: bool = False,
) -> dict:
    """
    Run the complete video production pipeline for one video.

    Args:
        topic_override: Optional dict with 'title' and 'niche' to use instead
                        of auto-generating a topic.
        privacy_status: YouTube privacy status ('private', 'unlisted', 'public').
        skip_upload: If True, skip the YouTube upload step.

    Returns:
        Dict with pipeline results and output file paths.
    """
    start_time = time.time()
    result = {
        "success": False,
        "title": None,
        "niche": None,
        "script_path": None,
        "audio_path": None,
        "video_path": None,
        "thumbnail_path": None,
        "youtube_video_id": None,
        "duration_seconds": 0,
        "errors": [],
    }

    try:
        # ── Step 1: Topic Selection ──────────────────────────────────────
        logger.info("=" * 60)
        logger.info("STEP 1: Topic Selection")
        if topic_override:
            topic = topic_override
            logger.info(f"Using override topic: {topic['title']}")
        else:
            topic = select_best_topic(CHANNEL_NICHE)
            logger.info(f"Selected topic: {topic['title']} (niche: {topic['niche']})")

        result["title"] = topic["title"]
        result["niche"] = topic.get("niche", "facts")

        # ── Step 2: Script Generation ────────────────────────────────────
        logger.info("=" * 60)
        logger.info("STEP 2: Script Generation (Claude AI)")
        script = generate_script(topic)
        result["script_path"] = str(
            Path("output/scripts") / f"{script.title[:50]}.json"
        )
        logger.info(
            f"Script ready: {len(script.sections)} sections, "
            f"~{script.estimated_duration_seconds // 60}min"
        )

        # ── Step 3: Audio Generation ─────────────────────────────────────
        logger.info("=" * 60)
        logger.info("STEP 3: TTS Audio Generation")
        audio_path = generate_audio_for_script(script)
        result["audio_path"] = str(audio_path)
        logger.info(f"Audio ready: {audio_path.name}")

        # ── Step 4: Video Creation ────────────────────────────────────────
        logger.info("=" * 60)
        logger.info("STEP 4: Video Creation")
        bg_music_path = _find_background_music()
        if bg_music_path:
            logger.info(f"Using background music: {bg_music_path.name}")
        video_path = create_video_from_script(script, audio_path, bg_music_path)
        result["video_path"] = str(video_path)
        logger.info(f"Video ready: {video_path.name}")

        # ── Step 5: Thumbnail Creation ────────────────────────────────────
        logger.info("=" * 60)
        logger.info("STEP 5: Thumbnail Creation")
        thumbnail_path = create_thumbnail(
            title=script.title,
            niche=script.niche,
            thumbnail_text=script.thumbnail_text,
        )
        result["thumbnail_path"] = str(thumbnail_path)
        logger.info(f"Thumbnail ready: {thumbnail_path.name}")

        # ── Step 6: YouTube Upload ────────────────────────────────────────
        logger.info("=" * 60)
        logger.info("STEP 6: YouTube Upload")
        video_id = None
        if not skip_upload and UPLOAD_ENABLED:
            video_id = upload_video(
                video_path=video_path,
                script=script,
                thumbnail_path=thumbnail_path,
                privacy_status=privacy_status,
            )
            result["youtube_video_id"] = video_id
            if video_id:
                logger.info(f"Uploaded! https://www.youtube.com/watch?v={video_id}")
        else:
            reason = "upload disabled" if not UPLOAD_ENABLED else "skip_upload=True"
            logger.info(f"Skipping upload ({reason})")

        # ── Step 7: Save Record ───────────────────────────────────────────
        save_upload_record(video_id, script, video_path, thumbnail_path)

        elapsed = time.time() - start_time
        result["success"] = True
        result["duration_seconds"] = round(elapsed, 1)
        logger.info("=" * 60)
        logger.info(
            f"Pipeline complete in {elapsed:.1f}s! "
            f"Video: {video_path.name}"
        )

    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")
        result["errors"].append(str(e))

    return result


def _find_background_music() -> Path | None:
    """Find a background music file in the assets directory."""
    music_dir = ASSETS_DIR / "background_music"
    if not music_dir.exists():
        return None

    for ext in ("*.mp3", "*.wav", "*.ogg"):
        files = list(music_dir.glob(ext))
        if files:
            import random
            return random.choice(files)

    return None


def run_daily_automation() -> None:
    """Run the daily video production and upload routine."""
    logger.info(f"Starting daily automation — producing {VIDEOS_PER_DAY} video(s)")
    for i in range(VIDEOS_PER_DAY):
        if i > 0:
            logger.info("Waiting 5 minutes before next video...")
            time.sleep(300)
        result = run_pipeline()
        status = "SUCCESS" if result["success"] else "FAILED"
        logger.info(f"Video {i + 1}/{VIDEOS_PER_DAY}: {status}")


def start_scheduler() -> None:
    """Start the automated scheduler to upload at configured time daily."""
    logger.info(
        f"Starting scheduler — will produce/upload {VIDEOS_PER_DAY} video(s) "
        f"daily at {UPLOAD_HOUR:02d}:00"
    )
    schedule.every().day.at(f"{UPLOAD_HOUR:02d}:00").do(run_daily_automation)

    logger.info("Scheduler running. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(60)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="YouTube Cash Cow Channel Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run pipeline once (no upload)
  python -m youtube_cash_cow.main --run-once

  # Run with a specific topic
  python -m youtube_cash_cow.main --run-once --title "Top 10 Space Facts" --niche top10

  # Run and upload as private
  python -m youtube_cash_cow.main --run-once --privacy private

  # Start the daily scheduler
  python -m youtube_cash_cow.main --schedule

  # Generate only a script (no video/audio)
  python -m youtube_cash_cow.main --script-only --title "Amazing Ocean Facts"
        """,
    )

    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run the pipeline once and exit",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Start the daily automated scheduler",
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Override the video title",
    )
    parser.add_argument(
        "--niche",
        type=str,
        default=None,
        choices=["top10", "facts", "educational", "motivational", "mystery"],
        help="Override the video niche",
    )
    parser.add_argument(
        "--privacy",
        type=str,
        default="private",
        choices=["private", "unlisted", "public"],
        help="YouTube privacy status (default: private)",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip YouTube upload even if enabled",
    )
    parser.add_argument(
        "--script-only",
        action="store_true",
        help="Generate only the script (no audio/video)",
    )

    args = parser.parse_args()

    topic_override = None
    if args.title:
        topic_override = {
            "title": args.title,
            "niche": args.niche or "facts",
        }

    if args.script_only:
        topic = topic_override or select_best_topic(CHANNEL_NICHE)
        script = generate_script(topic)
        print(f"\n{'=' * 60}")
        print(f"TITLE: {script.title}")
        print(f"NICHE: {script.niche}")
        print(f"DURATION: ~{script.estimated_duration_seconds // 60}min")
        print(f"\nHOOK:\n{script.hook}")
        print(f"\nDESCRIPTION:\n{script.description}")
        print(f"\nTAGS: {', '.join(script.tags)}")
        print(f"\nTHUMBNAIL TEXT: {script.thumbnail_text}")
        return

    if args.run_once:
        result = run_pipeline(
            topic_override=topic_override,
            privacy_status=args.privacy,
            skip_upload=args.no_upload,
        )
        print(f"\n{'=' * 60}")
        print(f"RESULT: {'SUCCESS' if result['success'] else 'FAILED'}")
        print(f"Title: {result['title']}")
        if result["video_path"]:
            print(f"Video: {result['video_path']}")
        if result["thumbnail_path"]:
            print(f"Thumbnail: {result['thumbnail_path']}")
        if result["youtube_video_id"]:
            print(
                f"YouTube: https://www.youtube.com/watch?v={result['youtube_video_id']}"
            )
        if result["errors"]:
            print(f"Errors: {result['errors']}")
        return

    if args.schedule:
        start_scheduler()
        return

    # Default: show help
    parser.print_help()


if __name__ == "__main__":
    main()
