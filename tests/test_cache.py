from __future__ import annotations

import time
from pathlib import Path

from plugin.core.cache import CacheStore


def test_query_cache_put_and_get(tmp_path: Path) -> None:
    cache = CacheStore(root_dir=str(tmp_path / "cache"), sqlite_path=str(tmp_path / "cache" / "index.sqlite"))

    cache.put_query("Listen to Good News", '{"ok": true}')
    assert cache.get_query("Listen to Good News", ttl_sec=60) == '{"ok": true}'


def test_query_cache_ttl_expiry(tmp_path: Path) -> None:
    cache = CacheStore(root_dir=str(tmp_path / "cache"), sqlite_path=str(tmp_path / "cache" / "index.sqlite"))
    cache.put_query("abc", "payload")
    time.sleep(1)
    assert cache.get_query("abc", ttl_sec=0) is None


def test_audio_and_feature_cache_roundtrip(tmp_path: Path) -> None:
    cache = CacheStore(root_dir=str(tmp_path / "cache"), sqlite_path=str(tmp_path / "cache" / "index.sqlite"))

    source_key = cache.normalize_key("src")
    audio = tmp_path / "cache" / "audio" / "x.wav"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"data")
    cache.put_audio(source_key, str(audio), "wav")
    assert cache.get_audio(source_key) == (str(audio), "wav")

    audio_key = cache.normalize_key(str(audio))
    feature_path = tmp_path / "cache" / "features" / "x.json"
    feature_path.parent.mkdir(parents=True, exist_ok=True)
    feature_path.write_text('{"tempo_bpm": 100}')
    cache.put_feature_path(audio_key, str(feature_path))
    assert cache.get_feature_path(audio_key) == str(feature_path)


def test_cache_status_flags(tmp_path: Path) -> None:
    cache = CacheStore(root_dir=str(tmp_path / "cache"), sqlite_path=str(tmp_path / "cache" / "index.sqlite"))
    key = "k"
    source_key = cache.normalize_key(key)

    cache.put_query(key, "payload")
    audio = tmp_path / "cache" / "audio" / "a.wav"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"audio")
    cache.put_audio(source_key, str(audio), "wav")

    status = cache.cache_status(key)
    assert status["query_cached"] is True
    assert status["audio_cached"] is True
