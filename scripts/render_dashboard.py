#!/usr/bin/env python3
"""Gera dashboard/index.html a partir de data/jobs/*.json.

Uso:
    python scripts/render_dashboard.py
"""
from __future__ import annotations

import html
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from common import DATA_DIR, load_all_jobs, parse_salary_brl

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = ROOT / "dashboard"
DASHBOARD_PATH = DASHBOARD_DIR / "index.html"

KANBAN_COLUNAS = [
    ("Vagas Encontradas", lambda j: j["status"] in {"Encontrada", "Em análise"}),
    ("Excelentes Matches", lambda j: (j.get("match_score") or 0) >= 80),
    ("Aguardando Aprovação", lambda j: j["status"] == "Aguardando aprovação"),
    ("Candidaturas Enviadas", lambda j: j["status"] == "Candidatura enviada"),
    ("Entrevistas", lambda j: j["status"] == "Entrevista"),
    ("Rejeitadas", lambda j: j["status"] == "Rejeitado"),
    ("Ofertas", lambda j: j["status"] == "Aprovado"),
]

PLATAFORMA_SLOT = {
    "indeed": "--series-1",
    "linkedin": "--series-2",
    "gupy": "--series-3",
    "solides": "--series-4",
}
PLATAFORMA_FALLBACK_SLOT = "--series-5"

SALARY_BUCKETS = [
    (6000, 8000, "R$ 6-8k"),
    (8000, 10000, "R$ 8-10k"),
    (10000, 12000, "R$ 10-12k"),
    (12000, 15000, "R$ 12-15k"),
    (15000, float("inf"), "R$ 15k+"),
]


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _job_salary(job: dict) -> float | None:
    return parse_salary_brl(job.get("salario"), job.get("salario_estimado"))


def _salary_bucket(value: float) -> str:
    for low, high, label in SALARY_BUCKETS:
        if low <= value < high:
            return label
    return "Não informado"


def aggregate(jobs: list[dict]) -> dict:
    today = _today()
    week_ago = today - timedelta(days=6)

    encontradas_hoje = 0
    candidatadas_hoje = 0
    total_candidaturas = 0
    scores = []
    salarios = []
    por_cidade = Counter()
    por_empresa = Counter()
    por_plataforma = Counter()
    por_status = Counter()
    por_faixa_salarial = Counter()
    evolucao = {
        (week_ago + timedelta(days=i)).isoformat(): {"encontradas": 0, "candidatadas": 0}
        for i in range(7)
    }
    empresas_favoritas = set()

    for job in jobs:
        por_cidade[job.get("cidade") or "Não informado"] += 1
        por_empresa[job.get("empresa") or "Não informado"] += 1
        por_plataforma[job.get("plataforma") or "Não informado"] += 1
        por_status[job.get("status") or "Encontrada"] += 1
        if job.get("empresa_favorita"):
            empresas_favoritas.add(job.get("empresa"))

        score = job.get("match_score")
        if isinstance(score, (int, float)):
            scores.append(score)

        salario = _job_salary(job)
        if salario:
            salarios.append(salario)
            por_faixa_salarial[_salary_bucket(salario)] += 1

        for evento in job.get("historico_status", []):
            try:
                evento_data = evento["data"][:10]
            except (KeyError, TypeError):
                continue
            if evento_data not in evolucao:
                continue
            if evento["status"] == "Encontrada":
                evolucao[evento_data]["encontradas"] += 1
                if evento_data == today.isoformat():
                    encontradas_hoje += 1
            if evento["status"] == "Candidatura enviada":
                evolucao[evento_data]["candidatadas"] += 1
                if evento_data == today.isoformat():
                    candidatadas_hoje += 1

        if job.get("status") in {"Candidatura enviada", "Entrevista", "Aprovado", "Rejeitado"}:
            total_candidaturas += 1

    return {
        "encontradas_hoje": encontradas_hoje,
        "candidatadas_hoje": candidatadas_hoje,
        "total_candidaturas": total_candidaturas,
        "media_match_score": round(sum(scores) / len(scores), 1) if scores else None,
        "salario_medio": round(sum(salarios) / len(salarios)) if salarios else None,
        "por_cidade": por_cidade.most_common(),
        "por_empresa": por_empresa.most_common(8),
        "por_plataforma": por_plataforma.most_common(),
        "por_status": por_status.most_common(),
        "por_faixa_salarial": [
            (label, por_faixa_salarial.get(label, 0)) for _, _, label in SALARY_BUCKETS
        ],
        "evolucao_semanal": [(dia, v["encontradas"], v["candidatadas"]) for dia, v in sorted(evolucao.items())],
        "total_empresas_favoritas": len(empresas_favoritas),
        "total_vagas": len(jobs),
        "acoes_pendentes": pending_actions(jobs),
    }


