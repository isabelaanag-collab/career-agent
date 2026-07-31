import argparse
import json

import pytest


def _patch_paths(monkeypatch, tmp_path):
    import common
    import ingest
    import update_status

    data_dir = tmp_path / "data"
    jobs_dir = data_dir / "jobs"
    seen_path = data_dir / "seen_index.json"
    applications_log = data_dir / "applications_log.jsonl"
    config_path = tmp_path / "nao_existe.yaml"

    monkeypatch.setattr(common, "DATA_DIR", data_dir)
    monkeypatch.setattr(common, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(common, "SEEN_INDEX_PATH", seen_path)
    monkeypatch.setattr(common, "CONFIG_PATH", config_path)
    monkeypatch.setattr(common, "APPLICATIONS_LOG_PATH", applications_log)
    monkeypatch.setattr(ingest, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(update_status, "APPLICATIONS_LOG_PATH", applications_log)
    return jobs_dir, seen_path, applications_log


def _draft_path(tmp_path, url="https://indeed.com/viewjob?jk=dup001"):
    draft = {
        "plataforma": "indeed",
        "url": url,
        "empresa": "Nestlé",
        "cargo": "Especialista em S&OE",
        "match_score": 88,
    }
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(draft), encoding="utf-8")
    return path


def test_mesma_vaga_nao_e_duplicada(tmp_path, monkeypatch):
    import ingest

    jobs_dir, seen_path, _ = _patch_paths(monkeypatch, tmp_path)
    path = _draft_path(tmp_path)

    ns = argparse.Namespace(input=str(path), force=False)
    assert ingest.cmd_write(ns) == 0
    assert ingest.cmd_write(ns) == 0  # segunda chamada, mesma vaga

    assert len(list(jobs_dir.glob("*.json"))) == 1
    seen = json.loads(seen_path.read_text(encoding="utf-8"))
    assert len(seen) == 1


def test_check_reporta_seen_depois_de_gravar(tmp_path, monkeypatch, capsys):
    import ingest

    _patch_paths(monkeypatch, tmp_path)
    path = _draft_path(tmp_path, url="https://indeed.com/viewjob?jk=dup002")

    check_ns = argparse.Namespace(plataforma="indeed", ref="https://indeed.com/viewjob?jk=dup002")
    assert ingest.cmd_check(check_ns) == 0
    assert "NEW" in capsys.readouterr().out

    write_ns = argparse.Namespace(input=str(path), force=False)
    assert ingest.cmd_write(write_ns) == 0

    assert ingest.cmd_check(check_ns) == 1
    assert "SEEN" in capsys.readouterr().out


def test_nao_candidata_duas_vezes(tmp_path, monkeypatch):
    import ingest
    import update_status

    jobs_dir, _, applications_log = _patch_paths(monkeypatch, tmp_path)
    path = _draft_path(tmp_path, url="https://indeed.com/viewjob?jk=dup003")
    ingest.cmd_write(argparse.Namespace(input=str(path), force=False))

    job_file = next(jobs_dir.glob("*.json"))
    id_externo = job_file.stem

    argv = ["update_status.py", id_externo, "Candidatura enviada"]
    monkeypatch.setattr("sys.argv", argv)
    assert update_status.main() == 0  # primeiro envio: ok

    monkeypatch.setattr("sys.argv", argv)
    assert update_status.main() == 3  # segunda tentativa de candidatura deve ser recusada

    job = json.loads(job_file.read_text(encoding="utf-8"))
    assert job["status"] == "Candidatura enviada"
    assert sum(1 for h in job["historico_status"] if h["status"] == "Candidatura enviada") == 1
    assert applications_log.exists()
    assert len(applications_log.read_text(encoding="utf-8").strip().splitlines()) == 1
