#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def main() -> None:
    parser = argparse.ArgumentParser(description="Discover candidate tracks for a text query")
    parser.add_argument("query", help="Song query")
    args = parser.parse_args()

    from plugin.core.orchestrator import discover
    from plugin.tools._common import get_cache, print_json

    cache = get_cache()
    result = discover(args.query, cache)
    print_json(result)


if __name__ == "__main__":
    main()
