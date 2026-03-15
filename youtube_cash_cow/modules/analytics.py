"""
Analytics Module
Tracks video performance and provides optimization insights using Claude AI.
Analyzes upload history and suggests improvements.
"""
import json
import logging
from pathlib import Path
from typing import Optional

import anthropic

from youtube_cash_cow.config import ANTHROPIC_API_KEY, CLAUDE_MODEL, LOGS_DIR

logger = logging.getLogger(__name__)


def load_upload_history() -> list[dict]:
    """Load all upload records from the JSONL log file."""
    record_path = LOGS_DIR / "uploads.jsonl"
    if not record_path.exists():
        return []

    records = []
    with open(record_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def get_youtube_video_stats(youtube, video_ids: list[str]) -> list[dict]:
    """Fetch statistics for uploaded videos from YouTube API."""
    if not video_ids:
        return []

    try:
        response = youtube.videos().list(
            part="statistics,snippet",
            id=",".join(video_ids[:50]),
        ).execute()

        stats = []
        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            statistics = item.get("statistics", {})
            stats.append({
                "video_id": item["id"],
                "title": snippet.get("title", ""),
                "views": int(statistics.get("viewCount", 0)),
                "likes": int(statistics.get("likeCount", 0)),
                "comments": int(statistics.get("commentCount", 0)),
                "published_at": snippet.get("publishedAt", ""),
            })
        return stats
    except Exception as e:
        logger.error(f"Failed to fetch video stats: {e}")
        return []


def analyze_performance_with_claude(stats: list[dict]) -> str:
    """
    Use Claude to analyze video performance and suggest optimizations.
    Returns a formatted analysis report.
    """
    if not stats:
        return "No performance data available yet. Upload some videos first!"

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    stats_json = json.dumps(stats, indent=2)
    prompt = f"""You are a YouTube analytics expert specializing in cash cow channels.
Analyze this video performance data and provide actionable insights:

{stats_json}

Please provide:
1. **Top Performers**: Which videos/niches are getting the most views?
2. **Engagement Analysis**: Like/view ratio and what it indicates
3. **Title Optimization**: Patterns in high vs low performing titles
4. **Niche Recommendations**: Which niches to focus on more/less
5. **Next 5 Video Ideas**: Based on what's working, suggest 5 specific video titles
6. **Upload Strategy**: Optimal posting frequency and timing suggestions

Be specific and data-driven. Format as a clear report."""

    with client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=2000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        response = stream.get_final_message()

    for block in response.content:
        if block.type == "text":
            return block.text

    return "Analysis failed."


def generate_performance_report() -> str:
    """Generate a full performance report from local upload history."""
    history = load_upload_history()

    if not history:
        return "No upload history found. Run the pipeline to create videos first."

    # Calculate local stats
    total_videos = len(history)
    uploaded = sum(1 for r in history if r.get("uploaded"))
    niches = {}
    for record in history:
        niche = record.get("niche", "unknown")
        niches[niche] = niches.get(niche, 0) + 1

    report = [
        "=" * 60,
        "YOUTUBE CASH COW — PERFORMANCE REPORT",
        "=" * 60,
        f"Total videos produced: {total_videos}",
        f"Successfully uploaded: {uploaded}",
        f"Upload rate: {uploaded / total_videos * 100:.1f}%" if total_videos else "N/A",
        "",
        "Videos by niche:",
    ]

    for niche, count in sorted(niches.items(), key=lambda x: -x[1]):
        report.append(f"  {niche}: {count} videos")

    report.extend([
        "",
        "Recent uploads:",
    ])

    for record in sorted(history, key=lambda x: x.get("timestamp", ""), reverse=True)[:5]:
        status = "✓" if record.get("uploaded") else "○"
        video_id = record.get("video_id", "not uploaded")
        report.append(f"  {status} {record.get('title', 'Unknown')} [{video_id}]")

    return "\n".join(report)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(generate_performance_report())
