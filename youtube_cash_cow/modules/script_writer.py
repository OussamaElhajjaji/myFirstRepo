"""
Script Writer Module
Uses Claude API (claude-opus-4-6 with adaptive thinking) to generate
engaging YouTube video scripts optimized for watch time and monetization.
"""
import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

import anthropic

from youtube_cash_cow.config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    SCRIPTS_DIR,
    VIDEO_NICHES,
)

logger = logging.getLogger(__name__)


@dataclass
class VideoScript:
    title: str
    niche: str
    hook: str
    sections: list[dict]
    outro: str
    tags: list[str]
    description: str
    thumbnail_text: str
    estimated_duration_seconds: int
    full_narration: str


def _build_script_prompt(topic: dict) -> str:
    niche = topic.get("niche", "facts")
    title = topic["title"]
    niche_info = VIDEO_NICHES.get(niche, VIDEO_NICHES["facts"])
    intro_style = niche_info["intro_style"]

    style_instructions = {
        "hook": "Start with a shocking or surprising statement that immediately grabs attention.",
        "question": "Open with a thought-provoking question that the viewer must know the answer to.",
        "story": "Begin with a brief compelling story or scenario before diving into the content.",
        "statement": "Open with a bold, powerful statement that challenges the viewer's beliefs.",
    }

    return f"""You are an expert YouTube scriptwriter specializing in viral "cash cow" channels.
These channels use AI voiceovers and stock footage, generating passive income through ad revenue.

Write a complete, engaging YouTube video script for:
**Title:** {title}
**Niche:** {niche}
**Target Length:** 8-12 minutes (1,200-1,800 words of narration)

CRITICAL REQUIREMENTS for monetization success:
1. {style_instructions.get(intro_style, style_instructions["hook"])}
2. Hook viewers in the first 30 seconds — they must NOT click away.
3. Use "pattern interrupts" every 60-90 seconds (surprising facts, "but wait..." moments).
4. Include strategic curiosity gaps: tease upcoming content to prevent drop-off.
5. Write for a voiceover AI — clear pronunciation, no complex abbreviations.
6. Use simple, engaging language (8th grade reading level).
7. Include natural pauses with "[PAUSE]" markers.
8. Add "[EMPHASIS]" before key points for the TTS engine.

Return ONLY valid JSON in this exact structure:
{{
  "title": "{title}",
  "niche": "{niche}",
  "hook": "The opening 2-3 sentences that serve as the video hook (max 50 words)",
  "sections": [
    {{
      "section_number": 1,
      "section_title": "Section name",
      "narration": "Full narration text for this section (200-300 words)",
      "visual_direction": "What should be shown on screen (stock footage/images)",
      "duration_seconds": 90
    }}
  ],
  "outro": "Closing call-to-action (subscribe, comment, like) — 3-4 sentences",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8"],
  "description": "YouTube video description (150-200 words, SEO optimized)",
  "thumbnail_text": "Short punchy text for thumbnail overlay (max 6 words in CAPS)",
  "estimated_duration_seconds": 600
}}

Create 6-8 sections. Make it genuinely interesting and informative.
The content must be accurate and engaging enough that viewers watch to the end.
"""


def generate_script(topic: dict) -> VideoScript:
    """
    Generate a complete video script for the given topic using Claude.
    Uses adaptive thinking for better creative output.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = _build_script_prompt(topic)

    logger.info(f"Generating script for: {topic['title']}")

    with client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        response = stream.get_final_message()

    # Extract text content
    raw_text = ""
    for block in response.content:
        if block.type == "text":
            raw_text = block.text
            break

    # Parse JSON from response
    script_data = _parse_script_json(raw_text)

    # Build full narration from sections
    full_narration = script_data.get("hook", "") + "\n\n"
    for section in script_data.get("sections", []):
        full_narration += section.get("narration", "") + "\n\n"
    full_narration += script_data.get("outro", "")

    # Estimate total duration
    total_duration = sum(
        s.get("duration_seconds", 90) for s in script_data.get("sections", [])
    )
    total_duration += 30  # hook + outro

    script = VideoScript(
        title=script_data.get("title", topic["title"]),
        niche=script_data.get("niche", topic.get("niche", "facts")),
        hook=script_data.get("hook", ""),
        sections=script_data.get("sections", []),
        outro=script_data.get("outro", ""),
        tags=script_data.get("tags", []),
        description=script_data.get("description", ""),
        thumbnail_text=script_data.get("thumbnail_text", topic["title"][:30].upper()),
        estimated_duration_seconds=total_duration,
        full_narration=full_narration.strip(),
    )

    # Save script to disk
    _save_script(script)
    logger.info(
        f"Script generated: {len(script.sections)} sections, "
        f"~{total_duration // 60}min {total_duration % 60}sec"
    )
    return script


def _parse_script_json(raw_text: str) -> dict:
    """Extract and parse JSON from Claude's response."""
    # Try to find JSON block
    text = raw_text.strip()

    # Remove markdown code fences if present
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        text = text[start:end].strip()

    # Find JSON object boundaries
    brace_start = text.find("{")
    brace_end = text.rfind("}") + 1
    if brace_start != -1 and brace_end > brace_start:
        text = text[brace_start:brace_end]

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse script JSON: {e}")
        logger.debug(f"Raw text: {raw_text[:500]}")
        return {}


def _save_script(script: VideoScript) -> Path:
    """Save script as JSON file."""
    safe_title = "".join(
        c if c.isalnum() or c in (" ", "-", "_") else "" for c in script.title
    )[:50]
    filename = SCRIPTS_DIR / f"{safe_title}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(asdict(script), f, indent=2, ensure_ascii=False)
    logger.info(f"Script saved: {filename}")
    return filename


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_topic = {
        "title": "Top 10 Most Dangerous Animals in the World",
        "niche": "top10",
    }
    script = generate_script(test_topic)
    print(f"Generated script: {script.title}")
    print(f"Sections: {len(script.sections)}")
    print(f"Duration: {script.estimated_duration_seconds}s")
    print(f"\nHook: {script.hook}")
