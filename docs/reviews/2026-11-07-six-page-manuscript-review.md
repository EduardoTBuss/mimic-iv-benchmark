# Six-page manuscript: coordinator verification and partial peer review

Date: 2026-11-07. Starting source revision:
`a257460b5cb51770aa33acbb062052996a89e4f9`.

## Scope and status

The user requested a six-page English draft, fuller discussion following the
original Brain proposal, some images and a compiled PDF in Downloads. The current
deliverable meets that document-preparation scope. It is still a placeholder
manuscript, not an empirically complete or submission-ready paper.

The coordinator performed final source, compilation, text/metadata and visual
checks. The independent `research-artifact-consistency-auditor` task
`MIMIC-COTB-2027-six-page-review` began a review and returned two actionable findings,
then failed because the service usage limit was reached. It did not deliver final
acceptance or a completed review note. Its partial observations are preserved
below and must not be described as a completed independent review of six pages.

## Partial peer findings and disposition

1. **Variant B wording.** The earlier sentence suggested any parser-derived valid
   numeric pain value was eligible. `preprocessing/pain.py` distinguishes plain
   numbers, ranges and fractions, and `preprocessing/cleaning.py` filters B on
   `pain_kind == numeric`. Methods, figure card and caption now specify valid
   plain numeric entries in [0,10], excluding ranges and fractions. This is a
   manuscript correction to match existing code, not a cohort/protocol change.
2. **Cost workload.** The earlier text did not identify the configured variant and
   seed. `configs/main.yaml` fixes A, seed 1, three repetitions;
   `evaluation/costbench.py` measures inference on validation features. The text
   now states those details. No timing result was inspected or inserted.

Source paths above are relative to `src/triagebench/` unless otherwise specified.

## Claim and figure traceability

| Manuscript material | Evidence and boundary |
|---|---|
| Central proposition, discussion and future reuse | Original Brain proposal `raw/contexto/ideia-cotb-paper-b-mimic-iv-ed-2026-11-04.md` and project note `projects/cotb-paper-b-mimic-iv-ed-triagem.md`; later fixed decisions take precedence. |
| H1/H2, seeds, splits, margin, correction and descriptive status | Unchanged `docs/analysis_plan.md` and method/config source; no new confirmatory criterion. |
| Literature comparison table | Existing `docs/literature_review.md` and nine-reference bibliography; abstract-only access explicitly qualified and no cross-paper score ranking or primacy claim. |
| Figure 1 | Protocol schematic: fixed inputs, patient splits, train-only fitting, validation selection, frozen refit, test, complementary views and paired inference. No measured counts or scores. |
| Figure 2 | A/B/C configuration and pain parser; equal card sizes explicitly do not encode sample sizes. |
| Figure 3 | Signed mathematical label difference in a 5x5 conceptual grid, matching `evaluation/metrics.py`; not a confusion-count matrix, patient sample or clinical harm model. |
| Grouped permutation importance | `analysis/importance.py`: mean-validation model selection and grouped permutation of representations from each raw variable; descriptive and noncausal. |
| Discussion of imbalance, missingness, budget and validity | Interpretation of fixed design and previously declared limitations, expressed conditionally; no empirical direction or superiority is asserted. |

## Final local validation

- From `paper/`: `powershell -NoProfile -File .\build.ps1`: exit 0.
  Local LaTeX compilation, with the unchanged official
  class, bibliography style, page geometry and font sizes.
- PyMuPDF verification: exactly **6 letter-size pages**, empty PDF author metadata,
  all three figure captions present, nine resolved references, no identifying
  author/project link in extracted text, and visible result placeholders.
- Rendered all six final pages and inspected them visually. Diagrams, captions,
  tables, equations and references are legible; no clipping, overlap or broken
  glyphs was identified. The final log has no overfull boxes, undefined references,
  missing glyphs or missing image-description warning.
- PDF SHA256:
  `2e688ac64127b69d36a2d5a355b8ff59496c1e086039cc4f6fee0b0450ff886e`.
- A byte-identical copy was verified at
  `C:/Users/eduar/Downloads/COTB2027_MIMIC-IV-ED_6pages_draft.pdf`.
- No runtime source, tests, scientific configuration, metrics definition or
  preregistration changed in this expansion. Tests were not rerun for the
  manuscript-only edit; the previous 329-test result applies to the unchanged code.

## Remaining gates

Campaign data and derivatives were not opened, processed, summarized or sent.
Empirical results remain placeholders. Service/derivative authorization,
immutable cutoff provenance and empirical statistical review remain unresolved.
Replacing placeholders with approved results will require another six-page,
source, disclosure, anonymity and visual check. Final independent review of this
expanded manuscript also remains pending; the earlier three-page/code acceptance
must not be automatically extended to this revision.
