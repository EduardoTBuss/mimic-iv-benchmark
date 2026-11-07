# Independent six-page manuscript review

Task: `MIMIC-COTB-2027-six-page-review`, resumed 2026-11-07. Reviewer: independent Codex research-artifact consistency reviewer. Source base: `f8280cc26f1c7bdd424fd5d19c176ad87f3e8e82`; final manuscript is a working-tree revision unless otherwise recorded below.

## Scope and provenance

The requested scope is the English six-page manuscript, three conceptual vector figures, source-supported claims, consistency with the fixed protocol and implementation, and the authored PDF. This is an editorial/method-consistency review, not acceptance of an empirical study or a submission-ready paper.

Supplied Brain provenance: `C:/Users/eduar/Brain/projects/cotb-paper-b-mimic-iv-ed-triagem.md`, execution checkpoints dated 2026-11-06/07, and `C:/Users/eduar/Brain/raw/contexto/ideia-cotb-paper-b-mimic-iv-ed-2026-11-04.md`. The original question compares eight simple/complex tabular models using six vital signs plus pain to predict recorded ordinal acuity, with patient splits, train-only preprocessing, ordinal errors, grouped permutation importance and computational cost. The fixed decisions are in `docs/analysis_plan.md`; neither that plan nor scientific code was changed by this reviewer. No direct Brain access occurred.

No actual `reports/`, `outputs/`, `private/`, `data/`, `datasets/`, patient file, campaign result, aggregate result or empirical derivative was listed or opened. Code under `src/triagebench/data/` is source, not patient data. The only PDF inspected is the authored `output/pdf/cotb2027-mimic-iv-ed-draft.pdf`. No project import, CLI, test, experiment, external upload or external runtime was used. No data-derived value embedded in methodology/source comments is treated as approved manuscript evidence.

Applied skills: supplied-context `brain-context`, `paper-figure-table-checklist`, `scientific-run-manifest` as a provenance checklist only, `pdf` for visual review, and `agent-result-contract`. No experiment manifest was created because no experiment was run. The existing independent statistical review in `docs/reviews/2026-11-06-protocol-code-review.md` remains the methodological review of unchanged H1/H2 mechanisms; this pass does not independently certify the statistical procedure's coverage.

## Claim and artifact traceability

All raw-result entries below are **not accessed / not authorized for this review**. No table, figure or caption in the reviewed draft may substitute a schematic or a missing-evidence marker for an empirical observation.

| Material claim | Equations / plan / configuration | Implementation or public evidence | Manuscript artifact | Raw-result status and interpretation |
|---|---|---|---|---|
| Recorded acuity 1–5; six vital signs plus pain; version 2.2 | `configs/main.yaml`: dataset/features | Official dataset/table records documented in `docs/literature_review.md`; `src/triagebench/data/schema.py` | Abstract; Methods 3.1; Figure 1 input box | No cohort size or label distribution established; clinical benefit is not inferred. |
| Earlier acuity work and differing downstream outcomes | No experimental equation | `docs/literature_review.md` source register; `paper/references.bib` | Related Work; Table 1 and caption | Bounded literature synthesis, not an empirical cross-paper ranking. Chonde/SCC access limitations are explicit. |
| Ten patient-disjoint 70/15/15 splits, most-urgent-visit stratification | Analysis-plan design; `configs/main.yaml`: split | `src/triagebench/data/split.py:16`; `runner/data_stages.py` shared A map | Methods 3.2; Figure 1 and caption | Fractions refer to patients; metrics to visits. Different seeds overlap and are not independent cohorts. |
| Train-only median imputation/scaling, binary absence indicators | Variant feature lists in `configs/main.yaml` | `preprocessing/pipeline.py:13`; `evaluation/protocol.py` | Methods 3.2; Figure 1 | Static design alignment only; no empirical leakage audit. |
| A keeps valid-label visits; B keeps plain numeric pain in [0,10]; C retains A visits without explicit flags/status | Analysis-plan sensitivity amendment; `configs/main.yaml`: variants | `preprocessing/pain.py` numeric-kind predicate; `runner/data_stages.py` map reuse | Methods 3.2; Figure 2 and caption | B excludes ranges/fractions even when parsable; A/B uses common test visits, A/C holds membership fixed. No causal decomposition claimed. |
| Eight primary models, four per group; extras/dummies excluded from H1; SVM/KNN caps | `configs/models.yaml`: groups/subsample; 20 configurations in `configs/main.yaml` | `evaluation/protocol.py:79`; `models/imbalance.py` | Methods 3.3; Table 2 and footnote | Budget is number of configurations, not equal compute or coverage. Caps apply after oversampling. |
| Macro-F1, MAE, QWK and signed ordinal disagreement | `d = predicted - recorded`; severe undertriage `d >= 2` | `evaluation/metrics.py:24` | Methods 3.4; Figure 3 and caption | All 25 schematic cells are arithmetic differences, not counts. Positive means less urgent prediction. No clinical harm weights established. |
| H1 is a comparison of validation-selected group procedures on A/none | `Delta_s = complex - simple`; Eq. 1; margin 0.01; all positive plus corrected lower 95% bound > 0.01 | `analysis/stats.py:267`, `:582`, `:598`; analysis-plan H1 | Methods 3.4; Results evidence slot; Discussion | No decision or effect estimate authorized. Failure to meet criterion does not establish equivalence. |
| H2 uses paired changes in class-1 recall, Macro-F1 and balanced accuracy | Analysis-plan H2; six strategy–metric Holm families | `analysis/stats.py:651`; two-sided corrected-t `p` | Methods 3.4; Results evidence slot; Discussion | Three positive means and adjusted p < 0.05 required per model/strategy. No global six-family multiplicity claim. |
| Bootstrap is patient-clustered, within-seed and excludes retraining uncertainty | 1,000 resamples; analysis-plan uncertainty section | `analysis/stats.py:338`, `:803` | Methods 3.4 | Not a replacement for H1; no numerical interval checked. |
| Grouped permutation importance measures model reliance | Selection by mean validation Macro-F1; no rebalancing | `analysis/importance.py:25`, `:37`, `:45` | Methods 3.5; Discussion | Raw vital and generated indicator remain linked; pain value/status share permutation. No causal importance asserted. |
| Controlled cost uses A/seed 1, three sequential one-thread refits and validation inference | `configs/main.yaml`: evaluation.cost_benchmark | `evaluation/costbench.py:23`; milliseconds per 1,000 visits | Methods 3.6; cost evidence slot; Discussion | Measurement settings/hardware provenance pending; concurrent campaign timings are not controlled benchmarks. |
| Deadline/prefix and principal certification remain gated | 2026-11-10 noon BRT = 15:00 UTC; at least five-seed complete prefix | `analysis/stats.py:62`, `:74`, `:108` | Methods 3.6; Discussion validity | Current code explicitly keeps `principal_analysis=False`; immutable cutoff provenance remains unresolved. |

