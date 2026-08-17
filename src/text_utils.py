"""Normalização de texto e correspondência de palavras-chave (sem acento, case-insensitive)."""
from __future__ import annotations

import unicodedata


def normalize(text: str | None) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return text.lower().strip()


def contains_any(haystack: str | None, needles: list[str]) -> str | None:
    """Retorna o primeiro termo de `needles` encontrado em `haystack` (normalizado), ou None."""
    norm_haystack = normalize(haystack)
    if not norm_haystack:
        return None
    for needle in needles:
        norm_needle = normalize(needle)
        if norm_needle and norm_needle in norm_haystack:
            return needle
    return None


def equals_any(value: str | None, options: list[str]) -> bool:
    norm_value = normalize(value)
    return any(norm_value == normalize(option) for option in options)
