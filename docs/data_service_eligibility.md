# Public-source check: data-service eligibility

Checked: 2026-11-07. Status: **not established for this session**.

Update 2026-11-08: Eduardo authorized Q-FLEX use and analysis of aggregate
results, excluding underlying data. This establishes the requested artifact
scope, but does not itself document the service-handling guarantees required
by the original conditional restriction. Confirmation has been requested.
The PhysioNet notice below was revisited on this date. Only hardware/runtime
information and Git commit IDs were checked remotely; no campaign artifacts
were opened. See `docs/qflex_closeout.md` for local execution and the explicit
aggregates-only mode; that mode is not service-eligibility evidence.

This check used public policy/documentation only. It did not open restricted
data, campaign reports, private predictions or account credentials. It does not
relax Eduardo's explicit prohibition on using those artifacts through this service.

## Primary sources

1. PhysioNet, [Use of MIMIC Data with Large Language Models and Online
   Services](https://physionet.org/news/post/llm-responsible-use/), dated
   2025-09-24, sections **Key Requirements** and **Recommendations**. This notice
   covers credentialed/restricted MIMIC data and derivatives. For cloud processing
   it requires verified zero retention, no training use and no human review; it
   also warns that processing/logging/caching can matter. It directs researchers
   not to use a service when its handling cannot be verified and endorses no
   particular provider. Local deployment is its preferred route.
2. OpenAI, [Data controls in the OpenAI
   platform](https://developers.openai.com/api/docs/guides/your-data), sections
   **Data retention controls for abuse monitoring**, **Zero Data Retention** and
   **Storage requirements and retention controls per endpoint**. API retention
   controls require customer eligibility and approval; defaults can retain abuse
   monitoring content, and endpoint/application-state exceptions remain relevant.
   An API being eligible for a control does not show that a particular project
   has that control enabled or that every used feature qualifies.
3. OpenAI, [HIPAA configuration guide for
   Codex](https://learn.chatgpt.com/docs/hipaa-configuration), **Codex sign-in**.
   The guide distinguishes ChatGPT authentication, which follows workspace
   settings, from API-key authentication, which follows API-organization controls.
   It is cited here only for that configuration distinction, not as a finding
   that this project needs or satisfies a particular healthcare agreement.

## Consequence for this project

The 2025 PhysioNet notice is newer than the 2023 provider examples recorded in
historical project notes. Those examples cannot serve as current provider
approval. Likewise, a no-training statement alone is not evidence of zero
retention or of the full required handling guarantees.

No verified contract/configuration evidence for this session's exact service,
authentication route, organization/project controls, used features, retention,
caching or human-review handling is available in the authorized project evidence.
The sources above therefore do not establish permission to read campaign
derivatives here. Nor does this public check classify any unopened result file
as exempt from the restriction. These are scope conclusions, not a claim about
an account setting that was inspected or a vendor-wide compliance determination.

## What is needed to proceed with empirical manuscript sections

- Documented handling guarantees and enabled controls for the exact service and
  feature path, or an authorized local execution/review environment.
- Confirmation of which result-artifact categories may be used and transferred,
  preserving the existing private-data and disclosure restrictions.
- An authorized review of cutoff completeness, immutable result/configuration
  provenance, H1/H2 calculations and disclosure before inserting estimates.

Until then, maintain manuscript result markers. Code, public literature,
conceptual figures and document typesetting can proceed within the authorized
scope. Do not upload material to test whether a service is eligible.
