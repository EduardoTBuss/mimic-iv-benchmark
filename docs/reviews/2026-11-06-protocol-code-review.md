# Independent static protocol-to-code review

Task: `MIMIC-COTB-2027-code-review`
Reviewer: Codex `experiment-design-statistics-reviewer`
Date: 2026-11-06
Source HEAD: `458a050667c7e9e6df6150c373e28c423db8411d` (verified with `git rev-parse HEAD`).

Citation convention: source paths such as `analysis/stats.py` are relative to `src/triagebench/`; bare `analysis_plan.md` refers to `docs/analysis_plan.md`. Other paths are repository-relative. Line references identify the reviewed source at this HEAD.

This review compares `docs/analysis_plan.md` with source, configuration, methodology documentation and synthetic test source. It does not establish campaign completion, empirical performance, correctness of stored results or data-service eligibility. No project import, CLI invocation, test, campaign, network call or restricted-artifact inspection was performed. In particular, no `private/`, `outputs/`, `data/`, `datasets/`, `reports/` or campaign-derived artifact was listed or opened. Reading `src/triagebench/data/*.py` means reading source code, not patient data.

Brain provenance is the coordinator's supplied bundle: `C:/Users/eduar/Brain/projects/mimic-iv-benchmark.md` (2026-11-04/05), `mimic-iv-benchmark-execucao.md`, checkpoint 5 (2026-11-06), and `cotb-paper-b-mimic-iv-ed-triagem.md` (2026-11-04). No direct vault access or Brain decision change occurred.

## Recovered design and estimands

- The target is recorded ordinal acuity 1..5 at an ED stay, using six vital signs and parsed pain. Patients define split groups; stays define the metric observations; seeds define the inferential units. This is label prediction within one dataset, not a patient-outcome or intervention-effect study (`analysis_plan.md:9-21`; `configs/main.yaml:35-40`).
- H1 is the test Macro-F1 difference between two validation-selected procedures: the best of four complex models minus the best of four simple models, separately for each seed, A/none. It does not estimate an intrinsic advantage of every complex algorithm. All seed differences must exceed zero and the corrected bilateral 95% CI lower bound must exceed 0.01 (`analysis_plan.md:25-31`).
- H2 compares each applicable rebalancing strategy with none within each primary model on A. Support requires positive differences and Holm-adjusted p < 0.05 for all three endpoints: recall_1, Macro-F1 and balanced accuracy. Class weighting and oversampling also receive their own validation-based HPO; H2 is therefore a comparison of tuned training procedures (`analysis_plan.md:12,33-34`).
- The configured design uses seeds 1..10, patient fractions 70/15/15, patient minimum acuity for stratification, 20 configurations including defaults, and train-only refits. Extras and dummies do not enter H1 (`configs/main.yaml:76-88`; `configs/models.yaml:8-14`; `evaluation/protocol.py:95-138`).
- B excludes nonnumeric pain and shares A's patient map. Its comparison with A is restricted to common test stays. C shares A's stays, removes explicit missingness indicators and pain status, and uses none only (`configs/main.yaml:45-74`; `runner/data_stages.py:138-149`; `analysis_plan.md:41,117`). These are descriptive sensitivity analyses.

## Prioritized implementation findings

### P1 — The registered calendar cutoff is not enforced or captured

**Requirement:** `docs/analysis_plan.md:72` fixes the principal analysis set at **2026-11-10 12:00 BRT (15:00 UTC)** and requires earlier analyses to be technical previews. The prefix depends on completeness at that time.

**Evidence:** `analysis/stats.py:393-430` selects from currently present finite validation/test Macro-F1 cells only. Neither its inputs nor the result metadata carry an analysis time, cutoff snapshot or preview/principal status (`analysis/stats.py:840-879`). `runner/pipeline.py:70-84` rebuilds current aggregates and writes statistics without such a distinction. The report labels them preregistered analysis (`reporting/summary.py:259-262`).

**Consequence:** An early run can appear principal, and an analysis rerun after late completions can change the prefix that should have been fixed at the deadline. This is a source-level gap; no actual timing violation is established here.

**Next decision:** Keep all pre-cutoff output explicitly a technical preview. Before treating any analysis as principal, require a reproducible record of the eligible tasks and complete prefix at the registered cutoff, with immutable provenance and an explicit status. Preserve the cutoff, seeds and performance-independent stopping rule.

