"""Central configuration for the social media video funnel."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Directories ──────────────────────────────────────────────────────────────
ASSETS_DIR = BASE_DIR / "assets"
VIDEOS_DIR = ASSETS_DIR / "videos"
IMAGES_DIR = ASSETS_DIR / "images"
AUDIO_DIR = ASSETS_DIR / "audio"
OUTPUT_DIR = ASSETS_DIR / "output"

for d in (VIDEOS_DIR, IMAGES_DIR, AUDIO_DIR, OUTPUT_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ── API Keys ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")

# ── Social Media Credentials ──────────────────────────────────────────────────
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME", "")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD", "")

YOUTUBE_CLIENT_SECRETS_FILE = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "config/youtube_client_secrets.json")
YOUTUBE_TOKEN_FILE = os.getenv("YOUTUBE_TOKEN_FILE", "config/youtube_token.json")

TIKTOK_SESSION_ID = os.getenv("TIKTOK_SESSION_ID", "")  # Cookie-based auth

# ── Video Settings ────────────────────────────────────────────────────────────
VIDEO_RESOLUTION = (1080, 1920)   # 9:16 vertical (Shorts / Reels / TikTok)
VIDEO_FPS = 30
CLIP_DURATION = 3                 # seconds per stock clip
MAX_VIDEO_DURATION = 60           # max total seconds
TRANSITION_DURATION = 0.5         # crossfade seconds

# ── Content Settings ──────────────────────────────────────────────────────────
NICHE_TOPICS = [
    "morning motivation",
    "productivity hacks",
    "financial freedom tips",
    "self improvement",
    "mindset shifts",
    "passive income ideas",
    "crypto investing basics",
    "health and wellness",
    "side hustle ideas",
    "success mindset",
]
SCRIPT_MAX_WORDS = 120            # TTS script length target
CLAUDE_MODEL = "claude-sonnet-4-6"

# ── Posting Schedule (24-h format) ───────────────────────────────────────────
POST_TIMES = ["08:00", "12:00", "18:00"]   # three posts per day

# ── Platforms to enable ───────────────────────────────────────────────────────
ENABLED_PLATFORMS = [p.strip() for p in os.getenv("ENABLED_PLATFORMS", "instagram,youtube,tiktok").split(",")]
