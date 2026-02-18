from __future__ import annotations

import json
import os
import re
import subprocess
from difflib import SequenceMatcher
from typing import Any

import requests

from .errors import DiscoveryError
from .models import DiscoveryResult, SourceCandidate


def _score(query: str, title: str, artist_guess: str | None, duration_sec: int | None) -> float:
    query_l = query.lower()
    title_l = title.lower()
    title_score = SequenceMatcher(None, query_l, title_l).ratio()

    artist_score = 0.0
    if artist_guess:
        artist_score = SequenceMatcher(None, query_l, artist_guess.lower()).ratio()

    duration_score = 0.5
    if duration_sec and 60 <= duration_sec <= 720:
        duration_score = 1.0

    return (0.50 * title_score) + (0.30 * artist_score) + (0.20 * duration_score)


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
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
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


def discover_song(query: str, max_results: int = 5) -> DiscoveryResult:
    trace: list[str] = []
    all_candidates: list[SourceCandidate] = []

    providers = [
        ("ytdlp", discover_with_ytdlp),
        ("youtube_api", discover_with_youtube_api),
        ("musicbrainz", discover_with_musicbrainz),
    ]

    for provider_name, provider_fn in providers:
        try:
            found = provider_fn(query, max_results=max_results)
            trace.append(f"{provider_name}:{len(found)}")
            all_candidates.extend(found)
        except DiscoveryError:
            trace.append(f"{provider_name}:error")

    if not all_candidates:
        raise DiscoveryError("DISCOVERY_NOT_FOUND", f"No candidates found for query '{query}'")

    all_candidates.sort(key=lambda c: c.confidence, reverse=True)
    selected = all_candidates[0]
    return DiscoveryResult(query=query, candidates=all_candidates, selected=selected, provider_trace=trace)