### P2 — The registered paired A-minus-C analysis is absent

**Requirement:** The 2026-11-05 amendment specifies per-model A-minus-C differences paired by seed, corrected t intervals, no multiplicity correction and descriptive status (`docs/analysis_plan.md:117`).

**Evidence:** C's feature/task specification exists (`configs/main.yaml:63-74`), but the statistical defaults and dispatch cover only main A and sensitivity B (`analysis/stats.py:31-34,888,910-934`). The result schema has no A-minus-C section (`analysis/stats.py:872-879`). The generic sensitivity reporting path displays each variant's own means (`reporting/summary.py:119-130`); it does not calculate the paired differences or uncertainty.

**Consequence:** C results, if available, cannot by themselves demonstrate delivery of the registered ablation contrast. A difference between separately displayed means omits the paired uncertainty and failure accounting.

**Next decision:** Treat the paired A-minus-C analysis as pending. A later authorized implementation can operate on already frozen per-seed metrics, preserving the descriptive endpoint and common eligible seeds, without HPO or retraining. Record missing C pairs explicitly. Do not infer its numerical outcome from this review.

### P2 — Metrics/predictions consistency is promised but not checked by analysis

**Requirement:** Any inconsistency between metrics and predictions must be noted (`docs/analysis_plan.md:89`).

**Evidence:** H1 consumes the metrics store (`analysis/stats.py:459-483`), whereas bootstrap and B sensitivity recompute from predictions (`analysis/stats.py:645-656,712-724`). `_Preds` only filters/arrays supplied records (`analysis/stats.py:359-377`), and the entry point checks prediction column names only (`analysis/stats.py:923-934`). There is no check of unique task/stay keys, matching true labels or test universes, or agreement of recomputed task Macro-F1 with supplied metrics. `_anomalies` receives only the metrics store (`analysis/stats.py:776-834`). Synthetic `tests/test_protocol.py:277-284` checks the producer on one generated task; it does not supply this runtime analysis safeguard.

**Consequence:** Stale, truncated or duplicated prediction files could produce bootstrap/sensitivity conclusions on a different analysis set from H1 without the registered anomaly. Shared patient-axis resampling does not establish that all model predictions cover the same stays.

**Next decision:** Require the integrity check before empirical use of prediction-derived sections; on failure, report the affected cells and omit their derived section instead of silently reconciling inputs. This is a missing check, not evidence that any stored file is inconsistent.

### P2 — Overview tables and secondary analyses ignore the selected seed prefix

**Requirement:** The principal analysis uses only the complete registered prefix; later seeds are excluded even when they have results (`docs/analysis_plan.md:72`).

**Evidence:** Statistics use `seeds_used` (`analysis/stats.py:888-920`), but `write_reports` passes the unfiltered metrics/timings to its main and per-class tables (`reporting/summary.py:189,236-244`). `_main_table` averages whatever seeds exist for each cell (`reporting/summary.py:31-43`); figures likewise use unfiltered tables (`reporting/summary.py:197-211`). The secondary validation-selected-strategy analysis iterates every seed present and accepts a seed with merely one available candidate per group (`analysis/secondary.py:80-96`), without the registered completeness selection.

**Consequence:** With incomplete cells or results outside the prefix, prominently displayed means, secondary contrasts and H1 can refer to different seeds and candidate sets. The table's seed count helps but does not identify the selected prefix or state that the overview lies outside the principal analysis. No discrepancy is asserted when all ten seeds/cells are complete.

**Next decision:** For principal presentation, use the same frozen prefix in overview tables and figures. If additional descriptive results are retained, label their seed sets and candidate availability separately. This preserves the stopping rule; it is not a reason to select different seeds after seeing performance.

### P3 — The new urgent-undertriage metric is computed but not exposed in the standard report

**Requirement:** The amendment adds `under_triage_rate_urgent = P(predicted acuity > recorded acuity | recorded acuity <= 2)` as a descriptive metric (`docs/analysis_plan.md:119`).

**Evidence:** It is correctly computed at `evaluation/metrics.py:55` and retained by scalar aggregation (`analysis/aggregate.py:36-41`), but is absent from report `MAIN_METRICS` (`reporting/summary.py:20-21`) and the H3 metric list (`analysis/stats.py:560`). The H3 renderer exposes the marginal rates only (`analysis/stats.py:1017-1024`).

