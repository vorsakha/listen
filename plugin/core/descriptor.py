from __future__ import annotations

from typing import Any

import requests

from .models import DescriptorArtifact, MetadataArtifact, SourceCandidate


def _nested(payload: dict[str, Any], path: list[str]) -> Any:
    cur: Any = payload
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _settings_descriptors(settings: dict[str, Any]) -> dict[str, Any]:
    return settings.get("descriptors") or {}


def _find_mbid(metadata: MetadataArtifact | None, source: SourceCandidate, timeout_sec: int) -> str | None:
    params: dict[str, str] = {"fmt": "json", "limit": "1"}
    headers = {"User-Agent": "openclaw-listen/0.1"}
    if metadata and metadata.isrc:
        params["query"] = f"isrc:{metadata.isrc}"
    else:
        title = metadata.title if metadata and metadata.title else source.title
        artist = ", ".join(metadata.artists) if metadata and metadata.artists else (source.artist_guess or "")
        params["query"] = f'recording:"{title}" AND artist:"{artist}"'.strip()

    try:
        resp = requests.get("https://musicbrainz.org/ws/2/recording", params=params, headers=headers, timeout=timeout_sec)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None

    data = resp.json()
    recordings = data.get("recordings") or []
    if not recordings or not isinstance(recordings[0], dict):
        return None
    mbid = recordings[0].get("id")
    return str(mbid) if mbid else None