def pending_actions(jobs: list[dict]) -> list[dict]:
    """Vagas que exigem uma ação da candidata agora, com o rótulo do que fazer."""
    acoes = []
    for job in jobs:
        if job.get("status") != "Aguardando aprovação":
            continue
        plataforma = (job.get("plataforma") or "").strip().lower()
        tem_pacote = bool(job.get("versao_curriculo")) and bool(job.get("versao_carta"))
        if plataforma == "indeed" and tem_pacote:
            tipo, label = "pronta", "Currículo e carta já prontos — revise e aprove o envio"
        elif plataforma == "indeed":
            tipo, label = "preparo_pendente", "Match bom, mas o preparo do currículo/carta ainda não foi concluído"
        else:
            tipo, label = "manual", f"Vaga em {job.get('plataforma') or 'outra plataforma'} — abra o link e candidate-se manualmente"
        acoes.append({**job, "_tipo_acao": tipo, "_label_acao": label})
    acoes.sort(key=lambda j: -(j.get("match_score") or 0))
    return acoes


# ---------------------------------------------------------------------------
# Renderização SVG (specs: barra <=24px, tampa arredondada 4px no fim do dado,
# reta na base; grid hairline; texto sempre em tinta, nunca na cor da série)
# ---------------------------------------------------------------------------

def _bar_path(x: float, y: float, w: float, h: float, r: float = 4) -> str:
    if w <= 0:
        w = 0.01
    r = min(r, w, h / 2)
    return (
        f"M{x:.1f},{y:.1f} H{x + w - r:.1f} "
        f"Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} "
        f"V{y + h - r:.1f} Q{x + w:.1f},{y + h:.1f} {x + w - r:.1f},{y + h:.1f} "
        f"H{x:.1f} Z"
    )


