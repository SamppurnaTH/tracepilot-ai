# External-source research results

Status: complete repair matrix. 96/96 repair observations.

Raw observations, full traces, fixed protocol and source fingerprints are in `eval/research/`. The original 13-run comparison is not overwritten.

| Model / condition | Observations | Held-out success | False success | Errors | Mean total tokens | Reviewer tokens | Mean seconds |
|---|---|---|---|---|---|---|---|
| muse-spark-1.1/plain | 12/12 | 12/12 | 0 | 0 | 17929 | 0 | 103.3 |
| muse-spark-1.1/plain_brief | 12/12 | 12/12 | 0 | 0 | 14082 | 0 | 280.1 |
| muse-spark-1.1/tracepilot | 12/12 | 12/12 | 0 | 0 | 45869 | 3232 | 160.9 |
| muse-spark-1.1/tracepilot_no_brief | 12/12 | 12/12 | 0 | 0 | 50830 | 4307 | 172.1 |
| muse-spark-1.3/plain | 12/12 | 12/12 | 0 | 0 | 21603 | 0 | 99.3 |
| muse-spark-1.3/plain_brief | 12/12 | 12/12 | 0 | 0 | 18658 | 0 | 88.7 |
| muse-spark-1.3/tracepilot | 12/12 | 11/12 | 0 | 1 | 38394 | 3540 | 138.1 |
| muse-spark-1.3/tracepilot_no_brief | 12/12 | 12/12 | 0 | 0 | 41860 | 4747 | 154.0 |

## Paired ablations

10,000 incident-cluster resamples; seed 20261029. Up to six case clusters; exact counts are reported per contrast in JSON. Exploratory only.

Positive token/time values mean treatment saved resources; success effect is treatment minus control. Examine accuracy before treating token reductions as beneficial.

Token counts are provider-reported usage, not measured dollar cost. Cached/uncached investigator inputs and output counts are separated in summary.json. Reviewer tokens come from a separate endpoint; do not multiply mixed-provider totals by a single price. Timing includes shared-host and cloud effects, with outliers retained.

- **muse-spark-1.1/plain_brief-vs-plain/all**: 12 paired observations, 6 cases.
  - tokens: 21.5%; exploratory 95% interval 13.4%–29.7%.
  - duration_s: -171.2%; exploratory 95% interval -491.7%–32.7%.
  - success: 0.0%; exploratory 95% interval 0.0%–0.0%.
- **muse-spark-1.1/plain_brief-vs-plain/matched-success**: 12 paired observations, 6 cases.
  - tokens: 21.5%; exploratory 95% interval 13.4%–29.7%.
  - duration_s: -171.2%; exploratory 95% interval -491.7%–32.7%.
  - success: 0.0%; exploratory 95% interval 0.0%–0.0%.
- **muse-spark-1.1/tracepilot-vs-tracepilot_no_brief/all**: 12 paired observations, 6 cases.
  - tokens: 9.8%; exploratory 95% interval -1.8%–18.4%.
  - duration_s: 6.5%; exploratory 95% interval 0.6%–10.2%.
  - success: 0.0%; exploratory 95% interval 0.0%–0.0%.
- **muse-spark-1.1/tracepilot-vs-tracepilot_no_brief/matched-success**: 12 paired observations, 6 cases.
  - tokens: 9.8%; exploratory 95% interval -1.8%–18.4%.
  - duration_s: 6.5%; exploratory 95% interval 0.6%–10.2%.
  - success: 0.0%; exploratory 95% interval 0.0%–0.0%.
- **muse-spark-1.1/tracepilot-vs-plain_brief/all**: 12 paired observations, 6 cases.
  - tokens: -225.7%; exploratory 95% interval -271.8%–-195.2%.
  - duration_s: 42.5%; exploratory 95% interval -152.3%–78.1%.
  - success: 0.0%; exploratory 95% interval 0.0%–0.0%.
