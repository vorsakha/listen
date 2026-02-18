# OpenClaw Music Listener

Music listening system for an OpenClaw agent using text-based models.

## What it does

Given a prompt like `Listen to Mac Miller's Good News`, it can:
1. Discover the track (yt-dlp first, YouTube API + MusicBrainz fallback)
2. Retrieve audio
3. Extract music features (tempo/key/energy/sections)
4. Retrieve lyrics when available (LRCLIB, optional ASR fallback)
5. Fall back to metadata-only analysis when full-audio retrieval/analysis is unavailable
6. Generate natural listening observations with audio + lyric feel (or metadata + lyric feel in fallback mode)

## Project layout

- `plugin/core/`: core pipeline logic
- `tools/`: CLI entrypoints for discovery/retrieval/analysis/listen/cache inspection
- `skills/`: OpenClaw-discoverable skill files (`skills/<name>/SKILL.md`)
- `config/settings.example.yaml`: runtime configuration
- `cache/`: audio/features/sqlite cache artifacts
- `tests/`: pytest suite

## Requirements

- Python 3.14+
- `ffmpeg` 

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt pytest
```

## Run tools

```bash
python3 tools/music_listen.py "Mac Miller Good News"
python3 tools/music_listen.py "Mac Miller Good News" --mode metadata_only
python3 tools/music_discover.py "Mac Miller Good News"
python3 tools/music_fetch.py "Mac Miller Good News"
python3 tools/music_analyze.py /path/to/audio.wav
python3 tools/music_cache_status.py "Mac Miller Good News"
```

## Configuration

Default config: `config/settings.example.yaml`

Useful env vars:
- `MUSIC_SETTINGS_PATH` (override settings path)
- `YOUTUBE_API_KEY` (optional YouTube Data API enrichment)
- `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` (optional Spotify metadata discovery)

Listening modes:
- `auto` (default): full-audio first, then metadata-only fallback
- `full_audio`: strict mode, no fallback
- `metadata_only`: metadata + lyrics only, no audio feature extraction

## Tests

```bash
.venv/bin/pytest -q
```

Current status: `33 passed`.

## Notes

- Primary discovery/retrieval is `yt-dlp` (no API key needed).
- Spotify integration is metadata-only and requires app credentials for discovery.
- The synthesis layer produces a prompt and natural observation text from extracted features.
- The synthesis layer now includes lyric-feeling and a combined observation when lyric evidence exists.
- Caching avoids repeated downloads and analysis for repeated listens.
