"""
Configuration management for YouTube Cash Cow automation.
Loads settings from .env file and provides defaults.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
YOUTUBE_CLIENT_SECRETS_FILE = os.getenv(
    "YOUTUBE_CLIENT_SECRETS_FILE", "client_secrets.json"
)

# Channel settings
CHANNEL_NAME = os.getenv("CHANNEL_NAME", "AutoChannel")
CHANNEL_NICHE = os.getenv("CHANNEL_NICHE", "top10,facts,educational").split(",")

# Video settings
VIDEO_WIDTH = int(os.getenv("VIDEO_WIDTH", "1920"))
VIDEO_HEIGHT = int(os.getenv("VIDEO_HEIGHT", "1080"))
VIDEO_FPS = int(os.getenv("VIDEO_FPS", "30"))
MAX_VIDEO_DURATION = int(os.getenv("MAX_VIDEO_DURATION", "600"))

# Upload settings
UPLOAD_ENABLED = os.getenv("UPLOAD_ENABLED", "false").lower() == "true"
VIDEOS_PER_DAY = int(os.getenv("VIDEOS_PER_DAY", "1"))
UPLOAD_HOUR = int(os.getenv("UPLOAD_HOUR", "14"))

# Directory paths
OUTPUT_DIR = BASE_DIR / os.getenv("OUTPUT_DIR", "output")
ASSETS_DIR = BASE_DIR / os.getenv("ASSETS_DIR", "assets")
VIDEOS_DIR = OUTPUT_DIR / "videos"
THUMBNAILS_DIR = OUTPUT_DIR / "thumbnails"
AUDIO_DIR = OUTPUT_DIR / "audio"
SCRIPTS_DIR = OUTPUT_DIR / "scripts"
LOGS_DIR = BASE_DIR / "logs"

# TTS settings
TTS_LANGUAGE = os.getenv("TTS_LANGUAGE", "en")
TTS_SLOW = os.getenv("TTS_SLOW", "false").lower() == "true"

# Claude model
CLAUDE_MODEL = "claude-opus-4-6"

# Video styles for cash cow channels
VIDEO_NICHES = {
    "top10": {
        "description": "Top 10 lists about interesting facts and topics",
        "tags": ["top10", "facts", "interesting", "amazing", "list"],
        "intro_style": "hook",
    },
    "facts": {
        "description": "Mind-blowing facts and educational content",
        "tags": ["facts", "didyouknow", "educational", "science", "history"],
        "intro_style": "question",
    },
    "educational": {
        "description": "Educational explainer videos on trending topics",
        "tags": ["educational", "explainer", "howto", "learn", "knowledge"],
        "intro_style": "story",
    },
    "motivational": {
        "description": "Motivational and self-improvement content",
        "tags": ["motivation", "success", "mindset", "inspiration", "goals"],
        "intro_style": "statement",
    },
    "mystery": {
        "description": "Mysterious and unexplained phenomena",
        "tags": ["mystery", "unexplained", "conspiracy", "secrets", "unknown"],
        "intro_style": "hook",
    },
}

# Ensure output directories exist
for directory in [OUTPUT_DIR, VIDEOS_DIR, THUMBNAILS_DIR, AUDIO_DIR, SCRIPTS_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)
