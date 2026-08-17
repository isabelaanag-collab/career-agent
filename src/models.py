"""Modelo de dado intermediário usado pelos scrapers, antes do filtro duro e da pontuação."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RawJob:
    """Uma vaga como veio do scraper — ainda não passou por filtro duro nem por score."""

    plataforma: str
    cargo: str
    empresa: str
    url: str
    cidade: str | None = None
    estado: str | None = None
    modalidade: str | None = None  # "presencial" | "hibrido" | "remoto" | None
    salario: str | None = None
    salario_estimado: str | None = None
    data_publicacao: str | None = None  # ISO date, quando disponível
    descricao: str = ""
    id_vaga_plataforma: str | None = None
    beneficios: list[str] = field(default_factory=list)

    @property
    def referencia_dedup(self) -> str:
        return self.url or self.id_vaga_plataforma or f"{self.empresa}|{self.cargo}"
