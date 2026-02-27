from __future__ import annotations

import json
from subprocess import CompletedProcess

import pytest

from plugin.core.discovery import _score, discover_song, discover_with_jamendo, discover_with_spotify, discover_with_ytdlp
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
    monkeypatch.setattr("plugin.core.discovery.discover_with_spotify", lambda query, max_results=5, settings=None: [])
    monkeypatch.setattr("plugin.core.discovery.discover_with_musicbrainz", lambda query, max_results=5: [])

    out = discover_song("right song")
    assert out.selected is not None
    assert out.selected.source_id == "1"
    assert out.provider_trace[0].startswith("ytdlp:")


def test_discover_song_not_found_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("plugin.core.discovery.discover_with_ytdlp", lambda query, max_results=5: [])
    monkeypatch.setattr("plugin.core.discovery.discover_with_youtube_api", lambda query, max_results=5: [])
    monkeypatch.setattr("plugin.core.discovery.discover_with_spotify", lambda query, max_results=5, settings=None: [])
    monkeypatch.setattr("plugin.core.discovery.discover_with_musicbrainz", lambda query, max_results=5: [])

    with pytest.raises(DiscoveryError) as exc:
        discover_song("missing track")
    assert exc.value.code == "DISCOVERY_NOT_FOUND"


def test_discover_with_spotify_maps_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setattr(
        "plugin.core.discovery.search_tracks",
        lambda query, settings, limit=5: [
            {
                "id": "sp1",
                "name": "Good News",
                "artists": [{"name": "Mac Miller"}],
                "duration_ms": 332000,
                "external_urls": {"spotify": "https://open.spotify.com/track/sp1"},
            }
        ],
    )

    out = discover_with_spotify("Mac Miller Good News", settings={"spotify": {"enabled": True}})
    assert out
    assert out[0].provider == "spotify"
    assert out[0].source_type == "metadata"


def test_score_is_accent_insensitive() -> None:
    with_accent = _score(
        "De Repente Lembrei de Voce Ulisses Rocha",
        "De Repente Lembrei de Você",
        "Ulisses Rocha",
        240,
    )
    without_accent = _score(
        "De Repente Lembrei de Voce Ulisses Rocha",
        "De Repente Lembrei de Voce",
        "Ulisses Rocha",
        240,
    )
    assert abs(with_accent - without_accent) < 0.02


def test_discover_song_obscure_title_ranks_correct_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    from plugin.core.models import SourceCandidate

    monkeypatch.setattr(
        "plugin.core.discovery.discover_with_ytdlp",
        lambda query, max_results=5: [
            SourceCandidate(provider="ytdlp", source_id="x1", title="Ulisses Rocha - Outra Cancao", confidence=0.8),
        ],
    )
    monkeypatch.setattr(
        "plugin.core.discovery.discover_with_youtube_api",
        lambda query, max_results=5: [
            SourceCandidate(
                provider="youtube_api",
                source_id="x2",
                title="De Repente Lembrei de Você",
                artist_guess="Ulisses Rocha",
                confidence=0.2,
            ),
        ],
    )
    monkeypatch.setattr("plugin.core.discovery.discover_with_spotify", lambda query, max_results=5, settings=None: [])
    monkeypatch.setattr("plugin.core.discovery.discover_with_musicbrainz", lambda query, max_results=5: [])

    out = discover_song("De Repente Lembrei de Voce Ulisses Rocha")
    assert out.selected is not None
    assert out.selected.source_id == "x2"


def test_discover_song_dedupes_cross_provider_duplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    from plugin.core.models import SourceCandidate

    monkeypatch.setattr(
        "plugin.core.discovery.discover_with_ytdlp",
        lambda query, max_results=5: [
            SourceCandidate(
                provider="ytdlp",
                source_type="youtube",
                source_id="yt1",
                title="De Repente Lembrei de Você",
                artist_guess="Ulisses Rocha",
                confidence=0.7,
            )
        ],
    )
    monkeypatch.setattr("plugin.core.discovery.discover_with_youtube_api", lambda query, max_results=5: [])
    monkeypatch.setattr(
        "plugin.core.discovery.discover_with_spotify",
        lambda query, max_results=5, settings=None: [
            SourceCandidate(
                provider="spotify",
                source_type="metadata",
                source_id="sp1",
                title="De Repente Lembrei de Voce",
                artist_guess="Ulisses Rocha",
                confidence=0.9,
            )
        ],
    )
    monkeypatch.setattr("plugin.core.discovery.discover_with_musicbrainz", lambda query, max_results=5: [])

    out = discover_song("De Repente Lembrei de Voce Ulisses Rocha")
    assert len(out.candidates) == 1
    assert out.selected is not None
    assert out.selected.source_type == "youtube"


