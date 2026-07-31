#!/usr/bin/env python3
"""Deduplicação e persistência de vagas para o career-agent.

Uso:
    python scripts/ingest.py check --plataforma indeed --ref "https://..."
    python scripts/ingest.py write --input caminho/para/rascunho.json [--force]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from common import (
    DEFAULT_LIMIAR_APROVACAO,
    JOBS_DIR,
    external_id,
    job_path,
    load_config,
    load_seen_index,
    save_seen_index,
)

REQUIRED_DRAFT_FIELDS = ["plataforma", "empresa", "cargo"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def cmd_check(args: argparse.Namespace) -> int:
    ext_id = external_id(args.plataforma, args.ref)
    seen = load_seen_index()
    if ext_id in seen:
        print("SEEN")
        return 1
    print("NEW")
    return 0


def cmd_write(args: argparse.Namespace) -> int:
    draft_path = Path(args.input)
    draft = json.loads(draft_path.read_text(encoding="utf-8"))

    missing = [f for f in REQUIRED_DRAFT_FIELDS if not draft.get(f)]
    if missing:
        print(f"Rascunho inválido, faltando campos: {missing}", file=sys.stderr)
        return 2

    referencia = draft.get("url") or draft.get("id_vaga_plataforma")
    if not referencia:
        print("Rascunho precisa de 'url' ou 'id_vaga_plataforma' para deduplicação.", file=sys.stderr)
        return 2

    ext_id = external_id(draft["plataforma"], referencia)
    seen = load_seen_index()
    if ext_id in seen and not args.force:
        print(f"Vaga já registrada ({ext_id}), ignorando.")
        return 0

    config = load_config()
    limiar_aprovacao = (
        config.get("match_score", {}).get("limiar_prepara_candidatura", DEFAULT_LIMIAR_APROVACAO)
    )
    favoritas = {c.strip().lower() for c in config.get("empresas_favoritas", [])}

    match_score = draft.get("match_score")
    status_inicial = (
        "Aguardando aprovação" if isinstance(match_score, (int, float)) and match_score >= limiar_aprovacao
        else "Encontrada"
    )

    job = {
        "id_externo": ext_id,
        "plataforma": draft["plataforma"],
        "url": draft.get("url"),
        "empresa": draft["empresa"],
        "cargo": draft["cargo"],
        "salario": draft.get("salario"),
        "salario_estimado": draft.get("salario_estimado"),
        "cidade": draft.get("cidade"),
        "estado": draft.get("estado"),
        "modalidade": draft.get("modalidade"),
        "data_publicacao": draft.get("data_publicacao"),
        "data_candidatura": None,
        "match_score": match_score,
        "probabilidade_estimada_entrevista": draft.get("probabilidade_estimada_entrevista"),
        "motivos_score": draft.get("motivos_score", []),
        "palavras_chave_encontradas": draft.get("palavras_chave_encontradas", []),
        "tecnologias_exigidas": draft.get("tecnologias_exigidas", []),
        "idiomas_exigidos": draft.get("idiomas_exigidos", []),
        "beneficios": draft.get("beneficios", []),
        "requisitos_obrigatorios": draft.get("requisitos_obrigatorios", []),
        "requisitos_desejaveis": draft.get("requisitos_desejaveis", []),
        "status": status_inicial,
        "empresa_favorita": draft["empresa"].strip().lower() in favoritas,
        "versao_curriculo": None,
        "versao_carta": None,
        "respostas_formulario": {},
        "historico_status": [{"status": status_inicial, "data": _now_iso()}],
    }

    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    job_path(ext_id).write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

    seen[ext_id] = {
        "empresa": job["empresa"],
        "plataforma": job["plataforma"],
        "registrado_em": _now_iso(),
    }
    save_seen_index(seen)

    print(f"Vaga registrada: {ext_id} ({job['empresa']} — {job['cargo']}) status={status_inicial}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="Verifica se uma vaga já foi vista")
    p_check.add_argument("--plataforma", required=True)
    p_check.add_argument("--ref", required=True, help="URL ou id da vaga na plataforma")
    p_check.set_defaults(func=cmd_check)

    p_write = sub.add_parser("write", help="Grava uma nova vaga a partir de um rascunho JSON")
    p_write.add_argument("--input", required=True, help="Caminho do JSON de rascunho da vaga")
    p_write.add_argument("--force", action="store_true", help="Grava mesmo se já vista (sobrescreve)")
    p_write.set_defaults(func=cmd_write)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
