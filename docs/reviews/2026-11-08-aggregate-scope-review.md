# Independent review: aggregates-only analysis (2026-11-08)

## Outcome

**Accept, limited to the reviewed implementation and synthetic evidence.** No confirmed defect was found in the requested aggregate-input boundary, report separation, or preservation of the existing statistical engine and cutoff gate. This is not acceptance of real campaign results, service eligibility for MIMIC derivatives, or submission readiness.

## Scope

Reviewer: coordinating Codex worker `aggregate_scope_review`; no prior implementation involvement. Reviewed the actual working-tree diff and its downstream call chain at HEAD `65a0a23805f272d6f5288c2ff913048536819e5e`.

Brain context was supplied by the caller, using checkpoints from 2026-11-07/08 in `projects/mimic-iv-benchmark-execucao.md` and `projects/cotb-paper-b-mimic-iv-ed-triagem.md`: paper6p still has placeholders; the historical 810/zero-failure count is unverified; registered cutoff is 2026-11-10 12:00 BRT. Authorization for aggregate Qflex/results does not establish this service's eligibility for the derivatives. No direct Brain/vault, SSH, network, real dataset, real campaign, private artifact, or real report access occurred.

Acceptance questions: `analyze --aggregates-only` must avoid raw/prepared/private/model inputs, keep the existing hypotheses/protocol/cutoff behavior, leave principal designation disabled, explain the missing prediction-dependent checks, and avoid overwriting full analysis reports. The separate inventory-script implementation is excluded.

## Changes reviewed

Reviewed files and SHA256 identities:

| File | SHA256 |
| --- | --- |
| `src/triagebench/cli.py` | `C14156C37D823BA92A02E62AFAF625B8A024AF615D7902EE444B34EF306E4F84` |
| `src/triagebench/runner/pipeline.py` | `F225E2AE015345C9576DA6D53044B5F650FEF27E0B19F0C70B049DAB65F46A57` |
| `src/triagebench/reporting/summary.py` | `2481613CAFD3A2724DD4A1F9DCFC0AAB0CE15700C41052615359F095B94CA6A0` |
| `tests/test_analysis_closure.py` | `22919A28BAEA6042ED6344E4CEE2A91B14D381A6624FCCB311E5036CD0ECE0C4` |

The review itself changes only this document, plus disposable diagnostic artifacts under the caller-authorized temporary directory. No implementation fix, commit, merge, deployment, or Brain update was made.

Static evidence:

- `cli.py:96` forwards the explicit opt-in flag; the parser defaults it to false. Existing full analysis remains the default.
- `runner/pipeline.py:71` passes `predictions=None` and does not construct or inspect the prepared path in aggregate mode. It does not invoke the training, importance-generation, or cost-benchmark stages from `run_all`.
- `analysis/aggregate.py:30` reads task aggregate `result.json`, trial summaries, ledger/error metadata, and grid metadata, then regenerates the eight shared aggregate Parquet tables. Its prediction loader at line 100 is a separate function bypassed by this mode. Thus the mode still needs campaign metadata and task summaries; it does not operate solely on precomputed `tables/*.parquet`.
- `reporting/summary.py:283`, `:348`, and `:370` gate prepared-document copying, strata, and alternative decodings. The input-scope notice explicitly lists missing bootstrap, prediction integrity, common-stay A/B comparison, strata, and decodings, and says the report does not replace full empirical review.
- `reporting/summary.py:90` and `:152` read only existing aggregate cost/importance tables. The imported importance helpers choose models from in-memory validation metrics and render aggregates; they do not call `run_importance`, refit models, or read prepared data. All four figure functions operate on in-memory aggregates.
- `runner/pipeline.py:94` uses `tables/stats_aggregates_only.json`; reports and the main-tag latest-summary pointer are rooted under the separate `reports/aggregates-only/` path. Full `tables/stats.json`, campaign report, and latest-summary pointer are preserved. Shared aggregate tables are regenerated, as they are in ordinary analysis.
- `analysis/stats.py` and `docs/analysis_plan.md` are unchanged by the reviewed diff. The same engine, configuration, hypothesis thresholds, seed rule, and cutoff apply. `stats.py:62` retains cutoff `2026-11-10T15:00:00+00:00`; principal designation and cutoff-provenance verification remain false (`:108`).

