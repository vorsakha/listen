from __future__ import annotations

import json
from typing import Literal

from .analysis import analyze_audio
from .cache import CacheStore
from .descriptor import build_descriptor_artifact
from .discovery import discover_song
from .errors import AnalysisError, DiscoveryError, RetrievalError
from .lyric_analysis import analyze_lyrics
from .lyrics import fetch_lyrics
from .models import DescriptorArtifact, DiscoveryResult, ListenResult, MetadataArtifact, SourceCandidate
from .retrieval import fetch_audio
from .settings import load_settings
from .synthesis import build_descriptor_synthesis, build_metadata_synthesis, build_synthesis


def discover(query: str, cache: CacheStore, ttl_sec: int = 604800) -> DiscoveryResult:
    cached_payload = cache.get_query(query, ttl_sec=ttl_sec)
    if cached_payload:
        return DiscoveryResult.model_validate_json(cached_payload)

    settings = load_settings()
    result = discover_song(query, settings=settings)
    cache.put_query(query, result.model_dump_json())
    return result


def _resolve_mode(mode: str | None, settings: dict) -> Literal["auto", "full_audio", "metadata_only", "descriptor_only"]:
    allowed = {"auto", "full_audio", "metadata_only", "descriptor_only"}
    if mode in allowed:
        return mode  # type: ignore[return-value]
    configured = ((settings.get("listen") or {}).get("default_mode")) or "auto"
    if configured in allowed:
        return configured  # type: ignore[return-value]
    return "auto"


def _metadata_from_source(source: SourceCandidate) -> MetadataArtifact:
    raw = source.raw or {}
    artists: list[str] = []
    album = None
    release_date = None
    isrc = None
    popularity = None
    metadata_source: Literal["spotify", "musicbrainz", "youtube", "unknown"] = "unknown"

    if source.provider == "spotify":
        metadata_source = "spotify"
        artists = [a.get("name") for a in raw.get("artists", []) if isinstance(a, dict) and a.get("name")]
        album = ((raw.get("album") or {}).get("name")) if isinstance(raw.get("album"), dict) else None
        release_date = (
            (raw.get("album") or {}).get("release_date")
            if isinstance(raw.get("album"), dict)
            else None
        )
        isrc = ((raw.get("external_ids") or {}).get("isrc")) if isinstance(raw.get("external_ids"), dict) else None
        popularity = raw.get("popularity") if isinstance(raw.get("popularity"), int) else None
    elif source.provider == "musicbrainz":
        metadata_source = "musicbrainz"
        if source.artist_guess:
            artists = [source.artist_guess]
    elif source.provider in {"ytdlp", "youtube_api"}:
        metadata_source = "youtube"
        if source.artist_guess:
            artists = [source.artist_guess]

    return MetadataArtifact(
        source=metadata_source,
        track_id=source.source_id,
        title=source.title,
        artists=artists,
        album=album,
        duration_sec=source.duration_sec,
        release_date=release_date,
        isrc=isrc,
        external_url=source.url,
        popularity=popularity,
    )


def _is_retrievable_source(source: SourceCandidate) -> bool:
    return source.source_type == "youtube" and bool(source.url)


def _audio_provider_priority(provider: str) -> int:
    if provider == "ytdlp":
        return 0
    if provider == "youtube_api":
        return 1
    if provider == "jamendo":
        return 2
    return 3


