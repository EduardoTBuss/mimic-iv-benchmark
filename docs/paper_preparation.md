# COTB 2027 manuscript preparation

## Scope and privacy boundary (2026-11-06)

The user authorized continued preparation, optional Codex delegation, Brain updates,
and GitHub updates when necessary. The manuscript language is English, with direct
explanations and a maximum of six pages. This authorization does not establish
PhysioNet/DUA eligibility for this service or authorize access to MIMIC-derived artifacts.

Do not open, process, summarize, or upload `private/`, `outputs/`, MIMIC source data,
campaign reports, tables, figures, or patient-level predictions while that boundary
remains unresolved. Public literature and the official event template are permitted.
The claim of campaign completion comes from the historical Brain checkpoint and has
not been independently verified here. No campaign performance belongs in this draft.

## Task ledger

| Task | Owner | Files | Acceptance / dependency |
|---|---|---|---|
| Static protocol review | Independent statistics reviewer | `docs/reviews/2026-11-06-protocol-code-review.md` | Completed on initial revision; no empirical validation |
| Bounded originality review | Literature researcher | `docs/literature_review.md`, `paper/references.bib` | Completed; primary-source matrix and abstract-only limits retained |
| Manuscript and integration | Codex coordinator | `paper/`, this note | Official template; English; anonymous PDF <=6 pages; result placeholders |
| Reporting correction | Codex coordinator | `src/triagebench/reporting/summary.py`, focused synthetic test | Correct seconds-to-ms/1,000 conversion; no metric/protocol change |
| Acceptance review | Independent integration reviewer | Read-only integrated changes | Code/report tests and manuscript integrity, without restricted artifacts |

## Frozen scientific decisions

`docs/analysis_plan.md` is not to be rewritten after the campaign. No changes to
hypotheses, metrics, seeds, splits, HPO budgets, model spaces, or decision rules.
No new campaign. Implementation/reporting repairs must be documented separately
and must not be presented as new preregistered decisions.

The seed cutoff is **2026-11-10 12:00 BRT (15:00 UTC)**. An analysis before this
cutoff is a technical preview, even if all expected tasks are reportedly complete.
The code currently enforces completeness but not the calendar or a preview label.
The A-minus-C paired descriptive comparison needs implementation review. These are
open closure items, not reasons to change the registered plan.

The paragraph above describes the initial revision. Follow-up repairs and their
acceptance evidence are recorded in the integration review; the analysis plan
itself remains unchanged. In particular, a conservative pending-provenance state
does not constitute delivery of the principal empirical analysis.

## Postprocessing repairs and remaining principal-analysis gate

The follow-up implementation adds a descriptive paired Macro-F1 contrast A minus
C with corrected intervals and missing-pair accounting; exposes urgent undertriage;
checks scalar metrics against predictions and compatible test universes; and uses
the selected task inventory/prefix in report views. The inference-time display is
now milliseconds per 1,000 stays rather than milliseconds per stay under that label.
These are implementation/reporting repairs, not amendments to scientific decisions.

Statistics metadata schema 2 records the explicit as-of time, registered cutoff,
producer completion provenance, excluded tasks and an inventory fingerprint.
Before the cutoff, the status is `technical_preview`. At or after the cutoff it
is `pending_cutoff_provenance`, with `principal_analysis=false` and no principal
inferential output. Producer timestamps alone are not treated as immutable proof.
There is deliberately no principal-designation path in this interim implementation.

An authorized local executor must preserve and independently verify:

- an immutable inventory of the eligible tasks at 2026-11-10 12:00 BRT;
- result and frozen-configuration hashes, producer completion timestamps and
  matching campaign/configuration/code provenance;
- completeness of the registered seed prefix at the cutoff, excluding late
  completions and without consulting performance to select seeds.

The current code must not be described as completing that provenance workflow.
Retain the registered date and stopping rule. Do not run real analysis through
this service while the data/derivative authorization gate remains unresolved.

## Evidence and release gates

1. **Service/data gate:** document eligibility of this service and permitted derived
   artifact categories. Masking alone is not evidence of authorization.
2. **Campaign gate:** an authorized environment verifies expected tasks, finite
   metrics, seed completeness, HPO errors, warnings, merges and code provenance.
   Zero failed tasks does not imply zero failed HPO configurations.
3. **Statistical gate:** independently check H1/H2 against the unchanged plan;
   distinguish preview from principal analysis at the registered cutoff. Bootstrap
   and common-subset checks may require private predictions and local execution.
4. **Publication gate:** transfer only approved aggregates, check disclosure and
   replace placeholders with supported estimates, uncertainty and conclusions.
5. **Blind-review gate:** remove identifying links, hostnames, author metadata and
   acknowledgments; retain an anonymous and accurate AI-use declaration.

## Public event requirements

Checked 2026-11-06:

- https://www.computeronthebeach.com.br/trilha-principal.html
- https://www.computeronthebeach.com.br/intrucoes-gerais.html
- https://computeronthebeach.com.br/files/templateCOTB2027.zip

Full paper: PDF, <=6 pages including references, double-blind review, submission
deadline 2026-11-15. English title/abstract/keywords are mandatory. The downloaded
template's `LEIA-ME.txt` explicitly requires the AI-use section in both review and
final versions; therefore the draft includes it already. The general webpage
explicitly mentions it for the final version. Follow the stricter template here.

## Page budget

| Content | Target pages |
|---|---:|
| Front matter and introduction | 0.9 |
| Related work | 0.6 |
| Materials and methods | 1.6 |
| Results | 1.3 |
| Discussion and conclusion | 0.8 |
| References, acknowledgments and AI disclosure | 0.8 |
| Total ceiling | 6.0 |

