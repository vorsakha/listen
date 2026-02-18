from __future__ import annotations

from plugin.core.models import FeatureResult, SourceCandidate
from plugin.core.synthesis import build_synthesis


def test_build_synthesis_contains_prompt_and_highlights() -> None:
    source = SourceCandidate(provider="ytdlp", source_id="x", title="Song", artist_guess="Artist", confidence=0.9)
    features = FeatureResult(tempo_bpm=88.0, key="F", mode="minor", energy_mean=0.03, section_map=[{"start_sec": 0.0, "end_sec": 10.0, "energy": 0.1}])

    out = build_synthesis(source, features)
    assert "Immediate feel" in out.prompt_for_glm5
    assert out.highlights
    assert "88.0" in " ".join(out.highlights)


def test_build_synthesis_adds_uncertainty_for_metadata_provider() -> None:
    source = SourceCandidate(provider="musicbrainz", source_type="metadata", source_id="x", title="Song")
    features = FeatureResult(tempo_bpm=120.0, key="C", mode="major")

    out = build_synthesis(source, features)
    assert any("metadata" in msg.lower() for msg in out.uncertainty_notes)
