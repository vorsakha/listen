from __future__ import annotations

import pytest

from plugin.core.spotify_client import SpotifyClientError, get_app_token, search_tracks


class _Resp:
    def __init__(self, status_code: int, payload: dict | None = None, headers: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


def test_get_app_token_missing_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    assert get_app_token({"spotify": {}}) is None


def test_get_app_token_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setattr(
        "plugin.core.spotify_client.requests.post",
        lambda *args, **kwargs: _Resp(200, {"access_token": "abc"}),
    )
    assert get_app_token({"spotify": {}}) == "abc"


def test_search_tracks_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setattr(
        "plugin.core.spotify_client.requests.post",
        lambda *args, **kwargs: _Resp(200, {"access_token": "abc"}),
    )
    monkeypatch.setattr(
        "plugin.core.spotify_client.requests.get",
        lambda *args, **kwargs: _Resp(429, headers={"Retry-After": "5"}),
    )
    with pytest.raises(SpotifyClientError) as exc:
        search_tracks("track", {"spotify": {}}, limit=5)
    assert exc.value.code == "SPOTIFY_RATE_LIMIT"


def test_search_tracks_parses_items(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setattr(
        "plugin.core.spotify_client.requests.post",
        lambda *args, **kwargs: _Resp(200, {"access_token": "abc"}),
    )
    monkeypatch.setattr(
        "plugin.core.spotify_client.requests.get",
        lambda *args, **kwargs: _Resp(200, {"tracks": {"items": [{"id": "t1", "name": "Song"}]}}),
    )
    out = search_tracks("song", {"spotify": {}}, limit=5)
    assert out and out[0]["id"] == "t1"
