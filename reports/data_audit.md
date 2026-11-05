# Auditoria do dataset (somente agregados)

> Gerado automaticamente por `triagebench audit`. Contagens de 1 a 10 aparecem como `<11`;
> percentuais derivados delas aparecem como `—`. Nenhuma linha, identificador ou registro individual.

## 1. Proveniência

| item | valor |
|---|---|
| dataset | MIMIC-IV-ED v2.2 |
| DOI | 10.13026/5ntk-km72 |
| URL | https://physionet.org/content/mimic-iv-ed/2.2/ |
| arquivo | mimic-iv-ed-2.2.zip |
| SHA256 do zip | `d17bbf2efe6a4a7e0f29c73b0743e6d2b7fb840e9b1a14f9064f23c70d868fc9` |
| SHA256 triage.csv.gz | `fde3d5910215454feec9494fcd2248c3ff7d871001990a8ac43ef67289d4d0d3` |
| SHA256 edstays.csv.gz | `33b3f4f07a075d725289241201fc39426437506688ebfc4cb69f45a5052a56d6` |
| verificação SHA256SUMS.txt | todos os 8 arquivos OK (2026-11-05T02:23:09+00:00) |

## 2. Schema e consistência

Colunas de `triage` e `edstays` idênticas à documentação da v2.2 (checagem automática). `chiefcomplaint` nunca é carregada.

| checagem | contagem |
|---|---|
| triage_duplicated_stay_id | 0 |
| edstays_duplicated_stay_id | 0 |
| triage_stays_not_in_edstays | 0 |
| edstays_stays_without_triage | 0 |
| subject_id_mismatch | 0 |
| valor não numérico convertido em NaN: temperature | 0 |
| valor não numérico convertido em NaN: heartrate | 0 |
| valor não numérico convertido em NaN: resprate | 0 |
| valor não numérico convertido em NaN: o2sat | 0 |
| valor não numérico convertido em NaN: sbp | 0 |
| valor não numérico convertido em NaN: dbp | 0 |
| acuity não numérica | 0 |

## 3. Coorte

| item | valor |
|---|---|
| linhas na triage | 425,087 |
| estadias distintas | 425,087 |
| pacientes distintos (subject_id) | 205,504 |
| estadias por paciente (média) | 2.07 |
| estadias por paciente (mediana / p90 / p99 / p99.9) | 1 / 4 / 14 / 39 |

| visitas por paciente | pacientes | estadias | % das estadias |
|---|---|---|---|
| 1 | 135,552 | 135,552 | 31.89% |
| 2 | 32,672 | 65,344 | 15.37% |
| 3-5 | 25,452 | 92,483 | 21.76% |
| 6-10 | 8,114 | 59,924 | 14.10% |
| 11-20 | 2,774 | 38,704 | 9.10% |
| >=21 | 940 | 33,080 | 7.78% |

## 4. Distribuição de `acuity` (alvo)

| acuity | estadias | % |
|---|---|---|
| 1 | 24,019 | 5.65% |
| 2 | 139,411 | 32.80% |
| 3 | 225,066 | 52.95% |
| 4 | 28,504 | 6.71% |
| 5 | 1,100 | 0.26% |
| ausente | 6,987 | 1.64% |
| fora de 1..5 | 0 | 0.00% |

## 5. Ausentes por variável

| variável | ausentes | % geral | % em acuity 1 | % em acuity 2 | % em acuity 3 | % em acuity 4 | % em acuity 5 |
|---|---|---|---|---|---|---|---|
| temperature | 23,415 | 5.51% | 36.85% | 3.41% | 1.17% | 1.10% | 3.64% |
| heartrate | 17,090 | 4.02% | 28.24% | 1.85% | 0.35% | 0.34% | 2.45% |
| resprate | 20,353 | 4.79% | 31.41% | 2.67% | 0.92% | 0.67% | 2.64% |
| o2sat | 20,596 | 4.85% | 31.05% | 2.68% | 1.03% | 0.84% | 3.55% |
| sbp | 18,291 | 4.30% | 28.96% | 2.07% | 0.61% | 0.81% | 3.09% |
| dbp | 19,091 | 4.49% | 29.61% | 2.23% | 0.78% | 0.95% | 3.36% |
| pain_raw | 12,896 | 3.03% | 13.19% | 1.09% | 0.57% | 0.55% | 1.36% |

Estadias sem nenhum dos 6 sinais vitais nem dor: 8,579.

## 6. Sinais vitais: distribuição e faixas

Faixas de Xie et al. (2022) (temperatura convertida para °F): abaixo/acima do limite de outlier → NaN; entre o limite de outlier e o limite válido → valor cortado no limite. A faixa clínica é só referência de auditoria.

### temperature