The displayed design parameters (eight primary models, ten seeds, 70/15/15 patient fractions, 20 configurations, 30,000/100,000-row caps, 1,000 bootstrap samples, 0.01 margin, 95% intervals, 0.05 H2 threshold, three timing repetitions, and [0,10] plain numeric pain range) agree with the inspected plan/configuration. They are protocol values, not observed sample counts. There are no reported empirical percentages, rounded scores or significance results to recompute.

## Findings and minimal corrections

1. **Reproducibility-blocking wording, corrected before this resumed pass:** B was described as retaining any valid parser-produced numeric value. The parser also produces values from ranges/fractions, but B uses the plain-numeric kind. Current Methods, Figure 2 card and caption specify plain numeric pain in [0,10] and exclude ranges/fractions.
2. **Reproducibility-blocking omission, corrected before this resumed pass:** Timing referred to a “specified variant and seed” without naming them. Current Methods identifies A, seed 1, three repetitions and validation-visit inference.
3. **Claim-affecting ambiguity, corrected in the final source revision:** “Single confirmatory criterion” in the opening could conceal the registered H2 tests. The revised opening identifies the primary H1 superiority rule, separate H2 tests and descriptive analyses. It also states that H1 compares validation-selected procedures; no hypothesis changed.
4. **Reproducibility-blocking wording, corrected in the final source revision:** H2 now explicitly names variant A, paired test-set differences and the same corrected resampled t procedure with two-sided p values.
5. **Clerical/terminological clarification, corrected in the final source revision:** “Excluding chief-complaint text” replaces the broader “excluding free text,” preserving the fact that pain strings are parsed into structured features.

The fuller discussion remains conditional and tied to the original question. It distinguishes procedure comparison from intrinsic algorithm superiority, recorded-label disagreement from clinical harm, observational sensitivity from causal effects, and fixed configuration count from equal computational budgets. No new experiment, endpoint, superiority decision, primacy claim or deployment-readiness claim is introduced. Failure/convergence accounting and MLP early-stopping/weighting limits remain visible. The final editorial pass replaces repetitive author instructions with concise visible missing-evidence markers and reader-oriented Results prose. The absence of campaign estimates is explicit rather than obscured. No unresolved source-level manuscript finding remains within this review scope.

## Final PDF acceptance

**ACCEPT for editorial clarity, method consistency and six-page authored-draft presentation. Not accepted as a complete empirical or submission-ready paper.** No unresolved manuscript correction was found within the assigned scope after the final revisions.

