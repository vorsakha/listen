#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect cache status by query/source/audio key")
    parser.add_argument("key", help="Query string or canonical source/audio key")
    args = parser.parse_args()

    from plugin.core.orchestrator import cache_status
    from tools._common import get_cache

    cache = get_cache()
    print(cache_status(cache, args.key))


if __name__ == "__main__":
    main()
