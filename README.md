# Social Media Cashcow Video Funnel

Automated pipeline that generates and posts AI-powered short-form videos to **TikTok**, **Instagram Reels**, and **YouTube Shorts** — fully hands-free.

```
Topic (random niche)
    │
    ▼
Claude AI → viral script + hashtags
    │
    ▼
gTTS → narration audio
    │
    ▼
Pexels / Pixabay → royalty-free video clips + photos
    │
    ▼
MoviePy → assembled 9:16 vertical video (hook overlay, captions, outro)
    │
    ▼
Dispatcher → TikTok · Instagram · YouTube Shorts
    │
    ▼
schedule → repeat 3×/day automatically
```

---

## Quick Start

### 1. Install dependencies
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> **Note:** MoviePy requires `ffmpeg`. Install it with:
> - macOS: `brew install ffmpeg`
> - Ubuntu/Debian: `sudo apt install ffmpeg`
> - Windows: Download from https://ffmpeg.org

### 2. Configure credentials
```bash
cp .env.example .env
# Edit .env with your API keys (see sections below)
```

### 3. Run once (test/dry run — no posting)
```bash
python -m src.scheduler.runner --once --dry-run --topic "morning motivation"
```

### 4. Run once with live posting
```bash
python -m src.scheduler.runner --once --topic "passive income ideas"
```

### 5. Start the automated scheduler (3 posts/day)
```bash
python -m src.scheduler.runner
```

---

## API Key Setup

### Anthropic (Claude) — Required
1. Sign up at https://console.anthropic.com
2. Create an API key under **API Keys**
3. Set `ANTHROPIC_API_KEY` in `.env`

### Pexels — Required
1. Sign up at https://www.pexels.com/api/
2. Generate a free API key
3. Set `PEXELS_API_KEY` in `.env`

### Pixabay — Optional (fallback)
1. Register at https://pixabay.com/accounts/register/
2. Find your API key at https://pixabay.com/api/docs/
3. Set `PIXABAY_API_KEY` in `.env`

### Instagram
Uses [instagrapi](https://github.com/subzeroid/instagrapi) with your username/password.
Set `INSTAGRAM_USERNAME` and `INSTAGRAM_PASSWORD` in `.env`.

> **Tip:** Use a dedicated Instagram account to avoid flagging your personal account.

### YouTube Shorts
1. Create a project in [Google Cloud Console](https://console.cloud.google.com)
2. Enable the **YouTube Data API v3**
3. Create OAuth 2.0 credentials (Desktop app) and download `client_secrets.json`
4. Place it at `config/youtube_client_secrets.json`
5. On first run an OAuth browser window will open — authorize once; token is saved

### TikTok
1. Apply for developer access at https://developers.tiktok.com
2. Create an app and complete OAuth2 to get your `access_token`
3. Set `TIKTOK_ACCESS_TOKEN` in `.env`

---

## Configuration

Edit `config/settings.py` to customize:

| Setting | Default | Description |
|---|---|---|
| `NICHE_TOPICS` | 10 pre-set topics | Content niches to rotate through |
| `POST_TIMES` | `08:00, 12:00, 18:00` | Daily posting schedule |
| `MAX_VIDEO_DURATION` | `60s` | Maximum video length |
| `VIDEO_RESOLUTION` | `1080×1920` | Portrait 9:16 |
| `CLIP_DURATION` | `3s` | Seconds per stock clip |
| `SCRIPT_MAX_WORDS` | `120` | Narration word limit |
| `ENABLED_PLATFORMS` | all three | Comma-separated platform list |

---

## Project Structure

```
├── config/
│   └── settings.py          # All configuration
├── src/
│   ├── pipeline.py           # Main orchestrator
│   ├── fetcher/
│   │   ├── pexels.py         # Pexels API client
│   │   ├── pixabay.py        # Pixabay API client
│   │   └── media_pool.py     # Unified media fetcher
│   ├── generator/
│   │   ├── script_writer.py  # Claude script generation
│   │   └── tts.py            # Text-to-speech (gTTS)
│   ├── editor/
│   │   └── video_builder.py  # MoviePy video assembly
│   ├── poster/
│   │   ├── instagram.py      # Instagram Reels
│   │   ├── youtube.py        # YouTube Shorts
│   │   ├── tiktok.py         # TikTok
│   │   └── dispatcher.py     # Route to all platforms
│   └── scheduler/
│       └── runner.py         # Daily schedule + CLI
├── assets/                   # Downloaded media (gitignored)
├── logs/                     # Runtime logs
├── requirements.txt
└── .env.example
```

---

## Monetisation Strategy (Cashcow Model)

1. **Niche selection** — pick high-CPM niches: finance, productivity, self-improvement
2. **Volume** — 3 posts/day × 3 platforms = 9 daily uploads on autopilot
3. **Monetisation paths:**
   - YouTube Partner Program (ad revenue)
   - TikTok Creator Rewards Program
   - Instagram Bonuses / Brand deals
   - Affiliate links in bio / descriptions
4. **Scale** — run multiple niche accounts in parallel by changing `NICHE_TOPICS`

---

## Disclaimer

- Always comply with each platform's Terms of Service and automation policies.
- Use royalty-free assets only (Pexels/Pixabay are CC0 / royalty-free for commercial use).
- AI-generated content must be disclosed where required by platform policy.