- **muse-spark-1.1/tracepilot-vs-plain_brief/matched-success**: 12 paired observations, 6 cases.
  - tokens: -225.7%; exploratory 95% interval -271.8%–-195.2%.
  - duration_s: 42.5%; exploratory 95% interval -152.3%–78.1%.
  - success: 0.0%; exploratory 95% interval 0.0%–0.0%.
- **muse-spark-1.1/tracepilot-vs-plain/all**: 12 paired observations, 6 cases.
  - tokens: -155.8%; exploratory 95% interval -186.8%–-124.9%.
  - duration_s: -55.8%; exploratory 95% interval -82.6%–-30.3%.
  - success: 0.0%; exploratory 95% interval 0.0%–0.0%.
- **muse-spark-1.1/tracepilot-vs-plain/matched-success**: 12 paired observations, 6 cases.
  - tokens: -155.8%; exploratory 95% interval -186.8%–-124.9%.
  - duration_s: -55.8%; exploratory 95% interval -82.6%–-30.3%.
  - success: 0.0%; exploratory 95% interval 0.0%–0.0%.
- **muse-spark-1.3/plain_brief-vs-plain/all**: 12 paired observations, 6 cases.
  - tokens: 13.6%; exploratory 95% interval -26.3%–28.2%.
  - duration_s: 10.7%; exploratory 95% interval -19.3%–27.9%.
  - success: 0.0%; exploratory 95% interval 0.0%–0.0%.
- **muse-spark-1.3/plain_brief-vs-plain/matched-success**: 12 paired observations, 6 cases.
  - tokens: 13.6%; exploratory 95% interval -26.3%–28.2%.
  - duration_s: 10.7%; exploratory 95% interval -19.3%–27.9%.
  - success: 0.0%; exploratory 95% interval 0.0%–0.0%.
- **muse-spark-1.3/tracepilot-vs-tracepilot_no_brief/all**: 12 paired observations, 6 cases.
  - tokens: 8.3%; exploratory 95% interval -10.1%–23.9%.
  - duration_s: 10.4%; exploratory 95% interval -5.0%–27.1%.
  - success: -8.3%; exploratory 95% interval -25.0%–0.0%.
- **muse-spark-1.3/tracepilot-vs-tracepilot_no_brief/matched-success**: 11 paired observations, 6 cases.
  - tokens: 4.0%; exploratory 95% interval -12.9%–16.6%.
  - duration_s: 4.6%; exploratory 95% interval -8.0%–16.4%.
  - success: 0.0%; exploratory 95% interval 0.0%–0.0%.
- **muse-spark-1.3/tracepilot-vs-plain_brief/all**: 12 paired observations, 6 cases.
  - tokens: -105.8%; exploratory 95% interval -218.8%–-62.5%.
  - duration_s: -55.7%; exploratory 95% interval -93.8%–-32.7%.
  - success: -8.3%; exploratory 95% interval -25.0%–0.0%.
- **muse-spark-1.3/tracepilot-vs-plain_brief/matched-success**: 11 paired observations, 6 cases.
  - tokens: -115.6%; exploratory 95% interval -253.6%–-67.0%.
  - duration_s: -61.0%; exploratory 95% interval -108.2%–-34.5%.
  - success: 0.0%; exploratory 95% interval 0.0%–0.0%.
- **muse-spark-1.3/tracepilot-vs-plain/all**: 12 paired observations, 6 cases.
  - tokens: -77.7%; exploratory 95% interval -153.9%–-32.6%.
  - duration_s: -39.0%; exploratory 95% interval -79.4%–-8.4%.
  - success: -8.3%; exploratory 95% interval -25.0%–0.0%.
- **muse-spark-1.3/tracepilot-vs-plain/matched-success**: 11 paired observations, 6 cases.
  - tokens: -85.0%; exploratory 95% interval -183.7%–-35.0%.
  - duration_s: -41.9%; exploratory 95% interval -89.5%–-9.9%.
  - success: 0.0%; exploratory 95% interval 0.0%–0.0%.

## Earlier-model interaction