def _audio_candidates_for_retry(discovery: DiscoveryResult) -> list[SourceCandidate]:
    pool = discovery.candidates or ([discovery.selected] if discovery.selected else [])
    retrievable = [candidate for candidate in pool if _is_retrievable_source(candidate)]
    retrievable.sort(key=lambda c: (_audio_provider_priority(c.provider), -c.confidence))

    seen: set[tuple[str, str]] = set()
    unique: list[SourceCandidate] = []
    for candidate in retrievable:
        key = (candidate.provider, candidate.source_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _primary_ytdlp_failure_marker(provider_trace: list[str]) -> str | None:
    for item in provider_trace:
        if item.startswith("ytdlp:error:"):
            reason = item.split(":", 2)[2] or "error"
            return f"primary:ytdlp_failed({reason})"
    return None


def listen(query: str, cache: CacheStore, deep_analysis: bool = True, mode: str | None = None) -> ListenResult:
    outcome = ListenResult(query=query)
    settings = load_settings()
    runtime_mode = _resolve_mode(mode, settings)

    try:
        d = discover(query, cache)
    except DiscoveryError as exc:
        outcome.errors.append({"code": exc.code, "message": exc.message})
        return outcome

    outcome.fallback_trace.extend(d.provider_trace)
    ytdlp_failure = _primary_ytdlp_failure_marker(d.provider_trace)
    if ytdlp_failure:
        outcome.fallback_trace.append(ytdlp_failure)
    if not d.selected:
        outcome.errors.append({"code": "DISCOVERY_EMPTY_SELECTION", "message": "No selected candidate"})
        return outcome

    should_try_full_audio = runtime_mode in {"auto", "full_audio"}
    audio_candidates: list[SourceCandidate] = []
    chosen_source = d.selected
    if should_try_full_audio:
        audio_candidates = _audio_candidates_for_retry(d)
        if audio_candidates:
            chosen_source = audio_candidates[0]
            outcome.fallback_trace.append(f"audio_source:selected({chosen_source.provider}:{chosen_source.source_id})")
        else:
            chosen_source = d.selected

    outcome.source = chosen_source
    outcome.metadata = _metadata_from_source(chosen_source)

    full_audio_ready = False
    audio_retrieved = False
    if should_try_full_audio:
        if not audio_candidates:
            if runtime_mode == "full_audio":
                outcome.errors.append(
                    {
                        "code": "RETRIEVAL_UNAVAILABLE",
                        "message": "No retrievable candidates found for full_audio mode",
                    }
                )
                outcome.analysis_mode = "failed"
                return outcome
            outcome.fallback_trace.append("mode:auto->metadata_only(no_retrievable_source)")
        else:
            retrieval_error: RetrievalError | None = None
            for idx, candidate in enumerate(audio_candidates):
                if idx > 0:
                    prev = audio_candidates[idx - 1]
                    outcome.fallback_trace.append(f"audio_source:retry({prev.provider}->{candidate.provider})")

                outcome.source = candidate
                outcome.metadata = _metadata_from_source(candidate)
                try:
                    fetched = fetch_audio(candidate, cache)
                except RetrievalError as exc:
                    retrieval_error = exc
                    outcome.errors.append({"code": exc.code, "message": exc.message})
                    continue

                outcome.audio = fetched.audio
                outcome.cache["audio_cache_hit"] = fetched.cache_hit
                audio_retrieved = True
                retrieval_error = None
                break

            if retrieval_error is not None:
                if runtime_mode == "full_audio":
                    outcome.analysis_mode = "failed"
                    return outcome
                outcome.fallback_trace.append("mode:auto->metadata_only(retrieval_failed_all_candidates)")
            elif outcome.audio:
                chosen_source = outcome.source

        if audio_retrieved and outcome.audio:
            try:
                feature = analyze_audio(outcome.audio.path, cache)
                outcome.features = feature
                outcome.cache["feature_cache_key"] = cache.normalize_key(outcome.audio.path)
                full_audio_ready = True
            except AnalysisError as exc:
                outcome.errors.append({"code": exc.code, "message": exc.message})
                if runtime_mode == "full_audio":
                    outcome.analysis_mode = "failed"
                    return outcome
                outcome.fallback_trace.append("mode:auto->metadata_only(analysis_failed)")

    if outcome.source:
        lyrics = fetch_lyrics(outcome.source, cache=cache, settings=settings, audio=outcome.audio)
        outcome.lyrics = lyrics
        if lyrics.text:
            outcome.lyrics_analysis = analyze_lyrics(lyrics, cache=cache)

    descriptor: DescriptorArtifact | None = None
    should_build_descriptor = runtime_mode in {"descriptor_only", "metadata_only", "auto"} and not full_audio_ready
    if should_build_descriptor and outcome.source:
        descriptor = build_descriptor_artifact(outcome.source, outcome.metadata, settings=settings)
        outcome.descriptor = descriptor
        if descriptor and descriptor.confidence > 0.0:
            outcome.fallback_trace.append("descriptor:resolved")
        elif runtime_mode == "descriptor_only":
            outcome.fallback_trace.append("descriptor:unavailable")

    if full_audio_ready:
        outcome.analysis_mode = "full_audio"
    elif descriptor and descriptor.confidence > 0:
        outcome.analysis_mode = "descriptor_only"
    else:
        outcome.analysis_mode = "metadata_only" if runtime_mode != "full_audio" else "failed"

    if deep_analysis and outcome.source and outcome.features and outcome.analysis_mode == "full_audio":
        outcome.synthesis = build_synthesis(
            outcome.source,
            outcome.features,
            lyrics_analysis=outcome.lyrics_analysis,
        )
    elif deep_analysis and outcome.source and outcome.analysis_mode == "descriptor_only" and outcome.descriptor:
        outcome.synthesis = build_descriptor_synthesis(
            source=outcome.source,
            descriptor=outcome.descriptor,
            lyrics_analysis=outcome.lyrics_analysis,
        )
    elif deep_analysis and outcome.source and outcome.analysis_mode == "metadata_only":
        outcome.synthesis = build_metadata_synthesis(
            source=outcome.source,
            metadata=outcome.metadata,
            lyrics_analysis=outcome.lyrics_analysis,
        )

    return outcome


def cache_status(cache: CacheStore, key: str) -> str:
    return json.dumps(cache.cache_status(key), indent=2)
