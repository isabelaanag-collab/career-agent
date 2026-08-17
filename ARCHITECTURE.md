# Arquitetura

## Por que duas partes (GitHub Actions + sessão local) em vez de um script só

A busca roda em **GitHub Actions** (`.github/workflows/daily_routine.yml`, 3x/dia — 07h, 12h e 18h BRT), executando `runner.py` — Python puro, sem CLI do Claude, sem navegador. Já a candidatura de fato — preencher formulário, anexar arquivo, clicar em enviar — só é possível com um navegador real, que só existe numa sessão local do Claude Code no PC da candidata (via `claude-in-chrome`).

Por isso o sistema é dividido assim:

```
┌─────────────────────────────┐        git push/pull        ┌──────────────────────────────┐
│  GitHub Actions (cron diário) │ ───────────────────────────▶│   Sessão local (sob demanda)   │
│                              │                              │                               │
│ • src/scrapers/* (requests)  │                              │ • git pull                    │
│   Gupy, Indeed, Vagas.com,   │                              │ • revisa "Aguardando aprovação"│
│   LinkedIn (best-effort)     │                              │ • adapta currículo/carta       │
│ • src/filters.py (área,      │                              │   (agent/prompts/              │
│   salário, local, recência)  │                              │    resume_tailoring.md)        │
│ • src/scorer.py — API         │                              │ • claude-in-chrome (só Indeed) │
│   Anthropic SÓ p/ vagas que   │                              │   preenche e PARA antes de     │
│   passaram no filtro duro     │                              │   enviar — espera aprovação    │
│ • ingest.py (dedup+persistir)│                              │ • update_status.py             │
│ • sheets_sync.py (Sheets)     │                              │ • git commit && push           │
│ • render_dashboard.py        │                              │                               │
│ • git commit && push          │                              │                               │
└─────────────────────────────┘                              └──────────────────────────────┘
```

## Redução de tokens: o que é LLM e o que é Python puro

A busca, o download de HTML/JSON de cada plataforma, o parsing e a deduplicação são **100% Python puro** (`src/scrapers/`, `src/filters.py`, `src/dedup.py`) — zero chamadas a modelo. A API da Anthropic (`src/scorer.py`) só é chamada **depois** que uma vaga já passou por todos os filtros determinísticos (área, salário ≥ R$ 6.000 ou não informado, localidade, não-vista, não-candidatada-fora-do-sistema, publicada nas últimas 48h). Isso significa que a imensa maioria das vagas encontradas em cada execução nunca chega a gastar um token — só as poucas dezenas que realmente têm chance de virar candidatura são pontuadas, e mesmo essas em lotes (`BATCH_SIZE` em `src/scorer.py`) com o bloco de rubrica+currículo marcado como `cache_control` para não ser reenviado do zero a cada lote.

O julgamento de match ainda é feito pelo modelo (Claude Haiku, ver `CAREER_AGENT_SCORING_MODEL` em `src/scorer.py`), seguindo a mesma rubrica versionada (`agent/prompts/scoring_rubric.md`) que antes — um algoritmo de keyword-overlap seria raso demais para julgar equivalência semântica ("essa responsabilidade é essencialmente a mesma coisa que a candidata já fez"). O que mudou é *quando* e *quantas vezes* isso é chamado, não a lógica de avaliação em si.

## Como cada plataforma é buscada (sem login, sem CLI do Claude)

| Plataforma | Como | Confiabilidade |
|---|---|---|
| Gupy | API pública não documentada (`employability-portal.gupy.io/api/v1/jobs`), descoberta por inspeção de rede do portal.gupy.io — sem autenticação | Alta |
| Indeed | HTML da página de busca (`br.indeed.com/jobs`), parsing do JSON embutido (`mosaic-provider-jobcards`) | **Baixa/Média** — funciona (testado, HTTP 200 com dados reais), mas o anti-bot da Indeed bloqueia com HTTP 403 conforme o IP/fingerprint de rede de origem; em teste real da IP usada para desenvolver isso, `curl` passou mas a biblioteca `requests` do Python foi bloqueada na mesma rede minutos depois. Runners do GitHub Actions (IPs de datacenter conhecidos) tendem a ser bloqueados com mais frequência ainda. |
| Vagas.com | HTML server-renderizado da página de busca, parsing direto com BeautifulSoup | Alta |
| LinkedIn | Endpoint público "guest" (`jobs-guest/jobs/api/seeMoreJobPostings/search`) — o mesmo que uma visita anônima usa, sem login/cookie de sessão | **Baixa** — o LinkedIn aplica rate-limit agressivo a esse endpoint; é comum retornar 0 resultados em várias execuções seguidas. Ver limitação abaixo. |
| Sólides | — | **Não implementado.** SPA Next.js cuja lista de vagas é buscada via JS para um endpoint que não ficou visível nem inspecionando o tráfego de rede. `src/scrapers/solides.py` sempre retorna lista vazia, documentando isso explicitamente. |

