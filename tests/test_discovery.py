from __future__ import annotations

import json
from subprocess import CompletedProcess

import pytest

from plugin.core.discovery import discover_song, discover_with_ytdlp
from plugin.core.errors import DiscoveryError


@pytest.fixture
def ytdlp_payload() -> str:
    return json.dumps(
        {
            "entries": [
                {
                    "id": "abc",
                    "title": "Mac Miller - Good News",
                    "uploader": "MacMillerVEVO",
                    "duration": 332,
                    "webpage_url": "https://www.youtube.com/watch?v=abc",
                },
                {
                    "id": "def",
                    "title": "Other Song",
                    "uploader": "Other",
                    "duration": 200,
                },
            ]
        }
    )


def test_discover_with_ytdlp_parses_candidates(monkeypatch: pytest.MonkeyPatch, ytdlp_payload: str) -> None:
    def fake_run(*args, **kwargs):
        return CompletedProcess(args=args, returncode=0, stdout=ytdlp_payload, stderr="")

    monkeypatch.setattr("plugin.core.discovery.subprocess.run", fake_run)
    out = discover_with_ytdlp("Mac Miller Good News")
    assert out
    assert out[0].source_id == "abc"
    assert out[0].provider == "ytdlp"


def test_discover_song_prefers_high_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    from plugin.core.models import SourceCandidate

    monkeypatch.setattr(
        "plugin.core.discovery.discover_with_ytdlp",
        lambda query, max_results=5: [
            SourceCandidate(provider="ytdlp", source_id="1", title="Right song", confidence=0.95),
        ],
    )
    monkeypatch.setattr("plugin.core.discovery.discover_with_youtube_api", lambda query, max_results=5: [])
    monkeypatch.setattr("plugin.core.discovery.discover_with_musicbrainz", lambda query, max_results=5: [])

    out = discover_song("right song")
    assert out.selected is not None
    assert out.selected.source_id == "1"
    assert out.provider_trace[0].startswith("ytdlp:")


def test_discover_song_not_found_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("plugin.core.discovery.discover_with_ytdlp", lambda query, max_results=5: [])
    monkeypatch.setattr("plugin.core.discovery.discover_with_youtube_api", lambda query, max_results=5: [])
    monkeypatch.setattr("plugin.core.discovery.discover_with_musicbrainz", lambda query, max_results=5: [])

    with pytest.raises(DiscoveryError) as exc:
        discover_song("missing track")
    assert exc.value.code == "DISCOVERY_NOT_FOUND"