**Consequence/next decision:** The statistic can exist internally without reaching the default paper-facing summary. Include its descriptive mean, variability and available-seed count in a future reporting correction; keep it secondary and preserve the original primary endpoint.

## Aligned safeguards and declared limitations

These items are not new protocol violations:

- **Patient grouping and train-only preprocessing:** Minimum-acuity stratification and patient allocation are explicit (`data/split.py:16-38`). One split map is constructed from A, reused across variants, and checked for patient overlap (`runner/data_stages.py:138-152`). Medians/scales are fitted inside the pipeline and IDs/target are excluded by configured feature selection (`preprocessing/pipeline.py:13-31`; `evaluation/protocol.py:82-90,111-112`). These are source guarantees, not a fresh empirical leakage audit.
- **Validation selection and test guard:** H1 tie breaking follows declared list order (`analysis/stats.py:433-440`), and its verdict implements both positivity and the corrected CI margin (`analysis/stats.py:443-483`). HPO chooses validation Macro-F1 and predicts test only after freezing (`evaluation/protocol.py:122-138`). The guard permits logged reaccess of the same frozen configuration after a crash (`evaluation/test_guard.py:18-31`); this does not authorize selecting another configuration on test.
- **Correlated splits and repeated measures:** Seeds are not ten independent datasets. The implemented variance factor is exactly `1/k + 0.15/0.70`, with t degrees of freedom k-1 and natural-unit differences, dz and corrected intervals (`analysis/stats.py:206-244`). Its approximation and low seed count are already declared (`analysis_plan.md:45-51`). Neither correction nor patient bootstrap establishes external validity. The paired patient bootstrap uses the same resample across models, remains per-seed, and excludes training uncertainty (`analysis/stats.py:277-327,678-679`).
- **Multiplicity:** H2's six strategy/metric families, primary-only Holm adjustment, positive direction and three-endpoint conjunction match the plan (`analysis/stats.py:512-557`). No global claim over all strategies/models is warranted; the absence of a global six-family correction is already disclosed (`analysis_plan.md:60`). The code uses two-sided p values; the plan does not explicitly designate a one-sided H2 test. This is not grounds to switch tails after results.
- **Failed cells and trials:** Primary-cell finite Macro-F1 completeness shortens the seed prefix; inapplicable KNN class weighting and rebalanced dummies are excluded (`analysis/stats.py:387-430`). HPO records failed configurations, selects successful configurations only, and reports their numbers (`evaluation/protocol.py:104-125,165-167`); aggregate/report paths retain HPO errors and final task failures (`analysis/aggregate.py:61-91`; `reporting/summary.py:74-86,160-169`). A task completed with failed HPO candidates has fewer successful candidates, not a fully successful 20-config search. Failure rates and convergence warnings remain necessary context. This review did not inspect raw trial records or actual failures.
- **Unequal effective training/optimization budgets:** KNN HPO and SVM HPO/final caps are configured (`configs/models.yaml:16-20`). Oversampling precedes the cap (`models/imbalance.py:65-70`). Twenty configurations equalize counts, not compute, training sample size or search coverage. MLP oversampling/early-stopping duplication and class-weight/batch-size interaction are already listed in `analysis_plan.md:123-124`; they must remain limitations, not be retroactively repaired with another campaign.
- **Missingness, selection and timing:** B changes both training population and feature representation; its common-test analysis uses stay intersection as registered (`analysis/stats.py:712-747`). It estimates procedure differences on numeric-pain stays, not generalization to excluded stays or a causal effect of removing nonnumeric pain. C removes explicit indicators/status but still uses median imputation (`preprocessing/pipeline.py:18-23`), so it cannot prove complete removal of documentation information. Complete/incomplete strata differ in case mix (`analysis/strata.py:29-47`); subgroup performance is descriptive, not a causal decomposition. Pain severity-proxy risk is already declared (`docs/cleaning_rules.md:58-69`). The loaded schema contains no measurement/label ordering timestamps (`data/schema.py:7-18,34-35`), so source inspection cannot establish prospective availability before acuity assignment. Do not call this clinical outcome prediction or prospective validation.
- **Interpretation:** “No consistent superiority” is the registered failure to meet a superiority criterion, not evidence of equivalence or no effect (`analysis_plan.md:28-30`; `analysis/stats.py:443-455`). HPO on validation does not by itself make a test-set Macro-F1 comparison circular; the more precise limitation is that the benchmark evaluates procedures optimized for that endpoint. Preserve all registered endpoints and treat this as wording guidance, not a revised hypothesis.

