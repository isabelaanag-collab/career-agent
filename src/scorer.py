"""Chamada cirúrgica à API da Anthropic — SÓ para vagas que já passaram por TODOS os
filtros duros (área, salário, localidade, não-vistas). Nunca é usada para buscar,
paginar HTML ou decidir o que é ou não uma vaga: isso é 100% Python puro em
`src/scrapers/` e `src/filters.py`.

Custo: um único bloco de sistema (rubrica + currículo) é marcado com
`cache_control` para ser reaproveitado entre lotes na mesma execução, e as vagas são
enviadas em lotes (`BATCH_SIZE`) para amortizar esse custo fixo por chamada.
"""
from __future__ import annotations

import json
import logging
import os
import re

from .models import RawJob

logger = logging.getLogger("career_agent.scorer")

MODEL = os.environ.get("CAREER_AGENT_SCORING_MODEL", "claude-haiku-4-5-20251001")
BATCH_SIZE = 8
MAX_TOKENS_PER_BATCH = 4096

REQUIRED_FIELDS = [
    "match_score",
    "motivos_score",
    "palavras_chave_encontradas",
    "tecnologias_exigidas",
    "idiomas_exigidos",
    "beneficios",
    "requisitos_obrigatorios",
    "requisitos_desejaveis",
    "probabilidade_estimada_entrevista",
]


def _build_system_prompt(rubric_text: str, resume_text: str) -> str:
    return (
        "Você pontua vagas de emprego para uma candidata real, seguindo a rubrica "
        "abaixo à risca. Regra de ouro: NUNCA invente nada sobre a candidata — toda "
        "afirmação precisa vir literalmente do currículo/perfil fornecido. Se não "
        "puder confirmar, trate como não verificável e não pontue a favor.\n\n"
        f"## Rubrica\n{rubric_text}\n\n"
        f"## Currículo / perfil da candidata\n{resume_text}\n\n"
        "Para cada vaga do lote enviado pelo usuário, responda com um objeto JSON "
        "por vaga, na MESMA ordem em que as vagas foram enviadas, dentro de um "
        "array JSON. Responda SOMENTE o array JSON, sem markdown, sem texto antes "
        "ou depois. Cada objeto deve ter exatamente estas chaves: "
        f"{', '.join(REQUIRED_FIELDS)}."
    )


def _job_to_prompt_dict(job: RawJob) -> dict:
    return {
        "cargo": job.cargo,
        "empresa": job.empresa,
        "cidade": job.cidade,
        "estado": job.estado,
        "modalidade": job.modalidade,
        "descricao": job.descricao[:4000],  # limite defensivo de tokens por vaga
    }


def _extract_json_array(text: str) -> list[dict]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.M)
    return json.loads(text)


def score_jobs(jobs: list[RawJob], *, rubric_text: str, resume_text: str, api_key: str | None = None) -> list[dict | None]:
    """Retorna uma lista paralela a `jobs`: dict com os campos de score, ou None se a
    vaga não pôde ser pontuada (erro de API/parsing — a vaga não é descartada por
    isso, só fica sem score, ver runner.py)."""
    if not jobs:
        return []

    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY ausente — %d vaga(s) ficarão sem match_score", len(jobs))
        return [None] * len(jobs)

    try:
        import anthropic
    except ImportError:
        logger.warning("Pacote 'anthropic' não instalado — pulando pontuação")
        return [None] * len(jobs)

    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = _build_system_prompt(rubric_text, resume_text)
    results: list[dict | None] = []

    for start in range(0, len(jobs), BATCH_SIZE):
        batch = jobs[start : start + BATCH_SIZE]
        user_payload = json.dumps([_job_to_prompt_dict(j) for j in batch], ensure_ascii=False, indent=2)
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS_PER_BATCH,
                system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": f"Vagas do lote:\n{user_payload}"}],
            )
            raw_text = "".join(block.text for block in response.content if block.type == "text")
            parsed = _extract_json_array(raw_text)
        except Exception as exc:  # nunca deixar um lote ruim derrubar a rotina inteira
            logger.warning("Falha ao pontuar lote de %d vaga(s): %s", len(batch), exc)
            results.extend([None] * len(batch))
            continue

        if not isinstance(parsed, list) or len(parsed) != len(batch):
            logger.warning("Resposta de score com formato inesperado (%d itens para %d vagas)", len(parsed) if isinstance(parsed, list) else -1, len(batch))
            results.extend([None] * len(batch))
            continue

        for item in parsed:
            if isinstance(item, dict) and all(field in item for field in REQUIRED_FIELDS):
                results.append(item)
            else:
                results.append(None)

    return results
