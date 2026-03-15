"""Text-to-speech: convert scripts to audio files."""

import logging
import uuid
from pathlib import Path
from typing import Optional

from config.settings import AUDIO_DIR

logger = logging.getLogger(__name__)


def text_to_speech(text: str, lang: str = "en", slow: bool = False) -> Optional[Path]:
    """Convert *text* to an MP3 using gTTS. Returns the output path."""
    try:
        from gtts import gTTS
    except ImportError:
        logger.error("gTTS not installed. Run: pip install gtts")
        return None

    dest = AUDIO_DIR / f"tts_{uuid.uuid4().hex[:8]}.mp3"
    try:
        tts = gTTS(text=text, lang=lang, slow=slow)
        tts.save(str(dest))
        logger.info("TTS saved to %s", dest)
        return dest
    except Exception as exc:
        logger.error("TTS generation failed: %s", exc)
        return None


def get_audio_duration(path: Path) -> float:
    """Return duration in seconds of an audio file."""
    try:
        from moviepy.editor import AudioFileClip
        with AudioFileClip(str(path)) as clip:
            return clip.duration
    except Exception:
        return 60.0  # safe fallback
