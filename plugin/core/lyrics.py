from __future__ import annotations

import json
from difflib import SequenceMatcher

import requests

from .cache import CacheStore
from .models import AudioArtifact, LyricsArtifact, SourceCandidate


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _candidate_score(
    source: SourceCandidate,
    title: str | None,
    artist: str | None,
    duration_sec: int | float | None,
) -> float:
    title_score = SequenceMatcher(None, _norm(source.title), _norm(title)).ratio()
    artist_score = 0.0
    if source.artist_guess and artist:
        artist_score = SequenceMatcher(None, _norm(source.artist_guess), _norm(artist)).ratio()

    duration_score = 0.5
    if source.duration_sec and duration_sec:
        delta = abs(float(source.duration_sec) - float(duration_sec))
        duration_score = max(0.0, 1.0 - (delta / 45.0))

    return (0.55 * title_score) + (0.30 * artist_score) + (0.15 * duration_score)


def _extract_lyrics_text(payload: dict) -> tuple[str | None, bool]:
    synced = payload.get("syncedLyrics")
    plain = payload.get("plainLyrics")
    if isinstance(synced, str) and synced.strip():
        return synced.strip(), True
    if isinstance(plain, str) and plain.strip():
        return plain.strip(), False
    return None, False


def _fetch_from_lrclib(source: SourceCandidate, timeout_sec: int) -> LyricsArtifact:
    search_url = "https://lrclib.net/api/search"
    q_artist = (source.artist_guess or "").strip()
    params_list = [
        {"track_name": source.title, "artist_name": q_artist},
        {"track_name": source.title},
    ]
    candidates: list[tuple[float, dict]] = []

    for params in params_list:
        try:
            resp = requests.get(search_url, params=params, timeout=timeout_sec)
        except requests.RequestException:
            continue
        if resp.status_code != 200:
            continue
        try:
            data = resp.json()
        except ValueError:
            continue
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            score = _candidate_score(
                source=source,
                title=item.get("trackName"),
                artist=item.get("artistName"),
                duration_sec=item.get("duration"),
            )
            candidates.append((score, item))
        if candidates:
            break

    if not candidates:
        return LyricsArtifact(source="none", warnings=["LYRICS_NOT_FOUND"])

    best = max(candidates, key=lambda t: t[0])
    text, is_synced = _extract_lyrics_text(best[1])
    if not text:
        return LyricsArtifact(source="none", warnings=["LYRICS_EMPTY_PAYLOAD"])

    return LyricsArtifact(
        source="lrclib",
        text=text,
        language=(best[1].get("lang") or None),
        is_synced=is_synced,
        provider_confidence=round(float(best[0]), 4),
    )


def _transcribe_audio_for_lyrics(audio: AudioArtifact, model_size: str = "small") -> LyricsArtifact:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return LyricsArtifact(source="none", warnings=["LYRICS_ASR_UNAVAILABLE"])

    try:
        model = WhisperModel(model_size, device="cpu")
        segments, _ = model.transcribe(audio.path, vad_filter=True)
        text_parts = [seg.text.strip() for seg in segments if seg.text.strip()]
    except Exception:
        return LyricsArtifact(source="none", warnings=["LYRICS_ASR_FAILED"])

    text = "\n".join(text_parts).strip()
    if not text:
        return LyricsArtifact(source="none", warnings=["LYRICS_ASR_EMPTY"])

    return LyricsArtifact(
        source="asr",
        text=text,
        language=None,
        is_synced=False,
        provider_confidence=None,
    )


def fetch_lyrics(
    source: SourceCandidate,
    cache: CacheStore,
    settings: dict,
    audio: AudioArtifact | None = None,
) -> LyricsArtifact:
    cfg = settings.get("lyrics") or {}
    if not cfg.get("enabled", True):
        return LyricsArtifact(source="none", warnings=["LYRICS_DISABLED"])

    source_key = cache.normalize_key(f"{source.provider}:{source.source_id}:lyrics")
    if cfg.get("include_in_cache", True):
        cached_payload = cache.get_lyrics(source_key)
        if cached_payload:
            return LyricsArtifact.model_validate_json(cached_payload)

    timeout_sec = int(cfg.get("request_timeout_sec", 10))
    min_chars = int(cfg.get("min_text_chars", 120))
    lyrics = _fetch_from_lrclib(source, timeout_sec=timeout_sec)

    if lyrics.text:
        max_chars = int(cfg.get("max_chars", 12000))
        lyrics.text = lyrics.text[:max_chars]
        if len(lyrics.text) < min_chars:
            lyrics = LyricsArtifact(source="none", warnings=["LYRICS_TOO_SHORT"])

    if (not lyrics.text) and cfg.get("allow_asr_fallback", False) and audio is not None:
        lyrics = _transcribe_audio_for_lyrics(
            audio=audio,
            model_size=str(cfg.get("asr_model_size", "small")),
        )
        if lyrics.text and len(lyrics.text) < min_chars:
            lyrics = LyricsArtifact(source="none", warnings=["LYRICS_TOO_SHORT"])

    if cfg.get("include_in_cache", True):
        cache.put_lyrics(source_key, json.dumps(lyrics.model_dump()))
    return lyrics
