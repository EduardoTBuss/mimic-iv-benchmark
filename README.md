# ed-triage-benchmark

Reproducible benchmark of tabular machine-learning models for **emergency-department triage
acuity prediction** (ESI-like levels 1–5, ordinal) from the structured triage vital signs of
**MIMIC-IV-ED v2.2**. Built to run unattended on a server: one command, resumable, with
automatic analysis and an aggregate-only report.

> Status: work in progress (research code). No clinical use: the target is the *recorded*
> triage label, not clinical truth, and nothing here is validated for deployment.

## Research question

Do more complex models consistently outperform simple ones when predicting the recorded triage
acuity from structured triage variables only (no chief-complaint text)?

| | |
|---|---|
| Data | MIMIC-IV-ED v2.2, table `triage` (+ `edstays` for consistency checks) |
| Features | `temperature`, `heartrate`, `resprate`, `o2sat`, `sbp`, `dbp`, `pain` (no `chiefcomplaint`, no identifiers) |
| Target | `acuity` (1 = most urgent … 5), never used as a feature |
| Models | Logistic Regression, Gaussian Naive Bayes, KNN, Decision Tree, Random Forest, SVM (RBF), XGBoost, MLP — plus HistGradientBoosting, ExtraTrees, ordinal logistic regression and two dummy baselines |
| Protocol | 10 patient-level splits (`subject_id`, 70/15/15, stratified); random-search HPO with the same budget for every model, selected on validation only; the test set of each split is evaluated **once** per frozen configuration |
| Imbalance | none · class weights · random oversampling (train only, inside the pipeline) |
| Metrics | Macro-F1, balanced accuracy, per-class precision/recall, confusion matrix, ordinal MAE, quadratic weighted kappa, error distance \|ŷ−y\|, under/over-triage rates, train/inference time |
| Cleaning | two pre-registered variants: **A** keeps every labelled stay and encodes `pain` as value + status (free-text kept as categories); **B** drops stays whose `pain` is not a plain number (sensitivity analysis) |

The analysis plan is written before any test metric is computed: [`docs/analysis_plan.md`](docs/analysis_plan.md).

## Data governance (PhysioNet DUA)

MIMIC-IV-ED is credentialed data (PhysioNet Credentialed Health Data License 1.5.0).
**This repository contains no data.** Only code, configuration and aggregate, small-cell-masked
reports (counts 1–10 shown as `<11`). Per-stay artifacts (predictions, excluded rows, cleaned
tables) live under `outputs/**/private/`, which is git-ignored; a bait test
(`scripts/check_gitignore.sh`) and a pre-commit hook (`.githooks/pre-commit`) enforce it.
See [`docs/data_governance.md`](docs/data_governance.md).

### Getting the data

1. Become a credentialed PhysioNet user and sign the data use agreement for
   [MIMIC-IV-ED v2.2](https://physionet.org/content/mimic-iv-ed/2.2/) (DOI
   [10.13026/5ntk-km72](https://doi.org/10.13026/5ntk-km72)).
2. Download the ZIP (this project used the copy downloaded on 2026-11-04) and point the config
   to it (`TRIAGEBENCH_ZIP` / `TRIAGEBENCH_DATA_DIR`, or a profile in `configs/profiles/`).
   `triagebench ingest` verifies every file against the archive's `SHA256SUMS.txt`.

## Quickstart

```bash
uv sync                                         # locked environment (Python 3.12)
uv run pytest                                   # synthetic data only
uv run python -m triagebench smoke              # full pipeline on a synthetic archive
uv run python -m triagebench audit              # aggregate-only audit -> reports/data_audit.md
uv run python -m triagebench run-all --profile local-pilot   # 5% of patients, quick check
```

On a Linux server (no global installs):

```bash
make setup                                      # .venv from requirements-lock.txt (hash-pinned)
make test smoke
make launch-bg PROFILE=qflex                    # detached in tmux, resumable
make status PROFILE=qflex                       # progress, ETA, failures
```

`run-all` = ingest → audit → prepare (cleaning variants + splits) → task grid → aggregation →
statistics → report. Every stage is idempotent; every task (variant, seed, model, strategy) is
checkpointed, HPO trials are journaled, results are written atomically, and a re-run skips what
is finished. Concurrency can be changed live via `control.yaml` in the campaign directory.

## Layout

```
configs/      main.yaml (single source of truth), cleaning.yaml, models.yaml, profiles/
src/triagebench/
  data/           ingest (SHA256), load (v2.2 schema check), audit, patient-level split
  preprocessing/  pain parser, cleaning rules, sklearn/imblearn pipelines
  models/         registry, search spaces, imbalance strategies, ordinal logit
  evaluation/     metrics (incl. ordinal), HPO/validation/test protocol, test-access guard
  runner/         task grid, scheduler (workers, retries, timeouts, resource guards), status
  analysis/       aggregation, pre-registered statistics, permutation importance
  reporting/      small-cell masking, tables, figures, reports/summary.md
  utils/          config + hashing, atomic I/O, manifests, logging, seeds, synthetic data
scripts/      launch_bg.sh, check_gitignore.sh, server helpers
tests/        synthetic-data tests (leakage, test-once, resume, golden)
docs/         plan, analysis plan, governance, cleaning rules, server runbook, decisions
reports/      aggregate-only outputs (committed)
```

## Reproducibility

Pinned dependencies (`uv.lock`, `requirements-lock.txt` with hashes), seeds derived
deterministically from the config, and a manifest per campaign (config hash, dataset SHA256,
git commit, library versions, hardware, timings). The campaign id is a hash of the scientific
configuration, so changing any scientific setting creates a new campaign instead of
overwriting results.

## Citation of the data

Johnson, A., Bulgarelli, L., Pollard, T., Celi, L. A., Mark, R., & Horng, S. (2023).
MIMIC-IV-ED (version 2.2). PhysioNet. https://doi.org/10.13026/5ntk-km72

## License

Code: MIT (see `LICENSE`). The data are not covered and are not distributed here.