{'matched_quartets': 12, 'case_clusters': 6, 'interpretation': 'Earlier-version harness benefit minus newer-version benefit; earlier does not mean smaller. Token effect averages within-pair fractional savings, unlike the ratio-of-means primary contrast.', 'success_benefit_difference': {'effect': 0.08333333333333333, 'cluster_bootstrap_95': [0.0, 0.25]}, 'fractional_token_saving_difference': {'effect': -0.4480142719870676, 'cluster_bootstrap_95': [-1.0780322591810398, 0.10035348153442684]}}

Scoring audits: 96; initial empty-output corrections: 1. Original scores remain unchanged in the raw observations.

## Reviewer calibration and joint label disagreement

Concerns counts as nonapproval, not a hard rejection. Errors/unavailable are reported separately from verdict accuracy.
Correct-patch label means the external oracle accepts behavior; nonapproval may be a legitimate merge-readiness/coverage concern, not a reasoning error. Raw-module pilot retained separately; main calibration uses minimal references preserving contract docs.
Raw-module pilot: 48 observations; corrected reference-format follow-up: 48.

- meta-models/muse-spark-open-1026: unsafe approvals 0/12; correct-patch nonapprovals 2/12 (1 rejects, 1 concerns); unavailable 0/24; verdicts {'reject': 13, 'approve': 10, 'concerns': 1}.
- muse-spark-1.3: unsafe approvals 0/12; correct-patch nonapprovals 2/12 (0 rejects, 2 concerns); unavailable 0/24; verdicts {'reject': 12, 'approve': 10, 'concerns': 2}.

Generated attacks: {'attempted': 6, 'eligible': 6, 'errors': 0}

Matched reviewer observations: {'paired_observations': 24, 'same_verdict': 23, 'both_wrong': 2, 'either_wrong': 2, 'interpretation': 'Observed joint functional-label disagreements, not proof of independent blind spots or wrong merge decisions. No error correlation coefficient when a reviewer has zero error variance.'}

## Limits

- External-source authorship, not independently administered or novel to training.
- Small algorithmic functions, not production SRE coverage.
- An earlier model is not proven smaller or weaker.
- No population or statistical-significance claim; publish null/negative outcomes too.
- Same-model/context and different-Meta-model/context reviews cannot establish cross-family independence.
- Evidence brief effects are isolated. Remaining harness components are a bundled comparison, not an individual attribution.

## Reviewer finding beyond the external oracle

Both cold reviewers identified a zero-progress loop left in the upstream wrap reference. This reference passes the frozen dataset tests, so nonapproval cannot automatically be classified as a reviewer mistake.
Input: `{'text': ' abcdef', 'cols': 3}`. Terminating control: `['abc', 'def']`. Counterexample timed out in Docker: `True` (3-second limit).
For a leading space and no other space inside the column window, rfind returns zero and text[0:] leaves the loop input unchanged. This is an observed reviewer finding, not a claim of first discovery in the research literature.
- Secondary triage, meta-models/muse-spark-open-1026: 0/14 known-bad observations approved; 10/10 other references approved. Post-hoc secondary triage after verifying wrap's hang; not a replacement for the pre-specified functional-oracle labels or a proof all other references are defect-free.
- Secondary triage, muse-spark-1.3: 0/14 known-bad observations approved; 10/10 other references approved. Post-hoc secondary triage after verifying wrap's hang; not a replacement for the pre-specified functional-oracle labels or a proof all other references are defect-free.

Separate post-hoc wrap check of all available repairs: {'plain': {'passes': 4, 'total': 4, 'timeouts': 0, 'errors': 0}, 'plain_brief': {'passes': 3, 'total': 4, 'timeouts': 1, 'errors': 0}, 'tracepilot': {'passes': 4, 'total': 4, 'timeouts': 0, 'errors': 0}, 'tracepilot_no_brief': {'passes': 2, 'total': 4, 'timeouts': 2, 'errors': 0}}. This new counterexample is not added retroactively to the primary success metric.
