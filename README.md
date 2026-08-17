# Career Agent AI

Agente pessoal de recolocação profissional: busca vagas de Supply Chain / PCP / Compras / Logística em Belo Horizonte, Betim, Contagem, Nova Lima e remoto, pontua a aderência ao perfil da candidata, prepara currículo/carta e mantém um dashboard com histórico completo — sempre com aprovação humana antes de qualquer candidatura ser enviada.

## Como o sistema funciona (visão geral)

Duas partes rodam em lugares diferentes, porque cada uma precisa de acesso a coisas diferentes:

1. **GitHub Actions** (1x ao dia, 07:00 horário de Brasília): roda `python runner.py`, que busca vagas em Gupy, Indeed, Vagas.com e LinkedIn (scrapers Python puros, sem CLI do Claude, sem custo de token), aplica o filtro duro (área/salário/localidade/recência), e só então chama a API da Anthropic — de forma cirúrgica, só para as vagas que já passaram no filtro — para pontuar a aderência ao perfil. Grava em `data/jobs/`, sincroniza as aprovadas com o Google Sheets, regera o dashboard e dá `git push`. Ver `ARCHITECTURE.md` para detalhes, incluindo por que Sólides não está implementado e por que o LinkedIn é instável.
2. **Sessão local** (quando você quiser): você abre o Claude Code no seu PC, dá `git pull`, revisa as vagas com status "Aguardando aprovação" no dashboard, aprova as que fazem sentido — aí o currículo/carta são adaptados e, para vagas do Indeed, o navegador (`claude-in-chrome`) preenche o formulário de candidatura e **para antes do envio**, esperando seu clique de confirmação.

## Estrutura

```
runner.py                      # orquestrador da rotina diária (GitHub Actions chama isso)
src/
  scrapers/                    # um módulo por plataforma (gupy, indeed, vagas_com, linkedin, solides)
  filters.py                   # filtro duro: área, salário, localidade, recência (48h)
  dedup.py                     # dedup por conteúdo (empresa+cargo+cidade) + candidaturas feitas fora do sistema
  scorer.py                    # chamada cirúrgica à API da Anthropic (só vagas pós-filtro)
  sheets_sync.py                # grava as vagas aprovadas no Google Sheets
agent/
  prompts/                     # rubrica de score (usada por src/scorer.py) e adaptação de currículo (sessão local)
  config/
    search_criteria.yaml       # critérios de busca — edite aqui para mudar áreas/cidades/salário/empresas
    linkedin_profile.txt       # perfil/resumo da candidata — fonte usada na pontuação
    resume.txt                 # opcional: currículo completo, além do perfil acima
data/
  jobs/                        # uma vaga = um arquivo JSON (fonte da verdade)
  seen_index.json              # índice de deduplicação por URL/id
  seen_content_hashes.json      # índice de deduplicação por conteúdo (empresa+cargo+cidade)
  applied_externos.json         # candidaturas feitas fora do sistema — edite para a rotina não repetir
  applications_log.jsonl       # histórico de candidaturas enviadas (append-only)
scripts/
  common.py                    # funções/constantes compartilhadas (status, dedup por URL, etc.)
  ingest.py                    # dedup + grava vaga nova (usado por runner.py e pela CLI)
  render_dashboard.py          # gera dashboard/index.html (abas: Visão geral, Minhas candidaturas, Comparar vagas)
  update_status.py             # muda o status de uma vaga (nunca edite o JSON à mão)
dashboard/
  index.html                   # gerado a cada rodada — abra no navegador para ver o painel
.github/workflows/
  daily_routine.yml            # cron 07:00 BRT rodando runner.py
tests/                         # pytest
```

## Modelo de dado de uma vaga (`data/jobs/<id_externo>.json`)

`empresa, cargo, salario, salario_estimado, cidade, estado, modalidade, url, plataforma, data_publicacao, data_candidatura, match_score, probabilidade_estimada_entrevista, motivos_score, palavras_chave_encontradas, tecnologias_exigidas, idiomas_exigidos, beneficios, requisitos_obrigatorios, requisitos_desejaveis, status, empresa_favorita, versao_curriculo, versao_carta, respostas_formulario, historico_status`.

## Status possíveis

Antes da candidatura: `Encontrada → Em análise → Currículo otimizado → Carta criada → Aguardando aprovação → Rejeitado` (candidata decidiu não se candidatar)

