# Conceptual manuscript figures

All three figures are original, code-native TikZ vector diagrams. They compile
inside the manuscript; no external image service, patient record, campaign output,
synthetic model score or observed confusion matrix is an input.

| Source | Purpose | Evidence / interpretation |
|---|---|---|
| `benchmark-flow.tex` | Show selection and evaluation order | Frozen analysis plan, train-only preprocessing, validation selection, held-out test and paired-seed contrasts. The 20 candidates apply to the primary predictive-model workflow; dummies are described separately in text. |
| `representation-variants.tex` | Compare A/B/C without implying cohort sizes | Configured inclusion and features. B requires plain numeric pain in [0,10], excluding ranges/fractions. A/C share visits; B shares patient assignments. Equal cards are not sample-size graphics. |
| `ordinal-disagreement.tex` | Explain sign and distance on an ordered label scale | Each cell is the mathematical expression predicted level minus recorded level. It is neither an observed count nor an actual prediction. Colors encode direction/magnitude; signed values also convey the distinction without color. |

Captions identify every diagram as conceptual. Each figure has an acmart
`Description` for accessibility. No figure implies that ordinal distance measures
calibrated clinical harm. The captions, text and axes must remain consistent if
the diagrams are edited. Actual result figures require a separate authorization,
disclosure check and empirical source trail.
