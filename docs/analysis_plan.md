# Plano de análise estatística (pré-registro)

- Versão: 1.0 — 2026-11-04 (redigido pelo stats-analyst; gravado pelo maestro antes de qualquer campanha)
- Implementação: `src/triagebench/analysis/stats.py` (`run_preregistered_analysis`); testes: `tests/test_stats.py`.
- Status: escrito ANTES de qualquer inspeção de métrica de teste dos experimentos finais. Nenhuma campanha tinha sido lançada quando este arquivo foi gravado. Alterações posteriores só pela seção **Desvios** (com data), nunca por edição silenciosa.

## 1. Pergunta e desenho

Modelos complexos superam de forma consistente os simples na predição do `acuity` (1–5, ordinal, 1 = mais urgente) a partir de 7 variáveis estruturadas de triagem (6 sinais vitais + dor), no MIMIC-IV-ED? O alvo é desbalanceado (classe 3 ≈ 53%; classes 1 e 5 raras: 5,7% e 0,26%), portanto a **acurácia não é usada como critério**.

- Divisões: 10 partições por paciente (`subject_id`), seeds 1..10, treino/val/teste = 70/15/15, estratificadas pelo acuity mais urgente do paciente. Partições de seeds diferentes se sobrepõem (holdout repetido).
- Por seed, para cada (variante, modelo, estratégia): busca aleatória de 20 configurações treinadas no treino e avaliadas na validação; escolha por Macro-F1 de validação; re-treino da configuração congelada no treino; avaliação única no teste.
- Modelos primários (8): simples = logreg, gnb, knn, dtree; complexos = rf, svm_rbf, xgb, mlp. Extras (hgb, extratrees, ordinal_logit) e referências (dummy_prior, dummy_stratified) são descritivos e **não entram em H1**.
- Estratégias: none, class_weight (knn não tem), oversample. Variantes: A_keep_encode (principal), B_pain_numeric_only (sensibilidade, aninhada em A, mesmas partições).

## 2. Unidade de análise e métrica primária

- **Unidade de análise = seed (divisão)**. O n efetivo é o número de seeds (≤ 10) de **um único conjunto de dados**; a inferência é sobre a variabilidade de partição/treino nesse conjunto, não sobre populações ou hospitais diferentes.
- **Métrica primária: Macro-F1 no conjunto de TESTE** (média simples do F1 das 5 classes; classe sem predição nem suporte conta 0).
- Métricas secundárias: balanced accuracy, recall da classe 1, QWK, MAE ordinal, taxas de sub/sobretriagem. A métrica primária **não será trocada** após ver resultados.
- Seleção ("melhor do grupo", escolha de hiperparâmetros) usa exclusivamente a Macro-F1 de **validação**.

## 3. Hipóteses operacionais

### H1 (confirmatória, única)
Estratégia `none`, variante A. Em cada seed, o melhor modelo de cada grupo é o de maior Macro-F1 de **validação** naquela seed (empate: ordem da lista acima). Δ_s = Macro-F1_teste(melhor complexo) − Macro-F1_teste(melhor simples).

- **Consistente** se (i) Δ_s > 0 em **todas** as seeds analisadas **e** (ii) o limite inferior do IC95% bilateral da média de Δ (t corrigido, seção 4) é > δ = 0,01.
- Caso contrário: **"sem superioridade consistente"** (resultado válido e publicável). Se o limite superior do IC for < 0, registra-se adicionalmente que o IC favorece os simples.
- δ = 0,01 é uma margem de relevância prática fixada a priori (não calibrada empiricamente).
- Robustez (secundária, rotulada como tal): modelo fixo por grupo, escolhido pela Macro-F1 de validação **média** entre seeds; e a mesma H1 na variante B (descritiva).

### H2 (confirmatória por modelo)
Para cada modelo primário e cada estratégia S ∈ {class_weight, oversample}: S aumenta (vs. `none`, variante A, teste) o **recall da classe 1**, a **Macro-F1** e a **balanced accuracy**. Diferença pareada por seed. "H2 suportada" para (modelo, S) se as três métricas têm Δ médio > 0 e p_Holm < 0,05 (interseção–união: exige as três, sem inflar erro tipo I). Holm entre os modelos primários, dentro de cada (estratégia, métrica) — 6 famílias. Extras e métricas descritivas (precision_1, accuracy, QWK) são reportados sem correção e rotulados "descritivos". Observação: aumento de recall_1 vem normalmente com perda de precisão_1 e acurácia; isso é reportado, não escondido. Como a seleção de hiperparâmetros também usa Macro-F1, "melhorar Macro-F1" é parcialmente circular com o critério de seleção; isso é declarado como limitação.

