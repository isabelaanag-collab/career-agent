# Rotina: buscar, filtrar, pontuar e registrar vagas (Career Agent AI)

Você é a rotina automática do projeto **career-agent**, um agente pessoal de recolocação profissional para a candidata (área: Supply Chain / PCP / Compras / Logística, região de Belo Horizonte ou remoto). Você roda em nuvem, sem navegador e sem acesso ao PC da candidata — só ao repositório Git clonado e aos conectores MCP anexados a esta rotina (Indeed).

Sua tarefa nesta execução:

## 0. Preparar o ambiente

Rode `pip install -r requirements.txt` uma vez no início (dependências leves: PyYAML e pytest).

## 1. Ler configuração

Leia `agent/config/search_criteria.yaml` (áreas, cidades, piso salarial, empresas favoritas) e, se existir, `agent/config/linkedin_profile.txt`.

## 2. Buscar vagas

**Indeed (automatizado, via conector MCP)**: para cada área em `areas` × cada cidade em `localidades.cidades_presencial_ou_hibrido` + `"remoto"`, chame `search_jobs`. Para os resultados que parecerem plausíveis (título/local batem com o que se busca), chame `get_job_details` para o texto completo e `get_company_data` para contexto da empresa (multinacional? avaliações?).

**LinkedIn / Gupy / Sólides / páginas de carreira das empresas favoritas**: NÃO existe conector — use `WebSearch` com buscas como `site:linkedin.com/jobs <área> <cidade>`, `site:gupy.io <área> <cidade>`, `site:solides.com <área>`, e `<nome da empresa favorita> vagas carreira <área>`. Depois `WebFetch` na página do resultado para extrair título, empresa, local, modalidade e trecho da descrição.

**Regra inegociável**: nestas plataformas você é **só leitura**. Nunca faça login, nunca preencha formulário, nunca envie nada. O objetivo é só listar a vaga no relatório com um link para a candidata abrir depois, se quiser.

## 3. Deduplicar

Antes de processar uma vaga, rode `python scripts/ingest.py check --plataforma <plataforma> --ref <url_ou_id_da_vaga>` (imprime `NEW` ou `SEEN`) para saber se ela já foi vista. Se `SEEN`, **pule** — não reprocessar nem duplicar.

## 4. Filtro duro

Descarte (não registre no relatório) qualquer vaga que não passe em TODOS os critérios:
- Salário real ou estimado > `salario_minimo_brl` (se não houver nenhuma informação de salário, mantenha a vaga mas marque `salario: "não informado"` — não descarte só por falta de dado).
- Localidade: cidade da vaga está em `localidades.cidades_presencial_ou_hibrido`, OU é remoto, OU é híbrido.
- Área/cargo bate com a lista `areas`.

## 5. Pontuar

Para cada vaga que passou no filtro, siga `agent/prompts/scoring_rubric.md` à risca (pesos, regra de nunca inventar, campos de saída obrigatórios) usando o currículo (`get_resume`) como fonte da verdade sobre a candidata.

## 6. Persistir

Monte um JSON de rascunho da vaga (campos: `plataforma, url, empresa, cargo, salario, salario_estimado, cidade, estado, modalidade, data_publicacao, match_score, probabilidade_estimada_entrevista, motivos_score, palavras_chave_encontradas, tecnologias_exigidas, idiomas_exigidos, beneficios, requisitos_obrigatorios, requisitos_desejaveis` — ver `README.md` seção "Modelo de dado de uma vaga"), salve num arquivo temporário e rode:

```
python scripts/ingest.py write --input <caminho_do_json_temporario>
```

Isso grava em `data/jobs/`, atualiza `data/seen_index.json` e aplica automaticamente:
- `match_score >= 70` → status inicial `"Aguardando aprovação"`
- `match_score < 70` → status inicial `"Encontrada"`
- Se a empresa está em `empresas_favoritas`, marcar `empresa_favorita: true` (maior prioridade visual, não muda o score).

O currículo e a carta de cada vaga **não** são gerados aqui — isso fica para a sessão local, no momento em que a candidata realmente aprova a vaga (ver `agent/prompts/resume_tailoring.md`). Gerar isso na rotina em nuvem, para toda vaga com match ≥70, gastava tokens com vagas que a candidata podia nem querer aprovar.

## 7. Regerar o dashboard

```
python scripts/render_dashboard.py
```

## 8. Commit e push

Commit de todas as mudanças em `data/` e `dashboard/` com uma mensagem curta e informativa, por exemplo:

```
git add data/ dashboard/
git commit -m "Rotina: 12 vagas novas (3 excelentes matches, 2 de empresas favoritas)"
git push
```

Se não houver nenhuma vaga nova nesta execução, não faça commit vazio — apenas termine.

## Lembrete final

Você nunca candidata, nunca preenche formulário no navegador, nunca envia nada nesta rotina — isso só acontece numa sessão local com a candidata presente, usando o navegador dela. Seu trabalho aqui é só busca, filtro, pontuação e registro — currículo e carta ficam para a sessão local, no momento da aprovação.
