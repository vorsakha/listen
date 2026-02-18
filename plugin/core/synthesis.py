from __future__ import annotations

from .models import FeatureResult, SourceCandidate, SynthesisResult


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


def build_synthesis(source: SourceCandidate, features: FeatureResult) -> SynthesisResult:
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

    natural = (
        f"This listen reads as {mood}, with a pulse near {tempo:.0f} BPM and a tonal center around "
        f"{features.key or 'an uncertain key'} {features.mode}. The energy contour suggests deliberate dynamic shaping "
        "rather than flat loudness, and the spectral balance points to a warm-mid texture with periodic transient lift."
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
        highlights=highlights,
        uncertainty_notes=uncertainty,
        prompt_for_glm5=prompt,
    )
