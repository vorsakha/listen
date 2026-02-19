---
name: listen
description: Autonomously listen to music by discovering tracks, retrieving audio, extracting musical features, analyzing lyrics when available, and generating natural listening observations. Use when a user asks to listen to a song, compare songs by sound, or analyze an instrumental/non-lyrical track from text input.
user-invocable: true
disable-model-invocation: false
---

# Music Listener Skill

Use this skill when the user asks to listen to music from a text query, for example: `Listen to Mac Miller's Good News`.

## Execution Flow

1. Discover candidates:
```bash
python3 tools/music_discover.py "<query>"
```

2. Run end-to-end listen:
```bash
python3 tools/music_listen.py "<query>"
```

Mode options:
```bash
python3 tools/music_listen.py "<query>" --mode auto
python3 tools/music_listen.py "<query>" --mode full_audio
python3 tools/music_listen.py "<query>" --mode metadata_only
python3 tools/music_listen.py "<query>" --mode descriptor_only
```

3. If the user requests low-level artifacts, run layer tools:
```bash
python3 tools/music_fetch.py "<query>"
python3 tools/music_analyze.py "<local_audio_path>"
python3 tools/music_cache_status.py "<query_or_key>"
```

## Behavioral Requirements

- Prefer primary discovery via yt-dlp.
- Use YouTube Data API only when `YOUTUBE_API_KEY` is configured.
- Use Spotify metadata discovery when Spotify credentials are configured.
- Use MusicBrainz as metadata fallback.
- Use AcousticBrainz/Deezer descriptor lookup in descriptor-only flows for tempo/key/texture proxies.
- Report uncertainty explicitly.
- Never invent lyrics.
- If lyrics are unavailable, continue with audio-only analysis and say so clearly.
- If audio retrieval/analysis fails in `auto`, continue with descriptor/metadata synthesis and state uncertainty and missing fields clearly.
- For instrumental tracks, focus on rhythm, harmony, texture, and dynamics.

## Response Requirements

- Return a natural listening response first.
- Include brief structured highlights (tempo/key/energy) only as supporting evidence.
- When lyrics are present, include a concise lyric-feeling section and a combined interpretation.
- If retrieval or analysis fails, explain fallback path and next best action.

## Configuration

- Default settings file: `config/settings.example.yaml`
- Override with: `MUSIC_SETTINGS_PATH=/path/to/settings.yaml`
- Cache root: `cache/`
