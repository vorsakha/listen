from __future__ import annotations

from plugin.core.cache import CacheStore
from plugin.core.lyric_analysis import analyze_lyrics
from plugin.core.models import LyricsArtifact


def test_analyze_lyrics_returns_structured_result(tmp_path) -> None:
    cache = CacheStore(root_dir=str(tmp_path / "cache"), sqlite_path=str(tmp_path / "cache" / "index.sqlite"))
    lyrics = LyricsArtifact(
        source="lrclib",
        text="I feel lost and broken tonight\nBut I still hope the morning light will heal me",
    )

    out = analyze_lyrics(lyrics, cache=cache)
    assert out is not None
    assert out.themes
    assert out.emotional_polarity in {"negative", "mixed", "positive", "neutral"}
    assert 0.0 <= out.confidence <= 1.0


def test_analyze_lyrics_uses_cache(tmp_path) -> None:
    cache = CacheStore(root_dir=str(tmp_path / "cache"), sqlite_path=str(tmp_path / "cache" / "index.sqlite"))
    lyrics = LyricsArtifact(source="lrclib", text="Love and fear keep me awake in the dark")

    first = analyze_lyrics(lyrics, cache=cache)
    second = analyze_lyrics(lyrics, cache=cache)
    assert first is not None
    assert second is not None
    assert second.summary == first.summary


def test_analyze_lyrics_returns_none_without_text() -> None:
    out = analyze_lyrics(LyricsArtifact(source="none", text=None))
    assert out is None
