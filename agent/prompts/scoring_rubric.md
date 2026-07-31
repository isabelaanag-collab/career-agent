# Rubrica de Match Score (0–100%)

Use esta rubrica para avaliar toda vaga que já passou pelo filtro duro (salário, localidade, área — ver `agent/config/search_criteria.yaml`). O score mede aderência da vaga ao perfil real da candidata, não potencial genérico.

## Regra de ouro

**Nunca invente.** Toda afirmação sobre a candidata (ferramenta que ela domina, anos de experiência, formação, idioma) precisa vir literalmente do currículo (`get_resume`) ou do texto do LinkedIn colado em `agent/config/linkedin_profile.txt` (se o arquivo existir). Se uma informação não puder ser confirmada em nenhuma dessas duas fontes, trate como "não verificável" e não pontue a favor dela — não assuma o benefício da dúvida.

## Dimensões e pesos (soma = 100)

| Dimensão | Peso | Como avaliar |
|---|---|---|
| Aderência de cargo/área | 20 | O cargo e a área da vaga batem com as áreas-alvo (Supply Chain, S&OE, Planejamento, MRP, PCP, Planejamento de Demanda, Supply Planning, Compras, Suprimentos, Logística)? |
| Senioridade | 10 | O nível pedido (júnior/pleno/sênior/especialista/coordenador/gerente) é compatível com o nível real da candidata pelo currículo? |
| Ferramentas/tecnologias | 20 | Sistemas/ferramentas exigidos (ex: SAP, ERP, Excel avançado, Power BI, WMS, TMS) — quantos a candidata comprovadamente já usou? |
| Palavras-chave da descrição | 15 | Sobreposição de termos-chave da descrição da vaga com currículo/LinkedIn (não é contagem cega — termos centrais valem mais que genéricos). |
| Responsabilidades/experiência prática | 20 | As responsabilidades listadas na vaga já foram exercidas de fato em experiências anteriores da candidata? |
| Formação | 5 | Requisito de formação (ex: Engenharia, Administração, Logística) é atendido? |
| Idiomas | 5 | Idiomas exigidos (ex: inglês avançado, espanhol) batem com o que consta no currículo/LinkedIn? |
| Fit de localização/modalidade | 5 | Mesmo já tendo passado no filtro duro, dar peso extra a match exato (ex: remoto pleno, ou cidade onde ela já mora) vs. match apenas aceitável. |

Some as pontuações ponderadas das 8 dimensões para chegar ao `match_score` final (0–100, inteiro).

## Saída obrigatória (por vaga)

Preencher, em português, todos os campos abaixo — eles vão direto para o JSON da vaga:

- `match_score`: inteiro 0–100
- `motivos_score`: lista de 3–6 frases curtas, uma por dimensão relevante, explicando o porquê da pontuação (positivo e negativo)
- `palavras_chave_encontradas`: lista de termos da descrição da vaga que também aparecem no currículo/LinkedIn
- `tecnologias_exigidas`: lista de ferramentas/sistemas pedidos na vaga (independente de a candidata ter ou não)
- `idiomas_exigidos`: lista de idiomas pedidos
- `beneficios`: lista de benefícios mencionados na vaga (se houver)
- `requisitos_obrigatorios`: lista
- `requisitos_desejaveis`: lista
- `probabilidade_estimada_entrevista`: uma de `baixa`, `média`, `alta` + uma frase de justificativa (baseada no match_score e em quão raros/concorridos são os requisitos)

## Faixas de ação (já configuráveis em `search_criteria.yaml`, hoje):

- `match_score >= 80` → vaga marcada como "Excelente Match" no dashboard; candidatura é preparada (currículo/carta) e fica com status "Aguardando aprovação" — **nunca enviada sem 1 clique de confirmação da candidata**, mesmo com score alto.
- `70 <= match_score < 80` → candidatura também preparada, status "Aguardando aprovação", mesma regra de confirmação.
- `match_score < 70` → só registrar no relatório com status "Encontrada"; não preparar currículo/carta.