def horizontal_bar_chart(items: list[tuple[str, int]], color_of=None, width: int = 560) -> str:
    """Gráfico de barras horizontais. `color_of(label)` opcionalmente retorna uma var CSS por barra."""
    if not items:
        return '<p class="viz-empty">Sem dados ainda.</p>'

    label_w = 150
    right_pad = 48
    chart_w = width - label_w - right_pad
    bar_h = 20
    gap = 12
    row_h = bar_h + gap
    height = row_h * len(items) + gap
    max_val = max(v for _, v in items) or 1

    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="Gráfico de barras">']
    for i, (label, value) in enumerate(items):
        y = gap + i * row_h
        bar_w = (value / max_val) * chart_w
        color_var = color_of(label) if color_of else "--series-1"
        safe_label = html.escape(str(label))[:26]
        parts.append(
            f'<text x="{label_w - 8}" y="{y + bar_h / 2 + 4}" text-anchor="end" '
            f'class="viz-axis-label">{safe_label}</text>'
        )
        parts.append(
            f'<path d="{_bar_path(label_w, y, bar_w, bar_h)}" fill="var({color_var})">'
            f'<title>{safe_label}: {value}</title></path>'
        )
        parts.append(
            f'<text x="{label_w + bar_w + 8}" y="{y + bar_h / 2 + 4}" class="viz-value-label">{value}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def weekly_line_chart(evolucao: list[tuple[str, int, int]], width: int = 560, height: int = 220) -> str:
    if not evolucao:
        return '<p class="viz-empty">Sem dados ainda.</p>'

    pad_left, pad_right, pad_top, pad_bottom = 36, 16, 16, 28
    chart_w = width - pad_left - pad_right
    chart_h = height - pad_top - pad_bottom
    max_val = max(1, max(max(e, c) for _, e, c in evolucao))
    n = len(evolucao)
    step_x = chart_w / max(1, n - 1)

    def points(idx: int) -> str:
        pts = []
        for i, row in enumerate(evolucao):
            val = row[idx]
            x = pad_left + i * step_x
            y = pad_top + chart_h - (val / max_val) * chart_h
            pts.append(f"{x:.1f},{y:.1f}")
        return " ".join(pts)

    def dots(idx: int, color_var: str) -> str:
        out = []
        for i, row in enumerate(evolucao):
            val = row[idx]
            x = pad_left + i * step_x
            y = pad_top + chart_h - (val / max_val) * chart_h
            out.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="var({color_var})" '
                f'stroke="var(--surface-1)" stroke-width="2"><title>{row[0]}: {val}</title></circle>'
            )
        return "".join(out)

    gridlines = "".join(
        f'<line x1="{pad_left}" x2="{width - pad_right}" y1="{pad_top + chart_h * f:.1f}" '
        f'y2="{pad_top + chart_h * f:.1f}" class="viz-grid" />'
        for f in (0, 0.5, 1)
    )
    day_labels = "".join(
        f'<text x="{pad_left + i * step_x:.1f}" y="{height - 6}" text-anchor="middle" '
        f'class="viz-axis-label">{row[0][5:]}</text>'
        for i, row in enumerate(evolucao)
    )

    return f"""
    <svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="Evolução semanal">
      {gridlines}
      <polyline points="{points(1)}" fill="none" stroke="var(--series-1)" stroke-width="2"
                stroke-linejoin="round" stroke-linecap="round" />
      <polyline points="{points(2)}" fill="none" stroke="var(--series-2)" stroke-width="2"
                stroke-linejoin="round" stroke-linecap="round" />
      {dots(1, "--series-1")}
      {dots(2, "--series-2")}
      {day_labels}
    </svg>
    <div class="viz-legend">
      <span class="viz-legend-item"><i style="background:var(--series-1)"></i>Encontradas</span>
      <span class="viz-legend-item"><i style="background:var(--series-2)"></i>Candidatadas</span>
    </div>
    """


def _table_fallback(items: list[tuple[str, int]]) -> str:
    rows = "".join(f"<tr><td>{html.escape(str(l))}</td><td>{v}</td></tr>" for l, v in items)
    return f'<details class="viz-table"><summary>Ver como tabela</summary><table><tbody>{rows}</tbody></table></details>'


def _kpi_card(label: str, value: str) -> str:
    return f'<div class="kpi-card"><span class="kpi-value">{value}</span><span class="kpi-label">{label}</span></div>'


_ACAO_BADGE = {
    "pronta": ("action-badge--ready", "Pronta para aprovar"),
    "preparo_pendente": ("action-badge--warning", "Preparo pendente"),
    "manual": ("action-badge--manual", "Candidatura manual"),
}


def _action_card(item: dict) -> str:
    score = item.get("match_score")
    score_txt = f"{score}% match" if isinstance(score, (int, float)) else "—"
    badge_class, badge_text = _ACAO_BADGE[item["_tipo_acao"]]
    link = item.get("url") or "#"
    return f"""
    <div class="action-card">
      <div class="action-card-top">
        <span class="action-badge {badge_class}">{badge_text}</span>
        <span class="action-score">{score_txt}</span>
      </div>
      <strong class="action-cargo">{html.escape(item.get('cargo') or '')}</strong>
      <span class="action-empresa">{html.escape(item.get('empresa') or '')}{' ★' if item.get('empresa_favorita') else ''} · {html.escape(item.get('cidade') or 'remoto')}</span>
      <p class="action-label">{html.escape(item['_label_acao'])}</p>
      <a class="action-link" href="{html.escape(link)}" target="_blank" rel="noopener">Ver vaga →</a>
    </div>
    """


