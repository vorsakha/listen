from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from plugin.core.analysis import analyze_audio
from plugin.core.cache import CacheStore


def test_analyze_audio_extracts_features_and_caches(tmp_path: Path) -> None:
    cache = CacheStore(root_dir=str(tmp_path / "cache"), sqlite_path=str(tmp_path / "cache" / "index.sqlite"))
    audio_path = tmp_path / "tone.wav"

    sr = 22050
    t = np.linspace(0, 2.0, int(sr * 2.0), endpoint=False)
    y = 0.2 * np.sin(2 * np.pi * 440.0 * t)
    sf.write(audio_path, y, sr)

    first = analyze_audio(str(audio_path), cache)
    second = analyze_audio(str(audio_path), cache)

    assert first.tempo_bpm is not None
    assert first.key is not None
    assert first.energy_mean is not None
    assert second.tempo_bpm == first.tempo_bpm
