# External research fixture subset

Source: [jkoppel/QuixBugs](https://github.com/jkoppel/QuixBugs), revision `4257f44b0ff1181dedaedee6a447e133219fcebf`. The six selected Python algorithms, correct implementations and JSON argument/expected-output pairs are copied unchanged apart from line endings. Original copyright/permission notice and legal notes are retained.

The upstream authors supplied the bugs, reference fixes and expected outputs. TracePilot supplies only the pytest adapter, incident prompt, first-two/remaining-line split and experiment runner. Reference implementations and held-out pairs are never copied into the agent's project. Validation confirms each original buggy program fails at least one held-out case and every reference passes the visible and held-out splits.

This is independent-source authorship, **not** independent administration, novel hidden tests, a guarantee against training contamination, or a production incident benchmark. The dataset is public and old; models may know its solutions. All six cases were frozen before model results were collected, and unsuccessful observations remain in the report.

Frozen design and per-file SHA-256 fingerprints: `eval/research/manifest.json`. Adapter/runner: `backend/scripts/research.py`.
