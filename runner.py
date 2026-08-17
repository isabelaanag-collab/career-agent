#!/usr/bin/env python3
"""Rotina diária do Career Agent AI — busca, filtra, pontua e registra vagas.

100% Python puro na busca/filtro/deduplicação (custo zero de tokens). A API da
Anthropic só é chamada, de forma cirúrgica, para pontuar vagas que já passaram por
TODOS os filtros duros (ver src/filters.py e src/scorer.py). Pensada para rodar sem
supervisão via GitHub Actions (.github/workflows/daily_routine.yml), mas roda igual
localmente:

    python runner.py

Este script NUNCA candidata, nunca abre navegador, nunca faz commit/push — isso é
responsabilidade do workflow do GitHub Actions (push) e da sessão local do Claude
Code com claude-in-chrome (candidatura). Ver ARCHITECTURE.md.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))  # common.py/ingest.py são importados como módulos soltos

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("career_agent.runner")

import common  # noqa: E402
import ingest  # noqa: E402
import render_dashboard  # noqa: E402

from src import dedup, filters, sheets_sync  # noqa: E402
from src.models import RawJob  # noqa: E402
from src.scorer import score_jobs  # noqa: E402
from src.scrapers import REGISTRY as SCRAPER_REGISTRY  # noqa: E402

RUBRIC_PATH = ROOT / "agent" / "prompts" / "scoring_rubric.md"
LINKEDIN_PROFILE_PATH = ROOT / "agent" / "config" / "linkedin_profile.txt"
RESUME_PATH = ROOT / "agent" / "config" / "resume.txt"  # opcional, além do perfil


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _build_search_terms(config: dict) -> list[str]:
    return list(config.get("areas", [])) or ["supply chain"]


def _collect_raw_jobs(termos: list[str], cidades: list[str]) -> list[RawJob]:
    all_jobs: list[RawJob] = []
    for plataforma, fetch in SCRAPER_REGISTRY.items():
        try:
            found = fetch(termos, cidades)
        except Exception:  # nenhuma plataforma pode derrubar a rotina inteira
            logger.exception("Scraper de %s falhou de forma inesperada — pulando", plataforma)
            continue
        logger.info("%s: %d vagas brutas", plataforma, len(found))
        all_jobs.extend(found)
    return all_jobs


def _draft_from_job(job: RawJob, score: dict | None) -> dict:
    salario_estimado = job.salario_estimado
    draft = {
        "plataforma": job.plataforma,
        "url": job.url,
        "id_vaga_plataforma": job.id_vaga_plataforma,
        "empresa": job.empresa,
        "cargo": job.cargo,
        "salario": job.salario,
        "salario_estimado": salario_estimado,
        "cidade": job.cidade,
        "estado": job.estado,
        "modalidade": job.modalidade,
        "data_publicacao": job.data_publicacao,
        "beneficios": job.beneficios,
    }
    if score:
        draft.update(
            {
                "match_score": score.get("match_score"),
                "probabilidade_estimada_entrevista": score.get("probabilidade_estimada_entrevista"),
                "motivos_score": score.get("motivos_score", []),
                "palavras_chave_encontradas": score.get("palavras_chave_encontradas", []),
                "tecnologias_exigidas": score.get("tecnologias_exigidas", []),
                "idiomas_exigidos": score.get("idiomas_exigidos", []),
                "beneficios": score.get("beneficios") or job.beneficios,
                "requisitos_obrigatorios": score.get("requisitos_obrigatorios", []),
                "requisitos_desejaveis": score.get("requisitos_desejaveis", []),
            }
        )
    return draft


def _write_github_output(**kv: object) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as fh:
        for key, value in kv.items():
            fh.write(f"{key}={value}\n")


def main() -> int:
    config = common.load_config()
    if not config:
        logger.error("Não foi possível ler agent/config/search_criteria.yaml — abortando")
        return 1

    termos = _build_search_terms(config)
    cidades = config.get("localidades", {}).get("cidades_presencial_ou_hibrido", [])
    logger.info("Buscando %d termos em %d cidades + remoto", len(termos), len(cidades))

    raw_jobs = _collect_raw_jobs(termos, cidades)
    logger.info("Total bruto coletado: %d vagas (todas as plataformas)", len(raw_jobs))

    # 1) descarta duplicadas por URL (já registradas em data/jobs/) e por conteúdo
    #    (empresa+cargo+cidade — pega reposts com URL nova) e candidaturas feitas
    #    fora do sistema (data/applied_externos.json) — tudo isso ANTES de qualquer
    #    filtro duro ou chamada de LLM, para gastar o mínimo possível.
    seen_index = common.load_seen_index()
    content_hashes = dedup.load_content_hashes()
    applied_external = dedup.load_applied_external_hashes()

    candidatos: list[RawJob] = []
    for job in raw_jobs:
        ext_id = common.external_id(job.plataforma, job.referencia_dedup)
        c_hash = dedup.job_content_hash(job)
        if ext_id in seen_index or c_hash in content_hashes or c_hash in applied_external:
            continue
        candidatos.append(job)
    logger.info("Após deduplicação: %d vagas novas candidatas", len(candidatos))

    # 2) filtro duro determinístico (sem LLM)
    aprovados_no_filtro: list[RawJob] = []
    for job in candidatos:
        passou, motivo = filters.passes_hard_filter(job, config)
        if passou:
            aprovados_no_filtro.append(job)
        else:
            logger.debug("Descartada (%s): %s @ %s — %s", motivo, job.cargo, job.empresa, job.url)
    logger.info("Após filtro duro: %d vagas passaram (área/salário/local/recência)", len(aprovados_no_filtro))

    # 3) só agora, cirurgicamente, a API da Anthropic é chamada — e só para essas vagas
    rubric_text = _read_text(RUBRIC_PATH)
    resume_text = "\n\n".join(filter(None, [_read_text(LINKEDIN_PROFILE_PATH), _read_text(RESUME_PATH)]))
    scores = score_jobs(aprovados_no_filtro, rubric_text=rubric_text, resume_text=resume_text)

    # 4) persiste (dedup por URL de novo, dentro de ingest.ingest_draft) e atualiza os índices
    novas_gravadas: list[dict] = []
    for job, score in zip(aprovados_no_filtro, scores):
        draft = _draft_from_job(job, score)
        resultado, saved_job, ext_id = ingest.ingest_draft(draft)
        if resultado != "gravado":
            continue
        content_hashes[dedup.job_content_hash(job)] = {"ext_id": ext_id, "plataforma": job.plataforma}
        novas_gravadas.append(saved_job)

    dedup.save_content_hashes(content_hashes)
    logger.info("Vagas novas gravadas em data/jobs/: %d", len(novas_gravadas))

    pendentes_aprovacao = [j for j in novas_gravadas if j["status"] == "Aguardando aprovação"]
    sincronizadas = sheets_sync.sync_new_jobs(pendentes_aprovacao, config)
    logger.info("Google Sheets: %d linha(s) sincronizada(s)", sincronizadas)

    render_dashboard.main()

    _write_github_output(
        vagas_novas=len(novas_gravadas),
        vagas_aguardando_aprovacao=len(pendentes_aprovacao),
    )

    if novas_gravadas:
        destaques = ", ".join(f"{j['empresa']} ({j['status']})" for j in novas_gravadas[:5])
        logger.info("Resumo: %d nova(s) — %s%s", len(novas_gravadas), destaques, "..." if len(novas_gravadas) > 5 else "")
    else:
        logger.info("Nenhuma vaga nova nesta execução.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
