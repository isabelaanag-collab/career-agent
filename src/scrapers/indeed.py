"""Scraper Indeed — faz parsing do JSON embutido na página de resultados HTML
(`window.mosaic.providerData["mosaic-provider-jobcards"]`), sem precisar de API paga
nem de JS headless. Indeed pode bloquear/mudar o HTML a qualquer momento — por isso
todo o parsing é best-effort e nunca propaga exceção (ver `fetch`).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from ..models import RawJob
from .base import make_session, polite_sleep, safe_get

logger = logging.getLogger("career_agent.scrapers.indeed")

SEARCH_URL = "https://br.indeed.com/jobs"
RESULTS_BLOB_RE = re.compile(
    r'window\.mosaic\.providerData\["mosaic-provider-jobcards"\]\s*=\s*(\{.*?\});\s*window\.mosaic\.providerData',
    re.S,
)


def _extract_results(html: str) -> list[dict]:
    match = RESULTS_BLOB_RE.search(html)
    if not match:
        return []
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        logger.warning("Bloco JSON da Indeed não pôde ser decodificado")
        return []
    model = payload.get("metaData", {}).get("mosaicProviderJobCardsModel", {})
    return model.get("results", [])


def _pub_date_iso(job: dict) -> str | None:
    ms = job.get("pubDate")
    if not isinstance(ms, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return None


def _map_modalidade(job: dict) -> str | None:
    if job.get("remoteLocation"):
        return "remoto"
    return None


def fetch(termos: list[str], cidades: list[str]) -> list[RawJob]:
    session = make_session()
    jobs: dict[str, RawJob] = {}
    locais = list(cidades) + ["remoto"]

    for termo in termos:
        for cidade in locais:
            if cidade == "remoto":
                params = {"q": f"{termo} remoto", "l": "", "fromage": "2"}
            else:
                params = {"q": termo, "l": cidade, "fromage": "2"}
            response = safe_get(session, SEARCH_URL, params=params)
            polite_sleep(1.0)
            if response is None:
                continue

            for item in _extract_results(response.text):
                job_key = item.get("jobkey")
                if not job_key or job_key in jobs:
                    continue
                salario = None
                salary_snippet = item.get("salarySnippet") or {}
                if salary_snippet.get("salaryTextFormatted"):
                    salario = salary_snippet.get("text")

                jobs[job_key] = RawJob(
                    plataforma="indeed",
                    cargo=item.get("title", "").strip(),
                    empresa=(item.get("company") or "").strip(),
                    url=f"https://br.indeed.com/viewjob?jk={job_key}",
                    cidade=item.get("jobLocationCity"),
                    estado=item.get("jobLocationState"),
                    modalidade=_map_modalidade(item),
                    salario=salario,
                    salario_estimado=None,
                    data_publicacao=_pub_date_iso(item),
                    descricao=item.get("snippet", "") or "",
                    id_vaga_plataforma=job_key,
                )

    logger.info("Indeed: %d vagas únicas coletadas", len(jobs))
    return list(jobs.values())
