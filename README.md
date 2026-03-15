# YouTube Cash Cow Channel Automation

Fully automated YouTube channel that generates videos end-to-end using AI:
**Topic → Script (Claude AI) → TTS Audio → Video → Thumbnail → Upload**

## Architecture

```
youtube_cash_cow/
├── modules/
│   ├── topic_generator.py   # Trending topic discovery
│   ├── script_writer.py     # Claude AI script generation
│   ├── tts_generator.py     # Google TTS narration
│   ├── video_creator.py     # MoviePy video assembly
│   ├── thumbnail_creator.py # Pillow thumbnail design
│   ├── youtube_uploader.py  # YouTube Data API v3
│   └── analytics.py         # Performance tracking
├── config.py                # Configuration management
└── main.py                  # Orchestrator + CLI + Scheduler
output/
├── scripts/    # Generated JSON scripts
├── audio/      # TTS MP3 files
├── videos/     # Final MP4 videos
└── thumbnails/ # PNG thumbnails
assets/
├── background_music/  # Optional royalty-free music (.mp3)
├── stock_images/      # Optional background images
└── fonts/             # Optional custom fonts
```

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env and set your ANTHROPIC_API_KEY
```

### 3. Generate a video (no upload)
```bash
python -m youtube_cash_cow.main --run-once --no-upload
```

### 4. Generate a specific topic
```bash
python -m youtube_cash_cow.main --run-once \
  --title "Top 10 Most Dangerous Animals" \
  --niche top10 \
  --no-upload
```

### 5. Script-only mode (fastest, no video/audio)
```bash
python -m youtube_cash_cow.main --script-only --niche facts
```

### 6. Enable automated daily uploads
```bash
# In .env:
# UPLOAD_ENABLED=true
# UPLOAD_HOUR=14   (2 PM daily)
# VIDEOS_PER_DAY=1

python -m youtube_cash_cow.main --schedule
```

## YouTube Upload Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → Enable **YouTube Data API v3**
3. Create **OAuth 2.0 credentials** → Download `client_secrets.json`
4. Place `client_secrets.json` in the project root
5. Set `UPLOAD_ENABLED=true` in `.env`
6. First run will open a browser for OAuth authorization

## Supported Niches

| Niche | Style | Example |
|-------|-------|---------|
| `top10` | Countdown lists | "Top 10 Most Dangerous Animals" |
| `facts` | Surprising facts | "Mind-Blowing Facts About Space" |
| `educational` | Explainers | "How Black Holes Actually Work" |
| `motivational` | Self-help | "Habits of Successful People" |
| `mystery` | Mysteries | "Unexplained Disappearances" |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | required | Claude API key |
| `CHANNEL_NICHE` | `top10,facts,educational` | Comma-separated niches |
| `VIDEOS_PER_DAY` | `1` | Videos to produce daily |
| `UPLOAD_HOUR` | `14` | Hour to upload (24h format) |
| `UPLOAD_ENABLED` | `false` | Enable YouTube uploads |
| `VIDEO_WIDTH` | `1920` | Video resolution width |
| `VIDEO_HEIGHT` | `1080` | Video resolution height |

## Adding Background Music

Place royalty-free MP3 files in `assets/background_music/`.
The system randomly selects one per video at 8% volume.

Free music sources:
- [YouTube Audio Library](https://studio.youtube.com/channel/music)
- [Pixabay Music](https://pixabay.com/music/)
- [Free Music Archive](https://freemusicarchive.org/)

## How the Pipeline Works

1. **Topic Generator**: Pulls from curated niche-specific topic banks + Google Trends
2. **Script Writer**: Claude `claude-opus-4-6` with adaptive thinking generates a 8-12 minute script with hook, sections, and CTA
3. **TTS Generator**: gTTS converts narration to MP3, handles `[PAUSE]` markers
4. **Video Creator**: MoviePy assembles gradient backgrounds with text overlays synced to audio
5. **Thumbnail Creator**: Pillow generates 1280×720 thumbnails with bold text and niche-specific color schemes
6. **YouTube Uploader**: Resumable upload via YouTube Data API v3 with OAuth2 auth
7. **Analytics**: Claude analyzes performance and suggests optimizations

## Monetization Notes

- Videos must be **original** to qualify for YouTube Partner Program
- Minimum 1,000 subscribers + 4,000 watch hours for monetization
- Cash cow channels typically make $2-10 RPM (revenue per 1000 views)
- Consistency is key — upload daily for fastest growth

## Requirements

- Python 3.10+
- `ANTHROPIC_API_KEY` (get at [console.anthropic.com](https://console.anthropic.com))
- FFmpeg (for MoviePy video encoding): `apt install ffmpeg` or `brew install ffmpeg`
