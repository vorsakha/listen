from __future__ import annotations

from .models import DescriptorArtifact, FeatureResult, LyricsAnalysisResult, MetadataArtifact, SourceCandidate, SynthesisResult


PROMPT_TEMPLATE = """You are listening to a song as a careful human critic.
Use only the provided structured features.
Clearly separate direct evidence from interpretation.
Do not invent lyrics or artist intent.

Song:
- Title: {title}
- Artist guess: {artist}
- Source confidence: {confidence:.2f}

Features:
- Tempo BPM: {tempo}
- Key/Mode: {key} {mode}
- RMS loudness: {rms}
- Dynamic range: {dr}
- Energy mean: {energy}
- Spectral centroid mean: {centroid}
- Onset density: {onset_density}
- Section count: {section_count}

Respond with:
1) Immediate feel
2) Rhythm and energy journey
3) Harmonic color and tension/release
4) Production texture and space
5) Confidence and uncertainty notes
"""


def build_synthesis(
    source: SourceCandidate,
    features: FeatureResult,
    lyrics_analysis: LyricsAnalysisResult | None = None,
) -> SynthesisResult:
    tempo = features.tempo_bpm or 0.0
    energy = features.energy_mean or 0.0

    mood = "restrained"
    if tempo > 120 and energy > 0.08:
        mood = "driving"
    elif tempo < 90 and energy < 0.06:
        mood = "reflective"

    highlights = [
        f"Tempo sits around {tempo:.1f} BPM.",
        f"Estimated key center is {features.key or 'unknown'} {features.mode}.",
        f"Perceived energy profile feels {mood}.",
    ]

    uncertainty = []
    if source.provider == "musicbrainz":
        uncertainty.append("Only metadata was available; no direct audio evidence from source provider.")
    if not features.section_map:
        uncertainty.append("Section segmentation confidence is low.")
    if not lyrics_analysis:
        uncertainty.append("Lyrics were unavailable or insufficient for textual-feeling analysis.")

    natural = (
        f"This listen reads as {mood}, with a pulse near {tempo:.0f} BPM and a tonal center around "
        f"{features.key or 'an uncertain key'} {features.mode}. The energy contour suggests deliberate dynamic shaping "
        "rather than flat loudness, and the spectral balance points to a warm-mid texture with periodic transient lift."
    )

    lyric_observation = None
    combined_observation = natural
    if lyrics_analysis:
        lyric_observation = (
            f"Lyrically, the text feels {lyrics_analysis.emotional_polarity}, touching themes like "
            f"{', '.join(lyrics_analysis.themes[:2])}. The wording suggests an intensity around "
            f"{(lyrics_analysis.intensity or 0.0):.2f}."
        )
        combined_observation = (
            f"{natural} Lyrically, it leans {lyrics_analysis.emotional_polarity}, which "
            "either reinforces or gently contrasts the sonic mood to create a fuller emotional arc."
        )

    prompt = PROMPT_TEMPLATE.format(
        title=source.title,
        artist=source.artist_guess or "unknown",
        confidence=source.confidence,
        tempo=f"{tempo:.2f}",
        key=features.key or "unknown",
        mode=features.mode,
        rms=f"{(features.loudness_rms or 0.0):.5f}",
        dr=f"{(features.dynamic_range or 0.0):.5f}",
        energy=f"{(features.energy_mean or 0.0):.5f}",
        centroid=f"{(features.spectral_centroid_mean or 0.0):.2f}",
        onset_density=f"{(features.onset_density or 0.0):.5f}",
        section_count=len(features.section_map),
    )

    return SynthesisResult(
        natural_observation=natural,
        lyric_observation=lyric_observation,
        combined_observation=combined_observation,
        highlights=highlights,
        uncertainty_notes=uncertainty,
        prompt_for_text_model=prompt,
    )


