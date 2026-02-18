from __future__ import annotations

import json

from .analysis import analyze_audio
from .cache import CacheStore
from .discovery import discover_song
from .errors import AnalysisError, DiscoveryError, RetrievalError
from .lyric_analysis import analyze_lyrics
from .lyrics import fetch_lyrics
from .models import DiscoveryResult, ListenResult
from .retrieval import fetch_audio
from .settings import load_settings
from .synthesis import build_synthesis


def discover(query: str, cache: CacheStore, ttl_sec: int = 604800) -> DiscoveryResult:
    cached_payload = cache.get_query(query, ttl_sec=ttl_sec)
    if cached_payload:
        return DiscoveryResult.model_validate_json(cached_payload)

    result = discover_song(query)
    cache.put_query(query, result.model_dump_json())
    return result


def listen(query: str, cache: CacheStore, deep_analysis: bool = True) -> ListenResult:
    outcome = ListenResult(query=query)
    settings = load_settings()

    try:
        d = discover(query, cache)
    except DiscoveryError as exc:
        outcome.errors.append({"code": exc.code, "message": exc.message})
        return outcome

    outcome.source = d.selected
    outcome.fallback_trace.extend(d.provider_trace)
    if not d.selected:
        outcome.errors.append({"code": "DISCOVERY_EMPTY_SELECTION", "message": "No selected candidate"})
        return outcome

    try:
        fetched = fetch_audio(d.selected, cache)
        outcome.audio = fetched.audio
        outcome.cache["audio_cache_hit"] = fetched.cache_hit
    except RetrievalError as exc:
        outcome.errors.append({"code": exc.code, "message": exc.message})
        return outcome

    try:
        feature = analyze_audio(outcome.audio.path, cache)
        outcome.features = feature
        outcome.cache["feature_cache_key"] = cache.normalize_key(outcome.audio.path)
    except AnalysisError as exc:
        outcome.errors.append({"code": exc.code, "message": exc.message})
        return outcome

    if outcome.source:
        lyrics = fetch_lyrics(outcome.source, cache=cache, settings=settings, audio=outcome.audio)
        outcome.lyrics = lyrics
        if lyrics.text:
            outcome.lyrics_analysis = analyze_lyrics(lyrics, cache=cache)

    if deep_analysis and outcome.source and outcome.features:
        outcome.synthesis = build_synthesis(
            outcome.source,
            outcome.features,
            lyrics_analysis=outcome.lyrics_analysis,
        )

    return outcome


def cache_status(cache: CacheStore, key: str) -> str:
    return json.dumps(cache.cache_status(key), indent=2)