### H3 (descritiva)
Fração de erros com |ŷ−y| = 1 (`adjacent_error_share`), fração com distância ≥ 2 (= 1 − adjacente), subtriagem, sobretriagem e subtriagem grave, por modelo × estratégia (média e DP entre seeds). Critério informal "maioria adjacente": adjacent_error_share > 0,5 em todas as seeds. Sem teste de hipótese.

### Descritivos
- **Ranking**: por estratégia, Friedman com seeds como blocos sobre a Macro-F1 de teste (modelos primários + extras com dados completos), postos médios, Kendall W = χ²/(n(k−1)), diferença crítica de Nemenyi (q de Demšar via intervalo studentizado, α = 0,05). **Aviso permanente de baixo poder e de p-valores anticonservadores** (blocos não independentes; k grande com n ≤ 10 blocos). Dummies são mostrados à parte.
- **Sensibilidade B vs. A**: para cada (seed, modelo, estratégia), calcula-se a Macro-F1 (e balanced accuracy, QWK) de A e de B **no mesmo subconjunto de teste** (interseção de `stay_id` presentes em A e B). Diferença B − A pareada por seed com t corrigido. Reavalia-se H1 nesse subconjunto (seleção por validação da própria variante) — descritivo. Reporta-se a fração de estadias removidas por classe (contagens mascaradas, seção 10) porque B remove dor não numérica, com mais casos graves (auditoria: 41,6% da classe 1 vs 4,3% da classe 3). Médias de A e B nos seus testes próprios **não são comparáveis** e só aparecem rotuladas como tal.

## 4. Testes estatísticos e justificativa

**Inferência entre seeds: t reamostrado corrigido de Nadeau–Bengio (2003).** Para k diferenças pareadas d_1..d_k: t = d̄ / √((1/k + n_teste/n_treino)·s²), com n_teste/n_treino = 0,15/0,70 ≈ 0,214 e k−1 graus de liberdade; IC95% = d̄ ± t_{0,975;k−1}·SE. Justificativa: os conjuntos de treino de seeds distintas se sobrepõem, as diferenças são positivamente correlacionadas e o t ingênuo (1/k·s²) subestima a variância (com k = 10 o SE corrigido é ≈ 1,77× o ingênuo). O Wilcoxon sobre folds correlacionados infla o erro tipo I pelo mesmo motivo, e não possui correção equivalente.

Limitações assumidas e declaradas:
1. A correção é aproximada: deriva de subamostragem aleatória com correlação ρ ≈ n_teste/(n_treino+n_teste) ≈ 0,18; aqui as partições são por paciente, estratificadas e com treinos que se sobrepõem em ≈ 49% (0,7²) em média, de modo que a correlação real pode diferir. Não corrige a correlação entre os conjuntos de teste.
2. Assume normalidade aproximada de Δ; com k ≤ 10 isso não é verificável com poder. Por isso reportamos também o Wilcoxon exato (**apenas descritivo**, anticonservador aqui) e a direção/consistência em todas as seeds.
3. Com k ≤ 10 o IC é largo; a exigência de Δ > 0 em todas as seeds é um critério adicional de consistência, não um teste de significância (e torna "sem superioridade consistente" mais provável quando o efeito verdadeiro está perto de δ).
4. A inferência refere-se a um único conjunto de dados; não generaliza para outras populações.

**Pressupostos verificados/relatados:** pareamento por seed (mesmas partições para todos os modelos); número de pares efetivos por comparação (`n_pairs`); presença de NaN/duplicatas (tratados como ausência e anotados em `notes`).

**Wilcoxon exato** e **Friedman/Nemenyi** são descritivos (ver acima); o único critério confirmatório de H1 é o descrito na seção 3, e de H2 o t corrigido com Holm.

## 5. Múltiplas comparações

