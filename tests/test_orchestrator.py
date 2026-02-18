from __future__ import annotations

import pytest

from plugin.core.cache import CacheStore
from plugin.core.errors import AnalysisError, DiscoveryError, RetrievalError
from plugin.core.models import (
    AudioArtifact,
    DiscoveryResult,
    FeatureResult,
    FetchResult,
    LyricsArtifact,
    SourceCandidate,
    SynthesisResult,
)
from plugin.core.orchestrator import listen


def _cache(tmp_path):
    return CacheStore(root_dir=str(tmp_path / "cache"), sqlite_path=str(tmp_path / "cache" / "index.sqlite"))


def _selected() -> SourceCandidate:
    return SourceCandidate(provider="ytdlp", source_id="a", title="Song", url="https://www.youtube.com/watch?v=a")


def test_listen_success(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    selected = _selected()

    monkeypatch.setattr(
        "plugin.core.orchestrator.discover",
        lambda query, cache: DiscoveryResult(query=query, selected=selected, candidates=[selected], provider_trace=["ytdlp:1"]),
    )
    monkeypatch.setattr(
        "plugin.core.orchestrator.fetch_audio",
        lambda source, cache: FetchResult(source=source, audio=AudioArtifact(path="/tmp/a.wav", format="wav"), cache_hit=False),
    )
    monkeypatch.setattr(
        "plugin.core.orchestrator.analyze_audio",
        lambda audio_path, cache: FeatureResult(tempo_bpm=100.0, key="C", mode="major", energy_mean=0.1),
    )
    monkeypatch.setattr(
        "plugin.core.orchestrator.fetch_lyrics",
        lambda source, cache, settings, audio: LyricsArtifact(source="none", warnings=["LYRICS_NOT_FOUND"]),
    )
    monkeypatch.setattr("plugin.core.orchestrator.analyze_lyrics", lambda lyrics, cache: None)
    monkeypatch.setattr(
        "plugin.core.orchestrator.build_synthesis",
        lambda source, features, lyrics_analysis=None: SynthesisResult(
            natural_observation="obs",
            lyric_observation=None,
            combined_observation="combined",
            highlights=["h"],
            uncertainty_notes=[],
            prompt_for_text_model="p",
        ),
    )

    out = listen("q", _cache(tmp_path), deep_analysis=True)
    assert not out.errors
    assert out.analysis_mode == "full_audio"
    assert out.source is not None
    assert out.metadata is not None
    assert out.audio is not None
    assert out.features is not None
    assert out.lyrics is not None
    assert out.lyrics.source == "none"
    assert out.lyrics_analysis is None
    assert out.synthesis is not None


def test_listen_discovery_error(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    def boom(query, cache):
        raise DiscoveryError("DISCOVERY_NOT_FOUND", "not found")

    monkeypatch.setattr("plugin.core.orchestrator.discover", boom)
    out = listen("q", _cache(tmp_path))
    assert out.errors[0]["code"] == "DISCOVERY_NOT_FOUND"


def test_listen_retrieval_error(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    selected = _selected()
    monkeypatch.setattr(
        "plugin.core.orchestrator.discover",
        lambda query, cache: DiscoveryResult(query=query, selected=selected, candidates=[selected], provider_trace=[]),
    )

    def boom(source, cache):
        raise RetrievalError("RETRIEVAL_TIMEOUT", "timeout")

    monkeypatch.setattr("plugin.core.orchestrator.fetch_audio", boom)
    monkeypatch.setattr(
        "plugin.core.orchestrator.fetch_lyrics",
        lambda source, cache, settings, audio: LyricsArtifact(source="none", warnings=["LYRICS_NOT_FOUND"]),
    )
    monkeypatch.setattr("plugin.core.orchestrator.analyze_lyrics", lambda lyrics, cache: None)
    monkeypatch.setattr(
        "plugin.core.orchestrator.build_metadata_synthesis",
        lambda source, metadata, lyrics_analysis=None: SynthesisResult(
            natural_observation="meta-obs",
            lyric_observation=None,
            combined_observation="meta-combined",
            highlights=["meta"],
            uncertainty_notes=["No direct audio analysis; interpretation is metadata/lyrics-based."],
            prompt_for_text_model="meta-prompt",
        ),
    )

    out = listen("q", _cache(tmp_path), mode="auto")
    assert out.errors[0]["code"] == "RETRIEVAL_TIMEOUT"
    assert out.analysis_mode == "metadata_only"
    assert out.synthesis is not None


def test_listen_analysis_error(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    selected = _selected()
    monkeypatch.setattr(
        "plugin.core.orchestrator.discover",
        lambda query, cache: DiscoveryResult(query=query, selected=selected, candidates=[selected], provider_trace=[]),
    )
    monkeypatch.setattr(
        "plugin.core.orchestrator.fetch_audio",
        lambda source, cache: FetchResult(source=source, audio=AudioArtifact(path="/tmp/a.wav", format="wav"), cache_hit=False),
    )

    def boom(audio_path, cache):
        raise AnalysisError("ANALYSIS_AUDIO_LOAD_FAILED", "bad")

    monkeypatch.setattr("plugin.core.orchestrator.analyze_audio", boom)
    monkeypatch.setattr(
        "plugin.core.orchestrator.fetch_lyrics",
        lambda source, cache, settings, audio: LyricsArtifact(source="none", warnings=["LYRICS_NOT_FOUND"]),
    )
    monkeypatch.setattr("plugin.core.orchestrator.analyze_lyrics", lambda lyrics, cache: None)
    monkeypatch.setattr(
        "plugin.core.orchestrator.build_metadata_synthesis",
        lambda source, metadata, lyrics_analysis=None: SynthesisResult(
            natural_observation="meta-obs",
            lyric_observation=None,
            combined_observation="meta-combined",
            highlights=["meta"],
            uncertainty_notes=["No direct audio analysis; interpretation is metadata/lyrics-based."],
            prompt_for_text_model="meta-prompt",
        ),
    )

    out = listen("q", _cache(tmp_path), mode="auto")
    assert out.errors[0]["code"] == "ANALYSIS_AUDIO_LOAD_FAILED"
    assert out.analysis_mode == "metadata_only"


def test_listen_full_audio_mode_remains_strict(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    selected = _selected()
    monkeypatch.setattr(
        "plugin.core.orchestrator.discover",
        lambda query, cache: DiscoveryResult(query=query, selected=selected, candidates=[selected], provider_trace=[]),
    )

    def boom(source, cache):
        raise RetrievalError("RETRIEVAL_TIMEOUT", "timeout")

    monkeypatch.setattr("plugin.core.orchestrator.fetch_audio", boom)
    out = listen("q", _cache(tmp_path), mode="full_audio")
    assert out.errors[0]["code"] == "RETRIEVAL_TIMEOUT"
    assert out.analysis_mode == "failed"