## Validation and next decision

All findings above are static and mechanism-based. Read/search commands completed with exit 0. `git rev-parse HEAD` completed with exit 0 and matched the caller's revision. Synthetic test source was read for relevant existing coverage, including H1 validation selection (`tests/test_stats.py:123-133`), completeness (`207-233`), bootstrap/B sensitivity (`193-203`), H2 (`260-264`) and producer metric/prediction agreement (`tests/test_protocol.py:277-284`). **No tests were run; no empirical claims were evaluated.** No execution specification or benchmark run is proposed, so the scientific-run-manifest skill is not needed for this review.

The immediate decision is to keep manuscript results as placeholders and any pre-cutoff analysis as a technical preview. Resolve the cutoff provenance and registered A-minus-C delivery before a principal empirical report; address the integrity and seed-set presentation gaps through separately authorized code work. No new campaign, changed endpoint, altered seed, hypothesis or significance-seeking sensitivity analysis is required by these findings. Data-service eligibility remains unresolved and is not inferred from authorization to edit documents.

## Agent result contract

- **Outcome:** Completed an independent static comparison; five implementation/reporting gaps are distinguished from pre-existing limitations.
- **Scope:** Source/config/methodology/synthetic test source only; no restricted files, empirical results, project execution, network or direct Brain access.
- **Changes/artifact:** Only `docs/reviews/2026-11-06-protocol-code-review.md` was created. Source, configuration and preregistration were unchanged by this reviewer; no commit.
- **Validation:** Read/search commands and HEAD check exited 0. Tests not run by task instruction.
- **Unresolved:** Actual deadline completeness, campaign failures/results, empirical integrity and service eligibility remain unverified.
- **Independent review handoff:** Return to coordinating Codex for integration review of finding priorities and the exact source evidence; no additional runtime or reviewer was launched.
- **Proposed Brain checkpoint:** `2026-11-06 — Task MIMIC-COTB-2027-code-review: independent static protocol review completed at HEAD 458a050. Evidence: docs/reviews/2026-11-06-protocol-code-review.md. Calendar cutoff/preview enforcement, paired A−C delivery, metric/prediction integrity checking, prefix-consistent report presentation and urgent-undertriage summary exposure are pending. H1/H2 source rules otherwise align within declared approximations. No empirical artifact inspected, test executed or scientific decision changed. Next: coordinator reviews findings; retain placeholders until service eligibility and principal-analysis provenance are established.`

## Follow-up — 2026-11-06, static review of statistical repairs

The coordinator requested a bounded rereview of the current working-tree additions to `src/triagebench/analysis/stats.py` and `src/triagebench/analysis/secondary.py`. The initial findings above describe the original reviewed HEAD and remain a historical record. References in this follow-up identify the repaired working-tree source inspected on 2026-11-06; they are not claims that these changes exist in the original commit. Scope remains source-only, with the same supplied Brain bundle and restrictions. No tests, imports, CLI, campaign, patient/results files, network or direct vault access were used.

**Disposition: ACCEPTED FOR STATIC STATISTICAL SCOPE ONLY.** No substantive statistical regression was found in the requested mechanisms. This does not accept empirical results, prove campaign completion, certify principal-analysis provenance or replace the coordinator's integration and reporting checks.

