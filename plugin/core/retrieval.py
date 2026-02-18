from __future__ import annotations

import subprocess
from pathlib import Path

from .cache import CacheStore
from .errors import RetrievalError
from .models import AudioArtifact, FetchResult, SourceCandidate


def fetch_audio(
    source: SourceCandidate,
    cache: CacheStore,
    output_format: str = "wav",
    timeout_sec: int = 120,
) -> FetchResult:
    source_key = cache.normalize_key(f"{source.provider}:{source.source_id}")
    cached = cache.get_audio(source_key)
    if cached:
        path, fmt = cached
        return FetchResult(
            source=source,
            audio=AudioArtifact(path=path, format=fmt),
            cache_hit=True,
        )

    if source.source_type != "youtube" or not source.url:
        raise RetrievalError("RETRIEVAL_UNAVAILABLE", "No retrievable URL available for source")

    out_tpl = str(cache.audio_dir / f"{source_key}.%(ext)s")
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format",
        output_format,
        "--audio-quality",
        "0",
        "-o",
        out_tpl,
        source.url,
    ]

    try:
        subprocess.run(cmd, check=True, timeout=timeout_sec, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RetrievalError("RETRIEVAL_YTDLP_MISSING", "yt-dlp is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise RetrievalError("RETRIEVAL_TIMEOUT", f"Audio retrieval timed out after {timeout_sec}s") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RetrievalError("RETRIEVAL_YTDLP_FAILED", f"yt-dlp failed: {stderr}") from exc

    produced = list(Path(cache.audio_dir).glob(f"{source_key}.*"))
    if not produced:
        raise RetrievalError("RETRIEVAL_NOT_FOUND", "yt-dlp completed but no audio artifact was produced")

    audio_path = str(produced[0])
    fmt = produced[0].suffix.lstrip(".") or output_format
    cache.put_audio(source_key, audio_path, fmt)
    return FetchResult(
        source=source,
        audio=AudioArtifact(path=audio_path, format=fmt),
        cache_hit=False,
    )
