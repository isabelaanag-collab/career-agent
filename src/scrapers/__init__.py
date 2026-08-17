"""Scrapers puros em Python (sem LLM) para cada plataforma de vagas.

Cada módulo expõe `fetch(termos: list[str], cidades: list[str]) -> list[RawJob]`.
Nenhum scraper deve lançar exceção para fora — falhas de rede/parsing são
capturadas e logadas pelo próprio módulo, retornando lista vazia, para que uma
plataforma fora do ar não derrube a rotina inteira (ver runner.py).
"""
from __future__ import annotations

from . import gupy, indeed, linkedin, solides, vagas_com

REGISTRY = {
    "gupy": gupy.fetch,
    "indeed": indeed.fetch,
    "linkedin": linkedin.fetch,
    "vagas.com": vagas_com.fetch,
    "solides": solides.fetch,
}
