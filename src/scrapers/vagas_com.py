"""Scraper Vagas.com — a busca é renderizada em HTML puro no servidor (sem SPA/JS),
então dá para usar `requests` + BeautifulSoup diretamente na página de resultados.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from ..models import RawJob
from ..text_utils import normalize
from .base import make_session, polite_sleep, safe_get

logger = logging.getLogger("career_agent.scrapers.vagas_com")

BASE_URL = "https://www.vagas.com.br"


def _slug(termo: str) -> str:
    slug = normalize(termo).replace(" ", "-")
    return re.sub(r"[^a-z0-9-]", "", slug)


def _parse_date_br(text: str) -> str | None:
    text = text.strip()
    try:
        return datetime.strptime(text, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def _map_modalidade(location_text: str) -> str | None:
    norm = normalize(location_text)
    if "remoto" in norm or "home office" in norm:
        return "remoto"
    if "hibrido" in norm:
        return "hibrido"
    if norm and "nao informad" not in norm:
        return "presencial"
    return None


def fetch(termos: list[str], cidades: list[str]) -> list[RawJob]:
    session = make_session()
    jobs: dict[str, RawJob] = {}

    for termo in termos:
        url = f"{BASE_URL}/vagas-de-{_slug(termo)}"
        response = safe_get(session, url)
        polite_sleep(1.0)
        if response is None:
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        for card in soup.select("li.vaga"):
            link_el = card.select_one("a.link-detalhes-vaga")
            if not link_el:
                continue
            href = link_el.get("href", "")
            if not href:
                continue
            job_url = BASE_URL + href
            if job_url in jobs:
                continue

            empresa_el = card.select_one(".emprVaga")
            local_el = card.select_one(".vaga-local")
            data_el = card.select_one(".data-publicacao")
            descricao_el = card.select_one(".detalhes p")

            local_text = local_el.get_text(strip=True) if local_el else ""
            data_text = data_el.get_text(strip=True) if data_el else ""

            jobs[job_url] = RawJob(
                plataforma="vagas.com",
                cargo=(link_el.get("title") or link_el.get_text(strip=True)).strip(),
                empresa=empresa_el.get_text(strip=True) if empresa_el else "",
                url=job_url,
                cidade=local_text or None,
                estado=None,
                modalidade=_map_modalidade(local_text),
                salario=None,
                salario_estimado=None,
                data_publicacao=_parse_date_br(data_text),
                descricao=descricao_el.get_text(strip=True) if descricao_el else "",
                id_vaga_plataforma=link_el.get("data-id-vaga"),
            )

    logger.info("Vagas.com: %d vagas únicas coletadas", len(jobs))
    return list(jobs.values())
