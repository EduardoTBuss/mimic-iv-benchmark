# Independent review: campaign byte inventory (2026-11-08)

## Outcome

**Accept, limited to the local preparation utility and the reviewed source identities.** No confirmed implementation defect was found against the requested input allowlist, explicit private scope, external receipt, exclusive output, or noncertification requirements. The capture/verify examples in the current closeout guide agree with the interface. This acceptance does not certify any actual capture, timestamp, campaign result, scientific conclusion, or service eligibility.

## Scope

Independent reviewer: Codex worker `aggregate_scope_review`, with no implementation involvement in this module or its tests. Reviewed the actual source and synthetic tests at HEAD `65a0a23805f272d6f5288c2ff913048536819e5e`, including compatibility with task IDs and producer artifact paths in the runner/evaluation/importance source. The earlier aggregate-mode review remains separate and unchanged.

Brain context was supplied by the coordinator from 2026-11-07/08 checkpoints in `projects/mimic-iv-benchmark-execucao.md` and `projects/cotb-paper-b-mimic-iv-ed-triagem.md`. The historical 810-task/zero-failure count remains unverified; the cutoff stays 2026-11-10 12:00 BRT; derivative/service eligibility remains unresolved. No direct Brain access, SSH, network, real data, real campaigns, or real reports were accessed. Only source, methodological documentation, and test definitions were read.

## Changes reviewed

| File | SHA256 |
| --- | --- |
| `scripts/campaign_inventory.py` | `239676C6026AC3C093A37CD06F3E296206CC6187FAD7134B8F15109EEB06A4E7` |
| `tests/test_campaign_inventory.py` | `2CB655208D2F19D6E70B32AF114BF7205936E63ED18326F985C79D4298351299` |
| `docs/qflex_closeout.md` (capture/verify instructions) | `1E50DC413FB856DFD0FBED246A4982D2AF83DF73603EB5AAFA4010D00471C287` |

The only file created by this follow-up review is this document. No implementation, previous review, tests, campaign files, or Brain notes were modified by the reviewer.

Source findings, with acceptance evidence:

- **Default allowlist:** `campaign_inventory.py:49-59` defines root metadata, task summaries/markers, optional cost/importance journals, and the two optional complementary aggregate tables. `_scan` (`:230`) selects those fixed names. It lists task directories to find allowed artifacts but enters `private/` only inside `if include_private`. Models, raw/prepared data, arbitrary recursive descendants, mutable control/log content and regenerated statistics tables are excluded. Listing may inspect the metadata of a private directory entry itself; the default does not list its children or hash their contents.
- **Explicit private scope:** only `capture --include-private` (`:494`) enables private hashing, and only `predictions.parquet` is selected there. Prediction bytes are streamed to SHA256; no pandas/Parquet parser, training, or analysis module is imported. `input_scope` makes private binding explicit (`:402`); verify reuses that captured, externally bound scope (`:460`). Verify does not silently downgrade a private-bound capture.
- **External digest:** verify requires `--expected-sha256` (`:497`). `_read_inventory` (`:412`) validates and compares it before constructing the output destination or scanning the campaign. It does not read the adjacent `inventory.sha256` as its trust anchor. Replacing both adjacent files does not replace an independently retained digest. Actual independent retention remains an operator responsibility that software cannot establish from a string argument.
- **Exclusive external outputs:** `_new_destination` (`:357`) rejects the campaign itself and descendants, checks the existing parent through `SafeTree`, and creates a new directory with `exist_ok=False`. `_write_new` uses `O_EXCL`; POSIX also uses `O_NOFOLLOW` and directory-relative opens. SafeTree rejects symlinks/reparse paths. No source files are rewritten or copied. Windows confidentiality requires an operator-provisioned ACL, as the module explicitly documents; POSIX requests directory/file modes 0700/0600.
- **Meaning of matching:** capture hashes the script and allowlisted bytes, preserving relative paths and structural task keys. Only `grid.json` is parsed for task structure; metric/configuration/prediction contents are not exported. Verify compares current hashes, sizes, and structural inventory with the bound capture, including added/removed empty task directories. Grid changes remain detectable by byte comparison even though verify uses the captured task keys to report the comparison.
- **No scientific or deadline claim:** policy fields state `content_validation=False`, untrusted local clock, structural presence only and no final-prefix certification. DONE/result markers are explicitly separate from missing structural artifacts. There is no cutoff/as-of input or call to the principal-analysis engine. Capture and verify do not enable principal analysis or establish a valid seed prefix. Ordinary changes are checked with stat/relisting; the module explicitly disclaims an atomic snapshot against a malicious writer.
- **CLI/error contract:** capture prints `CAPTURED`; verify prints `VERIFIED` or `DIFFERENT`; exit codes are 0/1/2 for success/difference/operational error. Parser and operational errors emit fixed codes, avoiding path/content/exception dumps (`:485`).