def render_actions_section(acoes: list[dict]) -> str:
    if not acoes:
        return (
            '<section class="actions-section"><h2>Ações pendentes</h2>'
            '<p class="viz-empty">Nada esperando sua aprovação agora.</p></section>'
        )
    cards = "".join(_action_card(a) for a in acoes)
    return f"""
    <section class="actions-section">
      <h2>Ações pendentes <span class="actions-count">{len(acoes)}</span></h2>
      <div class="actions-grid">{cards}</div>
    </section>
    """


def _job_card(job: dict) -> str:
    score = job.get("match_score")
    score_txt = f"{score}%" if isinstance(score, (int, float)) else "—"
    destaque = " job-card--favorita" if job.get("empresa_favorita") else ""
    salario = job.get("salario") or (f'~{job.get("salario_estimado")}' if job.get("salario_estimado") else "não informado")
    link = job.get("url") or "#"
    return f"""
    <a class="job-card{destaque}" href="{html.escape(link)}" target="_blank" rel="noopener">
      <div class="job-card-top">
        <span class="job-card-score">{score_txt}</span>
        <span class="job-card-plataforma">{html.escape(job.get('plataforma', ''))}</span>
      </div>
      <strong class="job-card-cargo">{html.escape(job.get('cargo', ''))}</strong>
      <span class="job-card-empresa">{html.escape(job.get('empresa', ''))}{' ★' if job.get('empresa_favorita') else ''}</span>
      <span class="job-card-local">{html.escape(job.get('cidade') or '')} · {html.escape(job.get('modalidade') or '')}</span>
      <span class="job-card-salario">{html.escape(str(salario))}</span>
    </a>
    """


def render_html(jobs: list[dict], stats: dict) -> str:
    kpis = "".join([
        _kpi_card("Vagas encontradas hoje", str(stats["encontradas_hoje"])),
        _kpi_card("Candidatadas hoje", str(stats["candidatadas_hoje"])),
        _kpi_card("Total de candidaturas", str(stats["total_candidaturas"])),
        _kpi_card("Média de Match Score", f'{stats["media_match_score"]}%' if stats["media_match_score"] is not None else "—"),
        _kpi_card("Salário médio", f'R$ {stats["salario_medio"]:,}'.replace(",", ".") if stats["salario_medio"] else "—"),
        _kpi_card("Empresas favoritas com vaga", str(stats["total_empresas_favoritas"])),
    ])

    def plataforma_color(label: str) -> str:
        return PLATAFORMA_SLOT.get(str(label).strip().lower(), PLATAFORMA_FALLBACK_SLOT)

    chart_cidade = horizontal_bar_chart(stats["por_cidade"])
    chart_empresa = horizontal_bar_chart(stats["por_empresa"])
    chart_plataforma = horizontal_bar_chart(stats["por_plataforma"], color_of=plataforma_color)
    chart_status = horizontal_bar_chart(stats["por_status"])
    chart_faixa = horizontal_bar_chart(stats["por_faixa_salarial"])
    chart_evolucao = weekly_line_chart(stats["evolucao_semanal"])

    kanban_cols = ""
    for titulo, filtro in KANBAN_COLUNAS:
        col_jobs = [j for j in jobs if filtro(j)]
        cards = "".join(_job_card(j) for j in sorted(col_jobs, key=lambda j: -(j.get("match_score") or 0)))
        kanban_cols += f"""
        <div class="kanban-col">
          <header class="kanban-col-header">{titulo} <span class="kanban-count">{len(col_jobs)}</span></header>
          <div class="kanban-col-body">{cards or '<p class="viz-empty">Vazio</p>'}</div>
        </div>
        """

    gerado_em = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Career Agent — painel de recolocação</title>
