from __future__ import annotations

import json
from typing import Any

from plugin.core import CacheStore
from plugin.core.settings import cache_config, load_settings


def get_cache() -> CacheStore:
    settings = load_settings()
    root_dir, sqlite_path = cache_config(settings)
    return CacheStore(root_dir=root_dir, sqlite_path=sqlite_path)


def print_json(data: Any) -> None:
    if hasattr(data, "model_dump"):
        print(json.dumps(data.model_dump(), indent=2))
        return
    print(json.dumps(data, indent=2))