The coordinator sent the final-ready signal on 2026-11-07. This reviewer independently reopened and rendered the authorized final PDF with system Python/PyMuPDF, then visually inspected all six pages at 1.5x resolution. It is six nonempty letter-size pages (612 x 792 pt), with no clipped text, overlapping captions, unreadable figure labels, broken equations or unresolved citation glyphs observed. Headers and anonymous submission markers are present on every page. No extracted text block extends outside its page. The log reports a six-page build and no overfull, undefined-reference or missing-character warning in the scoped search; underfull box warnings remain and correspond to acceptable whitespace in this draft. Compilation itself was performed by the coordinator, not by this reviewer.

Figure 1 has continuous directional arrows from fixed inputs through validation selection and frozen refitting to test assessment. Its caption restricts the 20-configuration workflow to predictive models, consistent with the dummy exception in prose. Figure 2 correctly shows A/C common membership and the plain-numeric B subset, without making equal card sizes represent cohort sizes. Figure 3's 25 signed differences match predicted minus recorded labels; the diagonal is zero, positive values run above it and negative below. Signs, numeric entries and text duplicate the color distinction. Captions explicitly distinguish schematics from observations and clinical loss. Each figure has a source `Description`; full PDF accessibility conformance was not audited. The PDF has no raster image objects, and its drawing objects support the intended vector presentation.

The final abstract, Results opening, Table 3, and conclusion visibly disclose missing empirical evidence. All nine bibliography entries are rendered and the paper makes no invented score, significance, cohort-count or clinical-readiness claim. Normal ACM column and float breaks remain; the main text and reference list are legible at page scale.

| Final artifact | SHA-256 |
|---|---|
| `output/pdf/cotb2027-mimic-iv-ed-draft.pdf` | `27ff40239c552fdef777d08d752ea72e9af0b67b2dc96d06b526212852da14a6` |
| `paper/main.tex` | `7f72754000cfa422600b6329a7908f37789507a9b8ea1c65d4b35da9ffc0f71d` |
| `paper/figures/benchmark-flow.tex` | `680a8fd49885988211eac4271850745b3289b00c365a7e2c6215678283e1b001` |
| `paper/figures/representation-variants.tex` | `4664c76e7e9718d43411fc18815fc29e264531762b5926abfea009c95d283872` |
| `paper/figures/ordinal-disagreement.tex` | `1223b5d46a7da98ee9a612196e5171b48e236185310c780e924286885a62aa73` |
| `docs/analysis_plan.md` | `88682f1f703f6148794ff5af56c637359585a5a7a66312f4b74e1a5fdf0b86cc` |

Reviewer renders: `paper/build/final-editorial-independent-review/page-1.png` through `page-6.png`. System Python rendering/hash diagnostics, PowerShell `Get-FileHash`, and log searches exited 0. The reviewer did not copy or verify the separate Downloads delivery; that remains the coordinator's delivery step.

## Evidence handoff

- **Outcome:** ACCEPT for editorial/method consistency and the six-page authored draft only; all five bounded wording findings resolved. No empirical or submission-readiness acceptance.
- **Scope:** Authored manuscript/figures, fixed methodology, source and existing public-source register only.
- **Changes:** This review file only; temporary authored-PDF renders under `paper/build/` are review aids. No manuscript/source/configuration edit, commit or Brain write by this reviewer.
- **Validation:** PowerShell read/search commands and `git rev-parse HEAD` exited 0. A scoped `git diff HEAD` over the plan and principal method/configuration files was empty. Independent final PyMuPDF rendering, six-page diagnostics and SHA-256 verification exited 0; all six renders visually checked. No tests run by task instruction.
- **Artifacts:** This review; final PDF and manuscript/figure hashes recorded above; temporary renders under `paper/build/final-editorial-independent-review/`.
- **Risks or unresolved items:** Approved empirical evidence, principal cutoff/inventory/content provenance, data-service eligibility, hardware/timing provenance, disclosure review and final author approval remain outstanding. These block a complete empirical/submission-ready paper, not editorial acceptance of a clearly labeled draft.
- **Independent review:** This reviewer performed the manuscript/artifact consistency pass. The prior independent statistical review supplies the unchanged-method context. No reviewer was spawned or other runtime contacted.

Proposed Brain checkpoint for coordinator review: `2026-11-07 — Independent editorial/artifact review accepts the six-page English COTB authored draft for clarity and consistency with the unchanged protocol, including three conceptual vector figures. Final PDF SHA-256 27ff40239c552fdef777d08d752ea72e9af0b67b2dc96d06b526212852da14a6. H1/H2 roles, plain-numeric B membership, and A/seed-1 validation-inference cost workload are explicit; pending evidence remains visible. Evidence: docs/reviews/2026-11-07-final-editorial-independent-review.md. This is not empirical certification or submission readiness: approved results, immutable principal cutoff/content provenance, eligibility and disclosure/author review remain pending. No restricted artifact, project execution, new experiment, scientific-plan change or direct Brain write by the reviewer. Coordinator owns Downloads delivery and Brain integration.`