| n não ausentes | média | q0.001 | q0.01 | q0.05 | q0.25 | q0.5 | q0.75 | q0.95 | q0.99 | q0.999 |
|---|---|---|---|---|---|---|---|---|---|---|
| 401,672 | 98.02 | 37.0 | 96.0 | 96.7 | 97.5 | 98.0 | 98.6 | 99.6 | 101.3 | 103.5 |

| faixa | acuity 1 | acuity 2 | acuity 3 | acuity 4 | acuity 5 | acuity ausente | total | % dos não ausentes |
|---|---|---|---|---|---|---|---|---|
| below_outlier_low (NaN) | 29 | 215 | 223 | 12 | 0 | 0 | 479 | 0.12% |
| clip_to_valid_low | <11 | 12 | 15 | <11 | 0 | 0 | 29 | 0.01% |
| valid | 15,139 | 134,423 | 222,186 | 28,177 | 1,060 | 170 | 401,155 | 99.87% |
| clip_to_valid_high | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% |
| above_outlier_high (NaN) | 0 | <11 | <11 | 0 | 0 | 0 | <11 | — |
| clínica: abaixo de 86.0 | 37 | 236 | 242 | 15 | 0 | 0 | 530 | 0.13% |
| clínica: acima de 110.0 | 0 | <11 | <11 | 0 | 0 | 0 | 13 | 0.00% |
| valor exatamente 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% |
| parece °C: 25.0–45.0 | 22 | 188 | 174 | <11 | 0 | 0 | 392 | 0.10% |

Valores com cara de °C: q0.05 / mediana / q0.95 = 35.9 / 36.6 / 37.7. Entre a faixa °C e o limite de outlier: <11.

### heartrate

| n não ausentes | média | q0.001 | q0.01 | q0.05 | q0.25 | q0.5 | q0.75 | q0.95 | q0.99 | q0.999 |
|---|---|---|---|---|---|---|---|---|---|---|
| 407,997 | 85.08 | 38.0 | 51.0 | 60.0 | 72.0 | 84.0 | 96.0 | 116.0 | 134.0 | 160.0 |

| faixa | acuity 1 | acuity 2 | acuity 3 | acuity 4 | acuity 5 | acuity ausente | total | % dos não ausentes |
|---|---|---|---|---|---|---|---|---|
| below_outlier_low (NaN) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% |
| clip_to_valid_low | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% |
| valid | 17,235 | 136,824 | 224,268 | 28,406 | 1,073 | 184 | 407,990 | 100.00% |
| clip_to_valid_high | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% |
| above_outlier_high (NaN) | <11 | <11 | <11 | 0 | 0 | 0 | <11 | — |
| clínica: abaixo de 20 | <11 | <11 | 12 | 0 | 0 | 0 | 22 | 0.01% |
| clínica: acima de 250 | <11 | <11 | <11 | 0 | 0 | 0 | <11 | — |
| valor exatamente 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% |

### resprate

| n não ausentes | média | q0.001 | q0.01 | q0.05 | q0.25 | q0.5 | q0.75 | q0.95 | q0.99 | q0.999 |
|---|---|---|---|---|---|---|---|---|---|---|
| 404,734 | 17.57 | 11.0 | 14.0 | 15.0 | 16.0 | 18.0 | 18.0 | 20.0 | 26.0 | 38.0 |

| faixa | acuity 1 | acuity 2 | acuity 3 | acuity 4 | acuity 5 | acuity ausente | total | % dos não ausentes |
|---|---|---|---|---|---|---|---|---|
| below_outlier_low (NaN) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% |
| clip_to_valid_low | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% |
| valid | 16,474 | 135,693 | 223,000 | 28,314 | 1,071 | 179 | 404,731 | 100.00% |
| clip_to_valid_high | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% |
| above_outlier_high (NaN) | 0 | 0 | <11 | 0 | 0 | 0 | <11 | — |
| clínica: abaixo de 4 | <11 | <11 | <11 | <11 | 0 | 0 | 19 | 0.00% |
| clínica: acima de 60 | 0 | 13 | 23 | <11 | 0 | 0 | 39 | 0.01% |
| valor exatamente 0 | 0 | <11 | <11 | <11 | 0 | 0 | <11 | — |

### o2sat

| n não ausentes | média | q0.001 | q0.01 | q0.05 | q0.25 | q0.5 | q0.75 | q0.95 | q0.99 | q0.999 |
|---|---|---|---|---|---|---|---|---|---|---|
| 404,491 | 98.47 | 82.0 | 92.0 | 95.0 | 97.0 | 99.0 | 100.0 | 100.0 | 100.0 | 100.0 |

