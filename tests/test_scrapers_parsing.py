from src.scrapers.indeed import _pub_date_iso
from src.scrapers.vagas_com import _map_modalidade as vagas_modalidade
from src.scrapers.vagas_com import _parse_date_br, _slug


def test_slug_normaliza_termo_composto():
    assert _slug("Supply Chain") == "supply-chain"
    assert _slug("Planejamento de Demanda") == "planejamento-de-demanda"


def test_parse_date_br_converte_para_iso():
    assert _parse_date_br("22/07/2026") == "2026-07-22"


def test_parse_date_br_invalido_retorna_none():
    assert _parse_date_br("data desconhecida") is None


def test_vagas_com_modalidade_remoto():
    assert vagas_modalidade("Home Office") == "remoto"


def test_vagas_com_modalidade_nao_informado_retorna_none():
    assert vagas_modalidade("Localização não informada") is None


def test_indeed_pub_date_converte_epoch_ms():
    resultado = _pub_date_iso({"pubDate": 1786770000000})
    assert resultado is not None
    assert resultado.startswith("20")


def test_indeed_pub_date_sem_campo_retorna_none():
    assert _pub_date_iso({}) is None
