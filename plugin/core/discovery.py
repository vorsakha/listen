from __future__ import annotations

import json
import os
import re
import subprocess
import unicodedata
from difflib import SequenceMatcher
from typing import Any

import requests

from .errors import DiscoveryError
from .models import DiscoveryResult, SourceCandidate
from .settings import load_settings
from .spotify_client import SpotifyClientError, search_tracks


def _fold_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _normalize_text(text: str) -> str:
    lowered = _fold_accents(text).lower()
    lowered = re.sub(r"[^\w\s]", " ", lowered)
    lowered = re.sub(r"_+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _tokens(text: str) -> set[str]:
    return {part for part in _normalize_text(text).split() if part}


def _token_overlap(left: set[str], right: set[str]) -> float:
    if not left:
        return 0.0
    return len(left & right) / len(left)


def _resolve_ranking_weights(settings: dict[str, Any] | None = None) -> dict[str, float]:
    defaults = {
        "title_similarity": 0.36,
        "title_token_overlap": 0.30,
        "artist_similarity": 0.18,
        "duration_sanity": 0.10,
        "containment_bonus": 0.06,
    }
    cfg = (((settings or {}).get("discovery") or {}).get("ranking_weights")) or {}
    if isinstance(cfg, dict):
        for key in defaults:
            value = cfg.get(key)
            if isinstance(value, (int, float)):
                defaults[key] = max(0.0, float(value))

    total = sum(defaults.values())
    if total <= 0:
        return {
            "title_similarity": 0.36,
            "title_token_overlap": 0.30,
            "artist_similarity": 0.18,
            "duration_sanity": 0.10,
            "containment_bonus": 0.06,
        }

    return {key: value / total for key, value in defaults.items()}


def _score(
    query: str,
    title: str,
    artist_guess: str | None,
    duration_sec: int | None,
    weights: dict[str, float] | None = None,
) -> float:
    score_weights = weights or _resolve_ranking_weights(None)
    query_n = _normalize_text(query)
    title_n = _normalize_text(title)
    query_tokens = set(query_n.split())
    title_tokens = set(title_n.split())

    title_score = SequenceMatcher(None, query_n, title_n).ratio()
    title_token_score = _token_overlap(query_tokens, title_tokens)

    artist_score = 0.0
    if artist_guess:
        artist_n = _normalize_text(artist_guess)
        artist_seq = SequenceMatcher(None, query_n, artist_n).ratio()
        artist_token = _token_overlap(query_tokens, _tokens(artist_guess))
        artist_score = max(artist_seq, artist_token)

    duration_score = 1.0 if duration_sec and 60 <= duration_sec <= 720 else 0.5
    containment_score = 1.0 if query_n and title_n and (query_n in title_n or title_n in query_n) else 0.0

    score = (
        score_weights["title_similarity"] * title_score
        + score_weights["title_token_overlap"] * title_token_score
        + score_weights["artist_similarity"] * artist_score
        + score_weights["duration_sanity"] * duration_score
        + score_weights["containment_bonus"] * containment_score
    )
    return max(0.0, min(1.0, score))


def _canonical_candidate_key(candidate: SourceCandidate) -> tuple[str, str]:
    return (_normalize_text(candidate.title), _normalize_text(candidate.artist_guess or ""))


def _dedupe_candidates(candidates: list[SourceCandidate]) -> list[SourceCandidate]:
    deduped: dict[tuple[str, str], SourceCandidate] = {}
    for candidate in candidates:
        key = _canonical_candidate_key(candidate)
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = candidate
            continue
        prefers_youtube = candidate.source_type == "youtube" and existing.source_type != "youtube"
        existing_is_youtube = existing.source_type == "youtube"
        should_replace = candidate.confidence > existing.confidence and not (
            existing_is_youtube and candidate.source_type != "youtube"
        )
        if prefers_youtube or should_replace:
            deduped[key] = candidate
    return list(deduped.values())


def _query_variants(query: str) -> list[str]:
    folded = _fold_accents(query)
    variants = [query]
    if folded != query:
        variants.append(folded)
    return variants


def _trace_reason_from_error(exc: DiscoveryError) -> str:
    mapping = {
        "DISCOVERY_YTDLP_MISSING_BINARY": "missing_binary",
        "DISCOVERY_YTDLP_FAILED": "query_failed",
        "DISCOVERY_BAD_JSON": "bad_json",
        "DISCOVERY_SPOTIFY_AUTH_MISSING": "auth_missing",
        "DISCOVERY_SPOTIFY_REQUEST_FAILED": "request_failed",
        "SPOTIFY_AUTH_FAILED": "auth_failed",
        "SPOTIFY_RATE_LIMIT": "rate_limited",
        "SPOTIFY_SEARCH_FAILED": "search_failed",
    }
    return mapping.get(exc.code, "error")


def discover_with_ytdlp(query: str, max_results: int = 5) -> list[SourceCandidate]:
    search_expr = f"ytsearch{max_results}:{query}"
    cmd = [
        "yt-dlp",
        "--dump-single-json",
        "--skip-download",
        search_expr,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise DiscoveryError("DISCOVERY_YTDLP_MISSING_BINARY", "yt-dlp binary not found in PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise DiscoveryError("DISCOVERY_YTDLP_FAILED", f"yt-dlp discovery failed: {exc}") from exc

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise DiscoveryError("DISCOVERY_BAD_JSON", "yt-dlp returned malformed JSON") from exc

    entries = payload.get("entries") or []
    candidates: list[SourceCandidate] = []

    for item in entries:
        title = item.get("title") or "Unknown title"
        uploader = item.get("uploader") or item.get("channel")
        duration_sec = item.get("duration")
        video_id = item.get("id")
        if not video_id:
            continue
        url = item.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"
        confidence = _score(query, title, uploader, duration_sec)
        candidates.append(
            SourceCandidate(
                provider="ytdlp",
                source_type="youtube",
                source_id=video_id,
                title=title,
                artist_guess=uploader,
                duration_sec=duration_sec,
                url=url,
                confidence=confidence,
                raw=item,
            )
        )

    return sorted(candidates, key=lambda c: c.confidence, reverse=True)


def discover_with_youtube_api(query: str, max_results: int = 5) -> list[SourceCandidate]:
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        return []

    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "maxResults": max_results,
        "type": "video",
        "key": api_key,
    }
    resp = requests.get(url, params=params, timeout=20)
    if resp.status_code != 200:
        return []

    data = resp.json()
    items = data.get("items", [])
    candidates: list[SourceCandidate] = []

    for item in items:
        vid = (((item.get("id") or {}).get("videoId")) or "").strip()
        if not vid:
            continue
        snippet = item.get("snippet") or {}
        title = snippet.get("title") or "Unknown title"
        channel = snippet.get("channelTitle")
        confidence = _score(query, title, channel, None)
        candidates.append(
            SourceCandidate(
                provider="youtube_api",
                source_type="youtube",
                source_id=vid,
                title=title,
                artist_guess=channel,
                duration_sec=None,
                url=f"https://www.youtube.com/watch?v={vid}",
                confidence=confidence,
                raw=item,
            )
        )

    return sorted(candidates, key=lambda c: c.confidence, reverse=True)


def discover_with_musicbrainz(query: str, max_results: int = 3) -> list[SourceCandidate]:
    mb_url = "https://musicbrainz.org/ws/2/recording"
    params = {"query": query, "fmt": "json", "limit": max_results}
    headers = {"User-Agent": "openclaw-listen/0.1"}

    try:
        resp = requests.get(mb_url, params=params, headers=headers, timeout=20)
    except requests.RequestException:
        return []

    if resp.status_code != 200:
        return []

    payload = resp.json()
    recs = payload.get("recordings") or []
    candidates: list[SourceCandidate] = []
    for rec in recs:
        title = rec.get("title") or "Unknown title"
        artist_credit = rec.get("artist-credit") or []
        artist = None
        if artist_credit:
            first = artist_credit[0]
            artist = (first.get("artist") or {}).get("name")
        duration_ms = rec.get("length")
        duration_sec = int(duration_ms / 1000) if isinstance(duration_ms, int) else None
        rid = rec.get("id") or re.sub(r"\s+", "-", title.lower())
        candidates.append(
            SourceCandidate(
                provider="musicbrainz",
                source_type="metadata",
                source_id=rid,
                title=title,
                artist_guess=artist,
                duration_sec=duration_sec,
                url=None,
                confidence=_score(query, title, artist, duration_sec),
                raw=rec,
            )
        )
    return sorted(candidates, key=lambda c: c.confidence, reverse=True)


def discover_with_spotify(query: str, max_results: int = 5, settings: dict[str, Any] | None = None) -> list[SourceCandidate]:
    runtime_settings = settings or load_settings()
    cfg = runtime_settings.get("spotify") or {}
    if not cfg.get("enabled", True):
        return []

    try:
        tracks = search_tracks(query, settings=runtime_settings, limit=max_results)
    except SpotifyClientError as exc:
        raise DiscoveryError(exc.code, exc.message) from exc
    except requests.RequestException as exc:
        raise DiscoveryError("DISCOVERY_SPOTIFY_REQUEST_FAILED", f"Spotify request failed: {exc}") from exc

    client_id_env = str(cfg.get("client_id_env", "SPOTIFY_CLIENT_ID"))
    client_secret_env = str(cfg.get("client_secret_env", "SPOTIFY_CLIENT_SECRET"))
    if not tracks and (not os.getenv(client_id_env) or not os.getenv(client_secret_env)):
        raise DiscoveryError(
            "DISCOVERY_SPOTIFY_AUTH_MISSING",
            "Spotify credentials missing; set client id/secret env vars.",
        )

    candidates: list[SourceCandidate] = []
    for item in tracks:
        track_id = (item.get("id") or "").strip()
        if not track_id:
            continue
        title = item.get("name") or "Unknown title"
        artists = item.get("artists") or []
        artist_names = [a.get("name") for a in artists if isinstance(a, dict) and a.get("name")]
        artist = ", ".join(artist_names) if artist_names else None
        duration_ms = item.get("duration_ms")
        duration_sec = int(duration_ms / 1000) if isinstance(duration_ms, int) else None
        external_url = ((item.get("external_urls") or {}).get("spotify")) or f"https://open.spotify.com/track/{track_id}"
        confidence = _score(query, title, artist, duration_sec)
        candidates.append(
            SourceCandidate(
                provider="spotify",
                source_type="metadata",
                source_id=track_id,
                title=title,
                artist_guess=artist,
                duration_sec=duration_sec,
                url=external_url,
                confidence=confidence,
                raw=item,
            )
        )

    return sorted(candidates, key=lambda c: c.confidence, reverse=True)


def discover_song(query: str, max_results: int = 5, settings: dict[str, Any] | None = None) -> DiscoveryResult:
    trace: list[str] = []
    all_candidates: list[SourceCandidate] = []
    runtime_settings = settings or load_settings()
    weights = _resolve_ranking_weights(runtime_settings)

    providers = [
        ("ytdlp", discover_with_ytdlp),
        ("youtube_api", discover_with_youtube_api),
        ("spotify", lambda q, max_results=5: discover_with_spotify(q, max_results=max_results, settings=runtime_settings)),
        ("musicbrainz", discover_with_musicbrainz),
    ]

    for provider_name, provider_fn in providers:
        provider_candidates: list[SourceCandidate] = []
        provider_error: DiscoveryError | None = None
        for query_variant in _query_variants(query):
            try:
                found = provider_fn(query_variant, max_results=max_results)
                provider_candidates.extend(found)
            except DiscoveryError as exc:
                provider_error = exc
                break

        if provider_error is not None:
            trace.append(f"{provider_name}:error:{_trace_reason_from_error(provider_error)}")
            continue

        provider_candidates = _dedupe_candidates(provider_candidates)
        trace.append(f"{provider_name}:{len(provider_candidates)}")
        all_candidates.extend(provider_candidates)

    if not all_candidates:
        hints: list[str] = []
        if any(t.startswith("ytdlp:error:missing_binary") for t in trace):
            hints.append("install yt-dlp and ensure it is on PATH")
        if not os.getenv("YOUTUBE_API_KEY"):
            hints.append("set YOUTUBE_API_KEY to enable YouTube API fallback")
        spotify_cfg = (runtime_settings.get("spotify") or {})
        if spotify_cfg.get("enabled", True):
            client_id_env = str(spotify_cfg.get("client_id_env", "SPOTIFY_CLIENT_ID"))
            client_secret_env = str(spotify_cfg.get("client_secret_env", "SPOTIFY_CLIENT_SECRET"))
            if not os.getenv(client_id_env) or not os.getenv(client_secret_env):
                hints.append(f"set {client_id_env}/{client_secret_env} to enable Spotify discovery")
        hint_text = f" Hints: {'; '.join(hints)}." if hints else ""
        raise DiscoveryError(
            "DISCOVERY_NOT_FOUND",
            f"No candidates found for query '{query}'. Provider trace: {', '.join(trace)}.{hint_text}",
        )

    all_candidates = _dedupe_candidates(all_candidates)
    for candidate in all_candidates:
        candidate.confidence = _score(query, candidate.title, candidate.artist_guess, candidate.duration_sec, weights=weights)

    all_candidates.sort(key=lambda c: c.confidence, reverse=True)
    selected = all_candidates[0]
    return DiscoveryResult(query=query, candidates=all_candidates, selected=selected, provider_trace=trace)