## Validation

This worker read the full utility and test source, inspected the actual producer task-ID format (`runner/tasks.py:23`, zero-padded seeds), and checked producer artifact filenames in evaluation and importance source. Successful read-only commands included `git rev-parse HEAD`, targeted `Get-Content`/`rg`, and `Get-FileHash -Algorithm SHA256`; script and test hashes remained stable through the review. No additional test execution was requested or performed.

The synthetic test definitions exercise default no-private descent, explicit prediction-byte binding, opaque-byte mutations, missing files, added/removed/empty task directories, optional evidence, ignored regenerated outputs, structural incompleteness, invalid grids, external-receipt substitution, clock rollback, destination exclusion/exclusivity, concurrent capture, symlink/reparse rejection, ordinary writer races, safe terminal output, CLI exit statuses and POSIX permissions. These are relevant behavioral checks rather than proof of scientific validity.

Coordinator-supplied execution evidence, **not independently rerun or certified by this worker**: Linux Q-FLEX 51/51 synthetic tests passed in 0.95 s in `validation/closeout-20261108-rdb0fnm85t`, with only the utility and test transferred; Windows inventory tests had 46 passed/5 skipped. The coordinator subsequently reported the complete synthetic suite at 376 passed, 5 skipped and 1 expected warning in 114.50 s. This review inspected no remote artifacts.

Closeout examples were checked against the parser and output contract. Capture uses a new external destination and defaults to aggregates/metadata; verify supplies the explicit independently retained digest and another new destination. The guide explains that ordinary aggregate analysis regenerates only tables excluded from this inventory's core allowlist.

## Artifacts

`docs/reviews/2026-11-08-inventory-review.md` is the review artifact. No new diagnostic files or data fixtures were created for this follow-up.

## Risks or unresolved items

No open confirmed defect in the reviewed utility. Two concrete documentation preconditions were identified during review and corrected by the coordinator before the final guide hash above: the external destination's parent must already exist, and campaign writers must stop before capture. The final guide creates the `closures/` parent and explicitly requires confirming that scheduler/merges/postprocessing are not writing before capture. No destructive stop command is prescribed.

Acceptance assumes the documented normal filesystem and campaign schema. A fresh exclusive destination can remain incomplete after a failed/interrupted capture; an adjacent receipt alone is not proof of successful publication or independent retention. The tool hashes current bytes and detects ordinary instability; it does not archive the source, certify original production time, authenticate the clock, defeat a malicious concurrent writer, verify finite metrics/predictions, or accept principal-analysis provenance. Windows ACL provisioning and semantic authorization of aggregate files remain external responsibilities. These are declared limits, not additional scientific acceptance.

Proposed Brain checkpoint for coordinator consideration only: on 2026-11-08, source/test review accepted the campaign-inventory preparation utility at the recorded hashes for default allowlist, explicit private binding, independently supplied digest and exclusive output behavior. No real capture or deadline certification occurred; principal-analysis activation, empirical checks and derivative/service eligibility remain pending.

## Independent review

Completed by Codex worker `aggregate_scope_review` for the caller's bounded inventory contract. No formula/statistical domain acceptance is inferred. Subsequent changes to the utility or documentation require assessing their effect on the recorded acceptance conditions.
