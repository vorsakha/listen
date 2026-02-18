#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch audio artifact for discovered query")
    parser.add_argument("query", help="Song query")
    parser.add_argument("--format", default="wav", help="Audio format for yt-dlp extraction")
    args = parser.parse_args()

    from plugin.core.discovery import discover_song
    from plugin.core.retrieval import fetch_audio
    from plugin.tools._common import get_cache, print_json

    cache = get_cache()
    discovery = discover_song(args.query)
    if not discovery.selected:
        print_json({"error": "No selected source from discovery"})
        return

    result = fetch_audio(discovery.selected, cache=cache, output_format=args.format)
    print_json(result)


if __name__ == "__main__":
    main()
