"""Scraper Sólides Vagas — status: NÃO IMPLEMENTADO de forma confiável.

Diferente da Gupy (API pública descoberta em employability-portal.gupy.io) e do
Vagas.com/Indeed (HTML com dados embutidos), o portal vagas.solides.com.br é uma SPA
Next.js cujo carregamento da lista de vagas não expõe nenhum endpoint JSON público
nem HTML server-renderizado com os dados — nem no `__NEXT_DATA__` inicial, nem nas
rotas `/_next/data/<buildId>/...json` (essas retornam só metadados de página, sem a
lista). A chamada real que popula a lista acontece via JS no navegador para um host
que não ficou visível nem inspecionando o tráfego de rede diretamente.

Em vez de chutar um endpoint não verificado (que quebraria silenciosamente e daria
falsa confiança de cobertura), esta plataforma fica registrada como lacuna conhecida:
`fetch` sempre retorna lista vazia. Ver ARCHITECTURE.md, seção "Limitações conhecidas".
Se descobrir o endpoint real (ex.: inspecionando a aba Network do navegador enquanto
usa o portal), implemente aqui seguindo o mesmo padrão de `gupy.py`.
"""
from __future__ import annotations

import logging

from ..models import RawJob

logger = logging.getLogger("career_agent.scrapers.solides")

_WARNED = False


def fetch(termos: list[str], cidades: list[str]) -> list[RawJob]:
    global _WARNED
    if not _WARNED:
        logger.warning(
            "Sólides: scraper não implementado (SPA sem endpoint público identificado) — "
            "0 vagas desta fonte em toda execução. Ver docstring de src/scrapers/solides.py."
        )
        _WARNED = True
    return []