Nenhum scraper faz login. Nenhum candidata, preenche formulário ou clica em nada nessas plataformas — a rotina diária só lê buscas públicas e registra a URL da vaga para a candidata abrir depois.

## Deduplicação (duas camadas)

1. **Por URL/id da vaga**: `id_externo = plataforma + hash(url_ou_id)` (`scripts/common.py::external_id`), chave em `data/seen_index.json`. Nunca grava duas vezes o mesmo id.
2. **Por conteúdo**: `hash(empresa + cargo + cidade)` (`src/dedup.py::content_hash`), em `data/seen_content_hashes.json`. Pega o caso de um mesmo anúncio ser republicado com uma URL nova (comum em Gupy/Indeed) — sem essa camada, a vaga pareceria "nova" de novo.

Além disso, `data/applied_externos.json` é uma lista mantida manualmente pela candidata com vagas às quais ela se candidatou **fora deste sistema** (direto no site da Gupy ou do LinkedIn) — como não há API para ler a aba "Minhas candidaturas" dessas plataformas sem login, esse arquivo é o jeito de a rotina não voltar a sugerir algo que ela já candidatou por fora. Formato: `[{"empresa": "...", "cargo": "...", "cidade": "..."}]`; o hash de conteúdo é recalculado a partir disso a cada execução.

`scripts/update_status.py` nunca deixa uma vaga ir para "Candidatura enviada" duas vezes dentro do sistema (mesma regra de antes).

## Limitações conhecidas (deliberadas, não bugs)

- **Sem notificação push a partir do GitHub Actions.** A forma de saber que a rotina achou algo bom continua sendo abrir o dashboard depois da execução diária (07h BRT) ou rodar `python runner.py` localmente sob demanda.
- **Indeed e LinkedIn podem bloquear a origem do GitHub Actions.** Ambos usam anti-bot que reage a fingerprint de rede/TLS, não só a headers — confirmado em teste real durante o desenvolvimento (ver tabela acima). Se um dia pararem de retornar qualquer resultado, isso é esperado, não um bug para "corrigir" adicionando headers mais elaborados ou driver headless (o que reintroduziria peso e custo que este projeto está deliberadamente evitando).
- **LinkedIn é a fonte mais instável.** Não há como contornar isso sem logar na conta da candidata dentro do workflow — o que violaria os Termos de Uso do LinkedIn e arriscaria suspensão de conta, exatamente como já valia para candidatura automática. Não vale a pena "consertar" isso com cookies de sessão salvos como secret.
- **Sólides não está implementado.** Ver tabela acima e o docstring de `src/scrapers/solides.py` — se alguém descobrir o endpoint real, é só seguir o padrão de `gupy.py`.
- **Candidatura assistida só existe no Indeed.** É a única plataforma com o fluxo local de `claude-in-chrome` desenhado para preencher o formulário — sempre parando antes do envio final para a candidata confirmar.
- **"Aba de candidaturas" da Gupy/LinkedIn não é lida automaticamente.** Sem login não há como acessar isso; a mitigação é `data/applied_externos.json` (ver seção de deduplicação).

## Fluxo de dados de uma vaga (ciclo de vida do arquivo JSON)

1. `runner.py` (GitHub Actions, 3x/dia) cria `data/jobs/<id_externo>.json` com status `Encontrada` ou `Aguardando aprovação` (conforme o Match Score retornado por `src/scorer.py`; se a chamada à API falhar ou a chave não estiver configurada, a vaga é registrada como `Encontrada` sem score, para revisão manual).
2. Sessão local, ao aprovar: `Aguardando aprovação` → `Currículo otimizado` → `Carta criada` (via `resume_tailoring.md` + `update_status.py`).
3. Após o clique de confirmação da candidata e envio real (só Indeed, via navegador): `Carta criada` → `Candidatura enviada` — nesse momento `update_status.py` também grava uma linha em `data/applications_log.jsonl`.
4. Atualizações manuais posteriores (candidata informa que teve retorno): `Candidatura enviada` → `Entrevista` → `Aprovado` ou `Rejeitado`.

Todas as transições passam por `scripts/update_status.py`, nunca por edição manual do JSON — é isso que garante `historico_status` e `applications_log.jsonl` consistentes.
