from __future__ import annotations

import json
import re
from collections import Counter
from typing import Literal

from .cache import CacheStore
from .models import LyricsAnalysisResult, LyricsArtifact

THEME_KEYWORDS: dict[str, set[str]] = {
    "love": {"love", "heart", "kiss", "romance", "darling"},
    "loss": {"gone", "leave", "lost", "grief", "empty", "alone"},
    "hope": {"rise", "light", "tomorrow", "heal", "hold on"},
    "pain": {"hurt", "bleed", "broken", "cry", "wound"},
    "freedom": {"free", "escape", "wings", "open road", "fly"},
    "identity": {"who am i", "myself", "name", "mirror", "be me"},
}

POSITIVE_WORDS = {
    "love",
    "hope",
    "alive",
    "shine",
    "joy",
    "dream",
    "heal",
    "peace",
    "smile",
}
NEGATIVE_WORDS = {
    "pain",
    "hurt",
    "lost",
    "alone",
    "dark",
    "broken",
    "cry",
    "fear",
    "empty",
}


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def _extract_themes(text: str) -> list[str]:
    text_l = text.lower()
    hits: list[str] = []
    for theme, keys in THEME_KEYWORDS.items():
        if any(k in text_l for k in keys):
            hits.append(theme)
    if hits:
        return hits[:3]
    counts = Counter(_tokenize(text))
    fallback = [word for word, _ in counts.most_common(3) if len(word) > 4]
    return fallback or ["reflection"]


def _pick_evidence_lines(text: str, limit: int = 3) -> list[str]:
    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not raw_lines:
        return []
    scored: list[tuple[int, str]] = []
    for line in raw_lines:
        tokens = _tokenize(line)
        if len(tokens) < 3:
            continue
        pos = sum(1 for t in tokens if t in POSITIVE_WORDS)
        neg = sum(1 for t in tokens if t in NEGATIVE_WORDS)
        scored.append((pos + neg, line[:160]))
    if not scored:
        return raw_lines[:limit]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [line for _, line in scored[:limit]]


def _polarity_intensity(text: str) -> tuple[Literal["negative", "mixed", "positive", "neutral"], float]:
    tokens = _tokenize(text)
    if not tokens:
        return "neutral", 0.0
    pos = sum(1 for t in tokens if t in POSITIVE_WORDS)
    neg = sum(1 for t in tokens if t in NEGATIVE_WORDS)
    total = max(1, pos + neg)
    intensity = min(1.0, total / max(12.0, len(tokens) / 8.0))
    if pos == 0 and neg == 0:
        return "neutral", round(intensity, 3)
    if abs(pos - neg) <= 1:
        return "mixed", round(intensity, 3)
    return ("positive" if pos > neg else "negative"), round(intensity, 3)


def analyze_lyrics(lyrics: LyricsArtifact, cache: CacheStore | None = None) -> LyricsAnalysisResult | None:
    if not lyrics.text:
        return None

    lyrics_key = None
    if cache:
        lyrics_key = cache.normalize_key(lyrics.text)
        cached = cache.get_lyrics_analysis(lyrics_key)
        if cached:
            return LyricsAnalysisResult.model_validate_json(cached)

    themes = _extract_themes(lyrics.text)
    polarity, intensity = _polarity_intensity(lyrics.text)
    evidence = _pick_evidence_lines(lyrics.text, limit=3)

    length_factor = min(1.0, len(lyrics.text) / 1200.0)
    signal_factor = 0.75 if polarity in {"neutral", "mixed"} else 0.9
    confidence = round(max(0.2, min(1.0, length_factor * signal_factor)), 3)

    summary = (
        f"The lyrics feel {polarity}, centered on {', '.join(themes[:2])}. "
        f"Emotional intensity reads around {intensity:.2f} with confidence {confidence:.2f}."
    )
    result = LyricsAnalysisResult(
        themes=themes,
        emotional_polarity=polarity,
        intensity=float(intensity),
        confidence=confidence,
        evidence_lines=evidence,
        summary=summary,
    )

    if cache and lyrics_key:
        cache.put_lyrics_analysis(lyrics_key, json.dumps(result.model_dump()))
    return result
