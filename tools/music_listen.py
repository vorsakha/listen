#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover, retrieve, analyze, and synthesize a music listening response")
    parser.add_argument("query", help="Song query, e.g. 'Mac Miller Good News'")
    parser.add_argument("--no-deep-analysis", action="store_true", help="Skip synthesis stage")
    args = parser.parse_args()

    from plugin.core.orchestrator import listen
    from tools._common import get_cache, print_json

    cache = get_cache()
    result = listen(query=args.query, cache=cache, deep_analysis=not args.no_deep_analysis)
    print_json(result)


if __name__ == "__main__":
    main()