<style>
  :root {{
    color-scheme: light;
    --page-plane:     #f9f9f7;
    --surface-1:      #fcfcfb;
    --text-primary:   #0b0b0b;
    --text-secondary: #52514e;
    --text-muted:     #898781;
    --grid:           #e1e0d9;
    --border:         rgba(11,11,11,0.10);
    --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a;
    --series-4: #eda100; --series-5: #e87ba4; --series-6: #4a3aa7;
    --status-good-text: #0ca30c;
    --status-warning-bg: rgba(250,178,25,0.18);
    --status-warning-text: #a66b00;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:where(:not([data-theme="light"])) {{
      color-scheme: dark;
      --page-plane:     #0d0d0d;
      --surface-1:      #1a1a19;
      --text-primary:   #ffffff;
      --text-secondary: #c3c2b7;
      --text-muted:     #898781;
      --grid:           #2c2c2a;
      --border:         rgba(255,255,255,0.10);
      --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70;
      --series-4: #c98500; --series-5: #d55181; --series-6: #9085e9;
      --status-good-text: #0ca30c;
      --status-warning-bg: rgba(250,178,25,0.22);
      --status-warning-text: #fab219;
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --page-plane:     #0d0d0d;
    --surface-1:      #1a1a19;
    --text-primary:   #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted:     #898781;
    --grid:           #2c2c2a;
    --border:         rgba(255,255,255,0.10);
    --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70;
    --series-4: #c98500; --series-5: #d55181; --series-6: #9085e9;
    --status-good-text: #0ca30c;
    --status-warning-bg: rgba(250,178,25,0.22);
    --status-warning-text: #fab219;
  }}

  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--page-plane); color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 32px clamp(16px, 4vw, 48px) 64px;
  }}
  header.page-header {{ margin-bottom: 32px; }}
  header.page-header h1 {{
    font-size: clamp(28px, 4vw, 40px); font-weight: 700; letter-spacing: -0.02em; margin: 0 0 4px;
  }}
  header.page-header p {{ color: var(--text-secondary); margin: 0; font-size: 14px; }}

  .kpi-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px; margin-bottom: 40px;
  }}
  .kpi-card {{
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px;
    padding: 16px 18px; display: flex; flex-direction: column; gap: 4px;
  }}
  .kpi-value {{ font-size: 28px; font-weight: 700; }}
  .kpi-label {{ font-size: 13px; color: var(--text-secondary); }}

  section {{ margin-bottom: 48px; }}
  section > h2 {{ font-size: 18px; font-weight: 600; margin: 0 0 16px; }}

  .actions-section {{
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 14px;
    padding: 20px 22px; margin-bottom: 40px;
  }}
  .actions-section h2 {{ font-size: 18px; font-weight: 600; margin: 0 0 16px; display: flex; align-items: center; gap: 8px; }}
  .actions-count {{
    font-size: 12px; font-weight: 700; background: var(--series-1); color: white;
    border-radius: 999px; padding: 2px 9px;
  }}
  .actions-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; }}
  .action-card {{
    background: var(--page-plane); border: 1px solid var(--border); border-radius: 12px;
    padding: 14px 16px; display: flex; flex-direction: column; gap: 4px; font-size: 13px;
  }}
  .action-card-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px; }}
  .action-badge {{ font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 999px; }}
  .action-badge--ready {{ background: rgba(12,163,12,0.15); color: var(--status-good-text); }}
  .action-badge--warning {{ background: var(--status-warning-bg); color: var(--status-warning-text); }}
  .action-badge--manual {{ background: rgba(137,135,129,0.18); color: var(--text-secondary); }}
  .action-score {{ font-size: 12px; color: var(--text-muted); font-weight: 600; }}
  .action-cargo {{ font-size: 14px; }}
  .action-empresa {{ color: var(--text-secondary); font-size: 12px; }}
  .action-label {{ color: var(--text-secondary); font-size: 12px; margin: 4px 0 2px; }}
  .action-link {{ font-size: 12px; font-weight: 600; color: var(--series-1); text-decoration: none; }}
  .action-link:hover {{ text-decoration: underline; }}

  .charts-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 24px; }}
  .chart-card {{
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 20px;
  }}
  .chart-card h3 {{ font-size: 14px; font-weight: 600; margin: 0 0 12px; color: var(--text-secondary); }}
  .viz-axis-label {{ fill: var(--text-muted); font-size: 11px; }}
  .viz-value-label {{ fill: var(--text-secondary); font-size: 11px; }}
  .viz-grid {{ stroke: var(--grid); stroke-width: 1; }}
  .viz-empty {{ color: var(--text-muted); font-size: 13px; }}
  .viz-legend {{ display: flex; gap: 16px; margin-top: 8px; font-size: 12px; color: var(--text-secondary); }}
  .viz-legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .viz-legend-item i {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}
  .viz-table {{ margin-top: 8px; font-size: 12px; color: var(--text-secondary); }}
  .viz-table table {{ width: 100%; border-collapse: collapse; margin-top: 6px; }}
  .viz-table td {{ padding: 4px 8px; border-bottom: 1px solid var(--border); }}

  .kanban {{ display: grid; grid-auto-flow: column; grid-auto-columns: minmax(220px, 1fr); gap: 16px; overflow-x: auto; padding-bottom: 8px; }}
  .kanban-col {{ background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; display: flex; flex-direction: column; min-height: 120px; }}
  .kanban-col-header {{
    padding: 12px 14px; font-size: 13px; font-weight: 600; border-bottom: 1px solid var(--border);
    display: flex; justify-content: space-between; align-items: center;
  }}
  .kanban-count {{ color: var(--text-muted); font-weight: 400; }}
  .kanban-col-body {{ padding: 10px; display: flex; flex-direction: column; gap: 8px; overflow-y: auto; max-height: 480px; }}

  .job-card {{
    display: flex; flex-direction: column; gap: 2px; text-decoration: none; color: inherit;
    background: var(--page-plane); border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px;
    font-size: 12px;
  }}
  .job-card--favorita {{ border-color: var(--series-4); }}
  .job-card-top {{ display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted); margin-bottom: 2px; }}
  .job-card-score {{ font-weight: 700; color: var(--text-primary); }}
  .job-card-cargo {{ font-size: 13px; }}
  .job-card-empresa {{ color: var(--text-secondary); }}
  .job-card-local, .job-card-salario {{ color: var(--text-muted); font-size: 11px; }}

  footer {{ color: var(--text-muted); font-size: 12px; margin-top: 32px; }}
