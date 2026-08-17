"""Integração com Google Sheets via gspread + oauth2client.

Credenciais (nessa ordem de prioridade):
1. Variável de ambiente GOOGLE_CREDENTIALS com o conteúdo JSON da service account
   (é assim que roda no GitHub Actions — secret do repositório).
2. Arquivo local `google_credentials.json` na raiz do projeto (uso local; está no
   .gitignore, nunca é commitado).

Se nenhuma das duas existir, ou se `spreadsheet_id` não estiver configurado em
agent/config/search_criteria.yaml (seção google_sheets), a sincronização é pulada
silenciosamente (log de aviso) — isso nunca deve impedir o resto da rotina de rodar.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("career_agent.sheets_sync")

ROOT = Path(__file__).resolve().parent.parent
LOCAL_CREDENTIALS_PATH = ROOT / "google_credentials.json"

SHEET_COLUMNS = [
    "Data Coleta",
    "Cargo",
    "Empresa",
    "Local/Modalidade",
    "Salário",
    "Match/Pontuação",
    "Link da Vaga",
    "Status",
]

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


def _load_credentials_dict() -> dict | None:
    env_value = os.environ.get("GOOGLE_CREDENTIALS")
    if env_value:
        try:
            return json.loads(env_value)
        except json.JSONDecodeError:
            logger.warning("GOOGLE_CREDENTIALS não é um JSON válido — pulando Sheets")
            return None
    if LOCAL_CREDENTIALS_PATH.exists():
        try:
            return json.loads(LOCAL_CREDENTIALS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("%s não é um JSON válido — pulando Sheets", LOCAL_CREDENTIALS_PATH)
            return None
    return None


def _open_worksheet(spreadsheet_id: str, worksheet_name: str | None):
    try:
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials
    except ImportError:
        logger.warning("gspread/oauth2client não instalados — pulando Sheets")
        return None

    creds_dict = _load_credentials_dict()
    if not creds_dict:
        logger.warning("Sem credenciais do Google (GOOGLE_CREDENTIALS ou google_credentials.json) — pulando Sheets")
        return None

    try:
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPES)
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(spreadsheet_id)
        return spreadsheet.worksheet(worksheet_name) if worksheet_name else spreadsheet.sheet1
    except Exception as exc:
        logger.warning("Falha ao abrir a planilha do Google Sheets: %s", exc)
        return None


def _row_for_job(job: dict) -> list[str]:
    local = job.get("cidade") or ""
    modalidade = job.get("modalidade") or ""
    local_modalidade = f"{local} ({modalidade})".strip() if modalidade else local
    salario = job.get("salario") or job.get("salario_estimado") or "Não informado"
    sheet_status = "Candidatado" if job.get("status") in {
        "Candidatura enviada", "Aguardando retorno", "Entrevista", "Em fase de testes", "Aprovado", "Retorno negativo",
    } else "Aprovação Pendente"

    return [
        job.get("data_publicacao") or "",
        job.get("cargo") or "",
        job.get("empresa") or "",
        local_modalidade,
        str(salario),
        str(job.get("match_score", "")),
        job.get("url") or "",
        sheet_status,
    ]


def sync_new_jobs(jobs: list[dict], config: dict) -> int:
    """Insere no Sheets as vagas passadas (já filtradas pelo runner — normalmente só
    as que chegaram a 'Aguardando aprovação'). Retorna quantas linhas foram inseridas."""
    sheets_config = config.get("google_sheets", {})
    spreadsheet_id = sheets_config.get("spreadsheet_id") or os.environ.get("GOOGLE_SHEET_ID")
    if not spreadsheet_id:
        logger.info("google_sheets.spreadsheet_id não configurado — pulando sincronização")
        return 0
    if not jobs:
        return 0

    worksheet = _open_worksheet(spreadsheet_id, sheets_config.get("worksheet_name"))
    if worksheet is None:
        return 0

    try:
        existing_header = worksheet.row_values(1)
        if existing_header != SHEET_COLUMNS:
            worksheet.update("A1", [SHEET_COLUMNS])
        rows = [_row_for_job(job) for job in jobs]
        worksheet.append_rows(rows, value_input_option="USER_ENTERED")
        return len(rows)
    except Exception as exc:
        logger.warning("Falha ao gravar no Google Sheets: %s", exc)
        return 0
