import argparse
import json

import pytest


def _patch_paths(monkeypatch, tmp_path):
    import common
    import ingest

    data_dir = tmp_path / "data"
    jobs_dir = data_dir / "jobs"
    seen_path = data_dir / "seen_index.json"
    config_path = tmp_path / "nao_existe.yaml"

    monkeypatch.setattr(common, "DATA_DIR", data_dir)
    monkeypatch.setattr(common, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(common, "SEEN_INDEX_PATH", seen_path)
    monkeypatch.setattr(common, "CONFIG_PATH", config_path)
    monkeypatch.setattr(ingest, "JOBS_DIR", jobs_dir)
    return jobs_dir, seen_path


def _write_draft(tmp_path, **overrides):
    draft = {
        "plataforma": "indeed",
        "url": "https://indeed.com/viewjob?jk=xyz789",
        "empresa": "Ambev",
        "cargo": "Analista de Planejamento de Demanda",
        "match_score": 78,
    }
    draft.update(overrides)
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(draft), encoding="utf-8")
    return path


def test_write_rejeita_rascunho_sem_campos_obrigatorios(tmp_path, monkeypatch):
    import ingest

    _patch_paths(monkeypatch, tmp_path)
    path = tmp_path / "draft.json"
    path.write_text(json.dumps({"plataforma": "indeed"}), encoding="utf-8")

    ns = argparse.Namespace(input=str(path), force=False)
    assert ingest.cmd_write(ns) == 2


@pytest.mark.parametrize(
    "score,status_esperado",
    [(85, "Aguardando aprovação"), (70, "Aguardando aprovação"), (69, "Encontrada"), (10, "Encontrada")],
)
def test_write_define_status_pelo_match_score(tmp_path, monkeypatch, score, status_esperado):
    import ingest

    jobs_dir, _ = _patch_paths(monkeypatch, tmp_path)
    path = _write_draft(tmp_path, match_score=score, url=f"https://indeed.com/viewjob?jk=score{score}")

    ns = argparse.Namespace(input=str(path), force=False)
    assert ingest.cmd_write(ns) == 0

    written = list(jobs_dir.glob("*.json"))
    assert len(written) == 1
    job = json.loads(written[0].read_text(encoding="utf-8"))
    assert job["status"] == status_esperado
    assert job["historico_status"][0]["status"] == status_esperado
