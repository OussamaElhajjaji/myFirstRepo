"""Generate viral short-form video scripts using Claude."""

import logging
import random
from typing import Optional

import anthropic

from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL, NICHE_TOPICS, SCRIPT_MAX_WORDS

logger = logging.getLogger(__name__)
_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


SYSTEM_PROMPT = """You are a viral short-form video scriptwriter specialising in
"cashcow" faceless content for TikTok, Instagram Reels, and YouTube Shorts.
Your scripts must:
- Hook the viewer in the first 3 seconds with a bold statement or question
- Deliver 3–5 actionable value points quickly
- End with a strong CTA (like, follow, or comment)
- Be conversational, punchy, and easy to understand
- Be narration-ready (no stage directions, no brackets)
- Stay within {max_words} words total
"""


def generate_script(topic: Optional[str] = None, trending_hook: bool = True) -> dict:
    """Return a dict with keys: topic, hook, body, cta, full_script, hashtags."""
    if topic is None:
        topic = random.choice(NICHE_TOPICS)

    hook_instruction = (
        "Start with a shocking statistic or controversial opinion to maximise watch-time."
        if trending_hook
        else "Start with a compelling question."
    )

    prompt = f"""Write a viral short-form video script about: "{topic}"

{hook_instruction}

Return your response as JSON with exactly these keys:
- "topic": the topic string
- "hook": opening sentence (max 15 words)
- "body": main content as 3-5 short punchy sentences
- "cta": call-to-action sentence
- "full_script": hook + body + cta combined as a single narration string
- "hashtags": list of 10 relevant hashtags (no # symbol)

JSON only, no markdown fences."""

    try:
        message = _get_client().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=600,
            system=SYSTEM_PROMPT.format(max_words=SCRIPT_MAX_WORDS),
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        text = message.content[0].text.strip()
        # Strip possible markdown fences
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
        logger.info("Script generated for topic: %s", topic)
        return data
    except Exception as exc:
        logger.error("Script generation failed: %s", exc)
        # Fallback minimal script
        return {
            "topic": topic,
            "hook": f"Here's what nobody tells you about {topic}.",
            "body": f"Most people overlook {topic} entirely. But a small change here can transform your results. Focus on consistency above all. Take action today, not tomorrow.",
            "cta": "Follow for more tips like this.",
            "full_script": f"Here's what nobody tells you about {topic}. Most people overlook it entirely. But a small change here can transform your results. Focus on consistency above all. Take action today, not tomorrow. Follow for more tips like this.",
            "hashtags": [topic.replace(" ", ""), "motivation", "viral", "tips", "growth", "mindset", "success", "lifestyle", "money", "fyp"],
        }


def generate_title_and_description(script_data: dict) -> dict:
    """Generate an SEO-optimised title and description for the video."""
    prompt = f"""Given this short video script about "{script_data['topic']}":

Hook: {script_data['hook']}
Body: {script_data['body']}
CTA: {script_data['cta']}

Return JSON with:
- "title": catchy YouTube/TikTok title (max 60 chars, include numbers or power words)
- "description": SEO description (150-200 words, include keywords naturally)
- "tags": list of 15 search tags (single words or short phrases)

JSON only."""
    try:
        message = _get_client().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        text = message.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception as exc:
        logger.error("Title generation failed: %s", exc)
        return {
            "title": f"{script_data['topic'].title()} — Must Watch",
            "description": script_data["full_script"],
            "tags": script_data.get("hashtags", []),
        }