The 2026-11-07 revision uses six pages at the user's request. Its additional space
develops the original scientific proposition, methodological interpretation and
three conceptual figures. It does not fill space with invented results.

## Authored draft validation

The local official-template build succeeds using `paper/build.ps1`. The current
2026-11-07 draft is six letter-size pages, with nine resolved references and visible empirical
placeholders. PDF author metadata is empty and no personal name, local repository
path, host identifier or identifying project link appears in the extracted text.
All six rendered pages were visually inspected by the coordinator and, after the
final editorial revision, by an independent artifact-consistency reviewer.
No clipping, overlapping content, unresolved citations or missing glyphs were
found. The final LaTeX log has no overfull boxes or missing figure descriptions.
The earlier interrupted peer review was resumed and completed. Its final decision
is ACCEPT for editorial clarity, method consistency and authored-draft presentation
only; it does not certify empirical results or submission readiness. See
`docs/reviews/2026-11-07-final-editorial-independent-review.md`.

PDF: `output/pdf/cotb2027-mimic-iv-ed-draft.pdf` (ignored by Git).
SHA256: `27ff40239c552fdef777d08d752ea72e9af0b67b2dc96d06b526212852da14a6`.
The source in `paper/main.tex` is versioned; the PDF is rebuilt locally.
A byte-identical copy was saved to
`C:/Users/eduar/Downloads/COTB2027_MIMIC-IV-ED_6pages_reviewed_draft.pdf` for user review.
The earlier Downloads draft is preserved as a separate version.

The expanded framing was checked against the original proposal at
`C:/Users/eduar/Brain/raw/contexto/ideia-cotb-paper-b-mimic-iv-ed-2026-11-04.md`:
controlled simple/complex comparison, imbalance, ordinal errors, variable
importance and relative computational cost. Earlier exploratory suggestions in
that proposal do not override the later fixed analysis plan. No new empirical
analysis, hypothesis or decision criterion was added for the expansion.

The local TinyTeX installation required missing template/font packages; the class
and bibliography style were not edited. Poppler could not load its Windows DLLs
(exit -1073741515), so PyMuPDF rendered the authored PDF for visual QA. The official
multilingual preamble emits unused-language/hyphenation warnings in this bundled
class; the manuscript is English and its fonts/layout render correctly.

This validation concerns document presentation and source support, not the
accuracy of any experiment. It is not a submission-ready full paper.

## Final editorial pass (2026-11-07)

The user requested continued autonomous refinement before final Brain integration.
The completed passes covered objective/contribution clarity, plan/code/figure
consistency, reader-oriented prose, citations/anonymity, and final six-page visual
proofreading. The opening now distinguishes primary H1 from separate confirmatory
H2 contrasts; H2 explicitly uses A, paired test differences and two-sided corrected
tests. Chief-complaint text is distinguished from parsed pain strings. Repetitive
imperative author instructions were replaced with concise evidence markers and
ordinary explanatory prose. The AI declaration now includes diagram authoring and
retains author responsibility without asserting completed author verification.

All bounded editorial findings are closed. The independent final review records
the claim traceability and final hashes. Code, tests, scientific configurations,
metric definitions and the preregistration remain unchanged; no new campaign or
real result analysis was run. The earlier 329-test pass is historical evidence
for the unchanged code, not a new execution claim.

A public-source eligibility check was also completed without data/account access:
`docs/data_service_eligibility.md`. The exact service's eligibility and permitted
derivative categories remain unestablished. The empirical paper still needs
approved result evidence, immutable cutoff provenance, independent result review
and final author approval. Continuing to rewrite prose cannot resolve these gates,
and this editorial acceptance must not be presented as scientific completion.

## Final validation (2026-11-06)

- Full synthetic suite: `.venv/Scripts/python.exe -m pytest tests -o addopts= -q
  -p no:cacheprovider --basetemp=paper/build/test-full-final`:
  **329 passed, 1 warning**, exit 0, 137.58 seconds. The warning is from a
  deliberately fabricated stratum with a predicted class absent from its labels.
- Lint: `.venv/Scripts/python.exe -m ruff check src tests`: exit 0.
- Frozen-file comparison: no differences in `docs/analysis_plan.md`, scientific
  configs, `evaluation/metrics.py` or `evaluation/protocol.py`.
- Independent statistical follow-up accepts the static statistical repair scope;
  independent integration review accepts the placeholder draft and technical
  preview scope, with 42 independently rerun focused tests passing.
- No real campaign, data preparation, result analysis or remote server command
  was run. All execution evidence here is authored-document or synthetic-test QA.

Publication scope is the explicit source/document/manuscript allowlist. The
pre-existing untracked `reports/campaigns/` directory remains unopened and is
excluded from staging. No prior commit or author identity is rewritten.

After independent acceptance, the coordinator removed Markdown trailing-space
hard breaks from the two review notes and one redundant trailing blank line from
the template preamble to pass staged whitespace checks. No manuscript text,
layout command or executable code changed. The final raw preamble SHA256 is
`e3397e0cda26f14321bf3f561d6889fde2ebe2e89eb15dbf4f73590e248c781a`;
the review's earlier preamble hash identifies its whitespace-equivalent input.
Unmodified upstream class/BST files are excluded from authored-file whitespace
checks and retained verbatim for template provenance.

## Historical context sources

- `C:/Users/eduar/Brain/projects/mimic-iv-benchmark.md`
- `C:/Users/eduar/Brain/projects/mimic-iv-benchmark-execucao.md`, checkpoint 5, 2026-11-06
- `C:/Users/eduar/Brain/projects/cotb-paper-b-mimic-iv-ed-triagem.md`

Starting code revision: `458a050667c7e9e6df6150c373e28c423db8411d`.
Starting Git status: `?? reports/campaigns/`. This directory is outside the scope of
inspection, staging, commits and publication by this session.