## Validation

Successful identity/read-only commands: `git rev-parse HEAD`, `git diff --numstat --` for the four reviewed files, their actual `git diff`, focused source reads/searches, and `Get-FileHash -Algorithm SHA256` on those files. One initial search named nonexistent `src/triagebench/config.py` and exited 1; the actual configuration module `src/triagebench/utils/config.py` was subsequently read successfully.

Final `git diff --check --` on the four reviewed files exited 0; the four file hashes were rechecked and remained identical to the identities above.

Independent disposable diagnostic, using only generated nonclinical fixtures:

```powershell
.venv/Scripts/python.exe .tmp-scope-review-8f8c6b12-4c98-4f36-876f-c5fa0aa75dc6/diagnostic.py
```

Final exit status: **0**. Diagnostic SHA256: `05E3CBCF90DFA662C3C166B8B8F35B5808B75C80868C050AB6AD90440B754DAD`.

The diagnostic creates 36 synthetic completed tasks, real result/trial/ledger summaries, aggregate importance/cost tables, and sentinel full-report artifacts. It executes the real aggregation and figure code. Python audit instrumentation guards file operations and external operations; a transparent wrapper calls the genuine `pandas.read_parquet` while tracing its inputs because native PyArrow opens do not emit Python `open` audit events. No result/figure/aggregation implementation is stubbed. The initial diagnostic exited 1 at its tracing assertion because of this PyArrow instrumentation gap; after adding that transparent trace, both analysis runs and all assertions passed. That initial failure was in diagnostic instrumentation, not the reviewed implementation.

Observed evidence:

```text
technical_preview: seeds [1,2,3,4,5,6], principal false, full artifacts preserved
pending_cutoff_provenance: seeds [], principal false, full artifacts preserved
36 task results; 5 actual PNG figures; 277 traced operations; 0 forbidden accesses
```

For both dates, `seeds_used`, H1, H2, H3, ranking, and A-minus-C ablation equal the unchanged engine's outputs for the same synthetic metrics with `predictions=None`. Bootstrap remains empty, prediction integrity remains unchecked, and common-stay sensitivity remains unavailable. Synthetic importance and descriptive cost content appear before cutoff; performance inventory is withheld after cutoff. Sentinels cover the full statistics file, campaign summary, and main-tag latest-summary pointer. The report path and incompleteness notice were asserted.

The coordinator owns execution of `tests/test_analysis_closure.py` and Ruff. This worker did not rerun or independently certify those checks. The synthetic diagnostic uses the existing test helper's `none` strategy and checks equality against the unchanged statistics engine; it does not independently validate statistical formulas or every H2 strategy.

## Artifacts

- This review: `docs/reviews/2026-11-08-aggregate-scope-review.md`.
- Disposable rerunnable script and generated synthetic fixtures: `.tmp-scope-review-8f8c6b12-4c98-4f36-876f-c5fa0aa75dc6/` (local, temporary, not a production input or publication artifact).

## Risks or unresolved items

No confirmed finding requiring an implementation change. The input-scope flag is a pipeline option, not a general filesystem/content sandbox: acceptance assumes the normal campaign schema, aggregate task summaries, and ordinary output-directory layout. This review does not certify the semantic contents or authorization status of any real aggregate/error/trial file. It does not establish real cohort sizes, data integrity, historical completion/failure counts, statistical conclusions, service privacy eligibility, or a complete empirical report. Prediction-dependent evidence remains deliberately unavailable.

Proposed Brain checkpoint for coordinator review only: on 2026-11-08, the aggregate-only code path received limited independent acceptance using source inspection and a generated 36-task diagnostic; five figures, cost/importance tables, report separation and unchanged cutoff gate were exercised. Real-data/service eligibility, real campaign verification and submission readiness remain unresolved. No vault write was performed.

## Independent review

Completed by Codex worker `aggregate_scope_review` for the exact aggregate-boundary and report-separation questions above. Acceptance applies to the recorded file hashes. Any later implementation change requires checking its effect on these findings. Domain-level mathematical/statistical acceptance was not requested or inferred from these pipeline checks.
