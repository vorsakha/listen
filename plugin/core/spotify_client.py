from __future__ import annotations

import os
from typing import Any

import requests


class SpotifyClientError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _credentials_from_settings(settings: dict[str, Any]) -> tuple[str | None, str | None]:
    cfg = settings.get("spotify") or {}
    client_id_env = cfg.get("client_id_env", "SPOTIFY_CLIENT_ID")
    client_secret_env = cfg.get("client_secret_env", "SPOTIFY_CLIENT_SECRET")
    return os.getenv(str(client_id_env)), os.getenv(str(client_secret_env))


def get_app_token(settings: dict[str, Any]) -> str | None:
    client_id, client_secret = _credentials_from_settings(settings)
    if not client_id or not client_secret:
        return None

    timeout_sec = int((settings.get("spotify") or {}).get("request_timeout_sec", 10))
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        timeout=timeout_sec,
    )
    if resp.status_code != 200:
        raise SpotifyClientError("SPOTIFY_AUTH_FAILED", f"Token request failed: {resp.status_code}")

    payload = resp.json()
    token = payload.get("access_token")
    if not token:
        raise SpotifyClientError("SPOTIFY_AUTH_FAILED", "Missing access_token in Spotify response")
    return str(token)


def search_tracks(query: str, settings: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    token = get_app_token(settings)
    if not token:
        return []

    cfg = settings.get("spotify") or {}
    timeout_sec = int(cfg.get("request_timeout_sec", 10))
    market = str(cfg.get("market", "US"))

    headers = {"Authorization": f"Bearer {token}"}
    params = {"q": query, "type": "track", "limit": limit, "market": market}
    resp = requests.get(
        "https://api.spotify.com/v1/search",
        headers=headers,
        params=params,
        timeout=timeout_sec,
    )
    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After", "unknown")
        raise SpotifyClientError("SPOTIFY_RATE_LIMIT", f"Rate-limited by Spotify (Retry-After: {retry_after}s)")
    if resp.status_code != 200:
        raise SpotifyClientError("SPOTIFY_SEARCH_FAILED", f"Search request failed: {resp.status_code}")

    payload = resp.json()
    tracks = (((payload.get("tracks") or {}).get("items")) or [])
    if not isinstance(tracks, list):
        return []
    return [item for item in tracks if isinstance(item, dict)]
