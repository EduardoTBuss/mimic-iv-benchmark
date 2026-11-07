# Independent integration acceptance review

Task: `MIMIC-COTB-2027-integration`
Reviewer: Codex integration reviewer, with no prior implementation involvement.
Date: 2026-11-06
Initial source HEAD: `458a050667c7e9e6df6150c373e28c423db8411d`.

## Scope and context

This review covers the anonymous English placeholder manuscript, official-template fidelity, public-source support, and the final authorized analysis/reporting repairs once handed off. It does not assess empirical findings, campaign completion or publication readiness. The reviewer owns only this review note and has made no production-code edits or commits.

Brain context is the coordinator's cited bundle: `projects/mimic-iv-benchmark.md` (2026-11-04/05), `mimic-iv-benchmark-execucao.md` checkpoint 5 (2026-11-06), and `cotb-paper-b-mimic-iv-ed-triagem.md` (2026-11-04). The `brain-context` skill permits this bundle to satisfy an isolated worker's context requirement. No direct vault access or durable decision change occurred.

The privacy boundary excludes opening or listing actual `reports/`, `outputs/`, `private/`, `data/`, `datasets/`, and campaign-derived artifacts, including aggregates. Only source, methodological documents, synthetic diagnostics and the explicitly authorized authored placeholder PDF are in scope. No project CLI, real campaign or external upload is authorized. `docs/analysis_plan.md` remains frozen.

## Initial manuscript check (separate from final acceptance)

Completed before inspecting the implementation worker's transient changes. Read `paper/main.tex`, `paper/cotb2027-preamble.tex`, `paper/references.bib`, `paper/README.md`, `paper/build.ps1`, `docs/literature_review.md`, `docs/paper_preparation.md`, the unchanged analysis plan, and the independent protocol/code review.

The English is clear. The paper states the recorded-label target, prospective-timing limitation, patient split unit, visit-weighted metrics and correlated-seed limitation. It preserves the operational simple/complex groups, validation selection, primary Macro-F1, H1 margin and positivity criterion, H2 conjunction/Holm families, fixed cutoff, descriptive sensitivities, caps and MLP limitations. Its contribution statement is bounded and explicitly disclaims exhaustive novelty. Empirical results remain visible placeholders; no numerical campaign conclusions are asserted. Anonymous front matter and the provisional AI-use declaration are present in source. No substantive manuscript blocker was identified in this first pass.

Independent public-source checks on 2026-11-06:

- [PhysioNet v2.2](https://physionet.org/content/mimic-iv-ed/2.2/) confirms version/date, authors and dataset DOI. Its current page also requests a platform citation; the coordinator was notified to consider adding Pollard et al. 2026, DOI `10.1038/s44360-026-00096-z`.
- [MIT triage specification](https://mimic.mit.edu/docs/iv/modules/ed/triage.html), Important considerations and acuity, supports nurse-assigned ESI direction and absent observation times.
- [Xie et al. full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC9610299/), Data processing and Benchmark tasks, supports the two-tier cleaning precedent and distinction between its downstream outcomes and the present acuity target.
- [Li et al. full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC12583869/), Methods/Table 1, supports the distinction between structured/derived baseline predictors and the hybrid text model.
- [Nadeau and Bengio primary conference derivation](https://papers.nips.cc/paper_files/paper/1999/file/7d12b66d3df6af8d429c1a357d8b9e1a-Paper.pdf), Section 3, supports the approximate corrected variance factor. Domain interpretation relies on the separately completed statistics review; this integration reviewer does not independently certify empirical inference.
- [Event instructions](https://www.computeronthebeach.com.br/intrucoes-gerais.html) confirm English front matter, PDF, six pages including references, anonymity and required sections. [Main-track page](https://www.computeronthebeach.com.br/trilha-principal.html) confirms the 2026-11-15 submission deadline.

Chonde's direct publisher page returned HTTP 403; SCC's direct publisher page returned an anti-bot page. These two records retain the abstract-level evidence/access limits documented by the literature reviewer. Their full methods were not independently verified here.

## Official-template evidence

Read-only Python `zipfile` comparison and `Get-FileHash` completed with exit 0. Archive `paper/build/templateCOTB2027.zip` SHA256 is `5264c5254a348b02b6f1ab2fb29f2e0938061178f16fc23e63ba8f5739b6e398`.

- `paper/acmart.cls` equals archive bytes: SHA256 `30a70845ad98ce61e44e3e5bfe3d202c59b19f025d5c008ecae20c842e7f6d7e`.
- `paper/ACM-Reference-Format.bst` equals archive bytes: SHA256 `6225898340ce8ca3536ab1141cfd822e4d80049bd3a19c85bd6221072e2466d0`.
- Comparing noncomment pre-document template lines with `cotb2027-preamble.tex` shows the anonymous option, comment cleanup and blank lines; packages, layout and event headers are retained. No margin/type-size/spacing reduction is introduced.
- Archive `LEIA-ME.txt` explicitly requests the AI-use section in both anonymous and final versions.

## Final acceptance

### Rendered placeholder manuscript: accept within scope

After the coordinator's manuscript/PDF ready signal, reopened the updated bibliography and checked the latest PDF directly. All nine references are cited/resolved, including the requested PhysioNet platform citation and its historical resource citation. The paper now clarifies that registration means the repository's versioned plan rather than an external registry. The earlier citation-completeness observation is closed.

Authored PDF: `output/pdf/cotb2027-mimic-iv-ed-draft.pdf`; SHA256 `2ba3667c00f2de88bf5ff37d597a44c4b33654b3b51696e3a04a7bdebc8c1a81`. PyMuPDF reports **3 pages**, each 612 x 792 points, and an empty author field. Extracted text contains anonymous author/header labels, no identifying author/address/repository links, all nine reference entries, the AI declaration and visible result placeholders. Re-rendered every page from this latest PDF into `paper/build/integration-page-{1,2,3}.png` and visually inspected all pages, with an additional page-2 header crop. Headers, columns, equations, tables and references are legible; no overlap, clipping or broken glyphs was identified. The six-page ceiling holds for this draft; replacing placeholders requires another page-count/visual check.

Diagnostics: the first `.venv/Scripts/python.exe` rendering attempt failed because that environment lacks `fitz`. System `python` has PyMuPDF; its initial combined extraction/render command hit a console CP1252 Unicode-encoding error after rendering page 2. Repeating with UTF-8 stdout completed successfully (exit 0) and rendered all three pages. These were tooling failures, not PDF defects. No dependency or production source was changed by this reviewer.

### Final code integration: pending

First code-ready pass inspected diffs in `analysis/stats.py`, `analysis/aggregate.py`, `analysis/secondary.py`, `runner/pipeline.py` and `reporting/summary.py`, together with synthetic test source. Paths without a repository prefix here refer to `src/triagebench/`. The initial patch conservatively blocks principal designation without an immutable cutoff inventory, adds descriptive paired A-minus-C, checks prediction/scalar-metric/universe agreement, uses the selected inventory/prefix in displays, exposes urgent undertriage and corrects seconds-to-ms/1,000 conversion. These mechanisms preserve the registered endpoint and stopping rule; the cutoff snapshot remains an explicit unresolved requirement.

Confirmed intermediate finding **P2**: `reporting/summary.py::write_reports` unconditionally substituted an omission string for previously working strata, importance, alternative decoding and controlled cost sections. Reproduction: supply the coherent synthetic tables in `test_analysis_closure.py::synthetic_tables`, compute an integrity-valid technical preview and call `write_reports`; the unconditional `omitted_unverified` entries suppress those sections regardless of valid inputs. Impact: descriptive output disappears, including cost that does not depend on prediction integrity. The coordinator independently identified this regression and authorized a conditional/inventory-filtered restoration. Final disposition is pending the restoration handoff; this is not a claim that the final tree still contains the defect.

Reviewer command `.venv/Scripts/python.exe -m pytest tests/test_analysis_closure.py tests/test_reporting_units.py -q -p no:cacheprovider --basetemp=paper/build/integration-tests` passed **15 tests**, exit 0. Temporary test data remain under `paper/build/`; no real artifacts or CLI were used. The first navigation search also named nonexistent `runner/task_worker.py` and returned an `rg` path error; subsequent targeted reads used existing source paths. No diagnostic failure was hidden.

### Final restoration and acceptance decision

**Decision: ACCEPT for the authorized placeholder-manuscript and technical-preview repair scope.** Principal empirical analysis and publication readiness remain outside this acceptance. No unresolved confirmed defect was identified in the final tree. The intermediate P2 regression above is closed: strata/alternative decodings are conditionally restored behind prediction integrity and selected task keys; task keys are checked before per-task prediction reads/recomputation. Importance aggregates are filtered to eligible tasks and validation-selected models and checked against the selected baseline Macro-F1. Controlled cost is restored independently of prediction integrity, scoped to the configured variant/seed and eligible model/strategy pairs, with measurement timestamps. Missing/bad inputs produce explicit omissions. No retraining/campaign was performed by this reviewer.

The `experiment-design-statistics-reviewer` completed a separate follow-up static acceptance of the final statistics/secondary changes (evidence appended to `2026-11-06-protocol-code-review.md`). That review found no substantive statistical regression and confirmed unchanged H1/H2/complete-prefix rules, corrected descriptive A-minus-C, and fail-closed cutoff/integrity behavior. This is domain-review evidence, not empirical certification.

Rechecked final `pipeline.py` and report interactions, including empty input status and explicit empty selected seeds. A disposable inline call on an empty metrics schema returned `technical_preview`, empty seeds and an explicit absent-main-variant note (exit 0). Its first invocation omitted the required `predictions` argument and failed with `TypeError`; the corrected diagnostic passed. Tests now fix their synthetic as-of time and match saved scalar metrics to their generated predictions rather than bypassing the integrity check.

The coordinator's final language edits were rechecked in a new three-page render. The **final** PDF SHA256 is `9052f410e601effe7c945e17a5a29917eaee27d374e8cabc01c6e5deeb9eb076`, superseding the earlier `2ba366...` draft hash. All three latest page PNGs were visually inspected again. Definitions of SVM, class weighting in Macro-F1, sample variance and timing units improve clarity without altering scientific claims. Empty PDF author metadata and the three-page ceiling remain verified.

Final working-tree identity is relative to HEAD `458a050667c7e9e6df6150c373e28c423db8411d`; source files are uncommitted edits and manuscript/test additions also form part of the reviewed tree. `git diff HEAD --check` over authorized source/docs/paper/test paths exited 0 (only CRLF normalization notices). The preregistration working blob equals HEAD: `01a13de8472fc7257453f86e3f0c7e7c7cae37b0`.

SHA256 identities of decisive final files:

| File | SHA256 |
|---|---|
| `paper/main.tex` | `7309c8d42ae7c455c0b0d8d172ba208115782bcbd2f997c986f481001f34f453` |
| `paper/cotb2027-preamble.tex` | `67aeef2f45741f6e47157f7e037992e814eee14484e1d55b686933487f47ac61` |
| `paper/references.bib` | `1cd38638b3514ec29449f9874c21271965d9dff7b1eb81d158eb006e2f566e2d` |
| `src/triagebench/analysis/stats.py` | `00d1ac4b04d182a53082f9757245e56b149c11e9d1b9ee494e48698d70c2b22e` |
| `src/triagebench/analysis/aggregate.py` | `93b094a57ab78ea8e111ac9602640249fe8e39490565198ee2a26799432df41b` |
| `src/triagebench/analysis/secondary.py` | `9d8b7ae695613cf6a1041fde3b5067f97f47b6a216c56853b0fa9cfcb213fdf2` |
| `src/triagebench/analysis/strata.py` | `8d7fba37658afefa1d0f06c9bd54057bd54f4aa1b09a556abf5623f57f17b550` |
| `src/triagebench/runner/pipeline.py` | `79ad66b7fc1cf0550062c02531d43cd9f38cf155c66dd3106c3ccfa900000003` |
| `src/triagebench/reporting/summary.py` | `be1d04680f1126ce6ff35a2a13870e9655ebd48b7ca80029433daeb408cb798f` |
| `tests/test_analysis_closure.py` | `26133a88c3eb1dbbeedae27459b504d486f7c9bc56cf2c193fb77eb51e3b66a7` |
| `tests/test_stats.py` | `781d5d3e3e11a1f91bc36a42ab5822f0b278478cdc7f6b03299e5dee3c64cfc4` |
| `tests/test_reporting_units.py` | `5febaf8b08554ed2c3a1c6e1689414ca2a3cb87b101018238cf9e95a8bf7fdb3` |

### Outstanding conditions and unverified concerns

- **Principal analysis remains unavailable by design.** No immutable inventory/result/configuration provenance at the registered cutoff has been implemented or reviewed. The post-cutoff status blocks inferential output rather than silently using current completion. A principal report requires this further authorized work and independent review; this acceptance does not close that gate.
- Service/data eligibility, actual campaign completeness, errors, stored metric/prediction coherence, empirical effect sizes and disclosure remain unverified. No restricted artifacts were accessed. Results must remain placeholders until these gates are resolved.
- Reload consistency is a residual architectural concern: strata/alternative decodings reopen task files after the in-memory integrity check, without immutable content hashes. No concurrent file replacement or inconsistent reload was observed, so this is an unverified concern rather than a confirmed defect. Use a frozen inventory/content snapshot when certifying real principal artifacts.
- Current six-page compliance concerns the authored placeholder draft. Replacing result placeholders, changing references or adding figures requires a fresh visual/anonymity/page-count review.

## Final validation and agent result contract

- **Outcome:** Accept the authored anonymous placeholder draft and bounded technical-preview/reporting repairs. No empirical, principal-analysis or submission-readiness acceptance is issued.
- **Scope:** Independent final-diff/source, method/documentation, public-reference and rendered-PDF review. Also checked the final `docs/data_governance.md` scope clarification and `docs/runbook_server.md` cutoff/provenance note; they preserve the privacy boundary and frozen decisions. No production fix, commit, merge, deployment, real CLI, campaign, vault access or restricted-artifact inspection by this reviewer.
- **Changes:** Reviewer changed only this note. Temporary rendered pages/header crop and disposable diagnostics/tests were created under `paper/build/`; they are authored/synthetic artifacts.
- **Validation:** Final reviewer command `.venv/Scripts/python.exe -m pytest tests/test_analysis_closure.py tests/test_stats.py tests/test_reporting_units.py -p no:cacheprovider --basetemp=paper/build/integration-final-tests` passed **42 tests**, exit 0, in 51.23 seconds. One sklearn warning is expected from a fabricated stratum whose predictions include an absent true class. The earlier 15-test pass, source/template hashes, unchanged-plan blob, `git diff HEAD --check`, empty-input diagnostic and visual inspection are recorded above. The coordinator's broader full-suite run is separate evidence and was not yet complete when this note was finalized.
- **Artifacts:** `docs/reviews/2026-11-06-integration-review.md`; final authored PDF identity `9052f410...` above; reproducible focused commands and exact source identities in this note.
- **Risks or unresolved items:** Principal immutable cutoff provenance, authorized empirical verification and data-service eligibility remain pending. Reload/content-hash consistency is explicitly an unverified concern. Two literature records retain abstract/access limitations. No finding here licenses insertion of campaign results.
- **Independent review:** Completed by this independent Codex reviewer for task `MIMIC-COTB-2027-integration`, with separate statistical follow-up from `experiment-design-statistics-reviewer`. Return evidence to the coordinating Codex session; no other runtime or reviewer launched.

Proposed Brain checkpoint for coordinator review: `2026-11-06 — Independent integration review accepts the anonymous English COTB placeholder manuscript (final PDF 3 pages, SHA2569052f410...) and bounded technical-preview/reporting repairs. Final reviewer focused42 tests passed; intermediate unconditional-omission regression resolved. Frozen analysis plan blob unchanged. Principal analysis remains blocked pending immutable cutoff inventory/content provenance; service eligibility and campaign empirical evidence remain unverified. Review evidence: docs/reviews/2026-11-06-integration-review.md. No restricted artifacts accessed or scientific decisions changed.`
