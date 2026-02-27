from __future__ import annotations

import pytest

from plugin.core.cache import CacheStore
from plugin.core.errors import AnalysisError, DiscoveryError, RetrievalError
from plugin.core.models import (
    AudioArtifact,
    DescriptorArtifact,
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
    monkeypatch.setattr("plugin.core.orchestrator.build_descriptor_artifact", lambda source, metadata, settings: None)

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
        "plugin.core.orchestrator.build_descriptor_artifact",
        lambda source, metadata, settings: DescriptorArtifact(
            tempo_bpm=90.0,
            key="C",
            mode="major",
            energy_proxy=0.5,
            texture_proxy={"spectral_centroid_mean": 1000.0, "spectral_complexity_mean": 0.3},
            confidence=0.8,
            coverage={"tempo_bpm": "direct", "key": "direct", "mode": "direct", "energy_proxy": "direct"},
            sources_used=["acousticbrainz.low-level"],
        ),
    )
    monkeypatch.setattr(
        "plugin.core.orchestrator.build_descriptor_synthesis",
        lambda source, descriptor, lyrics_analysis=None: SynthesisResult(
            natural_observation="desc-obs",
            lyric_observation=None,
            combined_observation="desc-combined",
            highlights=["desc"],
            uncertainty_notes=["descriptor"],
            prompt_for_text_model="desc-prompt",
        ),
    )

    out = listen("q", _cache(tmp_path), mode="auto")
    assert out.errors[0]["code"] == "RETRIEVAL_TIMEOUT"
    assert out.analysis_mode == "descriptor_only"
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
        "plugin.core.orchestrator.build_descriptor_artifact",
        lambda source, metadata, settings: DescriptorArtifact(
            tempo_bpm=90.0,
            key="C",
            mode="major",
            energy_proxy=0.5,
            texture_proxy={"spectral_centroid_mean": 1000.0, "spectral_complexity_mean": 0.3},
            confidence=0.8,
            coverage={"tempo_bpm": "direct", "key": "direct", "mode": "direct", "energy_proxy": "direct"},
            sources_used=["acousticbrainz.low-level"],
        ),
    )
    monkeypatch.setattr(
        "plugin.core.orchestrator.build_descriptor_synthesis",
        lambda source, descriptor, lyrics_analysis=None: SynthesisResult(
            natural_observation="desc-obs",
            lyric_observation=None,
            combined_observation="desc-combined",
            highlights=["desc"],
            uncertainty_notes=["descriptor"],
            prompt_for_text_model="desc-prompt",
        ),
    )

    out = listen("q", _cache(tmp_path), mode="auto")
    assert out.errors[0]["code"] == "ANALYSIS_AUDIO_LOAD_FAILED"
    assert out.analysis_mode == "descriptor_only"


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


