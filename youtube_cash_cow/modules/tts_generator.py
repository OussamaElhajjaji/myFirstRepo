"""
TTS Generator Module
Converts video scripts to audio using gTTS (Google Text-to-Speech).
Supports chunked generation for long scripts and audio stitching.
"""
import logging
import re
import time
from pathlib import Path

from pydub import AudioSegment

from youtube_cash_cow.config import AUDIO_DIR, TTS_LANGUAGE, TTS_SLOW
from youtube_cash_cow.modules.script_writer import VideoScript

logger = logging.getLogger(__name__)

# Pause durations in milliseconds
PAUSE_DURATIONS = {
    "[PAUSE]": 800,
    "[LONG_PAUSE]": 1500,
    "[SHORT_PAUSE]": 400,
}

# Max characters per TTS chunk (gTTS limit is ~5000)
TTS_CHUNK_SIZE = 3000


def _clean_for_tts(text: str) -> str:
    """Remove visual direction markers and format text for TTS."""
    # Remove emphasis markers (keep the word)
    text = text.replace("[EMPHASIS]", "")
    # Remove section numbers like "1." at start
    text = re.sub(r"^\d+\.\s+", "", text, flags=re.MULTILINE)
    # Clean up multiple spaces/newlines
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _split_into_chunks(text: str, chunk_size: int = TTS_CHUNK_SIZE) -> list[str]:
    """
    Split text into chunks that gTTS can handle.
    Splits at sentence boundaries to avoid cutting mid-sentence.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 <= chunk_size:
            current_chunk += (" " if current_chunk else "") + sentence
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def _text_to_audio_segment(text: str, retries: int = 3) -> AudioSegment | None:
    """Convert a single text chunk to an AudioSegment using gTTS."""
    from gtts import gTTS
    import io

    clean_text = _clean_for_tts(text)
    if not clean_text:
        return None

    for attempt in range(retries):
        try:
            tts = gTTS(text=clean_text, lang=TTS_LANGUAGE, slow=TTS_SLOW)
            mp3_fp = io.BytesIO()
            tts.write_to_fp(mp3_fp)
            mp3_fp.seek(0)
            segment = AudioSegment.from_mp3(mp3_fp)
            return segment
        except Exception as e:
            logger.warning(f"TTS attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)

    logger.error(f"Failed to convert text to audio after {retries} attempts")
    return None


def _process_pause_markers(text: str) -> list[tuple[str, int]]:
    """
    Split text by pause markers, returning list of (text, pause_after_ms).
    """
    parts = []
    segments = re.split(r"(\[PAUSE\]|\[LONG_PAUSE\]|\[SHORT_PAUSE\])", text)

    current_text = ""
    for segment in segments:
        if segment in PAUSE_DURATIONS:
            if current_text.strip():
                parts.append((current_text.strip(), PAUSE_DURATIONS[segment]))
            current_text = ""
        else:
            current_text += segment

    if current_text.strip():
        parts.append((current_text.strip(), 0))

    return parts


def generate_audio_for_script(script: VideoScript) -> Path:
    """
    Generate a single audio file for the complete script narration.
    Returns path to the generated MP3 file.
    """
    logger.info(f"Generating TTS audio for: {script.title}")

    safe_title = "".join(
        c if c.isalnum() or c in (" ", "-", "_") else "" for c in script.title
    )[:50]
    output_path = AUDIO_DIR / f"{safe_title}.mp3"

    if output_path.exists():
        logger.info(f"Audio already exists: {output_path}")
        return output_path

    # Process the full narration with pause markers
    text_with_pauses = _process_pause_markers(script.full_narration)
    combined_audio = AudioSegment.empty()

    for idx, (text_chunk, pause_ms) in enumerate(text_with_pauses):
        logger.debug(f"Processing text segment {idx + 1}/{len(text_with_pauses)}")

        # Split large chunks further
        sub_chunks = _split_into_chunks(text_chunk)
        for sub_chunk in sub_chunks:
            segment = _text_to_audio_segment(sub_chunk)
            if segment:
                combined_audio += segment

        # Add pause after segment
        if pause_ms > 0:
            combined_audio += AudioSegment.silent(duration=pause_ms)

    if len(combined_audio) == 0:
        raise RuntimeError("Failed to generate any audio content")

    # Export to MP3
    combined_audio.export(str(output_path), format="mp3", bitrate="192k")
    duration_sec = len(combined_audio) / 1000
    logger.info(
        f"Audio generated: {output_path} "
        f"({duration_sec:.1f}s, {output_path.stat().st_size / 1024:.1f}KB)"
    )
    return output_path


def generate_section_audios(script: VideoScript) -> list[Path]:
    """
    Generate separate audio files for each section.
    Useful for video editing with precise sync.
    """
    audio_paths = []
    safe_title = "".join(
        c if c.isalnum() or c in (" ", "-", "_") else "" for c in script.title
    )[:40]

    # Generate hook audio
    hook_path = AUDIO_DIR / f"{safe_title}_hook.mp3"
    if not hook_path.exists():
        hook_segment = _text_to_audio_segment(script.hook)
        if hook_segment:
            hook_segment.export(str(hook_path), format="mp3")
    audio_paths.append(hook_path)

    # Generate section audios
    for section in script.sections:
        section_path = AUDIO_DIR / f"{safe_title}_s{section['section_number']}.mp3"
        if not section_path.exists():
            narration = section.get("narration", "")
            segment = _text_to_audio_segment(narration)
            if segment:
                segment.export(str(section_path), format="mp3")
        audio_paths.append(section_path)

    # Generate outro
    outro_path = AUDIO_DIR / f"{safe_title}_outro.mp3"
    if not outro_path.exists():
        outro_segment = _text_to_audio_segment(script.outro)
        if outro_segment:
            outro_segment.export(str(outro_path), format="mp3")
    audio_paths.append(outro_path)

    logger.info(f"Generated {len(audio_paths)} section audio files")
    return audio_paths


def get_audio_duration(audio_path: Path) -> float:
    """Return the duration of an audio file in seconds."""
    try:
        audio = AudioSegment.from_file(str(audio_path))
        return len(audio) / 1000.0
    except Exception as e:
        logger.error(f"Could not get audio duration: {e}")
        return 0.0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Quick test
    from youtube_cash_cow.modules.script_writer import VideoScript
    test_script = VideoScript(
        title="Test Video",
        niche="facts",
        hook="Did you know that the world is full of amazing facts? [PAUSE] Today we explore them.",
        sections=[
            {
                "section_number": 1,
                "section_title": "Introduction",
                "narration": "Welcome to this fascinating journey through the world's most amazing facts.",
                "visual_direction": "Globe spinning",
                "duration_seconds": 30,
            }
        ],
        outro="If you enjoyed this video, please subscribe and hit the bell icon!",
        tags=["facts", "amazing"],
        description="Test description",
        thumbnail_text="AMAZING FACTS",
        estimated_duration_seconds=60,
        full_narration="Did you know that the world is full of amazing facts? [PAUSE] "
                       "Welcome to this fascinating journey. "
                       "If you enjoyed this video, please subscribe!",
    )
    path = generate_audio_for_script(test_script)
    print(f"Audio saved to: {path}")
