import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from render_dashboard import aggregate, render_html

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "jobs"


@pytest.fixture
def fixture_jobs():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(FIXTURES_DIR.glob("*.json"))]


def test_aggregate_totais(fixture_jobs):
    stats = aggregate(fixture_jobs)
    assert stats["total_vagas"] == 3
    assert stats["media_match_score"] == pytest.approx((85 + 55 + 91) / 3, abs=0.1)
    assert stats["total_candidaturas"] == 1  # só a vaga da Bosch está "Candidatura enviada"
    assert stats["total_empresas_favoritas"] == 2  # Vale e Bosch


def test_aggregate_por_status_e_plataforma(fixture_jobs):
    stats = aggregate(fixture_jobs)
    status_counts = dict(stats["por_status"])
    assert status_counts["Encontrada"] == 1
    assert status_counts["Aguardando aprovação"] == 1
    assert status_counts["Candidatura enviada"] == 1

    plataforma_counts = dict(stats["por_plataforma"])
    assert plataforma_counts["indeed"] == 1
    assert plataforma_counts["linkedin"] == 1
    assert plataforma_counts["gupy"] == 1


def test_aggregate_faixa_salarial(fixture_jobs):
    stats = aggregate(fixture_jobs)
    faixas = dict(stats["por_faixa_salarial"])
    # Vale R$9.000 -> 8-10k ; LinkedIn R$6.500 (estimado) -> 6-8k ; Bosch R$13.000 -> 12-15k
    assert faixas["R$ 8-10k"] == 1
    assert faixas["R$ 6-8k"] == 1
    assert faixas["R$ 12-15k"] == 1


def test_aggregate_eventos_de_hoje_sao_zero_para_fixtures_antigas(fixture_jobs):
    stats = aggregate(fixture_jobs)
    # todas as datas das fixtures são de janeiro/2026, não "hoje"
    assert stats["encontradas_hoje"] == 0
    assert stats["candidatadas_hoje"] == 0


def test_aggregate_conta_evento_de_hoje():
    hoje = datetime.now(timezone.utc).date().isoformat()
    job = {
        "empresa": "Teste Co",
        "cidade": "Belo Horizonte",
        "plataforma": "indeed",
        "status": "Encontrada",
        "match_score": 72,
        "historico_status": [{"status": "Encontrada", "data": f"{hoje}T10:00:00+00:00"}],
    }
    stats = aggregate([job])
    assert stats["encontradas_hoje"] == 1


def test_render_html_nao_quebra_e_contem_elementos_esperados(fixture_jobs):
    stats = aggregate(fixture_jobs)
    output = render_html(fixture_jobs, stats)
    assert "<html" in output
    assert "Painel de recolocação" in output
    assert "Aguardando Aprovação" in output
    assert "Vale" in output
    assert "Bosch" in output


def test_render_html_com_lista_vazia_nao_quebra():
    stats = aggregate([])
    output = render_html([], stats)
    assert "<html" in output
    assert "Sem dados ainda." in output
