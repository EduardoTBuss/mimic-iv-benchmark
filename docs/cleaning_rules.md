# Regras de limpeza (decididas na F1, antes de qualquer modelo)

Fonte dos números: `reports/data_audit.md` (MIMIC-IV-ED v2.2, zip SHA256 `d17bbf2e…`, 425.087
estadias de 205.504 pacientes). Todas as regras vivem em `configs/cleaning.yaml`; mudar uma
regra muda o hash e cria uma campanha nova (nada é sobrescrito). Contagens antes/depois de cada
regra, por variante, ficam em `data_preparation.md` de cada campanha. **Nenhuma regra de valor
apaga estadia**: o valor vira ausente (NaN) e é imputado dentro do pipeline de treino, com
indicador de ausência.

## 1. Linhas (estadias)

| Regra | Variante | Efeito | Por quê |
|---|---|---|---|
| `acuity` ausente | A e B | remove 6.987 (1,64%) | sem rótulo não há treino nem avaliação; quase todas também não têm dor (6.744) — provável saída antes da triagem completa |
| `acuity` fora de 1..5 | A e B | 0 | checagem |
| `pain` não é número puro em [0, 10] | **só B** | remove 7,79% | ideia original; **viés forte**: remove 41,6% da classe 1 e 4,3% da classe 3 (V de Cramér 0,32). Pela regra pré-registrada, B não pode ser a análise principal → A é a principal, B é sensibilidade |

As linhas removidas ficam guardadas em `outputs/prepared/<hash>/private/excluded/`.

## 2. Sinais vitais (valor → NaN ou corte; a estadia fica)

Base citável: regra de dois níveis de Xie et al. (2022), *Sci Data* 9:658, pipeline público
`mimic4ed-benchmark` (faixas herdadas do MIMIC-Extract): fora de `[outlier_low, outlier_high]`
→ NaN; entre o limite de outlier e o limite válido → corte no limite válido. Xie et al. trabalham
em °C; usamos os mesmos limites convertidos para °F.

| Variável | Regra | Afetados (auditoria) | Justificativa |
|---|---|---|---|
| temperature | 25–45 interpretado como °C e convertido para °F | 392 (0,10%) | mediana 36,6, q5–q95 = 35,9–37,7: são °C digitados no campo em °F. Xie et al. os transformariam em NaN; converter preserva medidas reais |
| temperature | Xie: < 57,56 °F → NaN; 57,56–78,8 → 78,8; > 116,6 → NaN | ~90 NaN + 29 cortes (≈0,03%) | valores incompatíveis com paciente vivo ou erros de digitação |
| heartrate, resprate, o2sat, sbp, dbp | Xie (ex.: FC > 390, o2sat > 150, PA > 375 → NaN; o2sat 100–150 → 100) | ≤ 0,10% por variável (dbp > 375: 395) | faixas publicadas, mínima intervenção |
| heartrate, resprate, o2sat, sbp, dbp | valor exatamente 0 → NaN | < 0,01% (dbp: 13) | impossível num paciente triado (Xie aceitaria 0) |
| sbp/dbp | diastólica ≥ sistólica → ambas NaN | 573 (0,14%) | fisiologicamente impossível; provável troca/erro de digitação |

Faixa clínica mais estreita (ex.: FC 20–250, o2sat 50–100, dbp 20–150) é **só referência de
auditoria**: valores entre ela e as faixas de Xie (ex.: dbp 150–375, 590 estadias) ficam como
estão. Nenhuma regra atinge mais de 0,2% dos valores de qualquer variável.

## 3. `pain` (texto livre desde a v2.0) — as strings são mantidas

O texto original fica preservado (`pain_raw`, privado). O modelo recebe dois campos:

* `pain_value`: número em [0, 10] (inteiro, decimal, faixa "5-6" → média 5,5, "7/10" → 7) ou NaN;
* `pain_status`: categoria do motivo, **uma das 5**:

| Status | O que entra | Estadias | % na classe 1 vs classe 3 |
|---|---|---|---|
| `numeric` | número em [0, 10], faixa, fração | 386.759 (91,0%) | — |
| `missing` | vazio | 12.896 (3,0%) | 13,2% vs 0,6% |
| `unable` | unable, uta, ua, u/a, u, uanble, non-verbal, unresponsive, intubat/ett, sedat, aphasic, unconscious, asleep, sleeping | ≈ 9,7 mil (2,3%) | 12,7% vs 0,9% |
| `out_of_range` | número fora de [0, 10]; **"13" sozinho = 10.921** (vs 69 para "12") | 11.205 (2,6%) | 7,2% vs 2,0% |
| `other` | qualquer outro texto: critical/crit/c, descrições (mild, bad, alot…), refused, denies, ?, unknown, n/a | ≈ 4,6 mil (1,1%) | — |

Decisões e cuidados:

* **"13" é um código do sistema, não uma nota de dor** (frequência 150× maior que 12 ou 11), por
  isso tem categoria própria em vez de ser misturado a texto.
* **"critical"/"crit" não ganham categoria própria**: é a avaliação de gravidade da enfermagem
  escrita no campo de dor, quase o próprio rótulo (proxy de `acuity`). Ficam em `other` e o risco
  está registrado; a ablação sem `pain_status` (F5) mede quanto do desempenho vem daí.
* Nada de texto é convertido em número por interpretação (ex.: "denies" não vira 0).

## 4. Achado que vai para a análise: ausência informativa

Sinais vitais ausentes são **muito** mais frequentes na classe 1 (28–37%) que na classe 3 (~1%),
e `pain` não numérico também. Os indicadores de ausência (SimpleImputer `add_indicator=True`)
deixam o modelo usar isso. É informação real do momento da triagem, mas reflete fluxo de
documentação (paciente crítico vai direto para a sala de emergência) e não fisiologia — fica
como **anomalia/limitação** no relatório e como ablação (sem indicadores) na F5.
