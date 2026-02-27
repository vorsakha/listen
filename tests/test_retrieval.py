from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

import pytest

from plugin.core.cache import CacheStore
from plugin.core.errors import RetrievalError
from plugin.core.models import SourceCandidate
from plugin.core.retrieval import fetch_audio


def _source() -> SourceCandidate:
    return SourceCandidate(
        provider="ytdlp",
        source_id="abc123",
        title="Track",
        url="https://www.youtube.com/watch?v=abc123",
    )


def test_fetch_audio_cache_hit(tmp_path: Path) -> None:
    cache = CacheStore(root_dir=str(tmp_path / "cache"), sqlite_path=str(tmp_path / "cache" / "index.sqlite"))
    source = _source()
    source_key = cache.normalize_key(f"{source.provider}:{source.source_id}")

    audio_path = tmp_path / "cache" / "audio" / f"{source_key}.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"x")
    cache.put_audio(source_key, str(audio_path), "wav")

    out = fetch_audio(source, cache)
    assert out.cache_hit is True
    assert out.audio.path == str(audio_path)


def test_fetch_audio_download_miss(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache = CacheStore(root_dir=str(tmp_path / "cache"), sqlite_path=str(tmp_path / "cache" / "index.sqlite"))
    source = _source()
    source_key = cache.normalize_key(f"{source.provider}:{source.source_id}")

    def fake_run(*args, **kwargs):
        produced = tmp_path / "cache" / "audio" / f"{source_key}.wav"
        produced.parent.mkdir(parents=True, exist_ok=True)
        produced.write_bytes(b"audio")
        return CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("plugin.core.retrieval.subprocess.run", fake_run)

    out = fetch_audio(source, cache)
    assert out.cache_hit is False
    assert out.audio.format == "wav"


def test_fetch_audio_metadata_only_source_fails(tmp_path: Path) -> None:
    cache = CacheStore(root_dir=str(tmp_path / "cache"), sqlite_path=str(tmp_path / "cache" / "index.sqlite"))
    source = SourceCandidate(provider="musicbrainz", source_type="metadata", source_id="mbid", title="T")

    with pytest.raises(RetrievalError) as exc:
        fetch_audio(source, cache)
    assert exc.value.code == "RETRIEVAL_UNAVAILABLE"


def test_fetch_audio_jamendo_download_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache = CacheStore(root_dir=str(tmp_path / "cache"), sqlite_path=str(tmp_path / "cache" / "index.sqlite"))
    source = SourceCandidate(
        provider="jamendo",
        source_type="youtube",
        source_id="j1",
        title="Track",
        url="https://cdn.jamendo.com/audio.mp3",
    )

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        @staticmethod
        def iter_content(chunk_size: int = 65536):
            yield b"abc"
            yield b"def"

    monkeypatch.setattr("plugin.core.retrieval.requests.get", lambda *args, **kwargs: _Resp())

    out = fetch_audio(source, cache)
    assert out.cache_hit is False
    assert out.audio.format == "mp3"
    assert Path(out.audio.path).exists()


def test_fetch_audio_jamendo_http_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import requests

    cache = CacheStore(root_dir=str(tmp_path / "cache"), sqlite_path=str(tmp_path / "cache" / "index.sqlite"))
    source = SourceCandidate(
        provider="jamendo",
        source_type="youtube",
        source_id="j1",
        title="Track",
        url="https://cdn.jamendo.com/audio.mp3",
    )

    monkeypatch.setattr(
        "plugin.core.retrieval.requests.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(requests.HTTPError("bad")),
    )

    with pytest.raises(RetrievalError) as exc:
        fetch_audio(source, cache)
    assert exc.value.code == "RETRIEVAL_JAMENDO_HTTP_FAILED"


def test_fetch_audio_jamendo_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import requests

    cache = CacheStore(root_dir=str(tmp_path / "cache"), sqlite_path=str(tmp_path / "cache" / "index.sqlite"))
    source = SourceCandidate(
        provider="jamendo",
        source_type="youtube",
        source_id="j1",
        title="Track",
        url="https://cdn.jamendo.com/audio.mp3",
    )

    monkeypatch.setattr(
        "plugin.core.retrieval.requests.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(requests.Timeout("timeout")),
    )

    with pytest.raises(RetrievalError) as exc:
        fetch_audio(source, cache)
    assert exc.value.code == "RETRIEVAL_JAMENDO_TIMEOUT"