| faixa | acuity 1 | acuity 2 | acuity 3 | acuity 4 | acuity 5 | acuity ausente | total | % dos não ausentes |
|---|---|---|---|---|---|---|---|---|
| below_outlier_low (NaN) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% |
| clip_to_valid_low | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% |
| valid | 16,557 | 135,662 | 222,719 | 28,262 | 1,061 | 183 | 404,444 | 99.99% |
| clip_to_valid_high | 0 | 0 | <11 | 0 | 0 | 0 | <11 | — |
| above_outlier_high (NaN) | <11 | 11 | 25 | <11 | 0 | 0 | 41 | 0.01% |
| clínica: abaixo de 50 | 11 | 35 | 40 | <11 | 0 | <11 | 92 | 0.02% |
| clínica: acima de 100 | <11 | 11 | 31 | <11 | 0 | 0 | 47 | 0.01% |
| valor exatamente 0 | <11 | <11 | <11 | 0 | 0 | 0 | <11 | — |

### sbp

| n não ausentes | média | q0.001 | q0.01 | q0.05 | q0.25 | q0.5 | q0.75 | q0.95 | q0.99 | q0.999 |
|---|---|---|---|---|---|---|---|---|---|---|
| 406,796 | 135.40 | 69.0 | 90.0 | 102.0 | 120.0 | 133.0 | 148.0 | 175.0 | 198.0 | 228.0 |

| faixa | acuity 1 | acuity 2 | acuity 3 | acuity 4 | acuity 5 | acuity ausente | total | % dos não ausentes |
|---|---|---|---|---|---|---|---|---|
| below_outlier_low (NaN) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% |
| clip_to_valid_low | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% |
| valid | 17,061 | 136,526 | 223,676 | 28,272 | 1,066 | 179 | 406,780 | 100.00% |
| clip_to_valid_high | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% |
| above_outlier_high (NaN) | <11 | <11 | <11 | 0 | 0 | 0 | 16 | 0.00% |
| clínica: abaixo de 50 | 20 | 61 | 100 | <11 | 0 | 0 | 190 | 0.05% |
| clínica: acima de 250 | <11 | 37 | 25 | 0 | 0 | 0 | 71 | 0.02% |
| valor exatamente 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% |

### dbp

| n não ausentes | média | q0.001 | q0.01 | q0.05 | q0.25 | q0.5 | q0.75 | q0.95 | q0.99 | q0.999 |
|---|---|---|---|---|---|---|---|---|---|---|
| 405,996 | 81.26 | 31.0 | 44.0 | 54.0 | 68.0 | 77.0 | 87.0 | 101.0 | 116.0 | 298.2 |

| faixa | acuity 1 | acuity 2 | acuity 3 | acuity 4 | acuity 5 | acuity ausente | total | % dos não ausentes |
|---|---|---|---|---|---|---|---|---|
| below_outlier_low (NaN) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% |
| clip_to_valid_low | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% |
| valid | 16,890 | 136,153 | 223,110 | 28,206 | 1,063 | 179 | 405,601 | 99.90% |
| clip_to_valid_high | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% |
| above_outlier_high (NaN) | 18 | 148 | 203 | 26 | 0 | 0 | 395 | 0.10% |
| clínica: abaixo de 20 | 17 | 55 | 68 | <11 | 0 | <11 | 152 | 0.04% |
| clínica: acima de 150 | 40 | 237 | 280 | 32 | 0 | <11 | 590 | 0.15% |
| valor exatamente 0 | <11 | <11 | <11 | 0 | 0 | 0 | 13 | 0.00% |

### Pressão: diastólica ≥ sistólica

| caso | acuity 1 | acuity 2 | acuity 3 | acuity 4 | acuity 5 | acuity ausente | total | % com ambas presentes |
|---|---|---|---|---|---|---|---|---|
| dbp ≥ sbp | 33 | 218 | 288 | 33 | 0 | <11 | 573 | 0.14% |

## 7. `pain` (texto livre desde a v2.0)

Classificação automática de cada valor bruto (os textos originais são preservados no dado privado).

| tipo (parser) | acuity 1 | acuity 2 | acuity 3 | acuity 4 | acuity 5 | acuity ausente | total | % |
|---|---|---|---|---|---|---|---|---|
| numeric | 14,035 | 127,152 | 215,411 | 27,881 | 1,070 | 175 | 385,724 | 90.74% |
| range | 27 | 257 | 679 | 49 | 0 | <11 | 1,014 | 0.24% |
| fraction | 0 | <11 | 15 | 0 | 0 | 0 | 21 | 0.00% |
| out_of_range | 1,738 | 4,613 | 4,588 | 243 | 11 | 12 | 11,205 | 2.64% |
| missing | 3,168 | 1,521 | 1,291 | 157 | 15 | 6,744 | 12,896 | 3.03% |
| unable | 3,192 | 4,442 | 2,121 | 60 | <11 | 49 | 9,868 | 2.32% |
| text_other | 1,859 | 1,420 | 961 | 114 | 0 | <11 | 4,359 | 1.03% |