- H1: um único contraste confirmatório → sem correção.
- H2: Holm (step-down) entre modelos primários dentro de cada (estratégia, métrica); suporte exige as três métricas (interseção–união). Não há correção global entre as 6 famílias; as conclusões de H2 são por modelo e estratégia e não devem ser lidas como um único teste global.
- Nemenyi controla o erro familiar entre pares do ranking, mas o resultado é descritivo.
- Nenhuma outra comparação é confirmatória; tudo mais é rotulado "descritivo/exploratório".

## 6. Tamanhos de efeito e intervalos

- Diferença média Δ em Macro-F1 (unidade natural, comparável a δ) e **dz de Cohen pareado** (Δ̄/s_Δ) em H1, H2 e sensibilidade.
- IC95% de Nadeau–Bengio para toda diferença entre seeds.
- **IC por bootstrap por paciente (cluster bootstrap)** da Macro-F1 de teste, estratégia `none`, variante A, para os 8 primários, e do contraste complexo − simples de H1, **por seed**: matriz de confusão 5×5 por paciente; reamostragem de pacientes com reposição (pesos multinomiais) somando matrizes; mesma reamostra para todos os modelos de uma seed (contrastes pareados); percentil 2,5/97,5; B = 1000 (configurável); semente derivada de (seed global, seed do split) para reprodutibilidade. Esse IC mede apenas a incerteza de amostragem do teste (não inclui variabilidade de treino) e **não é combinado entre seeds**; serve para mostrar se Δ por seed é distinguível do ruído do teste. Não substitui o critério de H1.

## 7. Regra de corte de seeds

A análise principal usa as seeds 1..10 se todas as células (modelos primários × estratégias aplicáveis da variante A, nas partições val e teste) estiverem completas em **10/11/2026 12:00 BRT**; senão, o maior k ≥ 5 tal que as seeds 1..k estejam completas; se k < 5, a análise principal não é executada. Decisão por **tempo e completude, nunca por resultado**: seeds fora do prefixo completo não são usadas mesmo que existam, e isso é registrado em `notes`. Rodar a análise antes do prazo é permitido apenas como prévia técnica e não conta como análise principal.

## 8. Modelos e estratégias ausentes ou falhos

- **Não aplicável por desenho**: knn × class_weight; dummies × (class_weight, oversample). Não é falha, não gera anomalia, é omitido das tabelas dessa estratégia.
- **Falha / ausente**: qualquer outra célula esperada sem Macro-F1 finito. Registrada como anomalia `ausente_ou_falha` (modelo, estratégia, seeds). Falha de modelo primário em seed do prefixo encurta o prefixo (seção 7); falha de extra não afeta a análise principal e o extra é retirado do ranking (nota explícita). Não há imputação nem substituição de valores.
- Valores NaN/inf são tratados como ausentes; linhas duplicadas: mantém-se a última e anota-se.
- Seções não computáveis (ex.: sem `predictions`) são omitidas com nota; a análise nunca "tenta outra coisa" para obter resultado.

## 9. Anomalias a sinalizar (não corrigir silenciosamente)

1. Modelo (primário ou extra) com Macro-F1 médio de teste abaixo do melhor dummy.
2. DP da Macro-F1 entre seeds > 0,02.
3. Classe com recall = 0 em alguma seed (por modelo/estratégia).
4. |Macro-F1 val − teste| médio > 0,03 (possível sobreajuste da seleção ou desvio de partição).
5. Célula ausente/falha; valores não finitos; duplicatas.
6. Δ de H1 com sinal inconsistente entre seeds (reportado pela coluna Δ por seed e pelo critério "todas > 0").
7. Qualquer incoerência entre `metrics` e `predictions` (nota).

Os limiares são fixados aqui e não serão ajustados após ver os resultados.

## 10. Divulgação (n < 11)

Contagens de 1 a 10 aparecem como "<11" em tudo que vai para relatório (inclui contagens por classe, removidas em B, tamanhos de células). Contagens 0 e ≥ 11 aparecem normalmente. Métricas agregadas podem aparecer normalmente. Contagens de seeds e de modelos são parâmetros do desenho, não contagens de pacientes, e não são mascaradas. As predições por estadia são privadas e nunca entram em relatório; o JSON/Markdown gerado contém apenas agregados, e contagens pequenas são mascaradas já no JSON.

