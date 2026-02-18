# OpenClaw Music Listener

Music listening system for an OpenClaw agent using text-based models.

## What it does

Given a prompt like `Listen to Mac Miller's Good News`, it can:
1. Discover the track (yt-dlp first, YouTube API + MusicBrainz fallback)
2. Retrieve audio
3. Extract music features (tempo/key/energy/sections)
4. Generate natural listening observations

## Project layout

- `plugin/`: core pipeline + tool entrypoints
- `skill/`: OpenClaw skill files (`SKILL.md`, `SOUL.md`, manifest, references)
- `config/settings.example.yaml`: runtime configuration
- `cache/`: audio/features/sqlite cache artifacts
- `tests/`: pytest suite

## Requirements

- Python 3.14+
- `ffmpeg` (already present on this machine at `/usr/bin/ffmpeg`)

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt pytest
```

## Run tools

```bash
python3 plugin/tools/music_listen.py "Mac Miller Good News"
python3 plugin/tools/music_discover.py "Mac Miller Good News"
python3 plugin/tools/music_fetch.py "Mac Miller Good News"
python3 plugin/tools/music_analyze.py /path/to/audio.wav
python3 plugin/tools/music_cache_status.py "Mac Miller Good News"
```

## Configuration

Default config: `config/settings.example.yaml`

Useful env vars:
- `MUSIC_SETTINGS_PATH` (override settings path)
- `YOUTUBE_API_KEY` (optional YouTube Data API enrichment)

## Tests

```bash
.venv/bin/pytest -q
```

Current status: `17 passed`.

## Notes

- Primary discovery/retrieval is `yt-dlp` (no API key needed).
- The synthesis layer produces a prompt and natural observation text from extracted features.
- Caching avoids repeated downloads and analysis for repeated listens.
