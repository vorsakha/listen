# OpenClaw Music Listener

Music listening system for an OpenClaw agent using text-based models.

## What it does

Given a prompt like `Listen to Mac Miller's Good News`, it can:
1. Discover the track (yt-dlp first, YouTube API + Jamendo + MusicBrainz fallback)
2. Retrieve audio
3. Extract music features (tempo/key/energy/sections)
4. Resolve descriptor-only musical data from public databases (AcousticBrainz/Deezer fallback)
5. Retrieve lyrics when available (LRCLIB, optional ASR fallback)
6. Fall back to metadata/descriptor-only analysis when full-audio retrieval/analysis is unavailable
7. Generate natural listening observations with audio + lyric feel (or descriptor/metadata + lyric feel in fallback mode)

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
python3 tools/music_listen.py "Mac Miller Good News" --mode descriptor_only
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
- `JAMENDO_CLIENT_ID` (optional Jamendo discovery/audio fallback)
- `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` (optional Spotify metadata discovery)

Listening modes:
- `auto` (default): full-audio first, then descriptor-only fallback, then metadata-only if descriptors are unavailable
- `full_audio`: strict mode, no fallback
- `metadata_only`: metadata + lyrics only, no audio feature extraction
- `descriptor_only`: metadata + public descriptor databases (tempo/key/texture proxies), no audio download

## Tests

```bash
.venv/bin/pytest -q
```

Current status: `37 passed`.

## Notes

- Primary discovery/retrieval is `yt-dlp` (no API key needed).
- Jamendo can provide direct audio fallback when YouTube retrieval fails and a matching track exists.
- Spotify integration is metadata-only and requires app credentials for discovery.
- Descriptor-only analysis uses MusicBrainz/AcousticBrainz/Deezer lookups with confidence-based partial returns.
- The synthesis layer produces a prompt and natural observation text from extracted features.
- The synthesis layer now includes lyric-feeling and a combined observation when lyric evidence exists.
- Caching avoids repeated downloads and analysis for repeated listens.
