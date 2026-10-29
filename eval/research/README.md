# Reproducing the research

Read `docs/RESEARCH_PROTOCOL.md` before interpreting the results. Source, split, conditions and repeats were frozen in `manifest.json`; model-generated attacks have their own `reviewer-manifest.json`. `reviewer-clean-manifest.json` records a separately labelled post-pilot reference-format sensitivity study. Do not merge pilot and follow-up rates.

## Files

- `observations/`: immutable repair outcomes, usage, patch, initial oracle score and provenance.
- `runs/`: full recorded reports/events, including unverified or failed investigations.
- `score-audits/`: a second scoring pass for **every** saved patch. Initial scores remain unchanged; empty outcomes are infrastructure unavailability, not automatically a false success.
- `generated-attacks/`: fixed generator prompt, visible-only input, raw response, code, usage and external-oracle validation. The generator never sees reference code or held-out rows.
- `review-observations/`: original raw-upstream-module reviewer pilot, retained even where its merge-readiness labels are inappropriate.
- `review-clean-observations/`: follow-up using minimal upstream executable fixes with original documentation preserved, plus the exact same generated attacks.
- `summary.json`, `RESULTS.md`: deterministic aggregations. A missing cell remains missing; a completed trial is not silently retried for a better model outcome.

## Inspect or resume this frozen experiment

Python 3.11+, Git, Docker and configured Meta/Baseten credentials are required. Commands from repository root:

```bash
python backend/scripts/research.py validate
python backend/scripts/research.py run
python backend/scripts/research.py audit
python backend/scripts/research.py attacks
python backend/scripts/research.py reviewers
python backend/scripts/research.py clean-prepare
python backend/scripts/research.py clean-reviewers
python backend/scripts/research_summary.py
```

Existing observation IDs are skipped. `audit-watch` is a finite local helper that audits new files until the frozen repair count is reached; it is not a recurring service.

## Independent replication without replacing published results

Clone QuixBugs and check out the revision named in the manifest. Set the desired Meta model endpoints in your own local environment; never share keys. Use the same `--study-dir` on **every** research command:

```bash
git clone https://github.com/jkoppel/QuixBugs.git runs/research/replication-upstream
git -C runs/research/replication-upstream checkout 4257f44b0ff1181dedaedee6a447e133219fcebf
python backend/scripts/research.py prepare --upstream runs/research/replication-upstream --study-dir runs/research/replication
python backend/scripts/research.py validate --study-dir runs/research/replication
python backend/scripts/research.py run --study-dir runs/research/replication
python backend/scripts/research.py audit --study-dir runs/research/replication
python backend/scripts/research.py reviewer-prepare --study-dir runs/research/replication
python backend/scripts/research.py attacks --study-dir runs/research/replication
python backend/scripts/research.py reviewers --study-dir runs/research/replication
python backend/scripts/research.py clean-prepare --study-dir runs/research/replication
python backend/scripts/research.py clean-reviewers --study-dir runs/research/replication
python backend/scripts/research_summary.py --study-dir runs/research/replication
```

Replication summaries stay in their separate directory. Public-source familiarity and vendor model revisions can affect reproduction. A third party must actually perform a replication before we can claim external administration or independent confirmation.

## Measured software version and later safeguard

The completed trials used the preserved application modules in `harness-snapshot/backend/app`; their LF-normalized hashes match per-trial fingerprints. The first two planned preflight observations predate the fingerprint metadata field and are retained unchanged. Before replicating the measured version, copy the snapshot modules into backend/app in a **separate matching checkout**, then follow the separate-study-dir commands above. Current product code adds a later review-required/apply gate; do not describe a current-code rerun as an exact replication of the older measured harness.
