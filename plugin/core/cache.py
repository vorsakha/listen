from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from pathlib import Path
from typing import Any


class CacheStore:
    def __init__(self, root_dir: str = "./cache", sqlite_path: str = "./cache/index.sqlite"):
        self.root_dir = Path(root_dir)
        self.audio_dir = self.root_dir / "audio"
        self.feature_dir = self.root_dir / "features"
        self.sqlite_path = Path(sqlite_path)

        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.feature_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(self.sqlite_path)
        self._init_tables()

    def _init_tables(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS query_cache (
                query_key TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS source_audio (
                source_key TEXT PRIMARY KEY,
                audio_path TEXT NOT NULL,
                format TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feature_cache (
                audio_key TEXT PRIMARY KEY,
                feature_path TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        self.conn.commit()

    @staticmethod
    def normalize_key(value: str) -> str:
        return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()

    def get_query(self, query: str, ttl_sec: int) -> str | None:
        query_key = self.normalize_key(query)
        cur = self.conn.cursor()
        row = cur.execute(
            "SELECT payload, created_at FROM query_cache WHERE query_key = ?", (query_key,)
        ).fetchone()
        if not row:
            return None
        payload, created_at = row
        if int(time.time()) - created_at > ttl_sec:
            return None
        return payload

    def put_query(self, query: str, payload: str) -> None:
        query_key = self.normalize_key(query)
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO query_cache(query_key, payload, created_at)
            VALUES(?, ?, ?)
            ON CONFLICT(query_key) DO UPDATE SET
              payload = excluded.payload,
              created_at = excluded.created_at
            """,
            (query_key, payload, int(time.time())),
        )
        self.conn.commit()

    def get_audio(self, source_key: str) -> tuple[str, str] | None:
        cur = self.conn.cursor()
        row = cur.execute(
            "SELECT audio_path, format FROM source_audio WHERE source_key = ?", (source_key,)
        ).fetchone()
        if not row:
            return None
        audio_path, fmt = row
        if not os.path.exists(audio_path):
            return None
        return audio_path, fmt

    def put_audio(self, source_key: str, audio_path: str, fmt: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO source_audio(source_key, audio_path, format, created_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(source_key) DO UPDATE SET
              audio_path = excluded.audio_path,
              format = excluded.format,
              created_at = excluded.created_at
            """,
            (source_key, audio_path, fmt, int(time.time())),
        )
        self.conn.commit()

    def get_feature_path(self, audio_key: str) -> str | None:
        cur = self.conn.cursor()
        row = cur.execute(
            "SELECT feature_path FROM feature_cache WHERE audio_key = ?", (audio_key,)
        ).fetchone()
        if not row:
            return None
        feature_path = row[0]
        if not os.path.exists(feature_path):
            return None
        return feature_path

    def put_feature_path(self, audio_key: str, feature_path: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO feature_cache(audio_key, feature_path, created_at)
            VALUES(?, ?, ?)
            ON CONFLICT(audio_key) DO UPDATE SET
              feature_path = excluded.feature_path,
              created_at = excluded.created_at
            """,
            (audio_key, feature_path, int(time.time())),
        )
        self.conn.commit()

    def cache_status(self, key: str) -> dict[str, Any]:
        query_key = self.normalize_key(key)
        cur = self.conn.cursor()
        q = cur.execute("SELECT created_at FROM query_cache WHERE query_key = ?", (query_key,)).fetchone()
        a = cur.execute("SELECT audio_path, created_at FROM source_audio WHERE source_key = ?", (query_key,)).fetchone()
        f = cur.execute("SELECT feature_path, created_at FROM feature_cache WHERE audio_key = ?", (query_key,)).fetchone()
        return {
            "query_cached": bool(q),
            "audio_cached": bool(a),
            "feature_cached": bool(f),
            "audio_path": a[0] if a else None,
            "feature_path": f[0] if f else None,
        }
