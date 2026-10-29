# Research protocol — frozen before model observations

## Questions

1. Does the evidence brief account for the original token-saving claim, and does the remaining harness help after a plain agent receives the same brief?
2. Does the workflow work on another accessible Meta model version?
3. Does success extend to independently authored bugs/tests rather than only TracePilot's fixtures?
4. How often do same-model and different-Meta-model cold reviewers approve incorrect patches or fail to approve correct ones?
5. Can the reviewer catch overfitting patches generated without access to the held-out oracle, instead of only hand-crafted attacks?

## Paired repair matrix

`eval/research/manifest.json` freezes six QuixBugs algorithms, upstream revision, source hashes, split, models, conditions, repeat count, shuffled job order and budget before collecting results. Every observation uses a fresh Docker sandbox with no network and the same visible source/tests. All trials, including infrastructure/model errors, are retained. Resume skips only existing saved observation IDs; it does not replace failures.

- Models: Muse Spark 1.1 and 1.3. Version 1.1 is an earlier model, **not asserted to be smaller or weaker**. Responses API availability is checked; requested model IDs are recorded per trial; access probes returned the requested version IDs.
- Conditions: plain; plain plus evidence brief; TracePilot; TracePilot without brief delivery.
- Six independently authored algorithms × two models × four conditions × two repetitions = **96 observations**. Two concurrent jobs maximum, 80,000-token investigator budget per trial (phase wrapping can exceed the threshold). Reviewer tokens are reported separately and included in full-system totals.
- Visible tests: first two upstream JSON lines. Held-out tests: all remaining upstream lines. Both splits keep upstream expected outputs and exact equality semantics. No test is selected after viewing a model patch.
- TracePilot-authored adapters and incident prompt are disclosed; the buggy/reference implementations and expected outputs originate upstream. An oracle validation checks known buggy/reference behavior before inference.

## Contrasts and inference limits

Within each model, pair observations by case and repetition. `plain_brief − plain` isolates brief delivery in the plain workflow. `tracepilot − tracepilot_no_brief` isolates brief delivery in TracePilot. `tracepilot − plain_brief` compares the remaining **bundled** method after evidence delivery is controlled; it does not isolate hypotheses, context compaction, phase gating or review individually. We do not assign percentages of the historical 31% saving to untested components.

Report investigator tokens, reviewer tokens, total tokens, visible/held-out success, false-success counts, errors and measured wall time. Token comparisons include failed runs and are also shown restricted to matched successful pairs. Faster/cheaper is not better if correctness falls. Report paired effects and incident-cluster bootstrap intervals with fixed seed; descriptive Wilson intervals do not make repeated cases independent. These are exploratory small-sample results, not a proof of a population effect.

## Reviewer extension

Freeze a separate protocol before generating adversarial patches. Generate patches using earlier Meta-model calls that see only the buggy source and visible tests, with a fixed request to overfit those tests. Do not call the patches incorrect merely because they were generated adversarially: label them by independently sourced held-out outcomes. Retain generation/validation failures and non-overfitting results. Reference fixes come from upstream and must pass both splits.

Use the same incident, facts, diff, changed file, and visible verification summary for cold reviewers: Muse Spark 1.3 (same model as the main investigator) and Muse Spark Open (different Meta model). Neither sees held-out tests, labels or the generator explanation. Run both on all eligible patches and report unsafe approvals, correct-patch nonapprovals, hard rejects versus concerns, agreement, and joint errors. Same-vendor results cannot establish independent model-family blind spots; this measures the observed behavior under controlled context.

## What cannot be “closed” by this study

Independent-source tests are not an external audit. Public algorithms are not unseen private repositories or production concurrency workloads. An earlier-model study is not a demonstrated small-model advantage. No ranking or broad security/generalization guarantee follows from these experiments. Positive, null and negative results must all update the presentation honestly.

## Scoring audit and reviewer sensitivity clarification

During collection, one scorer produced no held-out outcomes. A diagnostic rerun of the unchanged patch passed. Every saved patch will therefore receive a separate oracle audit, with both initial and audited results retained. Empty outcomes are scoring unavailability, not evidence of a model error. Inference trials are never rerun to improve their results.

The raw upstream reference modules include archived duplicate code in strings and replace original contract documentation. Reviewers correctly noticed those maintainability changes. The raw-reference pilot is preserved; a separately frozen post-pilot sensitivity follow-up uses the upstream executable FunctionDef prefix verbatim and preserves the original contract tail. Both visible and held-out behavior are validated before new reviews. A nonapproval of an oracle-accepted patch remains a functional-label disagreement, not automatically an incorrect merge decision.

The repair pool uses two workers and the review pool uses two workers; auxiliary model generation and scoring may overlap on the same host. Timing is observational under shared infrastructure, not an isolated latency benchmark. Large elapsed-time outliers are retained rather than discarded.

The frozen manifests are local audit artifacts, not a publicly registered protocol. Per-trial harness hashes were added before the main batch; the first two planned access-preflight observations predate that metadata field and are retained under their original IDs, without replacing their outcomes. The core dataset/split/condition/repetition manifest predates them.

## Focused service-domain extension

A separate plan in `eval/service-ablation/manifest.json` fixes Orders (red CI) and Inventory (green CI), Muse Spark 1.3, the same four workflow conditions and two repetitions: 16 observations. This directly checks the brief question on original-domain incidents. It uses the original project-authored hidden oracles, not the external-source QuixBugs oracle. Source/oracle hashes were frozen before launch; validation of both reference fixes completed alongside the first trials without changing the oracle. Production token thresholds are used, with method-specific reproduction/review retry overhead disclosed.

Its paired and individual-case effects are descriptive: two case clusters do not support population confidence claims. The new observations cannot retroactively decompose the historical 13-run average. The two-worker service pool overlaps the external study; cloud latency is not an isolated experimental variable.