Depois da candidatura: `Candidatura enviada → Aguardando retorno → Entrevista → Em fase de testes → Aprovado` ou, a qualquer momento depois do envio, `Retorno negativo` (empresa recusou). Os status pós-candidatura são atualizados pelos botões na aba "Minhas candidaturas" do dashboard.

## Configurando o GitHub Actions

O workflow (`.github/workflows/daily_routine.yml`) precisa destes secrets no repositório (Settings → Secrets and variables → Actions):

| Secret | Obrigatório? | Para quê |
|---|---|---|
| `ANTHROPIC_API_KEY` | Só se quiser pontuação automática | Chama a API da Anthropic para pontuar vagas pós-filtro. Sem ela, as vagas são registradas com status `Encontrada` e sem `match_score`, para revisão manual. |
| `GOOGLE_CREDENTIALS` | Só se quiser sincronizar com Sheets | Conteúdo JSON de uma service account do Google com acesso à planilha (ver abaixo). |
| `GOOGLE_SHEET_ID` | Só se quiser sincronizar com Sheets | ID da planilha (alternativa a preencher `google_sheets.spreadsheet_id` em `search_criteria.yaml`). |

`GITHUB_TOKEN` (automático) já tem permissão de push porque o workflow declara `permissions: contents: write`.

### Google Sheets — passo a passo

1. Crie um projeto no [Google Cloud Console](https://console.cloud.google.com/), ative a "Google Sheets API" e a "Google Drive API".
2. Crie uma Service Account, gere uma chave JSON.
3. Compartilhe a planilha de destino com o e-mail da service account (campo `client_email` no JSON), como Editor.
4. Cole o conteúdo do JSON no secret `GOOGLE_CREDENTIALS` do repositório (ou salve localmente como `google_credentials.json` na raiz — já está no `.gitignore`).
5. Preencha `google_sheets.spreadsheet_id` em `agent/config/search_criteria.yaml` (ou o secret `GOOGLE_SHEET_ID`).

Colunas gravadas: `Data Coleta, Cargo, Empresa, Local/Modalidade, Salário, Match/Pontuação, Link da Vaga, Status` (Status = "Aprovação Pendente" ou "Candidatado").

## Ignorar vagas já candidatadas fora do sistema

A rotina não tem como ler a aba "Minhas candidaturas" da Gupy ou do LinkedIn sem login. Se você se candidatou a algo direto no site dessas plataformas (fora deste sistema), adicione em `data/applied_externos.json`:

```json
[
  {"empresa": "Ambev", "cargo": "Analista de Supply Chain", "cidade": "Belo Horizonte"}
]
```

A próxima execução vai ignorar qualquer vaga com o mesmo hash de `empresa+cargo+cidade`.

## Rodando localmente

```bash
pip install -r requirements.txt
pytest                              # roda os testes
python runner.py                    # roda a rotina completa (busca + filtro + score + Sheets + dashboard)
python scripts/render_dashboard.py  # só regera o dashboard a partir de data/jobs/ existente
```

Para pontuação automática localmente, exporte `ANTHROPIC_API_KEY` antes de rodar `runner.py`. Sem ela, a busca/filtro/dedup funcionam normalmente — só a pontuação fica pendente.

Para revisar e aprovar candidaturas pendentes, abra uma sessão do Claude Code neste repositório e peça para revisar as vagas com status "Aguardando aprovação" — o fluxo está descrito em `ARCHITECTURE.md`.

## Editando critérios de busca

Tudo em `agent/config/search_criteria.yaml`: piso salarial, cidades aceitas, áreas de interesse, empresas favoritas, limiares de match score, configuração do Google Sheets. `runner.py` lê esse arquivo a cada execução — não precisa reimplantar nada.

## Regras que nunca mudam

- Nenhuma candidatura é enviada sem 1 clique de confirmação da candidata, independentemente do Match Score.
- Nunca se inventa experiência, ferramenta, formação, idioma ou data no currículo/carta — só se usa o que já existe em `agent/config/linkedin_profile.txt` e/ou `agent/config/resume.txt`.
- Nenhuma vaga é candidatada duas vezes (`scripts/update_status.py` recusa reenvio).
- Gupy/Indeed/Vagas.com/LinkedIn são sempre só leitura na rotina diária — sem login, sem preencher formulário. A busca/filtro/dedup nunca chamam a API da Anthropic; só a pontuação final chama, e só para vagas que já passaram em todos os filtros duros.
