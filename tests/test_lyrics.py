from __future__ import annotations

from plugin.core.cache import CacheStore
from plugin.core.lyrics import fetch_lyrics
from plugin.core.models import AudioArtifact, SourceCandidate


class _Resp:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _source() -> SourceCandidate:
    return SourceCandidate(
        provider="ytdlp",
        source_id="abc",
        title="Good News",
        artist_guess="Mac Miller",
        duration_sec=330,
        url="https://www.youtube.com/watch?v=abc",
    )


def test_fetch_lyrics_lrclib_hit(monkeypatch, tmp_path) -> None:
    cache = CacheStore(root_dir=str(tmp_path / "cache"), sqlite_path=str(tmp_path / "cache" / "index.sqlite"))

    def fake_get(url, params, timeout):
        return _Resp(
            200,
            [
                {
                    "trackName": "Good News",
                    "artistName": "Mac Miller",
                    "duration": 331,
                    "plainLyrics": "Hold on, hold on\nthere's a lot that's going on",
                    "lang": "en",
                }
            ],
        )

    monkeypatch.setattr("plugin.core.lyrics.requests.get", fake_get)
    out = fetch_lyrics(_source(), cache=cache, settings={"lyrics": {"min_text_chars": 5}})
    assert out.source == "lrclib"
    assert out.text is not None
    assert "hold on" in out.text.lower()


def test_fetch_lyrics_miss_returns_none(monkeypatch, tmp_path) -> None:
    cache = CacheStore(root_dir=str(tmp_path / "cache"), sqlite_path=str(tmp_path / "cache" / "index.sqlite"))

    def fake_get(url, params, timeout):
        return _Resp(200, [])

    monkeypatch.setattr("plugin.core.lyrics.requests.get", fake_get)
    out = fetch_lyrics(_source(), cache=cache, settings={"lyrics": {"allow_asr_fallback": False}})
    assert out.source == "none"
    assert "LYRICS_NOT_FOUND" in out.warnings


def test_fetch_lyrics_asr_fallback_dependency_missing(monkeypatch, tmp_path) -> None:
    cache = CacheStore(root_dir=str(tmp_path / "cache"), sqlite_path=str(tmp_path / "cache" / "index.sqlite"))

    def fake_get(url, params, timeout):
        return _Resp(200, [])

    monkeypatch.setattr("plugin.core.lyrics.requests.get", fake_get)
    out = fetch_lyrics(
        _source(),
        cache=cache,
        settings={"lyrics": {"allow_asr_fallback": True}},
        audio=AudioArtifact(path="/tmp/a.wav", format="wav"),
    )
    assert out.source == "none"
    assert "LYRICS_ASR_UNAVAILABLE" in out.warnings
