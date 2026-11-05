# Plano aprovado (04/11/2026)

Missão: `C:\repositorio\prompts\mimic-ed-triage-maestro-experimento.md` (CoTB 2027, Paper B).
Escopo deste repositório: **código e experimentos**; o artigo não é escrito aqui.

## Contexto confirmado (04/11/2026)

- **Computer on the Beach 2027** (site oficial): submissão 15/11/2026 (JEMS/SBC), notificação
  16/02/2027, artigo completo ≤ 6 páginas com referências, duplo-cego, PT/EN/ES com título,
  abstract e keywords em inglês, "Declaração de Uso de IA" obrigatória na versão final.
- **MIMIC-IV-ED v2.2** (05/01/2023, DOI 10.13026/5ntk-km72): `triage` tem 11 colunas e já traz
  `subject_id`; `pain` é texto livre desde a v2.0; a v2.2 removeu 22.625 `stay_id`.
- Literatura próxima (varredura rápida, só títulos): regressão logística ordinal para `acuity`
  no MIMIC-IV-ED (2025); predição de acuity no MIMIC-IV-ED (IEEE SCC 2023); benchmark de Xie
  et al. 2022 (acuity como entrada). Não alegar primazia.

## Decisões do Eduardo (04/11, ~23h)

| Tema | Decisão |
|---|---|
| Modelos | os 8 da proposta + extras permitidos (HGB, ExtraTrees, logística ordinal) + 2 dummies |
| Seeds | 10 divisões por paciente (prioridade às seeds 1–5) |
| `pain` | manter as strings (como categoria `pain_status`), documentado; remoção = sensibilidade (B) |
| Faixas fisiológicas | analisar com os dados antes de fixar; o modelo só recebe número |
| Servidor | Q-FLEX (zip enviado do notebook, pasta organizada no usuário); x299 liberado como reserva |
| GitHub | repositório privado com commits frequentes para mostrar progresso |
| Nome | `ed-triage-benchmark` (pacote `triagebench`), proposto pelo maestro |

Defaults do plano não contestados: seleção por Macro-F1 na validação, 20 configurações por
modelo (calibrado pelo piloto e congelado antes da campanha), H1 simples {LR, NB, KNN, DT} ×
complexos {RF, SVM, XGB, MLP} com δ = 0,01, SVM-RBF em subamostra de 30 mil do treino.

## Fluxo de um experimento

```
para cada seed s em 1..10:
    dividir PACIENTES em treino 70% / validação 15% / teste 15% (estratificado pelo acuity mais urgente)
    para cada variante (A, B), modelo m e estratégia e (none, class_weight, oversample):
        20 configurações (a 0 = padrão da biblioteca) -> treina no treino, mede na VALIDAÇÃO
        congela a melhor (Macro-F1 de validação)
        re-treina a congelada no treino -> avalia no TESTE uma única vez (trava em código)
=> cada (modelo, estratégia, variante) tem 10 métricas de teste independentes -> estatística
```

## Fases

| Fase | Entrega |
|---|---|
| F0 | esqueleto, lock, governança (iscas + hook), CI |
| F1 | ingestão com SHA256, auditoria agregada (`reports/data_audit.md`), regras de limpeza decididas |
| F2 | splits por paciente, pipelines sem vazamento, testes de vazamento, `docs/analysis_plan.md` |
| F3 | runner retomável (8 + extras), HPO na validação, teste 1×, manifestos |
| F4 | desbalanceamento × métricas ordinais, tabelas por classe, distância ordinal |
| F5 | permutation importance, estatística pareada, ablação (se houver tempo) |
| F6 | relatório automático, runbook do servidor, arquivamento no Brain |

## Critérios de parada (o maestro para e pergunta)

Colunas diferentes da v2.2, `stay_id` duplicado, `subject_id` divergente entre `triage` e
`edstays`, risco para dado ou servidor. Fora disso, decide, registra em `docs/decisions/` e segue.
