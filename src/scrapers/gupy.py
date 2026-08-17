"""Scraper Gupy — usa a API pública (não documentada, mas sem autenticação) que o
próprio portal.gupy.io consome no navegador: employability-portal.gupy.io/api/v1/jobs.

Descoberta por inspeção de rede em portal.gupy.io/job-search — sem login, sem scraping
de HTML renderizado por JS. Se a Gupy mudar o endpoint, `fetch` retorna lista vazia
(logando um aviso) em vez de quebrar a rotina inteira.
"""
from __future__ import annotations

import logging

from ..models import RawJob
from .base import make_session, polite_sleep, safe_get

logger = logging.getLogger("career_agent.scrapers.gupy")

API_URL = "https://employability-portal.gupy.io/api/v1/jobs"
RESULTS_PER_TERM = 20


def _map_modalidade(job: dict) -> str | None:
    if job.get("isRemoteWork"):
        return "remoto"
    workplace_type = (job.get("workplaceType") or "").lower()
    if "hybrid" in workplace_type:
        return "hibrido"
    if "remote" in workplace_type:
        return "remoto"
    if "on-site" in workplace_type or "onsite" in workplace_type:
        return "presencial"
    return None


def fetch(termos: list[str], cidades: list[str]) -> list[RawJob]:
    session = make_session()
    jobs: dict[int, RawJob] = {}

    for termo in termos:
        response = safe_get(
            session,
            API_URL,
            params={
                "jobName": termo,
                "limit": RESULTS_PER_TERM,
                "offset": 0,
                "sortBy": "publishedDate",
                "sortOrder": "desc",
            },
        )
        polite_sleep(0.5)
        if response is None:
            continue
        try:
            payload = response.json()
        except ValueError:
            logger.warning("Resposta da Gupy não é JSON válido para termo %r", termo)
            continue

        for item in payload.get("data", []):
            job_id = item.get("id")
            if job_id is None or job_id in jobs:
                continue
            jobs[job_id] = RawJob(
                plataforma="gupy",
                cargo=item.get("name", "").strip(),
                empresa=(item.get("careerPageName") or "").strip(),
                url=item.get("jobUrl", ""),
                cidade=item.get("city"),
                estado=item.get("state"),
                modalidade=_map_modalidade(item),
                salario=None,
                salario_estimado=None,
                data_publicacao=item.get("publishedDate"),
                descricao=item.get("description", "") or "",
                id_vaga_plataforma=str(job_id),
            )

    logger.info("Gupy: %d vagas únicas coletadas em %d termos", len(jobs), len(termos))
    return list(jobs.values())
