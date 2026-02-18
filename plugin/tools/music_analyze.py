#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a local audio file with librosa feature extraction")
    parser.add_argument("audio_path", help="Path to local audio file")
    args = parser.parse_args()

    from plugin.core.analysis import analyze_audio
    from plugin.tools._common import get_cache, print_json

    cache = get_cache()
    result = analyze_audio(args.audio_path, cache=cache)
    print_json(result)


if __name__ == "__main__":
    main()
