from __future__ import annotations

import pytest

from plugin.core.descriptor import build_descriptor_artifact
from plugin.core.models import MetadataArtifact, SourceCandidate


class _Resp:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_build_descriptor_artifact_maps_acousticbrainz_and_deezer(monkeypatch: pytest.MonkeyPatch) -> None:
    source = SourceCandidate(provider="spotify", source_type="metadata", source_id="sp1", title="Song", artist_guess="Artist")
    metadata = MetadataArtifact(source="spotify", title="Song", artists=["Artist"], isrc="USWB11801008")

    def fake_get(url, params=None, headers=None, timeout=10):
        if "musicbrainz.org" in url:
            return _Resp(200, {"recordings": [{"id": "mbid1"}]})
        if "acousticbrainz.org/mbid1/low-level" in url:
            return _Resp(
                200,
                {
                    "rhythm": {"bpm": 120.0},
                    "tonal": {"key_key": "C", "key_scale": "major"},
                    "lowlevel": {
                        "average_loudness": -10.0,
                        "spectral_centroid": {"mean": 1800.0},
                        "spectral_complexity": {"mean": 0.6},
                    },
                },
            )
        if "acousticbrainz.org/mbid1/high-level" in url:
            return _Resp(
                200,
                {
                    "highlevel": {
                        "mood_party": {"all": {"party": 0.7}},
                        "danceability": {"all": {"danceable": 0.8}},
                        "mood_acoustic": {"all": {"acoustic": 0.2}},
                        "voice_instrumental": {"all": {"instrumental": 0.1}},
                    }
                },
            )
        if "api.deezer.com" in url:
            return _Resp(200, {"id": 1, "bpm": 121, "gain": -9.8})
        return _Resp(404, {})

    monkeypatch.setattr("plugin.core.descriptor.requests.get", fake_get)

    out = build_descriptor_artifact(source, metadata, settings={"descriptors": {"enabled": True, "min_confidence": 0.1}})
    assert out is not None
    assert out.tempo_bpm == 120.0
    assert out.key == "C"
    assert out.mode == "major"
    assert out.energy_proxy == 0.7
    assert out.coverage["tempo_bpm"] == "direct"
    assert out.confidence > 0.5


def test_build_descriptor_artifact_returns_none_when_below_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    source = SourceCandidate(provider="spotify", source_type="metadata", source_id="sp1", title="Song", artist_guess="Artist")
    metadata = MetadataArtifact(source="spotify", title="Song", artists=["Artist"], isrc="USWB11801008")

    def fake_get(url, params=None, headers=None, timeout=10):
        if "musicbrainz.org" in url:
            return _Resp(200, {"recordings": []})
        return _Resp(404, {})

    monkeypatch.setattr("plugin.core.descriptor.requests.get", fake_get)
    out = build_descriptor_artifact(source, metadata, settings={"descriptors": {"enabled": True, "min_confidence": 0.45}})
    assert out is None