def test_trace_reports_missing_provider_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    from plugin.core.errors import DiscoveryError
    from plugin.core.models import SourceCandidate

    def raise_missing(query, max_results=5):
        raise DiscoveryError("DISCOVERY_YTDLP_MISSING_BINARY", "not found")

    monkeypatch.setattr("plugin.core.discovery.discover_with_ytdlp", raise_missing)
    monkeypatch.setattr("plugin.core.discovery.discover_with_youtube_api", lambda query, max_results=5: [])
    monkeypatch.setattr(
        "plugin.core.discovery.discover_with_spotify",
        lambda query, max_results=5, settings=None: [
            SourceCandidate(provider="spotify", source_type="metadata", source_id="sp1", title="Song", confidence=0.7)
        ],
    )
    monkeypatch.setattr("plugin.core.discovery.discover_with_musicbrainz", lambda query, max_results=5: [])

    out = discover_song("song")
    assert any(item.startswith("ytdlp:error:missing_binary") for item in out.provider_trace)


def test_not_found_error_includes_actionable_provider_hints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(
        "plugin.core.discovery.discover_with_ytdlp",
        lambda query, max_results=5: (_ for _ in ()).throw(DiscoveryError("DISCOVERY_YTDLP_MISSING_BINARY", "missing")),
    )
    monkeypatch.setattr("plugin.core.discovery.discover_with_youtube_api", lambda query, max_results=5: [])
    monkeypatch.setattr("plugin.core.discovery.discover_with_spotify", lambda query, max_results=5, settings=None: [])
    monkeypatch.setattr("plugin.core.discovery.discover_with_musicbrainz", lambda query, max_results=5: [])

    with pytest.raises(DiscoveryError) as exc:
        discover_song("missing track", settings={"spotify": {"enabled": True}})

    msg = exc.value.message
    assert "Provider trace" in msg
    assert "install yt-dlp" in msg
    assert "YOUTUBE_API_KEY" in msg


def test_discover_with_jamendo_maps_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAMENDO_CLIENT_ID", "jid")

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {
                "results": [
                    {
                        "id": "j1",
                        "name": "Song",
                        "artist_name": "Artist",
                        "duration": 210,
                        "audio": "https://cdn.jamendo.com/audio.mp3",
                    }
                ]
            }

    monkeypatch.setattr("plugin.core.discovery.requests.get", lambda *args, **kwargs: _Resp())
    out = discover_with_jamendo("Artist Song", settings={"jamendo": {"enabled": True}})
    assert out
    assert out[0].provider == "jamendo"
    assert out[0].source_type == "youtube"
    assert out[0].url == "https://cdn.jamendo.com/audio.mp3"


def test_discover_song_includes_jamendo_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    from plugin.core.models import SourceCandidate

    monkeypatch.setenv("JAMENDO_CLIENT_ID", "jid")
    monkeypatch.setattr("plugin.core.discovery.discover_with_ytdlp", lambda query, max_results=5: [])
    monkeypatch.setattr("plugin.core.discovery.discover_with_youtube_api", lambda query, max_results=5: [])
    monkeypatch.setattr(
        "plugin.core.discovery.discover_with_jamendo",
        lambda query, max_results=5, settings=None: [
            SourceCandidate(
                provider="jamendo",
                source_type="youtube",
                source_id="j1",
                title="Song",
                artist_guess="Artist",
                url="https://cdn.jamendo.com/audio.mp3",
                confidence=0.8,
            )
        ],
    )
    monkeypatch.setattr("plugin.core.discovery.discover_with_spotify", lambda query, max_results=5, settings=None: [])
    monkeypatch.setattr("plugin.core.discovery.discover_with_musicbrainz", lambda query, max_results=5: [])

    out = discover_song("Artist Song", settings={"jamendo": {"enabled": True}})
    assert any(item.startswith("jamendo:1") for item in out.provider_trace)
