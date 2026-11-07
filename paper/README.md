# COTB 2027 manuscript

English, anonymous working draft. **Not submission-ready:** every empirical result
remains a visible placeholder. No MIMIC-derived file is an input to the manuscript
build. The manuscript contains no campaign figures, cohort counts or metrics.

Current revision (2026-11-07): six pages, three original vector schematics, an
expanded related-work comparison and a fuller discussion of the original benchmark
idea. The figures explain the workflow, representations A/B/C and signed ordinal
disagreement; none visualizes measured performance. Figure sources and provenance
are in `figures/README.md`. This revision supersedes the earlier three-page draft.

The final editorial pass has an independent ACCEPT for clarity, consistency with
the unchanged method and six-page presentation; see
`../docs/reviews/2026-11-07-final-editorial-independent-review.md`. It distinguishes
H1/H2 roles and replaces repeated author instructions with concise evidence
markers. This acceptance does not cover empirical results or submission readiness.
The compiled, reviewed copy is saved separately in Downloads as
`COTB2027_MIMIC-IV-ED_6pages_reviewed_draft.pdf`.

## Build locally

From this directory:

```powershell
latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build main.tex
```

Or run `powershell -File build.ps1` to compile and copy the PDF to
`../output/pdf/cotb2027-mimic-iv-ed-draft.pdf`. Build products and the preview PDF
are ignored by Git. Editable manuscript and verified bibliography are tracked.
Compilation is local; do not upload result artifacts to external typesetting
services while data/derivative authorization is unresolved.

## Official template provenance

- Public URL: https://computeronthebeach.com.br/files/templateCOTB2027.zip
- Downloaded: 2026-11-06
- Archive SHA256: `5264c5254a348b02b6f1ab2fb29f2e0938061178f16fc23e63ba8f5739b6e398`
- `acmart.cls` and `ACM-Reference-Format.bst` are unmodified archive copies.
  Their upstream license notices remain in the files.
- `cotb2027-preamble.tex` preserves official packages, layout and event headers;
  instruction comments were removed and the supplied `anonymous` option enabled.
  No margin, type-size or spacing reduction is used to meet the page limit.
- The template README requests an AI-use declaration in both review and final
  versions. This draft includes an anonymous, provisional declaration.

## Before submission

See `../docs/paper_preparation.md`, the independent static protocol review and the
bounded literature review. The principal analysis cannot be declared final before
the registered 2026-11-10 12:00 BRT cutoff. Authorized evidence and independent
review must support every inserted result. Keep the unchanged analysis plan and
document repairs separately. Check page count <=6, anonymity, bibliography, units,
disclosure and the complete AI-use statement after the last edit.
