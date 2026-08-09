"""Funções e constantes compartilhadas entre os scripts do career-agent."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
JOBS_DIR = DATA_DIR / "jobs"
SEEN_INDEX_PATH = DATA_DIR / "seen_index.json"
APPLICATIONS_LOG_PATH = DATA_DIR / "applications_log.jsonl"
CONFIG_PATH = ROOT / "agent" / "config" / "search_criteria.yaml"

STATUS_ORDER = [
    "Encontrada",
    "Em análise",
    "Currículo otimizado",
    "Carta criada",
    "Aguardando aprovação",
    "Rejeitado",  # candidata decidiu não se candidatar a essa vaga
    "Candidatura enviada",
    "Aguardando retorno",
    "Entrevista",
    "Em fase de testes",
    "Aprovado",
    "Retorno negativo",  # empresa recusou depois da candidatura enviada
]

# Status que significam "já candidatada" — nunca reenviar depois deles.
STATUS_JA_CANDIDATADA = {
    "Candidatura enviada",
    "Aguardando retorno",
    "Entrevista",
    "Em fase de testes",
    "Aprovado",
    "Retorno negativo",
}

# Status pós-candidatura que a candidata atualiza manualmente pelo dashboard,
# na ordem em que costumam aparecer nos botões (não é uma ordem fixa de transição).
STATUS_POS_CANDIDATURA = [
    "Aguardando retorno",
    "Entrevista",
    "Em fase de testes",
    "Aprovado",
    "Retorno negativo",
]

DEFAULT_LIMIAR_APROVACAO = 70
DEFAULT_LIMIAR_EXCELENTE = 80


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "item"


def external_id(plataforma: str, referencia: str) -> str:
    """Id estável e determinístico para deduplicação: plataforma + hash da referência (URL ou id)."""
    digest = hashlib.sha1(referencia.strip().encode("utf-8")).hexdigest()[:12]
    return f"{slugify(plataforma)}__{digest}"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    try:
        return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def load_seen_index() -> dict:
    if SEEN_INDEX_PATH.exists():
        return json.loads(SEEN_INDEX_PATH.read_text(encoding="utf-8"))
    return {}


def save_seen_index(index: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )


def job_path(ext_id: str) -> Path:
    return JOBS_DIR / f"{ext_id}.json"


def load_all_jobs() -> list[dict]:
    if not JOBS_DIR.exists():
        return []
    jobs = []
    for path in sorted(JOBS_DIR.glob("*.json")):
        try:
            jobs.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return jobs


def parse_salary_brl(*values: str | None) -> float | None:
    """Extrai o primeiro valor numérico de strings tipo 'R$ 8.000 - R$ 10.000'."""
    for value in values:
        if not value:
            continue
        match = re.search(r"(\d{1,3}(?:\.\d{3})*(?:,\d+)?)", value)
        if match:
            number = match.group(1).replace(".", "").replace(",", ".")
            try:
                return float(number)
            except ValueError:
                continue
    return None
