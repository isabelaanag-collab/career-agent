from datetime import datetime, timedelta, timezone

from src.filters import is_recent, matches_area, matches_location, matches_salary, passes_hard_filter
from src.models import RawJob

CONFIG = {
    "salario_minimo_brl": 6000,
    "localidades": {
        "cidades_presencial_ou_hibrido": ["Belo Horizonte", "Betim", "Contagem", "Nova Lima"],
        "aceita_remoto": True,
        "aceita_hibrido": True,
    },
    "areas": ["Supply Chain", "PCP", "Compras", "Logística"],
}


def _job(**overrides) -> RawJob:
    base = dict(
        plataforma="gupy",
        cargo="Analista de Supply Chain Pleno",
        empresa="Ambev",
        url="https://ambev.gupy.io/job/abc",
        cidade="Belo Horizonte",
        estado="MG",
        modalidade="presencial",
        salario=None,
        salario_estimado=None,
        data_publicacao=datetime.now(timezone.utc).isoformat(),
        descricao="Planejamento de materiais, MRP e S&OP.",
    )
    base.update(overrides)
    return RawJob(**base)


def test_vaga_completa_passa_no_filtro_duro():
    passou, motivo = passes_hard_filter(_job(), CONFIG)
    assert passou is True
    assert motivo == ""


def test_area_fora_do_escopo_e_reprovada():
    job = _job(cargo="Analista Financeiro", descricao="Contas a pagar e conciliação bancária.")
    passou, motivo = passes_hard_filter(job, CONFIG)
    assert passou is False
    assert "área" in motivo


def test_cidade_fora_da_lista_presencial_e_reprovada():
    job = _job(cidade="Curitiba", modalidade="presencial")
    passou, _ = passes_hard_filter(job, CONFIG)
    assert passou is False


def test_remoto_sempre_aceito_independente_da_cidade():
    job = _job(cidade=None, modalidade="remoto")
    assert matches_location(job, CONFIG["localidades"]["cidades_presencial_ou_hibrido"], True, True) is True


def test_salario_abaixo_do_minimo_e_reprovado():
    assert matches_salary(_job(salario="R$ 4.000,00"), 6000) is False


def test_salario_nao_informado_nao_e_motivo_de_descarte():
    assert matches_salary(_job(salario=None, salario_estimado=None), 6000) is True


def test_vaga_antiga_e_descartada_por_recencia():
    velha = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
    assert is_recent(velha) is False


def test_vaga_sem_data_nao_e_descartada_por_recencia():
    assert is_recent(None) is True


def test_area_bate_com_termo_do_cargo():
    assert matches_area(_job(cargo="Analista de Compras Pleno"), ["Compras"]) is True
