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

from common import (
    DATA_DIR,
    DEFAULT_LIMIAR_APROVACAO,
    STATUS_JA_CANDIDATADA,
    STATUS_ORDER,
    STATUS_POS_CANDIDATURA,
    load_all_jobs,
    load_config,
    parse_salary_brl,
)

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = ROOT / "dashboard"
DASHBOARD_PATH = DASHBOARD_DIR / "index.html"

BRASILIA_TZ = timezone(timedelta(hours=-3))  # Brasília não usa horário de verão desde 2019

BUSCAR_AGORA_TEXTO = (
    "Rode uma busca agora no Career Agent AI, sem esperar a próxima execução agendada da rotina "
    "em nuvem (rotina \"career-agent-busca-vagas\") — dispare a rotina via RemoteTrigger "
    "(action: run) ou, se preferir, execute a lógica de "
    "agent/prompts/routine_search_and_score.md diretamente nesta sessão local."
)

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

        if job.get("status") in STATUS_JA_CANDIDATADA:
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
    id_externo = item.get("id_externo") or ""
    cargo = item.get("cargo") or ""
    empresa = item.get("empresa") or ""
    vaga_desc = f"{cargo} na {empresa}".strip()

    aprovar_texto = (
        f"Aprovar e processar o envio da candidatura para a vaga {id_externo} ({vaga_desc}) — "
        f"pode preencher o formulário no Indeed, mas pare antes do envio final esperando minha confirmação."
    )
    reprovar_texto = (
        f"Reprovar a vaga {id_externo} ({vaga_desc}) — marcar como Rejeitado, não candidatar."
    )
    ja_candidatei_texto = (
        f"Marcar a vaga {id_externo} ({vaga_desc}) como Candidatura enviada — já me candidatei "
        f"manualmente pelo link (rode scripts/update_status.py {id_externo} \"Candidatura enviada\")."
    )

    botoes = (
        f'<button type="button" class="action-btn action-btn--reject" data-copy="{html.escape(reprovar_texto)}">✕ Reprovar</button>'
        f'<button type="button" class="action-btn action-btn--applied" data-copy="{html.escape(ja_candidatei_texto)}">✓ Já me candidatei</button>'
    )
    if item["_tipo_acao"] == "pronta":
        botoes = (
            f'<button type="button" class="action-btn action-btn--approve" data-copy="{html.escape(aprovar_texto)}">✓ Aprovar</button>'
            + botoes
        )

    return f"""
    <div class="action-card">
      <div class="action-card-top">
        <span class="action-badge {badge_class}">{badge_text}</span>
        <span class="action-score">{score_txt}</span>
      </div>
      <strong class="action-cargo">{html.escape(cargo)}</strong>
      <span class="action-empresa">{html.escape(empresa)}{' ★' if item.get('empresa_favorita') else ''} · {html.escape(item.get('cidade') or 'remoto')}</span>
      <p class="action-label">{html.escape(item['_label_acao'])}</p>
      <a class="action-link" href="{html.escape(link)}" target="_blank" rel="noopener">Ver vaga →</a>
      <div class="action-buttons">{botoes}</div>
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


_STATUS_BADGE = {
    "Encontrada": "status-badge--neutro",
    "Em análise": "status-badge--neutro",
    "Currículo otimizado": "status-badge--preparo",
    "Carta criada": "status-badge--preparo",
    "Aguardando aprovação": "status-badge--preparo",
    "Rejeitado": "status-badge--negativo",
    "Candidatura enviada": "status-badge--enviada",
    "Aguardando retorno": "status-badge--espera",
    "Entrevista": "status-badge--entrevista",
    "Em fase de testes": "status-badge--entrevista",
    "Aprovado": "status-badge--aprovado",
    "Retorno negativo": "status-badge--negativo",
}


def _job_card(job: dict) -> str:
    score = job.get("match_score")
    score_txt = f"{score}%" if isinstance(score, (int, float)) else "—"
    destaque = " job-card--favorita" if job.get("empresa_favorita") else ""
    salario = job.get("salario") or (f'~{job.get("salario_estimado")}' if job.get("salario_estimado") else "não informado")
    link = job.get("url") or "#"
    status = job.get("status") or "Encontrada"
    status_class = _STATUS_BADGE.get(status, "status-badge--neutro")
    return f"""
    <a class="job-card{destaque}" data-status="{html.escape(status)}" href="{html.escape(link)}" target="_blank" rel="noopener">
      <div class="job-card-top">
        <span class="job-card-score">{score_txt}</span>
        <span class="job-card-plataforma">{html.escape(job.get('plataforma', ''))}</span>
      </div>
      <strong class="job-card-cargo">{html.escape(job.get('cargo', ''))}</strong>
      <span class="job-card-empresa">{html.escape(job.get('empresa', ''))}{' ★' if job.get('empresa_favorita') else ''}</span>
      <span class="job-card-local">{html.escape(job.get('cidade') or '')} · {html.escape(job.get('modalidade') or '')}</span>
      <span class="job-card-salario">{html.escape(str(salario))}</span>
      <span class="status-badge {status_class}">{html.escape(status)}</span>
    </a>
    """


def render_all_jobs_section(jobs: list[dict]) -> str:
    """Grade única de vagas com filtro por status (substitui o quadro Kanban)."""
    status_presentes = [s for s in STATUS_ORDER if any((j.get("status") or "Encontrada") == s for j in jobs)]
    pills = ['<button type="button" class="filter-pill active" data-status="__all__">Todas <span>' + str(len(jobs)) + '</span></button>']
    for s in status_presentes:
        count = sum(1 for j in jobs if (j.get("status") or "Encontrada") == s)
        pills.append(
            f'<button type="button" class="filter-pill" data-status="{html.escape(s)}">{html.escape(s)} <span>{count}</span></button>'
        )
    cards = "".join(_job_card(j) for j in sorted(jobs, key=lambda j: -(j.get("match_score") or 0)))
    return f"""
    <div class="jobs-filter">{''.join(pills)}</div>
    <div class="jobs-grid" id="all-jobs-grid">{cards or '<p class="viz-empty">Nenhuma vaga ainda.</p>'}</div>
    """


def _application_card(job: dict) -> str:
    status = job.get("status") or ""
    status_class = _STATUS_BADGE.get(status, "status-badge--neutro")
    cargo = job.get("cargo") or ""
    empresa = job.get("empresa") or ""
    id_externo = job.get("id_externo") or ""
    salario = job.get("salario") or (f'~{job.get("salario_estimado")}' if job.get("salario_estimado") else "não informado")
    data_candidatura = job.get("data_candidatura") or "—"
    link = job.get("url") or "#"

    botoes = []
    for novo_status in STATUS_POS_CANDIDATURA:
        if novo_status == status:
            continue
        texto = (
            f'Atualizar o status da vaga {id_externo} ({cargo} na {empresa}) para "{novo_status}" '
            f'(rode scripts/update_status.py {id_externo} "{novo_status}").'
        )
        extra_cls = (
            " app-status-btn--negativo" if novo_status == "Retorno negativo"
            else " app-status-btn--positivo" if novo_status == "Aprovado"
            else ""
        )
        botoes.append(
            f'<button type="button" class="app-status-btn{extra_cls}" data-copy="{html.escape(texto)}">{html.escape(novo_status)}</button>'
        )

    return f"""
    <div class="application-card">
      <div class="action-card-top">
        <span class="status-badge {status_class}">{html.escape(status)}</span>
        <span class="application-date">Candidatou em {html.escape(str(data_candidatura))}</span>
      </div>
      <strong class="action-cargo">{html.escape(cargo)}</strong>
      <span class="action-empresa">{html.escape(empresa)}{' ★' if job.get('empresa_favorita') else ''} · {html.escape(job.get('cidade') or 'remoto')}</span>
      <span class="job-card-salario">{html.escape(str(salario))}</span>
      <a class="action-link" href="{html.escape(link)}" target="_blank" rel="noopener">Ver vaga →</a>
      <div class="application-buttons">{''.join(botoes)}</div>
    </div>
    """


def render_applications_section(jobs: list[dict]) -> str:
    candidaturas = [j for j in jobs if j.get("status") in STATUS_JA_CANDIDATADA]
    if not candidaturas:
        return '<p class="viz-empty">Nenhuma candidatura enviada ainda.</p>'
    candidaturas.sort(key=lambda j: j.get("data_candidatura") or "", reverse=True)
    cards = "".join(_application_card(j) for j in candidaturas)
    return f'<div class="actions-grid">{cards}</div>'


def render_comparison_section(jobs: list[dict], pretensao: float | None) -> str:
    pretensao_txt = f'R$ {pretensao:,.0f}'.replace(",", ".") if pretensao else "não definida"
    comparaveis = [
        j for j in jobs
        if (j.get("match_score") or 0) >= DEFAULT_LIMIAR_APROVACAO or j.get("status") in STATUS_JA_CANDIDATADA
    ]

    def sort_key(j: dict) -> tuple:
        salario = _job_salary(j)
        return (salario is None, -(salario or 0))

    comparaveis.sort(key=sort_key)

    rows = []
    for j in comparaveis:
        salario = j.get("salario") or (f'~{j.get("salario_estimado")}' if j.get("salario_estimado") else "não informado")
        beneficios = j.get("beneficios") or []
        chips = "".join(f'<span class="benefit-chip">{html.escape(b)}</span>' for b in beneficios) or '<span class="viz-empty">—</span>'
        status = j.get("status") or "Encontrada"
        status_class = _STATUS_BADGE.get(status, "status-badge--neutro")
        rows.append(f"""
        <tr>
          <td><strong>{html.escape(j.get('cargo') or '')}</strong><br><span class="text-muted">{html.escape(j.get('empresa') or '')}{' ★' if j.get('empresa_favorita') else ''}</span></td>
          <td>{html.escape(str(salario))}</td>
          <td class="benefits-cell">{chips}</td>
          <td>{html.escape(j.get('modalidade') or '')}</td>
          <td><span class="status-badge {status_class}">{html.escape(status)}</span></td>
        </tr>
        """)

    if not comparaveis:
        table_html = '<p class="viz-empty">Nenhuma vaga com match alto ou candidatura ainda para comparar.</p>'
    else:
        table_html = f"""
        <div class="compare-table-wrap">
          <table class="compare-table">
            <thead><tr><th>Vaga</th><th>Salário</th><th>Benefícios</th><th>Modalidade</th><th>Status</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </div>
        """

    return f"""
    <div class="pretensao-banner">
      <span class="pretensao-label">Sua pretensão salarial (piso mínimo aceito)</span>
      <span class="pretensao-value">{pretensao_txt}</span>
      <span class="pretensao-hint">Editável em <code>agent/config/search_criteria.yaml</code>, campo <code>salario_minimo_brl</code></span>
    </div>
    {table_html}
    """


def render_html(jobs: list[dict], stats: dict, pretensao_salarial: float | None) -> str:
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

    all_jobs_section = render_all_jobs_section(jobs)
    applications_section = render_applications_section(jobs)
    comparison_section = render_comparison_section(jobs, pretensao_salarial)

    gerado_em = datetime.now(BRASILIA_TZ).strftime("%d/%m/%Y %H:%M")

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
    --status-critical-text: #d03b3b;
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
      --status-critical-text: #d03b3b;
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
    --status-critical-text: #d03b3b;
  }}

  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--page-plane); color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 32px clamp(16px, 4vw, 48px) 64px;
  }}
  header.page-header {{ margin-bottom: 32px; }}
  .page-header-top {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; flex-wrap: wrap; }}
  header.page-header h1 {{
    font-size: clamp(28px, 4vw, 40px); font-weight: 700; letter-spacing: -0.02em; margin: 0 0 4px;
  }}
  header.page-header p {{ color: var(--text-secondary); margin: 0; font-size: 14px; }}
  .header-actions {{ display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }}
  .action-btn--primary {{
    background: var(--series-1); border-color: var(--series-1); color: white; padding: 8px 14px; white-space: nowrap;
  }}
  .last-update {{ color: var(--text-muted); font-size: 12px; white-space: nowrap; }}

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
  .action-buttons {{ display: flex; gap: 8px; margin-top: 8px; }}
  .action-btn {{
    font: inherit; font-size: 12px; font-weight: 600; cursor: pointer; border-radius: 8px;
    padding: 6px 10px; border: 1px solid var(--border); background: var(--surface-1); color: var(--text-primary);
  }}
  .action-btn--approve {{ border-color: var(--status-good-text); color: var(--status-good-text); }}
  .action-btn--reject {{ border-color: var(--status-critical-text); color: var(--status-critical-text); }}
  .action-btn--applied {{ border-color: var(--series-1); color: var(--series-1); }}
  .action-btn:hover {{ filter: brightness(1.15); }}
  .action-btn:active {{ filter: brightness(0.9); }}

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

  .tabs {{ display: flex; gap: 6px; border-bottom: 1px solid var(--border); margin-bottom: 24px; flex-wrap: wrap; }}
  .tab-btn {{
    font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; color: var(--text-secondary);
    background: none; border: none; border-bottom: 2px solid transparent; padding: 10px 4px; margin-bottom: -1px;
  }}
  .tab-btn:hover {{ color: var(--text-primary); }}
  .tab-btn.active {{ color: var(--text-primary); border-bottom-color: var(--series-1); }}
  .tab-panel {{ display: none; }}
  .tab-panel.active {{ display: block; }}
  .tab-hint {{ color: var(--text-muted); font-size: 12px; margin: -8px 0 16px; }}

  .jobs-filter {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }}
  .filter-pill {{
    font: inherit; font-size: 12px; font-weight: 600; cursor: pointer; border-radius: 999px;
    padding: 6px 12px; border: 1px solid var(--border); background: var(--surface-1); color: var(--text-secondary);
  }}
  .filter-pill span {{ color: var(--text-muted); font-weight: 400; }}
  .filter-pill:hover {{ color: var(--text-primary); }}
  .filter-pill.active {{ background: var(--series-1); border-color: var(--series-1); color: white; }}
  .filter-pill.active span {{ color: rgba(255,255,255,0.8); }}
  .jobs-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }}

  .application-card {{
    background: var(--page-plane); border: 1px solid var(--border); border-radius: 12px;
    padding: 14px 16px; display: flex; flex-direction: column; gap: 4px; font-size: 13px;
  }}
  .application-date {{ font-size: 11px; color: var(--text-muted); }}
  .application-buttons {{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }}
  .app-status-btn {{
    font: inherit; font-size: 11px; font-weight: 600; cursor: pointer; border-radius: 8px;
    padding: 5px 9px; border: 1px solid var(--border); background: var(--surface-1); color: var(--text-primary);
  }}
  .app-status-btn:hover {{ filter: brightness(1.15); }}
  .app-status-btn:active {{ filter: brightness(0.9); }}
  .app-status-btn--positivo {{ border-color: var(--status-good-text); color: var(--status-good-text); }}
  .app-status-btn--negativo {{ border-color: var(--status-critical-text); color: var(--status-critical-text); }}

  .pretensao-banner {{
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px;
    padding: 16px 18px; display: flex; flex-direction: column; gap: 4px; margin-bottom: 20px;
  }}
  .pretensao-label {{ font-size: 12px; color: var(--text-secondary); }}
  .pretensao-value {{ font-size: 24px; font-weight: 700; }}
  .pretensao-hint {{ font-size: 11px; color: var(--text-muted); }}
  .pretensao-hint code {{ background: var(--page-plane); border-radius: 4px; padding: 1px 4px; }}

  .compare-table-wrap {{ overflow-x: auto; }}
  .compare-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  .compare-table th {{
    text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.03em;
    color: var(--text-muted); padding: 8px 10px; border-bottom: 1px solid var(--border);
  }}
  .compare-table td {{ padding: 10px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  .text-muted {{ color: var(--text-muted); font-size: 11px; }}
  .benefits-cell {{ display: flex; flex-wrap: wrap; gap: 4px; max-width: 320px; }}
  .benefit-chip {{
    font-size: 11px; background: rgba(42,120,214,0.12); color: var(--series-1);
    border-radius: 999px; padding: 2px 8px; white-space: nowrap;
  }}

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
  .status-badge {{
    align-self: flex-start; margin-top: 4px; font-size: 10px; font-weight: 700;
    padding: 2px 7px; border-radius: 999px; letter-spacing: 0.02em;
  }}
  .status-badge--neutro {{ background: rgba(137,135,129,0.18); color: var(--text-secondary); }}
  .status-badge--preparo {{ background: var(--status-warning-bg); color: var(--status-warning-text); }}
  .status-badge--enviada {{ background: rgba(42,120,214,0.16); color: var(--series-1); }}
  .status-badge--espera {{ background: rgba(237,161,0,0.16); color: var(--series-4); }}
  .status-badge--entrevista {{ background: rgba(74,58,167,0.18); color: var(--series-6); }}
  .status-badge--aprovado {{ background: rgba(12,163,12,0.15); color: var(--status-good-text); }}
  .status-badge--negativo {{ background: rgba(208,59,59,0.15); color: var(--status-critical-text); }}

  footer {{ color: var(--text-muted); font-size: 12px; margin-top: 32px; }}
</style>
</head>
<body>
  <header class="page-header">
    <div class="page-header-top">
      <div>
        <h1>Painel de recolocação</h1>
        <p>{stats["total_vagas"]} vagas no histórico</p>
      </div>
      <div class="header-actions">
        <button type="button" class="action-btn action-btn--primary" data-copy="{html.escape(BUSCAR_AGORA_TEXTO)}">🔄 Forçar busca agora</button>
        <span class="last-update">Última atualização: {gerado_em} (Brasília)</span>
      </div>
    </div>
  </header>

  <div class="kpi-grid">{kpis}</div>

  {render_actions_section(stats["acoes_pendentes"])}

  <nav class="tabs">
    <button type="button" class="tab-btn active" data-tab="geral">Visão geral</button>
    <button type="button" class="tab-btn" data-tab="candidaturas">Minhas candidaturas</button>
    <button type="button" class="tab-btn" data-tab="comparar">Comparar vagas</button>
  </nav>

  <div class="tab-panel active" id="tab-geral">
    <section>
      <h2>Vagas</h2>
      {all_jobs_section}
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
  </div>

  <div class="tab-panel" id="tab-candidaturas">
    <section>
      <h2>Minhas candidaturas</h2>
      <p class="tab-hint">Clique num botão de status para copiar o comando — cole numa sessão local do Claude Code para atualizar a vaga.</p>
      {applications_section}
    </section>
  </div>

  <div class="tab-panel" id="tab-comparar">
    <section>
      <h2>Comparar vagas</h2>
      {comparison_section}
    </section>
  </div>

  <footer>Career Agent AI — busca automática (Indeed) + listagem pública (LinkedIn/Gupy/Sólides/Vagas.com/InfoJobs/99Jobs/Adecco/CIA de Talentos/i9 Hunter/Manpower/Catho/Page Personnel/carreiras). Candidaturas sempre passam por aprovação manual antes do envio.</footer>

  <script>
    document.querySelectorAll('[data-copy]').forEach(function (btn) {{
      btn.addEventListener('click', function () {{
        var texto = btn.getAttribute('data-copy');
        var original = btn.textContent;
        var textarea = document.createElement('textarea');
        textarea.value = texto;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        var copiado = false;
        try {{ copiado = document.execCommand('copy'); }} catch (e) {{ copiado = false; }}
        document.body.removeChild(textarea);
        btn.textContent = copiado ? 'Copiado ✓' : 'Erro ao copiar';
        setTimeout(function () {{ btn.textContent = original; }}, 1500);
      }});
    }});

    document.querySelectorAll('.tab-btn').forEach(function (btn) {{
      btn.addEventListener('click', function () {{
        document.querySelectorAll('.tab-btn').forEach(function (b) {{ b.classList.remove('active'); }});
        document.querySelectorAll('.tab-panel').forEach(function (p) {{ p.classList.remove('active'); }});
        btn.classList.add('active');
        document.getElementById('tab-' + btn.getAttribute('data-tab')).classList.add('active');
      }});
    }});

    document.querySelectorAll('.filter-pill').forEach(function (pill) {{
      pill.addEventListener('click', function () {{
        document.querySelectorAll('.filter-pill').forEach(function (p) {{ p.classList.remove('active'); }});
        pill.classList.add('active');
        var status = pill.getAttribute('data-status');
        document.querySelectorAll('#all-jobs-grid .job-card').forEach(function (card) {{
          var match = status === '__all__' || card.getAttribute('data-status') === status;
          card.style.display = match ? '' : 'none';
        }});
      }});
    }});
  </script>
</body>
</html>
"""


def main() -> int:
    jobs = load_all_jobs()
    stats = aggregate(jobs)
    config = load_config()
    pretensao_salarial = config.get("salario_minimo_brl")
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARD_PATH.write_text(render_html(jobs, stats, pretensao_salarial), encoding="utf-8")
    print(f"Dashboard gerado em {DASHBOARD_PATH} ({len(jobs)} vagas).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
