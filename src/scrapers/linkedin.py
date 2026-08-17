"""Scraper LinkedIn — usa o endpoint público "guest" de busca de vagas
(jobs-guest/jobs/api/seeMoreJobPostings/search), o mesmo que a página de vagas do
LinkedIn usa para visitantes não autenticados. NÃO faz login, não usa cookies de
sessão, não acessa a conta de ninguém — é leitura pública, igual a abrir a busca de
vagas em uma aba anônima.

Esta é de longe a fonte mais instável das cinco: o LinkedIn aplica rate-limit
agressivo a esse endpoint e pode retornar uma resposta vazia (ou bloquear
temporariamente o IP) mesmo para uma única requisição legítima. Por isso o scraper:
- faz no máximo 1 tentativa por termo/cidade (sem insistir e piorar o bloqueio);
- trata qualquer resposta vazia/pequena como "sem resultados desta vez", não como erro;
- nunca lança exceção — uma falha aqui não deve impedir as outras plataformas.

Se o LinkedIn continuar bloqueando consistentemente, considere isso uma limitação
conhecida (documentada no ARCHITECTURE.md) e não um bug a "consertar" com login
automatizado — automatizar login no LinkedIn viola os Termos de Uso.

Observação adicional: o parâmetro `location` desse endpoint público é só um filtro
"melhor esforço" — em teste real, buscas por "Belo Horizonte" retornaram vagas nos
EUA junto com vagas do Brasil. Isso é inofensivo aqui porque toda vaga ainda passa
pelo filtro duro de localidade em `src/filters.py` antes de virar candidata a score;
só significa que uma fração das requisições feitas ao LinkedIn "não rende" vaga
aproveitável, não que vagas fora de escopo vazem para o dashboard.
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from ..models import RawJob
from .base import make_session, polite_sleep, safe_get

logger = logging.getLogger("career_agent.scrapers.linkedin")

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
MIN_VALID_RESPONSE_SIZE = 500  # respostas de bloqueio vêm com poucas dezenas de bytes


def _parse_cards(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = []
    for card in soup.select("li"):
        link_el = card.select_one("a.base-card__full-link, a.base-search-card__full-link")
        title_el = card.select_one("h3.base-search-card__title")
        company_el = card.select_one("h4.base-search-card__subtitle a, h4.base-search-card__subtitle")
        location_el = card.select_one("span.job-search-card__location")
        time_el = card.select_one("time")
        if not (link_el and title_el):
            continue
        cards.append(
            {
                "url": link_el.get("href", "").split("?")[0],
                "cargo": title_el.get_text(strip=True),
                "empresa": company_el.get_text(strip=True) if company_el else "",
                "local": location_el.get_text(strip=True) if location_el else "",
                "data_publicacao": time_el.get("datetime") if time_el else None,
            }
        )
    return cards


def fetch(termos: list[str], cidades: list[str]) -> list[RawJob]:
    session = make_session()
    jobs: dict[str, RawJob] = {}
    locais = list(cidades) + ["Brasil"]  # "Brasil" cobre remoto/geral quando a cidade não bate

    for termo in termos:
        for cidade in locais:
            referer = (
                "https://www.linkedin.com/jobs/search?"
                f"keywords={termo.replace(' ', '%20')}&location={cidade.replace(' ', '%20')}"
            )
            headers = {"Referer": referer, "Accept": "text/html,application/xhtml+xml"}
            params = {"keywords": termo, "location": cidade, "f_TPR": "r172800", "start": 0}  # últimas 48h
            response = safe_get(session, SEARCH_URL, params=params, headers=headers)
            polite_sleep(2.0)
            if response is None or len(response.text) < MIN_VALID_RESPONSE_SIZE:
                continue

            try:
                cards = _parse_cards(response.text)
            except Exception:  # parsing best-effort — nunca deixar isso derrubar a rotina
                logger.warning("Falha ao interpretar HTML do LinkedIn para %r/%r", termo, cidade)
                continue

            for card in cards:
                url = card["url"]
                if not url or url in jobs:
                    continue
                job_id_match = re.search(r"-(\d+)(?:$|[/?])", url)
                cidade_extraida, _, estado_extraida = card["local"].partition(",")
                jobs[url] = RawJob(
                    plataforma="linkedin",
                    cargo=card["cargo"],
                    empresa=card["empresa"],
                    url=url,
                    cidade=cidade_extraida.strip() or None,
                    estado=estado_extraida.strip() or None,
                    modalidade=None,
                    salario=None,
                    salario_estimado=None,
                    data_publicacao=card["data_publicacao"],
                    descricao="",
                    id_vaga_plataforma=job_id_match.group(1) if job_id_match else None,
                )

    logger.info("LinkedIn: %d vagas únicas coletadas (fonte instável, 0 pode só significar bloqueio momentâneo)", len(jobs))
    return list(jobs.values())