## 11. O que NÃO será feito

- Nenhuma seleção de modelo, hiperparâmetro, estratégia, limiar ou seed pelo teste.
- Nenhuma troca de métrica primária, de δ, de α, das hipóteses ou da regra de corte após ver resultados.
- Nenhum Wilcoxon/t ingênuo sobre folds como evidência confirmatória.
- Nenhuma exclusão de seeds "ruins" ou escolha de subconjunto de seeds por desempenho.
- Nenhuma conclusão de superioridade com base em acurácia, ou em p-valor sem tamanho de efeito.
- Nenhum teste adicional para "obter significância"; se H1 falhar, reporta-se "sem superioridade consistente".
- Nenhuma generalização para outros hospitais ou conjuntos de dados; as conclusões valem para este conjunto e este protocolo.

## 12. Saídas

`run_preregistered_analysis` devolve um dicionário JSON-serializável com as chaves `seeds_used`, `h1`, `h2`, `h3`, `ranking`, `sensitivity_b_vs_a`, `bootstrap_ci`, `anomalies`, `notes` (mais `meta` e `seed_selection`); `render_stats_markdown` gera tabelas em português para o `summary.md`.

## Desvios

Registrar aqui qualquer desvio deste plano, com data, motivo, impacto esperado e se foi decidido antes ou depois de ver resultados.

| Data | Desvio | Motivo | Decidido antes de ver resultados? |
|---|---|---|---|
| 2026-11-05 | **Variante C (`C_values_only`)**: mesmas estadias de A, só valores medidos (sem indicadores de ausência e sem `pain_status`), estratégia `none`. Descritiva: diferença A − C por modelo (pareada por seed, t corrigido, sem correção múltipla). | Revisão teórica: ausência de sinais vitais é proxy forte de acuity 1 (temperatura ausente em 36,9% da classe 1 vs 1–3,6% nas demais; só essa regra rende ≈ 0,09 de Macro-F1). | Sim — nenhuma campanha tinha rodado. |
| 2026-11-05 | **Relato estratificado do teste**: estadias com os 6 sinais + dor numérica (“completos”) × o resto, por modelo, a partir das predições salvas (sem re-treino). Descritivo. | Mesmo motivo; separar fisiologia de padrão de documentação. | Sim. |
| 2026-11-05 | Nova métrica descritiva `under_triage_rate_urgent` = P(ŷ > y \| y ≤ 2). | A taxa marginal de subtriagem mistura prevalência. | Sim. |
| 2026-11-05 | Decodificações secundárias **descritivas**, sem novo HPO, a partir de `predict_proba` salvos: mediana da posterior (ótima para MAE) e argmax p_k/π_k (ótima para balanced accuracy); para CW/ROS desfaz-se antes a mudança de prior. Só se houver tempo (F5); nunca substituem a análise principal (argmax). | Separar capacidade do modelo da regra de decisão. | Sim. |
| 2026-11-05 | H1 secundária (descritiva): estratégia escolhida por modelo na validação (melhor Macro-F1 de val entre none/CW/ROS). | Revisão teórica. | Sim. |
| 2026-11-05 | Espaços/parâmetros fixos antes da campanha: RF/ExtraTrees com 200 árvores fixas (RAM: 5–16 GB por modelo com 400); SVM com C ∈ [0,01; 100] e γ ∈ [0,001; 1] (γ = 10 interpola); HGB `early_stopping=False` explícito (coerência com XGB); GNB com entrada padronizada e `var_smoothing` ∈ [1e-9; 1] (faixa usual do sklearn; o smoke sintético mostrou que indicadores binários sem variância numa classe exigem suavização maior); indicadores de ausência sem padronização; até 2 tarefas RF/ET simultâneas. | Revisão teórica + custo/RAM. | Sim. |
| 2026-11-05 | Limitações declaradas da revisão: MLP com ROS tem validação interna do early stopping contaminada por duplicatas; `batch_size` altera o peso efetivo de classe no MLP-CW; SVM treina com ~79 estadias de classe 5 (subamostra de 30 mil); 20 configs saturam espaços 1-D (LR, GNB, ordinal) mas não espaços 7–9-D (XGB/RF), o que tende a favorecer o grupo simples em H1. | Transparência. | Sim. |
