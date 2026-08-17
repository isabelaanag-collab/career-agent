"""Deduplicação por conteúdo (empresa+cargo+cidade) e lista de candidaturas feitas
fora deste sistema (direto na Gupy/LinkedIn), para não reprocessar vagas já
candidatadas mesmo quando o `scripts/seen_index.json` (por URL) não pegaria — ex.:
o mesmo anúncio republicado com uma URL nova.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import RawJob
from .text_utils import normalize

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CONTENT_HASH_PATH = DATA_DIR / "seen_content_hashes.json"
APPLIED_EXTERNAL_PATH = DATA_DIR / "applied_externos.json"


def content_hash(empresa: str, cargo: str, cidade: str | None) -> str:
    raw = f"{normalize(empresa)}|{normalize(cargo)}|{normalize(cidade)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def job_content_hash(job: RawJob) -> str:
    return content_hash(job.empresa, job.cargo, job.cidade)


def load_content_hashes() -> dict[str, dict]:
    if CONTENT_HASH_PATH.exists():
        return json.loads(CONTENT_HASH_PATH.read_text(encoding="utf-8"))
    return {}


def save_content_hashes(index: dict[str, dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONTENT_HASH_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )


def load_applied_external_hashes() -> set[str]:
    """Candidaturas feitas fora deste sistema, mantidas manualmente pela candidata em
    data/applied_externos.json — formato: [{"empresa", "cargo", "cidade"}, ...].
    Ver README.md, seção 'Ignorar vagas já candidatadas fora do sistema'.
    """
    if not APPLIED_EXTERNAL_PATH.exists():
        return set()
    try:
        entries = json.loads(APPLIED_EXTERNAL_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    return {
        content_hash(entry.get("empresa", ""), entry.get("cargo", ""), entry.get("cidade"))
        for entry in entries
    }