def _fetch_acousticbrainz(mbid: str, timeout_sec: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    base = "https://acousticbrainz.org"
    low = None
    high = None
    try:
        low_resp = requests.get(f"{base}/{mbid}/low-level", params={"n": 0}, timeout=timeout_sec)
        if low_resp.status_code == 200:
            low = low_resp.json()
    except requests.RequestException:
        low = None

    try:
        high_resp = requests.get(f"{base}/{mbid}/high-level", params={"n": 0}, timeout=timeout_sec)
        if high_resp.status_code == 200:
            high = high_resp.json()
    except requests.RequestException:
        high = None
    return low, high


def _fetch_deezer_track(metadata: MetadataArtifact | None, source: SourceCandidate, timeout_sec: int) -> dict[str, Any] | None:
    if metadata and metadata.isrc:
        try:
            resp = requests.get(f"https://api.deezer.com/track/isrc:{metadata.isrc}", timeout=timeout_sec)
            if resp.status_code == 200:
                payload = resp.json()
                if isinstance(payload, dict) and payload.get("id"):
                    return payload
        except requests.RequestException:
            pass

    query_parts = [source.title]
    if source.artist_guess:
        query_parts.append(source.artist_guess)
    query = " ".join(query_parts).strip()
    if not query:
        return None
    try:
        resp = requests.get("https://api.deezer.com/search", params={"q": query}, timeout=timeout_sec)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    payload = resp.json()
    items = payload.get("data") or []
    if not items or not isinstance(items[0], dict):
        return None
    return items[0]


def _default_coverage() -> dict[str, str]:
    return {
        "tempo_bpm": "missing",
        "key": "missing",
        "mode": "missing",
        "loudness_proxy": "missing",
        "energy_proxy": "missing",
        "texture_proxy": "missing",
        "danceability_proxy": "missing",
        "acousticness_proxy": "missing",
        "instrumentalness_proxy": "missing",
    }


def _confidence_from_coverage(coverage: dict[str, str]) -> float:
    weights = {
        "tempo_bpm": 0.16,
        "key": 0.12,
        "mode": 0.08,
        "loudness_proxy": 0.10,
        "energy_proxy": 0.14,
        "texture_proxy": 0.16,
        "danceability_proxy": 0.10,
        "acousticness_proxy": 0.07,
        "instrumentalness_proxy": 0.07,
    }
    score_map = {"direct": 1.0, "mapped": 0.7, "missing": 0.0}
    num = 0.0
    den = 0.0
    for field, weight in weights.items():
        den += weight
        num += weight * score_map.get(coverage.get(field, "missing"), 0.0)
    return round((num / den) if den else 0.0, 4)


def build_descriptor_artifact(
    source: SourceCandidate,
    metadata: MetadataArtifact | None,
    settings: dict[str, Any],
) -> DescriptorArtifact | None:
    cfg = _settings_descriptors(settings)
    if not cfg.get("enabled", True):
        return None
    min_confidence = float(cfg.get("min_confidence", 0.45))

    timeout_sec = int(cfg.get("request_timeout_sec", 10))
    warnings: list[str] = []
    coverage = _default_coverage()
    sources_used: list[str] = []

    descriptor = DescriptorArtifact(
        mode="unknown",
        coverage={k: "missing" for k in coverage},
        texture_proxy={"spectral_centroid_mean": None, "spectral_complexity_mean": None},
    )

    mbid = _find_mbid(metadata, source, timeout_sec=timeout_sec)
    low = None
    high = None
    if mbid:
        low, high = _fetch_acousticbrainz(mbid, timeout_sec=timeout_sec)
    else:
        warnings.append("DESCRIPTOR_MBID_NOT_FOUND")

    if low:
        sources_used.append("acousticbrainz.low-level")
        tempo = _as_float(_nested(low, ["rhythm", "bpm"]))
        if tempo is not None:
            descriptor.tempo_bpm = tempo
            coverage["tempo_bpm"] = "direct"

        key_name = _nested(low, ["tonal", "key_key"])
        if isinstance(key_name, str) and key_name:
            descriptor.key = key_name
            coverage["key"] = "direct"

        key_scale = _nested(low, ["tonal", "key_scale"])
        if key_scale in {"major", "minor"}:
            descriptor.mode = key_scale
            coverage["mode"] = "direct"

        loudness = _as_float(_nested(low, ["lowlevel", "average_loudness"]))
        if loudness is None:
            loudness = _as_float(_nested(low, ["lowlevel", "loudness_ebu128", "integrated"]))
        if loudness is not None:
            descriptor.loudness_proxy = loudness
            coverage["loudness_proxy"] = "direct"

        centroid = _as_float(_nested(low, ["lowlevel", "spectral_centroid", "mean"]))
        complexity = _as_float(_nested(low, ["lowlevel", "spectral_complexity", "mean"]))
        descriptor.texture_proxy["spectral_centroid_mean"] = centroid
        descriptor.texture_proxy["spectral_complexity_mean"] = complexity
        if centroid is not None or complexity is not None:
            coverage["texture_proxy"] = "direct"

    if high:
        sources_used.append("acousticbrainz.high-level")
        energy = _as_float(_nested(high, ["highlevel", "mood_party", "all", "party"]))
        if energy is not None:
            descriptor.energy_proxy = energy
            coverage["energy_proxy"] = "direct"

        danceability = _as_float(_nested(high, ["highlevel", "danceability", "all", "danceable"]))
        if danceability is not None:
            descriptor.danceability_proxy = danceability
            coverage["danceability_proxy"] = "direct"

        acousticness = _as_float(_nested(high, ["highlevel", "mood_acoustic", "all", "acoustic"]))
        if acousticness is not None:
            descriptor.acousticness_proxy = acousticness
            coverage["acousticness_proxy"] = "direct"

        instrumental = _as_float(_nested(high, ["highlevel", "voice_instrumental", "all", "instrumental"]))
        if instrumental is not None:
            descriptor.instrumentalness_proxy = instrumental
            coverage["instrumentalness_proxy"] = "direct"

    deezer_track = _fetch_deezer_track(metadata, source, timeout_sec=timeout_sec)
    if deezer_track:
        sources_used.append("deezer.track")
        if coverage["tempo_bpm"] == "missing":
            tempo = _as_float(deezer_track.get("bpm"))
            if tempo is not None:
                descriptor.tempo_bpm = tempo
                coverage["tempo_bpm"] = "direct"
        if coverage["loudness_proxy"] == "missing":
            gain = _as_float(deezer_track.get("gain"))
            if gain is not None:
                descriptor.loudness_proxy = gain
                coverage["loudness_proxy"] = "direct"

    if descriptor.energy_proxy is None and descriptor.loudness_proxy is not None:
        # Provide a soft energy proxy from normalized loudness when no direct energy signal exists.
        descriptor.energy_proxy = max(0.0, min(1.0, (descriptor.loudness_proxy + 15.0) / 30.0))
        coverage["energy_proxy"] = "mapped"

    descriptor.coverage = {k: v for k, v in coverage.items()}
    descriptor.sources_used = sources_used
    descriptor.warnings = warnings
    descriptor.confidence = _confidence_from_coverage(coverage)

    if not sources_used:
        descriptor.warnings.append("DESCRIPTOR_SOURCES_UNAVAILABLE")
    if descriptor.confidence < min_confidence:
        descriptor.warnings.append(f"DESCRIPTOR_CONFIDENCE_BELOW_MIN:{descriptor.confidence:.2f}")
        return None
    return descriptor