def build_metadata_synthesis(
    source: SourceCandidate,
    metadata: MetadataArtifact | None,
    lyrics_analysis: LyricsAnalysisResult | None = None,
) -> SynthesisResult:
    artist = ", ".join(metadata.artists) if metadata and metadata.artists else (source.artist_guess or "unknown artist")
    duration_text = (
        f"{metadata.duration_sec // 60}:{metadata.duration_sec % 60:02d}"
        if metadata and metadata.duration_sec
        else "unknown duration"
    )
    release_text = metadata.release_date if metadata and metadata.release_date else "unknown release date"
    source_label = metadata.source if metadata else "unknown"

    natural = (
        f"This interpretation is metadata-led for '{source.title}' by {artist}. "
        f"Catalog cues suggest a track length around {duration_text} with release context {release_text}, "
        "so the observation focuses on framing and lyrical affect rather than acoustic evidence."
    )
    highlights = [
        f"Metadata source: {source_label}.",
        f"Track duration: {duration_text}.",
        "Acoustic feature extraction was not available.",
    ]

    uncertainty = [
        "No direct audio analysis; interpretation is metadata/lyrics-based.",
        "Tempo/key/energy/timbre observations are intentionally omitted.",
    ]

    lyric_observation = None
    combined_observation = natural
    if lyrics_analysis:
        lyric_observation = (
            f"Lyrically, the text feels {lyrics_analysis.emotional_polarity}, touching themes like "
            f"{', '.join(lyrics_analysis.themes[:2])}."
        )
        combined_observation = (
            f"{natural} Lyrical evidence adds a {lyrics_analysis.emotional_polarity} emotional signal "
            "to this metadata-based reading."
        )
    else:
        uncertainty.append("Lyrics were unavailable or insufficient for textual-feeling analysis.")

    prompt = (
        "You are analyzing a song with metadata and optional lyric evidence only.\n"
        "Do not infer acoustic properties (tempo, key, timbre, dynamics).\n"
        f"Song title: {source.title}\n"
        f"Artist: {artist}\n"
        f"Release date: {release_text}\n"
        f"Duration: {duration_text}\n"
        f"Source confidence: {source.confidence:.2f}\n"
        "Respond with:\n"
        "1) Contextual framing from metadata\n"
        "2) Lyric emotional reading (if present)\n"
        "3) Explicit uncertainty due to no audio analysis\n"
    )

    return SynthesisResult(
        natural_observation=natural,
        lyric_observation=lyric_observation,
        combined_observation=combined_observation,
        highlights=highlights,
        uncertainty_notes=uncertainty,
        prompt_for_text_model=prompt,
    )


def build_descriptor_synthesis(
    source: SourceCandidate,
    descriptor: DescriptorArtifact,
    lyrics_analysis: LyricsAnalysisResult | None = None,
) -> SynthesisResult:
    tempo = descriptor.tempo_bpm
    tonal = f"{descriptor.key or 'unknown'} {descriptor.mode}"
    energy = descriptor.energy_proxy
    centroid = descriptor.texture_proxy.get("spectral_centroid_mean")
    complexity = descriptor.texture_proxy.get("spectral_complexity_mean")

    highlights = [
        f"Tempo estimate: {tempo:.1f} BPM." if tempo is not None else "Tempo estimate unavailable.",
        f"Key/mode estimate: {tonal}.",
        f"Descriptor confidence: {descriptor.confidence:.2f}.",
    ]

    texture_phrase = "texture descriptors are limited"
    if centroid is not None or complexity is not None:
        texture_phrase = "texture leans bright and layered" if (centroid or 0.0) > 1500 else "texture leans warm and focused"

    natural = (
        f"Descriptor-level analysis suggests a pulse near {tempo:.0f} BPM and tonal center around {tonal}. "
        f"Energy proxy sits near {(energy or 0.0):.2f}, and {texture_phrase}. "
        "This read uses catalog-linked descriptor databases rather than direct waveform extraction."
    )

    uncertainty = ["Derived from external descriptor datasets, not direct local audio analysis."]
    missing_fields = [k for k, v in descriptor.coverage.items() if v == "missing"]
    if missing_fields:
        uncertainty.append(f"Missing descriptor fields: {', '.join(missing_fields[:4])}.")

    lyric_observation = None
    combined_observation = natural
    if lyrics_analysis:
        lyric_observation = (
            f"Lyrically, the text feels {lyrics_analysis.emotional_polarity}, touching themes like "
            f"{', '.join(lyrics_analysis.themes[:2])}."
        )
        combined_observation = (
            f"{natural} Lyrical evidence adds a {lyrics_analysis.emotional_polarity} emotional layer "
            "to the descriptor-based sonic read."
        )
    else:
        uncertainty.append("Lyrics were unavailable or insufficient for textual-feeling analysis.")

    prompt = (
        "You are analyzing a song from precomputed descriptors and optional lyric evidence.\n"
        "Separate direct descriptor evidence from interpretation.\n"
        f"Title: {source.title}\n"
        f"Tempo: {tempo if tempo is not None else 'unknown'}\n"
        f"Key/Mode: {tonal}\n"
        f"Energy proxy: {(energy if energy is not None else 'unknown')}\n"
        f"Descriptor confidence: {descriptor.confidence:.2f}\n"
        "Respond with:\n"
        "1) Rhythm/motion feel\n"
        "2) Tonal and texture color\n"
        "3) Confidence and missing data caveats\n"
    )

    return SynthesisResult(
        natural_observation=natural,
        lyric_observation=lyric_observation,
        combined_observation=combined_observation,
        highlights=highlights,
        uncertainty_notes=uncertainty,
        prompt_for_text_model=prompt,
    )