| status (feature do modelo) | acuity 1 | acuity 2 | acuity 3 | acuity 4 | acuity 5 | acuity ausente | total | % |
|---|---|---|---|---|---|---|---|---|
| numeric | 14,062 | 127,415 | 216,105 | 27,930 | 1,070 | 177 | 386,759 | 90.98% |
| missing | 3,168 | 1,521 | 1,291 | 157 | 15 | 6,744 | 12,896 | 3.03% |
| unable | 3,192 | 4,442 | 2,121 | 60 | <11 | 49 | 9,868 | 2.32% |
| out_of_range | 1,738 | 4,613 | 4,588 | 243 | 11 | 12 | 11,205 | 2.64% |
| other | 1,859 | 1,420 | 961 | 114 | 0 | <11 | 4,359 | 1.03% |

Valores numéricos inteiros 0–10:

| dor | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| estadias | 140,791 | 5,910 | 13,904 | 16,124 | 19,723 | 29,219 | 25,218 | 31,427 | 41,746 | 20,221 | 41,006 |

Numéricos não inteiros (ex.: 7.5): 435.

Strings não numéricas distintas: 688. Abaixo, só as que aparecem ≥ 11 vezes (normalizadas: minúsculas, espaços colapsados); as raras somam 1,122 estadias em 619 strings.

| string normalizada | estadias | tipo atribuído |
|---|---|---|
| `13` | 10,921 | out_of_range |
| `unable` | 4,143 | unable |
| `uta` | 3,243 | unable |
| `critical` | 1,809 | text_other |
| `ua` | 1,683 | unable |
| `u/a` | 360 | unable |
| `c` | 323 | text_other |
| `crit` | 140 | text_other |
| `6-7` | 140 | range |
| `5-6` | 135 | range |
| `7-8` | 134 | range |
| `8-9` | 116 | range |
| `yes` | 113 | text_other |
| `3-4` | 109 | range |
| `4-5` | 94 | range |
| `2-3` | 89 | range |
| `?` | 88 | text_other |
| `ett` | 87 | unable |
| `u` | 81 | unable |
| `denies` | 76 | text_other |
| `12` | 69 | out_of_range |
| `mild` | 64 | text_other |
| `non-verbal` | 63 | unable |
| `11` | 62 | out_of_range |
| `o` | 61 | text_other |
| `1-2` | 54 | range |
| `prehosp` | 54 | text_other |
| `moderate` | 52 | text_other |
| `refused` | 48 | text_other |
| `alot` | 46 | text_other |
| `20` | 45 | out_of_range |
| `bad` | 43 | text_other |
| `sleeping` | 42 | unable |
| `unknown` | 41 | text_other |
| `not bad` | 38 | text_other |
| `asleep` | 37 | unable |
| `pre-hosp` | 35 | text_other |
| `pain` | 35 | text_other |
| `unresponsive` | 34 | unable |
| `n/a` | 31 | text_other |
| `"yes"` | 29 | text_other |
| `15` | 27 | out_of_range |
| `mucho` | 27 | text_other |
| `uncomfortable` | 25 | text_other |
| `"alot"` | 23 | text_other |
| `uanble` | 23 | unable |
| `9-10` | 23 | range |
| `discomfort` | 23 | text_other |
| `"pain"` | 21 | text_other |
| `refusing` | 21 | text_other |
| `it hurts` | 20 | text_other |
| `na` | 18 | text_other |
| `3t` | 18 | text_other |
| `"a little"` | 17 | text_other |
| `very bad` | 15 | text_other |
| `a little` | 15 | text_other |
| `unk` | 15 | text_other |
| `tightness` | 14 | text_other |
| `little` | 14 | text_other |
| `sore` | 13 | text_other |

## 8. Viés da variante B (remover `pain` não numérico)

Regra pré-registrada: B can be the primary analysis only if overall removal <= 5%, max/min class removal ratio <= 1.5 and Cramer's V < 0.05.

| acuity | estadias | removidas em B | % removida |
|---|---|---|---|
| 1 | 24,019 | 9,984 | 41.57% |
| 2 | 139,411 | 12,259 | 8.79% |
| 3 | 225,066 | 9,655 | 4.29% |
| 4 | 28,504 | 623 | 2.19% |
| 5 | 1,100 | 30 | 2.73% |

| indicador | valor |
|---|---|
| remoção total | 7.79% |
| razão máx/mín entre classes | 19.02 |
| V de Cramér (removida × acuity) | 0.3225 |
| B pode ser a análise principal? | **não** → A é a principal; B fica como sensibilidade |

