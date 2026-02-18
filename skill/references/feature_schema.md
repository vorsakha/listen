# Feature Schema

`FeatureResult` fields returned by `music_analyze` and `music_listen`:

- `tempo_bpm`: Estimated beats per minute.
- `key`: Estimated tonal center (`C`, `C#`, ...).
- `mode`: `major`, `minor`, or `unknown`.
- `loudness_rms`: Mean RMS level.
- `dynamic_range`: RMS percentile spread (95th - 5th).
- `energy_mean`: Mean absolute amplitude proxy.
- `spectral_centroid_mean`: Average brightness proxy.
- `onset_density`: Detected onsets per second.
- `section_map`: Segment list (`start_sec`, `end_sec`, `energy`).
- `optional_features`: Additional provider-specific descriptors.
- `warnings`: Extraction caveats.
