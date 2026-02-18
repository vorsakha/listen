from __future__ import annotations

import json
from pathlib import Path

from .cache import CacheStore
from .errors import AnalysisError
from .models import FeatureResult


def _key_from_chroma(chroma) -> tuple[str, str]:
    pitch_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    major_template = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
    minor_template = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

    import numpy as np

    chroma_mean = chroma.mean(axis=1)
    best_key = "C"
    best_mode = "unknown"
    best_score = -1.0

    for i, pitch in enumerate(pitch_names):
        major = np.roll(major_template, i)
        minor = np.roll(minor_template, i)
        major_score = float(np.corrcoef(chroma_mean, major)[0, 1])
        minor_score = float(np.corrcoef(chroma_mean, minor)[0, 1])
        if major_score > best_score:
            best_score = major_score
            best_key = pitch
            best_mode = "major"
        if minor_score > best_score:
            best_score = minor_score
            best_key = pitch
            best_mode = "minor"
    return best_key, best_mode


def analyze_audio(audio_path: str, cache: CacheStore, sample_rate: int = 22050) -> FeatureResult:
    audio_key = cache.normalize_key(audio_path)
    cached_feature_path = cache.get_feature_path(audio_key)
    if cached_feature_path:
        payload = json.loads(Path(cached_feature_path).read_text())
        return FeatureResult.model_validate(payload)

    try:
        import librosa
        import numpy as np
    except ImportError as exc:
        raise AnalysisError("ANALYSIS_LIBROSA_MISSING", "librosa/numpy is required for analysis") from exc

    try:
        y, sr = librosa.load(audio_path, sr=sample_rate, mono=True)
    except Exception as exc:
        raise AnalysisError("ANALYSIS_AUDIO_LOAD_FAILED", f"Unable to load audio: {exc}") from exc

    if y.size == 0:
        raise AnalysisError("ANALYSIS_EMPTY_AUDIO", "Audio payload is empty")

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    rms = librosa.feature.rms(y=y)[0]
    spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr)
    onset_density = float(len(onset_frames) / max(1.0, librosa.get_duration(y=y, sr=sr)))

    chroma = librosa.feature.chroma_stft(y=y, sr=sr)
    key, mode = _key_from_chroma(chroma)

    duration_sec = librosa.get_duration(y=y, sr=sr)
    segs = librosa.effects.split(y, top_db=28)
    section_map = [
        {
            "start_sec": float(s / sr),
            "end_sec": float(e / sr),
            "energy": float(np.mean(np.abs(y[s:e]))) if e > s else 0.0,
        }
        for s, e in segs[:12]
    ]

    feature = FeatureResult(
        tempo_bpm=float(tempo),
        key=key,
        mode=mode,
        loudness_rms=float(rms.mean()),
        dynamic_range=float(np.percentile(rms, 95) - np.percentile(rms, 5)),
        energy_mean=float(np.mean(np.abs(y))),
        spectral_centroid_mean=float(spectral_centroid.mean()),
        onset_density=onset_density,
        section_map=section_map,
        optional_features={
            "duration_sec": float(duration_sec),
        },
    )

    feature_path = cache.feature_dir / f"{audio_key}.json"
    feature_path.write_text(feature.model_dump_json(indent=2))
    cache.put_feature_path(audio_key, str(feature_path))
    return feature
