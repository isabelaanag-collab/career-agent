# Arquitetura

## Por que duas partes (nuvem + local) em vez de um script só

Uma rotina agendada em nuvem (Claude Code Routine) roda num ambiente isolado, sem navegador e sem acesso ao disco do PC da candidata — só ao repositório Git clonado e aos conectores MCP anexados a ela (hoje, só o Indeed). Já a candidatura de fato — preencher formulário, anexar arquivo, clicar em enviar — só é possível com um navegador real, que só existe numa sessão local do Claude Code no PC da candidata (via `claude-in-chrome`).

Por isso o sistema é dividido assim:

```
┌─────────────────────────────┐        git push/pull        ┌──────────────────────────────┐
│   Rotina em nuvem (cron)     │ ───────────────────────────▶│   Sessão local (sob demanda)   │
│                              │                              │                               │
│ • search_jobs (Indeed MCP)   │                              │ • git pull                    │
│ • WebSearch/WebFetch         │                              │ • revisa "Aguardando aprovação"│
│   (LinkedIn/Gupy/Sólides —   │                              │ • adapta currículo/carta       │
│   só leitura, sem login)     │                              │ • claude-in-chrome (só Indeed) │
│ • aplica scoring_rubric.md   │                              │   preenche e PARA antes de     │
│ • ingest.py (dedup+persistir)│                              │   enviar — espera aprovação    │
│ • render_dashboard.py        │                              │ • update_status.py             │
│ • git commit && push         │                              │ • git commit && push           │
└─────────────────────────────┘                              └──────────────────────────────┘
```

## Por que o Match Score não é um algoritmo Python

Um algoritmo de keyword-overlap seria raso (não entende sinônimos, contexto, nem "essa responsabilidade é essencialmente a mesma coisa que a candidata já fez"). Em vez disso, o próprio Claude, dentro da rotina em nuvem, faz o julgamento seguindo uma rubrica fixa e versionada (`agent/prompts/scoring_rubric.md`), comparando a vaga com o currículo real da candidata. Python fica só com a parte determinística e testável: filtro duro (salário/cidade/área), deduplicação, persistência e geração do dashboard. Isso também facilita ajustar a rubrica no futuro sem tocar em código.

## Deduplicação

Cada vaga recebe um `id_externo = plataforma + hash(url_ou_id)` (ver `scripts/common.py::external_id`). Esse id é a chave em `data/seen_index.json`; `scripts/ingest.py` nunca grava duas vezes o mesmo id, e `scripts/update_status.py` nunca deixa uma vaga ir para "Candidatura enviada" duas vezes (uma vez em `Candidatura enviada`/`Entrevista`/`Aprovado`/`Rejeitado`, uma nova tentativa de reenvio é recusada).

## Limitações conhecidas (deliberadas, não bugs)

- **Sem notificação push a partir da rotina em nuvem.** Ela não tem como avisar o celular da candidata diretamente. Hoje, a forma de saber que a rotina achou algo bom é abrir o dashboard ou pedir, numa sessão local, para revisar o que foi encontrado. Se no futuro a candidata conectar Slack ou e-mail como MCP connector, dá pra revisitar isso.
- **LinkedIn/Gupy/Sólides são só leitura.** Não há API pública, e automatizar login/candidatura nessas plataformas violaria os Termos de Uso e arrisca suspensão de conta. A rotina só lista essas vagas via busca pública (`WebSearch`/`WebFetch`), sem login e sem preencher nada.
- **Candidatura assistida só existe no Indeed.** É a única plataforma com conector oficial e onde o fluxo local com `claude-in-chrome` foi desenhado para preencher o formulário — sempre parando antes do envio final para a candidata confirmar.
- **A rotina em nuvem precisa de `pip install -r requirements.txt`** (PyYAML para ler o config, pytest para os testes) — isso está no passo 0 de `agent/prompts/routine_search_and_score.md`.

## Fluxo de dados de uma vaga (ciclo de vida do arquivo JSON)

1. Rotina em nuvem cria `data/jobs/<id_externo>.json` com status `Encontrada` ou `Aguardando aprovação` (conforme o Match Score).
2. Sessão local, ao aprovar: `Aguardando aprovação` → `Currículo otimizado` → `Carta criada` (via `resume_tailoring.md` + `update_status.py`).
3. Após o clique de confirmação da candidata e envio real (só Indeed, via navegador): `Carta criada` → `Candidatura enviada` — nesse momento `update_status.py` também grava uma linha em `data/applications_log.jsonl`.
4. Atualizações manuais posteriores (candidata informa que teve retorno): `Candidatura enviada` → `Entrevista` → `Aprovado` ou `Rejeitado`.

Todas as transições passam por `scripts/update_status.py`, nunca por edição manual do JSON — é isso que garante `historico_status` e `applications_log.jsonl` consistentes.
