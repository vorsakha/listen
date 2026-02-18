from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceCandidate(BaseModel):
    provider: Literal["ytdlp", "youtube_api", "musicbrainz"]
    source_type: Literal["youtube", "metadata"] = "youtube"
    source_id: str
    title: str
    artist_guess: str | None = None
    duration_sec: int | None = None
    url: str | None = None
    confidence: float = 0.0
    raw: dict[str, Any] = Field(default_factory=dict)


class DiscoveryResult(BaseModel):
    query: str
    candidates: list[SourceCandidate] = Field(default_factory=list)
    selected: SourceCandidate | None = None
    provider_trace: list[str] = Field(default_factory=list)


class AudioArtifact(BaseModel):
    path: str
    format: str
    sample_rate: int | None = None
    duration_sec: float | None = None


class FetchResult(BaseModel):
    source: SourceCandidate
    audio: AudioArtifact
    cache_hit: bool = False


class FeatureResult(BaseModel):
    tempo_bpm: float | None = None
    key: str | None = None
    mode: Literal["major", "minor", "unknown"] = "unknown"
    loudness_rms: float | None = None
    dynamic_range: float | None = None
    energy_mean: float | None = None
    spectral_centroid_mean: float | None = None
    onset_density: float | None = None
    section_map: list[dict[str, Any]] = Field(default_factory=list)
    optional_features: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class LyricsArtifact(BaseModel):
    source: Literal["lrclib", "asr", "none"] = "none"
    text: str | None = None
    language: str | None = None
    is_synced: bool = False
    provider_confidence: float | None = None
    warnings: list[str] = Field(default_factory=list)


class LyricsAnalysisResult(BaseModel):
    themes: list[str] = Field(default_factory=list)
    emotional_polarity: Literal["negative", "mixed", "positive", "neutral"] = "neutral"
    intensity: float | None = None
    confidence: float = 0.0
    evidence_lines: list[str] = Field(default_factory=list)
    summary: str = ""
    warnings: list[str] = Field(default_factory=list)


class SynthesisResult(BaseModel):
    natural_observation: str
    lyric_observation: str | None = None
    combined_observation: str
    highlights: list[str] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)
    prompt_for_text_model: str


class ListenResult(BaseModel):
    query: str
    source: SourceCandidate | None = None
    audio: AudioArtifact | None = None
    features: FeatureResult | None = None
    lyrics: LyricsArtifact | None = None
    lyrics_analysis: LyricsAnalysisResult | None = None
    synthesis: SynthesisResult | None = None
    cache: dict[str, Any] = Field(default_factory=dict)
    errors: list[dict[str, str]] = Field(default_factory=list)
    fallback_trace: list[str] = Field(default_factory=list)
