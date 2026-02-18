from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def load_settings(path: str | None = None) -> dict[str, Any]:
    config_path = Path(path or os.getenv("MUSIC_SETTINGS_PATH", "config/settings.example.yaml"))
    if not config_path.exists():
        return {}
    return yaml.safe_load(config_path.read_text()) or {}


def cache_config(settings: dict[str, Any]) -> tuple[str, str]:
    cache = settings.get("cache") or {}
    return cache.get("root_dir", "./cache"), cache.get("sqlite_path", "./cache/index.sqlite")
