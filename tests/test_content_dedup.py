import json

from src import dedup
from src.models import RawJob


def _patch_paths(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(dedup, "DATA_DIR", data_dir)
    monkeypatch.setattr(dedup, "CONTENT_HASH_PATH", data_dir / "seen_content_hashes.json")
    monkeypatch.setattr(dedup, "APPLIED_EXTERNAL_PATH", data_dir / "applied_externos.json")
    return data_dir


def test_hash_e_estavel_e_insensivel_a_acento_maiusculas_e_espacos():
    a = dedup.content_hash("Ambev", "Analista de Supply Chain", "Belo Horizonte")
    b = dedup.content_hash("  ambev  ", "ANALISTA DE SUPPLY CHAIN", "belo horizonte")
    assert a == b


def test_empresas_diferentes_geram_hash_diferente():
    a = dedup.content_hash("Ambev", "Analista de Supply Chain", "Belo Horizonte")
    b = dedup.content_hash("Nestlé", "Analista de Supply Chain", "Belo Horizonte")
    assert a != b


def test_content_hashes_persistem_em_disco(tmp_path, monkeypatch):
    data_dir = _patch_paths(monkeypatch, tmp_path)
    index = {"abc123": {"ext_id": "gupy__xyz"}}
    dedup.save_content_hashes(index)

    assert (data_dir / "seen_content_hashes.json").exists()
    assert dedup.load_content_hashes() == index


def test_load_content_hashes_sem_arquivo_retorna_vazio(tmp_path, monkeypatch):
    _patch_paths(monkeypatch, tmp_path)
    assert dedup.load_content_hashes() == {}


def test_applied_externos_e_convertido_em_hashes(tmp_path, monkeypatch):
    data_dir = _patch_paths(monkeypatch, tmp_path)
    data_dir.mkdir(parents=True, exist_ok=True)
    entries = [{"empresa": "Ambev", "cargo": "Analista de Supply Chain", "cidade": "Belo Horizonte"}]
    (data_dir / "applied_externos.json").write_text(json.dumps(entries), encoding="utf-8")

    hashes = dedup.load_applied_external_hashes()
    expected = dedup.content_hash("Ambev", "Analista de Supply Chain", "Belo Horizonte")
    assert expected in hashes


def test_job_content_hash_usa_campos_da_rawjob():
    job = RawJob(plataforma="gupy", cargo="Analista", empresa="Ambev", url="https://x", cidade="Belo Horizonte")
    assert dedup.job_content_hash(job) == dedup.content_hash("Ambev", "Analista", "Belo Horizonte")
