# Bounded literature review: model complexity and recorded ED triage acuity

Coordinator citation supplement (2026-11-06): nine bibliography records now include
the original platform reference requested alongside Pollard (2026) by the official
[PhysioNet About / Citation section](https://physionet.org/about/): Goldberger AL,
Amaral LAN, Glass L, Hausdorff JM, Ivanov PCh, Mark RG, Mietus JE, Moody GB,
Peng C-K, Stanley HE. (2000). *PhysioBank, PhysioToolkit, and PhysioNet: Components
of a New Research Resource for Complex Physiologic Signals*. Circulation
101(23):e215-e220. DOI [10.1161/01.CIR.101.23.e215](https://doi.org/10.1161/01.CIR.101.23.e215).
Metadata independently checked against the official citation block and the
[publisher PDF](https://www.ahajournals.org/doi/epdf/10.1161/01.CIR.101.23.e215),
first-page title/author block. Key: `goldberger2000physionet`. This platform
reference extends citation completeness, not the number of empirical comparisons.

Task: `MIMIC-COTB-2027-literature`. Search date: 2026-11-06.

## Question and supplied project context

Do complex models consistently predict the recorded five-level acuity label better than simple models when all models receive the same six triage vital signs plus pain?

The coordinator supplied Brain context from `projects/mimic-iv-benchmark.md` (2026-11-04/05), `mimic-iv-benchmark-execucao.md` (checkpoint 5, 2026-11-06), and `cotb-paper-b-mimic-iv-ed-triagem.md` (2026-11-04). Accepted scope: MIMIC-IV-ED 2.2; no demographics or text; patient-disjoint 70/15/15 splits with ten seeds; 20 hyperparameter configurations per model; ordinal metrics, missingness and pain sensitivities, and runtime. This review neither changes that protocol nor verifies campaign results. No local patient data or campaign artifacts were accessed or sent externally.

## Search scope and evidence status

Public-topic web queries combined `MIMIC-IV-ED`, `triage acuity`, `ordinal logistic regression`, `model comparison`, and the supplied titles/DOIs. Primary publisher pages, PMC author articles, PhysioNet/MIT documentation, and author code were preferred. Crossref was used to confirm publisher-deposited bibliographic metadata and locate a journal PDF. The bounded comparison retains seven source records below: four empirical papers, dataset documentation, a table specification, and one statistical-method reference. A subsequent integration check adds the current PhysioNet platform citation as a bibliographic supplement, not another model-comparison study. Author artifacts are supporting links, not additional studies.

This is a bounded narrative search, not a systematic review or proof of novelty. Coverage emphasizes matching targets and predictors; it does not exhaust all triage systems, languages, LLM studies, or 2026 publications. Two empirical records were assessed from publisher-indexed abstracts only; opening their publisher pages was attempted but blocked. Their methods are not treated as fully verified. `Unknown` means not established from the material accessed, not necessarily absent from the original work.

## Comparison matrix

| Primary empirical source | Target and predictors | Split / missingness | Evaluation, tuning, costs and implementation | Comparability |
|---|---|---|---|---|
| Chonde et al. (2013), publisher abstract | Assigned ESI; 947 patients at one hospital; vital signs, pain, chief complaint, age and gender; OLR uses a subset | Training-size comparison, 50–100%; exact independent test procedure, grouping and missingness unknown | OLR, neural networks and naive Bayesian networks; accuracy and evaluation speed; code and tuning unknown | Direct prior simple/complex acuity comparison; neither MIMIC nor fixed seven-feature protocol |
| Xie et al. (2022), full text | Hospitalization, critical outcome and 72-hour reattendance; vitals plus age, complaints and comorbidity; ESI is a comparator, not the target | 441,437 adult visits; random 80/20 split; patient disjointness not established by article; incomplete/pediatric exclusions; complete missing-value recipe not established here | LR/RF/GB, clinical scores, MLP/Med2Vec/LSTM; AUROC/AUPRC, bootstrapped intervals, training runtime; default conventional ML settings; public author code | Same data family and complexity question; different endpoints and predictors |
| Yaddaden et al. (2023), publisher abstract | ESI, hospitalization and mortality; MIMIC-IV and MIMIC-IV-ED; exact predictors unknown | Split, patient grouping, cohort and missingness unknown | Polynomial features and PCA; LR/RF/decision tree; abstract reports 99.80% acuity accuracy; tuning, ordinal metrics, runtime and code unknown | Direct acuity precedent; reported accuracy cannot be compared without full protocol |
| Li et al. (2025), full text | Recorded acuity; vitals/pain plus NEWS and abnormal-vital count; hybrid adds chief complaints | 391,533 retained records; 70/15/15 split; patient grouping, seed repetition and missing-value handling unknown; range filtering | RF/GB/feed-forward baseline; transformer hybrid; Hyperband; accuracy, class precision/recall, ROC/PR; test accuracy 0.5932/0.5941/0.6014 vs hybrid 0.7065; public code and measured runtime not located | Closest numerical baseline; engineered scores and text differ; no ordinal error metric established |

**Interpretation (reviewer's inference):** These protocols cannot support a cross-paper ranking. Differences in target, information available to models, cohort filtering and split unit can dominate apparent performance differences. Any empirical claim for the present benchmark must come from its own matched comparisons.

## Source register and precise supporting locations

1. **Chonde, Seifu J.; Ashour, Omar M.; Nembhard, David A.; Kremer, Gül E. Okudan. (2013).** *Model comparison in Emergency Severity Index level prediction*. Expert Systems with Applications 40(17):6901–6909. [DOI 10.1016/j.eswa.2013.06.026](https://doi.org/10.1016/j.eswa.2013.06.026). [Publisher abstract](https://www.sciencedirect.com/science/article/abs/pii/S0957417413004065), **Abstract**; direct open returned HTTP 403. Crossref confirms citation metadata. Supports the existence of an earlier explicit OLR/neural/Bayesian ESI comparison, not a reproducible reconstruction. BibTeX: `chonde2013comparison`.

2. **Xie, Feng; Zhou, Jun; Lee, Jin Wee; Tan, Mingrui; Li, Siqi; Rajnthern, Logasan; Chee, Marcel Lucas; Chakraborty, Bibhas; Wong, An-Kwok Ian; Dagan, Alon; Ong, Marcus Eng Hock; Gao, Fei; Liu, Nan. (2022).** *Benchmarking emergency department prediction models with machine learning and public electronic health records*. Scientific Data 9:658. [DOI 10.1038/s41597-022-01782-9](https://doi.org/10.1038/s41597-022-01782-9); [full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC9610299/), **Benchmark tasks; Table 1; Experiments, settings, and evaluation; Baseline characteristics; Tables 4–7; Discussion**. [Author repository](https://github.com/nliulab/mimic4ed-benchmark), **Requirements and Setup / Cohort Filtering**, references version 1.0; do not silently substitute 2.2. BibTeX: `xie2022benchmark`.

3. **Yaddaden, Yacine; Benahmed, Yacine; Rioux, Marc-Denis; Kallel, Mariem. (2023).** *Machine Learning-Based Pre-Diagnosis Tools in Emergency Departments: Predicting Hospitalization, Mortality and Triage Acuity*. 2023 IEEE Third International Conference on Signal, Control and Communication (SCC). [DOI 10.1109/SCC59637.2023.10527491](https://doi.org/10.1109/SCC59637.2023.10527491); [publisher record](https://ieeexplore.ieee.org/document/10527491/), **Abstract** accessible through the search index; direct open presented an anti-bot page. Conference year is 2023; Xplore addition is 2024. The abstract's result is an author claim, not an independently verified generalization estimate. BibTeX: `scc2023prediagnosis`.

4. **Li, Zongrun; Lockington, Julie; Torres, Samya; Jafari, Nooshin; Lim, Michael; Andjelic, Dragan; Cretu, Edmond; Ho, Kendall; Gopaluni, Bhushan. (2025).** *Hybrid triaging assistance algorithm for continuous patient monitoring*. Digital Health 11:20552076251388141. [DOI 10.1177/20552076251388141](https://doi.org/10.1177/20552076251388141); [full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC12583869/), **Methods; Table 1; Results, filtering paragraph; Table 2; Limitations**. Secondary filtering retains the modal acuity within NEWS/complaint groups. **Inference:** this changes the evaluated population using labels and cannot establish performance on the original population. The article discusses CTAS although its cited dataset defines ESI; preserve the official dataset label definition. BibTeX: `li2025hybrid`.

5. **Johnson, Alistair; Bulgarelli, Lucas; Pollard, Tom; Celi, Leo Anthony; Mark, Roger; Horng, Steven. (2023), version 2.2.** *MIMIC-IV-ED*. PhysioNet. [DOI 10.13026/5ntk-km72](https://doi.org/10.13026/5ntk-km72); [official record](https://physionet.org/content/mimic-iv-ed/2.2/), **Data Description: triage; Release Notes: v2.0/v2.2; Limitations**. Defines six triage vitals, pain and acuity 1–5; v2.0 preserved nonnumeric pain strings, while v2.2 removed a held-back patient subset. Routine records can contain implausible measurements and missing documentation. BibTeX: `mimicived22`.

6. **MIT Laboratory for Computational Physiology (undated living documentation; accessed 2026-11-06).** *The triage table*. [Official specification](https://mimic.mit.edu/docs/iv/modules/ed/triage.html), **Important considerations; temperature; pain; acuity**. Documents nurse-assigned ESI, absence of observation timestamps, and possible temperature-unit errors. Its prose on numeric pain conversion is less version-specific than the PhysioNet release notes; use the versioned source for pain storage. **Inference:** agreement with a documented nurse label does not establish clinical correctness or justify deployment. BibTeX: `mimictriagedoc`.

7. **Nadeau, Claude; Bengio, Yoshua. (2003).** *Inference for the Generalization Error*. Machine Learning 52(3):239–281. [DOI 10.1023/A:1024068626366](https://doi.org/10.1023/A:1024068626366); [publisher record](https://link.springer.com/article/10.1023/A:1024068626366), **Abstract / Cite this article** verifies the journal citation. The same authors' [1999 primary conference paper](https://papers.nips.cc/paper_files/paper/1999/file/7d12b66d3df6af8d429c1a357d8b9e1a-Paper.pdf), **Section 1, pp. 307–308; Section 3, p. 310, equation (7)**, provides the inspected derivation: overlapping resamples invalidate independence-based variance estimates; the corrected estimator approximates the correlation, giving `(1/J + n_test/n_train) s²`. It can over- or underestimate variance. **Inference:** ten seeds do not create ten independent cohorts; application to patient clusters, a separate validation subset and nonlinear aggregate metrics needs justification. No protocol change is proposed. BibTeX: `nadeau2003inference`.

### Platform citation supplement (integration check, 2026-11-06)

**Pollard, Tom; Moody, Benjamin E.; Lehman, Li-wei H.; Gow, Brian J.; Fernandes, Chrystinne; Xie, Chen; Johnson, Alistair; Mark, Roger G.; Heldt, Thomas. (2026).** *PhysioNet as a global platform for biomedical research*. Nature Health 1(8):792–795. [DOI 10.1038/s44360-026-00096-z](https://doi.org/10.1038/s44360-026-00096-z); [primary author manuscript](https://pmc.ncbi.nlm.nih.gov/articles/PMC13641116/), **publication header and author list**. Publisher-deposited Crossref metadata corroborates authors, journal, volume, issue, pages and online publication on 2026-03-26; the manuscript identifies the August issue. Direct Nature access was blocked by its cookie redirect. BibTeX: `physionet2026`.

The [version 2.2 resource page](https://physionet.org/content/mimic-iv-ed/2.2/), **citation block immediately above Abstract**, separately requests the dataset citation and says, “Please include the standard citation for PhysioNet,” followed by this 2026 article. Thus retain `mimicived22` and add `physionet2026` where introducing dataset provenance. The platform paper is not evidence about acuity model performance. A broader [PhysioNet About page](https://physionet.org/about/), **Citation**, additionally asks for Goldberger et al. (2000); this broader instruction is flagged for coordinator integration rather than silently treated as an additional comparative study.

Suggested sentence: “We used MIMIC-IV-ED version 2.2, distributed through PhysioNet (`mimicived22`; `physionet2026`).”

## Unverified lead retained for follow-up, excluded from bibliography

*Predictive Modeling in Triage Using Ordinal Logistic Regression: A Study Based on the MIMIC-IV-ED Dataset*, DOI `10.32997/rcb-2025-5945`, 2025. Crossref supplies publisher metadata and [the journal landing page](https://revistas.unicartagena.edu.co/index.php/cbiomedicas/article/view/5945), plus [the version-of-record PDF](https://revistas.unicartagena.edu.co/index.php/cbiomedicas/article/download/5945/4507). Both primary pages returned HTTP 403; the DOI could not be opened. Secondary-index details were not promoted into evidence. Obtain this exact journal PDF before stating its features, splitting protocol or results.

## Conservative manuscript position

Use a bounded contribution statement: **“We compare simple and complex models under a common seven-feature, patient-disjoint protocol for predicting recorded triage acuity, reporting ordinal performance, preprocessing sensitivities and computational cost.”** The supplied protocol is the basis of this statement, not a conclusion drawn from external papers.

Avoid “first,” “state of the art,” claims of clinical superiority, or assertions that complex models generally fail. A six-page manuscript can cite the nearest acuity precedents briefly, distinguish the outcome benchmark, and reserve space for its own design and uncertainty. Report the actual search limits if discussing a gap. Recommend methodology review by `experiment-design-statistics-reviewer` for the exact estimand, corrected resampling calculation, multiplicity and interpretation of practical differences. Such review is recommended here, not performed or newly commissioned by this worker.

## Proposed Brain checkpoint (coordinator review only)

2026-11-06 — Bounded public-source review completed for COTB acuity paper. Evidence matrix and access limits: `docs/literature_review.md`; verified bibliographic records: `paper/references.bib`. Direct acuity precedents include Chonde 2013, SCC 2023 and Li 2025; Xie 2022 predicts downstream outcomes. No primacy claim is warranted. Ordinal-regression 2025 journal PDF remains inaccessible and excluded. Existing protocol preserved; no patient/campaign artifacts accessed, new experiments run, or Brain notes changed. Next: coordinator integrates concise related work and reviewer checks statistical comparability.

Integration addendum, 2026-11-06 — Current v2.2 citation instructions verified and `physionet2026` added as platform provenance alongside the dataset citation. Seven-source comparative scope retained; platform source is a supplement. Broader About-page request also names Goldberger 2000; coordinator should reconcile citation coverage before submission.
