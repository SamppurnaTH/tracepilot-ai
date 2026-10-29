# Original-domain service ablation

Complete: 16/16 observations.

Model: Muse Spark 1.3. Cases: Orders (red CI) and Inventory (green CI). Four configurations, two repetitions. Source and oracle hashes were frozen in manifest.json before inference.

| Workflow | Observed | Held-out pass | Errors | Score unavailable | False success | Mean total tokens | Mean reviewer tokens |
|---|---|---|---|---|---|---|---|
| plain | 4/4 | 4/4 | 0 | 0 | 0 | 117773 | 0 |
| plain_brief | 4/4 | 4/4 | 0 | 0 | 0 | 84379 | 0 |
| tracepilot | 4/4 | 4/4 | 0 | 0 | 0 | 110957 | 4420 |
| tracepilot_no_brief | 4/4 | 4/4 | 0 | 0 | 0 | 177110 | 5760 |

## Paired token contrasts

Positive saving means the first workflow used fewer total tokens. A negative value means overhead. With two cases these are descriptive, not population-level causal estimates.

- plain_brief-vs-plain: 4 matched pairs, token saving 28.4%, success difference 0.0%.
- tracepilot-vs-tracepilot_no_brief: 4 matched pairs, token saving 37.4%, success difference 0.0%.
- tracepilot-vs-plain_brief: 4 matched pairs, token saving -31.5%, success difference 0.0%.
- tracepilot-vs-plain: 4 matched pairs, token saving 5.8%, success difference 0.0%.

## Per-case contrasts

- orders/plain_brief-vs-plain: 2 pairs, token saving 37.9%.
- inventory/plain_brief-vs-plain: 2 pairs, token saving 25.8%.
- orders/tracepilot-vs-tracepilot_no_brief: 2 pairs, token saving 27.3%.
- inventory/tracepilot-vs-tracepilot_no_brief: 2 pairs, token saving 41.4%.
- orders/tracepilot-vs-plain_brief: 2 pairs, token saving -135.8%.
- inventory/tracepilot-vs-plain_brief: 2 pairs, token saving -7.9%.
- orders/tracepilot-vs-plain: 2 pairs, token saving -46.4%.
- inventory/tracepilot-vs-plain: 2 pairs, token saving 19.9%.

## Limits

- Two project-authored service cases only; do not treat two-cluster bootstrap ranges as population confidence intervals.
- This is a new contemporaneous check, not a causal decomposition of the historical 13-run mean.
- Full method includes reviewer and report overhead; only evidence-brief delivery is isolated.
- Cloud/host work is concurrent; no isolated latency claim or token-to-dollar conversion.
