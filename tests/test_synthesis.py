from __future__ import annotations

from plugin.core.models import FeatureResult, LyricsAnalysisResult, MetadataArtifact, SourceCandidate
from plugin.core.synthesis import build_metadata_synthesis, build_synthesis


def test_build_synthesis_contains_prompt_and_highlights() -> None:
    source = SourceCandidate(provider="ytdlp", source_id="x", title="Song", artist_guess="Artist", confidence=0.9)
    features = FeatureResult(tempo_bpm=88.0, key="F", mode="minor", energy_mean=0.03, section_map=[{"start_sec": 0.0, "end_sec": 10.0, "energy": 0.1}])

    out = build_synthesis(source, features)
    assert "Immediate feel" in out.prompt_for_text_model
    assert out.highlights
    assert "88.0" in " ".join(out.highlights)
    assert out.combined_observation


def test_build_synthesis_adds_uncertainty_for_metadata_provider() -> None:
    source = SourceCandidate(provider="musicbrainz", source_type="metadata", source_id="x", title="Song")
    features = FeatureResult(tempo_bpm=120.0, key="C", mode="major")

    out = build_synthesis(source, features)
    assert any("metadata" in msg.lower() for msg in out.uncertainty_notes)


def test_build_synthesis_with_lyrics_analysis_adds_lyric_observation() -> None:
    source = SourceCandidate(provider="ytdlp", source_id="x", title="Song")
    features = FeatureResult(tempo_bpm=95.0, key="A", mode="minor")
    lyrics = LyricsAnalysisResult(
        themes=["loss", "hope"],
        emotional_polarity="mixed",
        intensity=0.7,
        confidence=0.8,
        evidence_lines=["line one"],
        summary="summary",
    )

    out = build_synthesis(source, features, lyrics_analysis=lyrics)
    assert out.lyric_observation is not None
    assert "Lyrically" in out.combined_observation


def test_build_metadata_synthesis_omits_acoustic_claims() -> None:
    source = SourceCandidate(provider="spotify", source_type="metadata", source_id="sp1", title="Song")
    metadata = MetadataArtifact(source="spotify", title="Song", artists=["Artist"], duration_sec=215)

    out = build_metadata_synthesis(source, metadata)
    assert any("No direct audio analysis" in note for note in out.uncertainty_notes)
    assert "tempo" in out.uncertainty_notes[1].lower()
