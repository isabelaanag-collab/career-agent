from src.models import RawJob
from src.scorer import REQUIRED_FIELDS, _extract_json_array, score_jobs


def test_extract_json_array_aceita_bloco_markdown():
    texto = '```json\n[{"a": 1}]\n```'
    assert _extract_json_array(texto) == [{"a": 1}]


def test_extract_json_array_aceita_json_puro():
    assert _extract_json_array('[{"a": 1}, {"b": 2}]') == [{"a": 1}, {"b": 2}]


def test_score_jobs_sem_api_key_retorna_none_para_cada_vaga(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    jobs = [RawJob(plataforma="gupy", cargo="Analista", empresa="Ambev", url="https://x")]
    resultado = score_jobs(jobs, rubric_text="rubrica", resume_text="perfil", api_key=None)
    assert resultado == [None]


def test_score_jobs_lista_vazia_retorna_lista_vazia():
    assert score_jobs([], rubric_text="", resume_text="") == []


def test_required_fields_cobre_campos_do_modelo_de_dado():
    assert "match_score" in REQUIRED_FIELDS
    assert "motivos_score" in REQUIRED_FIELDS
