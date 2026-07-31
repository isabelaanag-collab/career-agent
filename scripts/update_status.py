#!/usr/bin/env python3
"""Transição de status de uma vaga (fluxo local de aprovação/candidatura).

Uso:
    python scripts/update_status.py <id_externo> "<Novo Status>" \
        [--curriculo caminho] [--carta caminho] [--resposta "pergunta=resposta"]...

Nunca edite os JSONs de vaga à mão — este script mantém o historico_status
e o applications_log.jsonl consistentes, e impede candidatura duplicada.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from common import (
    APPLICATIONS_LOG_PATH,
    STATUS_JA_CANDIDATADA,
    STATUS_ORDER,
    job_path,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("id_externo")
    parser.add_argument("novo_status", choices=STATUS_ORDER)
    parser.add_argument("--curriculo", help="Caminho do arquivo de currículo adaptado usado")
    parser.add_argument("--carta", help="Caminho do arquivo da carta de apresentação usada")
    parser.add_argument(
        "--resposta",
        action="append",
        default=[],
        help='Resposta enviada no formulário, formato "pergunta=resposta" (pode repetir)',
    )
    args = parser.parse_args()

    path = job_path(args.id_externo)
    if not path.exists():
        print(f"Vaga não encontrada: {args.id_externo}", file=sys.stderr)
        return 2

    job = json.loads(path.read_text(encoding="utf-8"))
    status_atual = job.get("status")

    if args.novo_status == "Candidatura enviada" and status_atual in STATUS_JA_CANDIDATADA:
        print(
            f"Vaga {args.id_externo} já está em '{status_atual}' — não candidatar de novo.",
            file=sys.stderr,
        )
        return 3

    job["status"] = args.novo_status
    job.setdefault("historico_status", []).append({"status": args.novo_status, "data": _now_iso()})

    if args.curriculo:
        job["versao_curriculo"] = args.curriculo
    if args.carta:
        job["versao_carta"] = args.carta
    for resposta in args.resposta:
        if "=" not in resposta:
            print(f"Ignorando --resposta mal formatada: {resposta!r}", file=sys.stderr)
            continue
        pergunta, valor = resposta.split("=", 1)
        job.setdefault("respostas_formulario", {})[pergunta.strip()] = valor.strip()

    if args.novo_status == "Candidatura enviada":
        job["data_candidatura"] = datetime.now(timezone.utc).date().isoformat()

    path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.novo_status == "Candidatura enviada":
        APPLICATIONS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "data_hora": _now_iso(),
            "id_externo": args.id_externo,
            "empresa": job.get("empresa"),
            "plataforma": job.get("plataforma"),
            "versao_curriculo": job.get("versao_curriculo"),
            "versao_carta": job.get("versao_carta"),
            "respostas_formulario": job.get("respostas_formulario", {}),
        }
        with APPLICATIONS_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"Vaga {args.id_externo}: {status_atual!r} -> {args.novo_status!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