</style>
</head>
<body>
  <header class="page-header">
    <h1>Painel de recolocação</h1>
    <p>Gerado em {gerado_em} · {stats["total_vagas"]} vagas no histórico</p>
  </header>

  <div class="kpi-grid">{kpis}</div>

  {render_actions_section(stats["acoes_pendentes"])}

  <section>
    <h2>Quadro Kanban</h2>
    <div class="kanban">{kanban_cols}</div>
  </section>

  <section>
    <h2>Análises</h2>
    <div class="charts-grid">
      <div class="chart-card"><h3>Por cidade</h3>{chart_cidade}{_table_fallback(stats["por_cidade"])}</div>
      <div class="chart-card"><h3>Por empresa (top 8)</h3>{chart_empresa}{_table_fallback(stats["por_empresa"])}</div>
      <div class="chart-card"><h3>Por plataforma</h3>{chart_plataforma}{_table_fallback(stats["por_plataforma"])}</div>
      <div class="chart-card"><h3>Por status</h3>{chart_status}{_table_fallback(stats["por_status"])}</div>
      <div class="chart-card"><h3>Por faixa salarial</h3>{chart_faixa}{_table_fallback(stats["por_faixa_salarial"])}</div>
      <div class="chart-card"><h3>Evolução semanal</h3>{chart_evolucao}</div>
    </div>
  </section>

  <footer>Career Agent AI — busca automática (Indeed) + listagem pública (LinkedIn/Gupy/Sólides/carreiras). Candidaturas sempre passam por aprovação manual antes do envio.</footer>
</body>
</html>
"""


def main() -> int:
    jobs = load_all_jobs()
    stats = aggregate(jobs)
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARD_PATH.write_text(render_html(jobs, stats), encoding="utf-8")
    print(f"Dashboard gerado em {DASHBOARD_PATH} ({len(jobs)} vagas).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
