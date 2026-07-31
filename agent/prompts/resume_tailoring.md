# Adaptação de currículo e carta de apresentação

Usado na sessão local, depois que a candidata aprova uma vaga com status "Aguardando aprovação".

## Regras inegociáveis

1. **Nunca inventar experiência, ferramenta, curso, certificação ou idioma** que não exista no currículo-fonte (`get_resume`) ou em `agent/config/linkedin_profile.txt`.
2. **Nunca alterar datas** de início/fim de experiências ou formação.
3. **Nunca criar cargos ou empresas** que a candidata não teve.
4. Adaptação = reordenar, reformular e priorizar o que já existe para a linguagem da vaga — não é criar conteúdo novo.

## Adaptação de currículo para ATS

1. Ler a descrição completa da vaga (`get_job_details` ou o texto extraído da página) e a lista `tecnologias_exigidas` / `palavras_chave_encontradas` já calculada no score.
2. Reescrever bullets de experiência usando os mesmos termos da vaga quando a candidata genuinamente fez aquilo (ex: se a vaga pede "S&OP" e o currículo diz "planejamento de vendas e operações", pode alinhar a terminologia — não é invenção, é sinonímia).
3. Priorizar no topo do currículo as experiências/skills mais relevantes para esta vaga específica.
4. Manter formatação simples (sem tabelas/colunas complexas) para compatibilidade com parsers de ATS.
5. Salvar a versão gerada em `data/resumes/<job_id>__<timestamp>.md` (ou .txt) e registrar o nome do arquivo no campo `versao_curriculo` do log de candidatura.

## Carta de apresentação

1. 3–4 parágrafos, tom profissional e direto, em português (a menos que a vaga seja explicitamente em inglês).
2. Parágrafo 1: por que esta vaga/empresa específica interessa (usar dado real da empresa via `get_company_data` quando disponível — não genérico).
3. Parágrafo 2–3: 2–3 conquistas/experiências reais da candidata que respondem diretamente às responsabilidades da vaga.
4. Fechamento: disponibilidade e agradecimento, sem clichês vazios.
5. Salvar em `data/cover_letters/<job_id>__<timestamp>.md` e registrar em `versao_carta`.

## Depois de gerar

Atualizar o status da vaga: `Aguardando aprovação` → `Currículo otimizado` → `Carta criada`, sempre via `scripts/update_status.py` (nunca editar o JSON à mão) para manter `historico_status` consistente.
