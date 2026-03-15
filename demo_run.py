"""
Demo run — exercises the full pipeline with a pre-written sample script
so the video/thumbnail/audio generation can be demonstrated without
needing a live Anthropic API key.
"""
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Point pydub to the bundled ffmpeg from imageio_ffmpeg
import imageio_ffmpeg
_ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
os.environ["PATH"] = str(Path(_ffmpeg_path).parent) + ":" + os.environ.get("PATH", "")

# Also configure pydub directly
from pydub import AudioSegment
AudioSegment.converter = _ffmpeg_path
AudioSegment.ffmpeg = _ffmpeg_path
AudioSegment.ffprobe = _ffmpeg_path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("demo")

# ── Step 1: Topic Selection ────────────────────────────────────────────────────
from youtube_cash_cow.modules.topic_generator import select_best_topic, TOPIC_BANKS
import random

logger.info("=" * 60)
logger.info("STEP 1 — Topic Selection")
niches = ["top10", "facts", "educational", "motivational", "mystery"]
topic = select_best_topic(niches)
logger.info(f"Selected: {topic['title']} (niche: {topic['niche']})")

# ── Step 2: Mock Script (pre-written sample) ──────────────────────────────────
from youtube_cash_cow.modules.script_writer import VideoScript

logger.info("=" * 60)
logger.info("STEP 2 — Script (using sample script — swap for Claude API in production)")

sample = VideoScript(
    title=topic["title"],
    niche=topic["niche"],
    hook=(
        f"What you're about to discover will completely change how you see the world. "
        f"[PAUSE] Welcome to {topic['title']}. Stay until the end — number one will shock you."
    ),
    sections=[
        {
            "section_number": i + 1,
            "section_title": f"#{10 - i}: {entry}",
            "narration": (
                f"Coming in at number {10 - i} on our list: {entry}. "
                f"This is one of the most fascinating examples you'll ever encounter. "
                f"Scientists and researchers have spent decades studying this phenomenon. "
                f"[PAUSE] The results are truly breathtaking."
            ),
            "visual_direction": f"Stock footage of {entry.lower()}",
            "duration_seconds": 60,
        }
        for i, entry in enumerate(
            random.sample(TOPIC_BANKS.get(topic["niche"], TOPIC_BANKS["facts"]), min(6, len(TOPIC_BANKS.get(topic["niche"], TOPIC_BANKS["facts"]))))
        )
    ],
    outro=(
        "That wraps up today's video! [PAUSE] If you found this interesting, "
        "hit the like button and subscribe for more amazing content every week. "
        "Drop a comment below with which fact surprised you the most!"
    ),
    tags=["amazing", "facts", "top10", "educational", "interesting", topic["niche"]],
    description=(
        f"{topic['title']} — Explore the most fascinating and mind-blowing examples "
        f"in this category. Like and subscribe for weekly videos!"
    ),
    thumbnail_text=topic["title"].split()[:4],
    estimated_duration_seconds=420,
    full_narration="",
)

# Build full narration
parts = [sample.hook, "\n\n"]
for s in sample.sections:
    parts.append(s["narration"] + "\n\n")
parts.append(sample.outro)
sample.full_narration = "".join(parts)
sample.thumbnail_text = " ".join(str(w) for w in sample.thumbnail_text).upper()

logger.info(f"Script ready: {len(sample.sections)} sections")
logger.info(f"Hook: {sample.hook[:80]}...")

# ── Step 3: TTS Audio ─────────────────────────────────────────────────────────
logger.info("=" * 60)
logger.info("STEP 3 — TTS Audio Generation")

try:
    from youtube_cash_cow.modules.tts_generator import generate_audio_for_script
    audio_path = generate_audio_for_script(sample)
    logger.info(f"Audio: {audio_path}")
    audio_ok = True
except Exception as e:
    logger.warning(f"TTS skipped (no internet or gTTS issue): {e}")
    # Create a 30-second silent audio file as fallback
    from youtube_cash_cow.config import AUDIO_DIR
    audio_path = AUDIO_DIR / "demo_silent.mp3"
    silent = AudioSegment.silent(duration=30_000)
    silent.export(str(audio_path), format="mp3")
    logger.info(f"Using silent fallback audio: {audio_path}")
    audio_ok = False

# ── Step 4: Video Creation ────────────────────────────────────────────────────
logger.info("=" * 60)
logger.info("STEP 4 — Video Creation")

try:
    from youtube_cash_cow.modules.video_creator import create_video_from_script
    video_path = create_video_from_script(sample, audio_path)
    size_mb = video_path.stat().st_size / 1024 / 1024
    logger.info(f"Video: {video_path} ({size_mb:.1f} MB)")
except Exception as e:
    logger.error(f"Video creation failed: {e}")
    video_path = None

# ── Step 5: Thumbnail ─────────────────────────────────────────────────────────
logger.info("=" * 60)
logger.info("STEP 5 — Thumbnail Creation")

from youtube_cash_cow.modules.thumbnail_creator import create_thumbnail
thumb_path = create_thumbnail(
    title=sample.title,
    niche=sample.niche,
    thumbnail_text=sample.thumbnail_text,
    section_number=10,
)
logger.info(f"Thumbnail: {thumb_path}")

# ── Summary ───────────────────────────────────────────────────────────────────
logger.info("=" * 60)
logger.info("DEMO COMPLETE")
logger.info(f"  Topic:     {sample.title}")
logger.info(f"  Niche:     {sample.niche}")
logger.info(f"  Sections:  {len(sample.sections)}")
logger.info(f"  Audio:     {audio_path} {'(TTS)' if audio_ok else '(silent fallback)'}")
logger.info(f"  Video:     {video_path or 'FAILED'}")
logger.info(f"  Thumbnail: {thumb_path}")
logger.info("")
logger.info("To run with Claude AI script generation, set ANTHROPIC_API_KEY in .env")
logger.info("and run: python -m youtube_cash_cow.main --run-once --no-upload")
