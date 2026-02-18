# Fallback Policy

## Discovery

1. Try `yt-dlp` search first.
2. If `YOUTUBE_API_KEY` exists, also query YouTube Data API for metadata candidates.
3. Query MusicBrainz for metadata fallback.

## Retrieval

- Only retrievable providers (`youtube`) can produce audio.
- Metadata-only results should return an explicit retrieval error.

## Analysis

- If librosa is missing, return typed error `ANALYSIS_LIBROSA_MISSING`.
- If audio cannot load, return typed error `ANALYSIS_AUDIO_LOAD_FAILED`.

## User Response

- Explain what failed.
- Show which fallback path ran.
- Offer next step (different query, shorter title, or provider check).