def test_listen_descriptor_only_mode(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    selected = _selected()
    monkeypatch.setattr(
        "plugin.core.orchestrator.discover",
        lambda query, cache: DiscoveryResult(query=query, selected=selected, candidates=[selected], provider_trace=[]),
    )
    monkeypatch.setattr(
        "plugin.core.orchestrator.fetch_lyrics",
        lambda source, cache, settings, audio: LyricsArtifact(source="none", warnings=["LYRICS_NOT_FOUND"]),
    )
    monkeypatch.setattr("plugin.core.orchestrator.analyze_lyrics", lambda lyrics, cache: None)
    monkeypatch.setattr(
        "plugin.core.orchestrator.build_descriptor_artifact",
        lambda source, metadata, settings: DescriptorArtifact(
            tempo_bpm=102.0,
            key="F",
            mode="minor",
            energy_proxy=0.62,
            texture_proxy={"spectral_centroid_mean": 900.0, "spectral_complexity_mean": 0.5},
            confidence=0.88,
            coverage={"tempo_bpm": "direct", "key": "direct", "mode": "direct", "energy_proxy": "direct"},
            sources_used=["acousticbrainz.low-level", "acousticbrainz.high-level"],
        ),
    )
    monkeypatch.setattr(
        "plugin.core.orchestrator.build_descriptor_synthesis",
        lambda source, descriptor, lyrics_analysis=None: SynthesisResult(
            natural_observation="desc",
            lyric_observation=None,
            combined_observation="desc-c",
            highlights=["h"],
            uncertainty_notes=[],
            prompt_for_text_model="p",
        ),
    )

    out = listen("q", _cache(tmp_path), mode="descriptor_only")
    assert out.analysis_mode == "descriptor_only"
    assert out.descriptor is not None


def test_listen_auto_prefers_ytdlp_for_audio(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    selected = SourceCandidate(provider="spotify", source_type="metadata", source_id="sp1", title="Song", confidence=0.99)
    ytdlp_candidate = SourceCandidate(
        provider="ytdlp",
        source_type="youtube",
        source_id="yt1",
        title="Song",
        url="https://www.youtube.com/watch?v=yt1",
        confidence=0.85,
    )
    youtube_api_candidate = SourceCandidate(
        provider="youtube_api",
        source_type="youtube",
        source_id="yt2",
        title="Song",
        url="https://www.youtube.com/watch?v=yt2",
        confidence=0.95,
    )
    monkeypatch.setattr(
        "plugin.core.orchestrator.discover",
        lambda query, cache: DiscoveryResult(
            query=query,
            selected=selected,
            candidates=[selected, youtube_api_candidate, ytdlp_candidate],
            provider_trace=["ytdlp:1", "youtube_api:1", "spotify:1"],
        ),
    )

    called: list[str] = []

    def fake_fetch_audio(source, cache):
        called.append(source.provider)
        return FetchResult(source=source, audio=AudioArtifact(path="/tmp/a.wav", format="wav"), cache_hit=False)

    monkeypatch.setattr("plugin.core.orchestrator.fetch_audio", fake_fetch_audio)
    monkeypatch.setattr(
        "plugin.core.orchestrator.analyze_audio",
        lambda audio_path, cache: FeatureResult(tempo_bpm=100.0, key="C", mode="major", energy_mean=0.1),
    )
    monkeypatch.setattr(
        "plugin.core.orchestrator.fetch_lyrics",
        lambda source, cache, settings, audio: LyricsArtifact(source="none", warnings=["LYRICS_NOT_FOUND"]),
    )
    monkeypatch.setattr("plugin.core.orchestrator.analyze_lyrics", lambda lyrics, cache: None)
    monkeypatch.setattr("plugin.core.orchestrator.build_descriptor_artifact", lambda source, metadata, settings: None)

    out = listen("q", _cache(tmp_path), mode="auto")
    assert called == ["ytdlp"]
    assert out.analysis_mode == "full_audio"
    assert out.source is not None
    assert out.source.provider == "ytdlp"


def test_listen_auto_retries_next_retrievable_candidate(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    selected = SourceCandidate(provider="spotify", source_type="metadata", source_id="sp1", title="Song", confidence=0.99)
    ytdlp_candidate = SourceCandidate(
        provider="ytdlp",
        source_type="youtube",
        source_id="yt1",
        title="Song",
        url="https://www.youtube.com/watch?v=yt1",
        confidence=0.85,
    )
    youtube_api_candidate = SourceCandidate(
        provider="youtube_api",
        source_type="youtube",
        source_id="yt2",
        title="Song",
        url="https://www.youtube.com/watch?v=yt2",
        confidence=0.95,
    )
    monkeypatch.setattr(
        "plugin.core.orchestrator.discover",
        lambda query, cache: DiscoveryResult(
            query=query,
            selected=selected,
            candidates=[selected, ytdlp_candidate, youtube_api_candidate],
            provider_trace=["ytdlp:error:query_failed", "youtube_api:1", "spotify:1"],
        ),
    )

    calls: list[str] = []

    def fake_fetch_audio(source, cache):
        calls.append(source.provider)
        if source.provider == "ytdlp":
            raise RetrievalError("RETRIEVAL_YTDLP_FAILED", "bad")
        return FetchResult(source=source, audio=AudioArtifact(path="/tmp/b.wav", format="wav"), cache_hit=False)

    monkeypatch.setattr("plugin.core.orchestrator.fetch_audio", fake_fetch_audio)
    monkeypatch.setattr(
        "plugin.core.orchestrator.analyze_audio",
        lambda audio_path, cache: FeatureResult(tempo_bpm=100.0, key="C", mode="major", energy_mean=0.1),
    )
    monkeypatch.setattr(
        "plugin.core.orchestrator.fetch_lyrics",
        lambda source, cache, settings, audio: LyricsArtifact(source="none", warnings=["LYRICS_NOT_FOUND"]),
    )
    monkeypatch.setattr("plugin.core.orchestrator.analyze_lyrics", lambda lyrics, cache: None)
    monkeypatch.setattr("plugin.core.orchestrator.build_descriptor_artifact", lambda source, metadata, settings: None)

    out = listen("q", _cache(tmp_path), mode="auto")
    assert calls == ["ytdlp", "youtube_api"]
    assert out.analysis_mode == "full_audio"
    assert out.source is not None
    assert out.source.provider == "youtube_api"
    assert any(item.startswith("primary:ytdlp_failed(") for item in out.fallback_trace)
    assert any(item.startswith("audio_source:retry(") for item in out.fallback_trace)


def test_listen_auto_no_retrievable_candidates(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    selected = SourceCandidate(provider="spotify", source_type="metadata", source_id="sp1", title="Song", confidence=0.99)
    monkeypatch.setattr(
        "plugin.core.orchestrator.discover",
        lambda query, cache: DiscoveryResult(
            query=query,
            selected=selected,
            candidates=[selected],
            provider_trace=["ytdlp:error:missing_binary", "spotify:1", "musicbrainz:1"],
        ),
    )

    def fail_if_called(source, cache):
        raise AssertionError("fetch_audio should not be called when no retrievable candidate exists")

    monkeypatch.setattr("plugin.core.orchestrator.fetch_audio", fail_if_called)
    monkeypatch.setattr(
        "plugin.core.orchestrator.fetch_lyrics",
        lambda source, cache, settings, audio: LyricsArtifact(source="none", warnings=["LYRICS_NOT_FOUND"]),
    )
    monkeypatch.setattr("plugin.core.orchestrator.analyze_lyrics", lambda lyrics, cache: None)
    monkeypatch.setattr("plugin.core.orchestrator.build_descriptor_artifact", lambda source, metadata, settings: None)

    out = listen("q", _cache(tmp_path), mode="auto")
    assert out.analysis_mode == "metadata_only"
    assert any(item == "mode:auto->metadata_only(no_retrievable_source)" for item in out.fallback_trace)
    assert any(item.startswith("primary:ytdlp_failed(") for item in out.fallback_trace)


def test_listen_full_audio_no_retrievable_candidates(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    selected = SourceCandidate(provider="spotify", source_type="metadata", source_id="sp1", title="Song", confidence=0.99)
    monkeypatch.setattr(
        "plugin.core.orchestrator.discover",
        lambda query, cache: DiscoveryResult(query=query, selected=selected, candidates=[selected], provider_trace=["spotify:1"]),
    )

    out = listen("q", _cache(tmp_path), mode="full_audio")
    assert out.analysis_mode == "failed"
    assert out.errors
    assert out.errors[0]["code"] == "RETRIEVAL_UNAVAILABLE"
