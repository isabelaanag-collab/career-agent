# Career Agent AI

Agente pessoal de recolocação profissional: busca vagas de Supply Chain / PCP / Compras / Logística em Belo Horizonte, Betim, Contagem, Nova Lima e remoto, pontua a aderência ao perfil da candidata, prepara currículo/carta e mantém um dashboard com histórico completo — sempre com aprovação humana antes de qualquer candidatura ser enviada.

## Como o sistema funciona (visão geral)

Duas partes rodam em lugares diferentes, porque cada uma precisa de acesso a coisas diferentes:

1. **Rotina em nuvem** (2x ao dia, 6h e 14h): busca vagas no Indeed (API oficial) e lista vagas públicas de LinkedIn/Gupy/Sólides/Vagas.com/InfoJobs/99Jobs/Adecco/CIA de Talentos/i9 Hunter/Manpower/Catho/Page Personnel/páginas de carreira (via busca na web, só leitura). Pontua cada vaga, grava em `data/jobs/`, regera o dashboard e dá `git push`. Ver `ARCHITECTURE.md` para os detalhes e limitações (ela não tem navegador nem acesso ao seu PC).
2. **Sessão local** (quando você quiser): você abre o Claude Code no seu PC, dá `git pull`, revisa as vagas com status "Aguardando aprovação" no dashboard, aprova as que fazem sentido — aí o currículo/carta são adaptados e, para vagas do Indeed, o navegador (`claude-in-chrome`) preenche o formulário de candidatura e **para antes do envio**, esperando seu clique de confirmação.

## Estrutura

```
agent/
  prompts/                     # prompts versionados (rotina, rubrica de score, adaptação de currículo)
  config/
    search_criteria.yaml       # critérios de busca — edite aqui para mudar áreas/cidades/salário/empresas
data/
  jobs/                        # uma vaga = um arquivo JSON (fonte da verdade)
  seen_index.json              # índice de deduplicação
  applications_log.jsonl       # histórico de candidaturas enviadas (append-only)
scripts/
  common.py                    # funções/constantes compartilhadas
  ingest.py                    # dedup + grava vaga nova
  render_dashboard.py          # gera dashboard/index.html (Kanban + gráficos + KPIs)
  update_status.py             # muda o status de uma vaga (nunca edite o JSON à mão)
dashboard/
  index.html                   # gerado a cada rodada — abra no navegador para ver o painel
tests/                         # pytest
```

## Modelo de dado de uma vaga (`data/jobs/<id_externo>.json`)

`empresa, cargo, salario, salario_estimado, cidade, estado, modalidade, url, plataforma, data_publicacao, data_candidatura, match_score, probabilidade_estimada_entrevista, motivos_score, palavras_chave_encontradas, tecnologias_exigidas, idiomas_exigidos, beneficios, requisitos_obrigatorios, requisitos_desejaveis, status, empresa_favorita, versao_curriculo, versao_carta, respostas_formulario, historico_status`.

## Status possíveis

`Encontrada → Em análise → Currículo otimizado → Carta criada → Aguardando aprovação → Candidatura enviada → Entrevista → Aprovado → Rejeitado`

## Rodando localmente

```bash
pip install -r requirements.txt
pytest                              # roda os testes
python scripts/render_dashboard.py  # gera dashboard/index.html a partir de data/jobs/
```

Para revisar e aprovar candidaturas pendentes, abra uma sessão do Claude Code neste repositório e peça para revisar as vagas com status "Aguardando aprovação" — o fluxo está descrito em `ARCHITECTURE.md`.

## Editando critérios de busca

Tudo em `agent/config/search_criteria.yaml`: piso salarial, cidades aceitas, áreas de interesse, empresas favoritas, limiares de match score. A rotina em nuvem lê esse arquivo a cada execução — não precisa reimplantar nada.

## Regras que nunca mudam

- Nenhuma candidatura é enviada sem 1 clique de confirmação da candidata, independentemente do Match Score.
- Nunca se inventa experiência, ferramenta, formação, idioma ou data no currículo/carta — só se usa o que já existe no currículo (`get_resume`) e/ou em `agent/config/linkedin_profile.txt`.
- Nenhuma vaga é candidatada duas vezes (`scripts/update_status.py` recusa reenvio).
- LinkedIn/Gupy/Sólides/páginas de carreira são sempre só leitura — sem login, sem preencher formulário.
