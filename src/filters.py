"""Filtro duro — determinístico, sem LLM. Roda para toda vaga coletada, antes de
qualquer chamada à API da Anthropic (ver README, seção 'redução de tokens').
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .models import RawJob
from .text_utils import contains_any, normalize

MAX_IDADE_HORAS = 48


def is_recent(data_publicacao: str | None, max_age_hours: int = MAX_IDADE_HORAS) -> bool:
    """Vaga sem data (não deu pra extrair) é mantida — melhor processar de mais do que
    descartar por falta de dado. Vaga com data válida e velha é descartada."""
    if not data_publicacao:
        return True
    try:
        parsed = datetime.fromisoformat(data_publicacao.replace("Z", "+00:00"))
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed) <= timedelta(hours=max_age_hours)


def matches_area(job: RawJob, areas: list[str]) -> bool:
    texto = f"{job.cargo} {job.descricao}"
    return contains_any(texto, areas) is not None


def matches_seniority_exclusion(job: RawJob, excluded_keywords: list[str]) -> str | None:
    """Filtro rígido de senioridade: retorna o termo excluído encontrado no título
    (cargo), ou None se o título não contiver nenhum termo de nível júnior/operacional.
    Só olha o título — descrição pode citar "requisitos para estagiários" como parte
    de um programa maior sem a vaga em si ser de estágio.
    """
    return contains_any(job.cargo, excluded_keywords)


def has_seniority_signal(job: RawJob, allowed_seniorities: list[str]) -> bool:
    return contains_any(job.cargo, allowed_seniorities) is not None


def matches_location(job: RawJob, cidades_aceitas: list[str], aceita_remoto: bool, aceita_hibrido: bool) -> bool:
    if job.modalidade == "remoto":
        return aceita_remoto
    if job.modalidade == "hibrido":
        return aceita_hibrido
    if job.cidade:
        norm_cidade = normalize(job.cidade)
        return any(normalize(aceita) in norm_cidade or norm_cidade in normalize(aceita) for aceita in cidades_aceitas)
    # sem modalidade nem cidade identificadas: não descarta por falta de dado,
    # deixa passar para a pontuação decidir com o texto completo da descrição.
    return True


def parse_salary_brl(*values: str | None) -> float | None:
    """Extrai o primeiro valor numérico de strings tipo 'R$ 8.000 - R$ 10.000'.

    Duplicado de scripts/common.py de propósito: scripts/ não é um pacote Python
    (sem __init__.py, importado via sys.path por convenção nos scripts/tests
    existentes) e src/ é um pacote de verdade — evitar acoplar os dois import
    systems é mais simples do que fazer os dois convívios funcionarem juntos.
    """
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


def matches_salary(job: RawJob, salario_minimo: float, allowed_seniorities: list[str] | None = None) -> bool:
    valor = parse_salary_brl(job.salario, job.salario_estimado)
    if valor is not None:
        return valor >= salario_minimo
    # Sem informação de salário: só mantém se o título indicar nível sênior/estratégico
    # explicitamente — vaga genérica sem nível e sem salário informado é descartada.
    if not allowed_seniorities:
        return True
    return has_seniority_signal(job, allowed_seniorities)


def passes_hard_filter(job: RawJob, config: dict) -> tuple[bool, str]:
    """Retorna (passou, motivo_se_reprovado)."""
    if not is_recent(job.data_publicacao):
        return False, "vaga antiga (> 48h)"

    filtro_cargo = config.get("filtro_cargo", {})
    excluded_keywords = filtro_cargo.get("excluded_keywords", [])
    termo_excluido = matches_seniority_exclusion(job, excluded_keywords) if excluded_keywords else None
    if termo_excluido:
        return False, f"título indica nível júnior/operacional ('{termo_excluido}')"

    areas = config.get("areas", [])
    if areas and not matches_area(job, areas):
        return False, "área/cargo não bate com search_criteria.yaml"

    localidades = config.get("localidades", {})
    if not matches_location(
        job,
        cidades_aceitas=localidades.get("cidades_presencial_ou_hibrido", []),
        aceita_remoto=localidades.get("aceita_remoto", True),
        aceita_hibrido=localidades.get("aceita_hibrido", True),
    ):
        return False, "localidade fora dos critérios"

    salario_minimo = config.get("salario_minimo_brl", 0)
    allowed_seniorities = filtro_cargo.get("allowed_seniorities", [])
    if salario_minimo and not matches_salary(job, salario_minimo, allowed_seniorities):
        return False, f"salário abaixo de R$ {salario_minimo} (ou não informado sem nível explícito no título)"

    return True, ""