| Initial finding / question | Follow-up evidence and disposition |
|---|---|
| P1 calendar cutoff and preview status | `analysis/stats.py:61-117` fixes the existing cutoff at 2026-11-10 15:00 UTC, requires explicit time zones, excludes known late tasks and inconsistent task timestamps, records inventory metadata, and declares either `technical_preview` or `pending_cutoff_provenance`. It always sets `principal_analysis=False` and `cutoff_provenance_verified=False`. `analysis/stats.py:1068-1087` empties `seeds_used` and returns before H1/H2/ablation/bootstrap when status is pending. **Conservative guard implemented; principal provenance remains deliberately unresolved.** |
| P2 paired A-minus-C missing | `analysis/stats.py:730-750` now pairs finite A and C test Macro-F1 within the selected A prefix for each model, computes A minus C in the registered direction, reports paired seeds and missing variant/seed pairs, and calls the existing corrected test. The helper retains `SE = sqrt((1/k + test_frac/train_frac) * sample_variance)`, k-1 degrees of freedom and bilateral CI (`267-305`). Role is descriptive with no multiplicity correction. **Formula and estimand match the existing amendment.** Missing C pairs do not change the A prefix; an incomplete contrast describes its reported available pairs. With fewer than two pairs, the helper supplies no inferential interval/p value. |
| P2 prediction integrity absent | `analysis/stats.py:441-516` now checks required columns, duplicate/missing task-specific stay identifiers, finite integer identifiers and labels, expected task presence, all supplied scalar test metrics having a producer definition (including n), identical test universes/labels across tasks within variant and seed, B nesting, and exact C/A stay-label correspondence. Diagnostics contain task cells rather than patient identifiers. `analysis/stats.py:1103-1127` suppresses bootstrap/common-subset sensitivity on an anomaly or exception; exception diagnostics retain the error type only. **Required fail-closed behavior implemented for prediction-derived sections.** H1/H2 and metric-based A-minus-C remain metric-based; this guard does not certify their underlying stored results. |
| P2 secondary H1 outside prefix / incomplete candidates | `analysis/secondary.py:83-134` accepts the selected seed list, uses the same complete-prefix selector when none is supplied, and requires every applicable primary model/strategy validation/test cell before selecting a winner. Selection uses validation only, deterministic configured tie order and the existing complex-minus-simple test contrast. Missing candidate cells are recorded, rather than silently selecting a smaller model group. The report call passes `seeds` explicitly (`reporting/summary.py:179-184`), so an empty gated list is preserved. **Secondary helper repaired.** Broader optional reporting restoration was still in progress and is outside this bounded acceptance. |
| P3 urgent-undertriage exposure | The repaired statistical H3 code records the endpoint's mean, SD and available-seed count (`analysis/stats.py:703-722`); the statistics renderer exposes it (`1217-1224` in the inspected version). **Statistical-summary exposure implemented.** Full report integration remains the integration reviewer's responsibility. |

The A-minus-C estimand remains the performance difference between the registered separately tuned A and C procedures on the same designed stay population. It is not a causal estimate of documentation influence, and removing explicit indicators does not remove information carried by imputed values. The new code does not silently change that estimand, primary metric, H1/H2 hypotheses, margin, seeds, HPO budget or campaign.

The remaining principal-analysis requirement is substantive: producer timestamps and an inventory hash of a mutable aggregate do not demonstrate what was complete at the cutoff. The repaired gate explicitly acknowledges this and blocks principal designation. An immutable, verifiable task/result inventory and completeness decision at the registered cutoff still require a separately reviewed implementation/process. Undated tasks are permitted only as technical-preview content by the current gate; they cannot justify a principal result. Re-running a past `analysis_time` can create a labeled replay/preview, not independent evidence of historical completion.

This follow-up used bounded reads/searches of the requested source and the secondary report call; all completed with exit 0. No execution test is claimed. Only this owned review document was modified by this reviewer. No further scientific design change or campaign is recommended.

### Follow-up agent result contract

- **Outcome:** Static statistical acceptance of the paired A-minus-C formula, prediction-integrity fail-closed path, complete-prefix secondary selection and conservative cutoff gate.
- **Scope:** Two statistical source modules plus the narrow caller contract; empirical validation and the in-progress optional report restoration are excluded.
- **Changes/artifact:** Appended this dated follow-up to `docs/reviews/2026-11-06-protocol-code-review.md`; no source, configuration or preregistration edits by this reviewer.
- **Validation:** Source reads/searches exited 0. No tests/imports/project execution/restricted-artifact access.
- **Remaining risk:** Principal analysis is intentionally unavailable until immutable cutoff completeness provenance is established; actual results and service eligibility remain unverified.
- **Independent review:** Return static acceptance to coordinating Codex, analysis-repairs worker and integration reviewer. No additional reviewer/runtime was launched.
- **Updated proposed Brain checkpoint:** `2026-11-06 — MIMIC-COTB-2027-code-review follow-up: statistical repairs accepted by independent static review only. Paired descriptive A−C, prediction-integrity checks with omission on failure, complete-prefix secondary H1 and technical_preview/pending_cutoff_provenance gating are implemented in the working tree. No substantive statistical regression identified. Principal analysis remains blocked pending immutable cutoff inventory/completeness evidence. Full reporting integration and execution evidence belong to the coordinator/integration review. Evidence: docs/reviews/2026-11-06-protocol-code-review.md, dated follow-up. No empirical artifacts inspected or scientific decisions changed.`
