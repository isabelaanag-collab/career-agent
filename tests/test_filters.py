from datetime import datetime, timedelta, timezone

from src.filters import (
    has_seniority_signal,
    is_recent,
    matches_area,
    matches_location,
    matches_salary,
    matches_seniority_exclusion,
    passes_hard_filter,
)
from src.models import RawJob

EXCLUDED_KEYWORDS = [
    "Estágio", "Estagiário", "Estagiária", "Trainee", "Assistente", "Auxiliar",
    "Operador", "Conferente", "Jovem Aprendiz", "Prático", "Técnico", "Ajudante",
    "Motorista", "Estoquista",
]
ALLOWED_SENIORITIES = ["Analista", "Pleno", "Sênior", "Lead", "Especialista", "Coordenador", "Supervisor", "Gerente"]

CONFIG = {
    "salario_minimo_brl": 6000,
    "localidades": {
        "cidades_presencial_ou_hibrido": ["Belo Horizonte", "Betim", "Contagem", "Nova Lima"],
        "aceita_remoto": True,
        "aceita_hibrido": True,
    },
    "areas": ["Supply Chain", "PCP", "Compras", "Logística", "S&OP", "Demand Planning", "Analista de Demanda", "Especialista de Demanda"],
    "filtro_cargo": {
        "excluded_keywords": EXCLUDED_KEYWORDS,
        "allowed_seniorities": ALLOWED_SENIORITIES,
    },
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


def test_titulo_de_estagio_e_descartado_mesmo_com_area_e_salario_ok():
    job = _job(cargo="Estágio em Supply Chain", salario="R$ 8.000,00")
    passou, motivo = passes_hard_filter(job, CONFIG)
    assert passou is False
    assert "júnior" in motivo


def test_titulo_de_assistente_e_descartado():
    assert matches_seniority_exclusion(_job(cargo="Assistente de Logística"), EXCLUDED_KEYWORDS) == "Assistente"


def test_titulo_de_tecnico_e_descartado():
    assert matches_seniority_exclusion(_job(cargo="Técnico de Suprimentos"), EXCLUDED_KEYWORDS) == "Técnico"


def test_titulo_sem_termo_excluido_nao_e_reprovado_pela_senioridade():
    assert matches_seniority_exclusion(_job(cargo="Especialista de Supply Chain"), EXCLUDED_KEYWORDS) is None


def test_analista_de_demanda_bate_area():
    assert matches_area(_job(cargo="Analista de Demanda Pleno", descricao=""), CONFIG["areas"]) is True


def test_especialista_de_demanda_bate_area():
    assert matches_area(_job(cargo="Especialista de Demanda", descricao=""), CONFIG["areas"]) is True


def test_sop_e_demand_planning_batem_area():
    assert matches_area(_job(cargo="Coordenador S&OP", descricao=""), CONFIG["areas"]) is True
    assert matches_area(_job(cargo="Demand Planning Specialist", descricao=""), CONFIG["areas"]) is True


def test_sem_salario_e_sem_nivel_explicito_e_descartado():
    job = _job(cargo="Comprador", salario=None, salario_estimado=None)
    assert matches_salary(job, 6000, ALLOWED_SENIORITIES) is False


def test_sem_salario_mas_com_nivel_explicito_passa():
    job = _job(cargo="Comprador Sênior", salario=None, salario_estimado=None)
    assert matches_salary(job, 6000, ALLOWED_SENIORITIES) is True


def test_especialista_sem_salario_passa_no_filtro_duro_completo():
    job = _job(cargo="Especialista de Demanda", salario=None, salario_estimado=None, descricao="")
    passou, motivo = passes_hard_filter(job, CONFIG)
    assert passou is True, motivo


def test_vaga_generica_sem_nivel_e_sem_salario_e_descartada_no_filtro_completo():
    # bate na área (Supply Chain) mas o título não tem nenhum termo de allowed_seniorities
    job = _job(cargo="Supply Chain Planner", salario=None, salario_estimado=None)
    passou, motivo = passes_hard_filter(job, CONFIG)
    assert passou is False
    assert "salário" in motivo


def test_has_seniority_signal_detecta_termo_no_titulo():
    assert has_seniority_signal(_job(cargo="Gerente de Compras"), ALLOWED_SENIORITIES) is True
    assert has_seniority_signal(_job(cargo="Comprador"), ALLOWED_SENIORITIES) is False
