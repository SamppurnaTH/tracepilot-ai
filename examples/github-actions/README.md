# Incident investigation in CI

Copy `tracepilot.yml` into an authorized project's `.github/workflows/`. Set repository variable `TRACEPILOT_COMMIT` to a reviewed TracePilot commit SHA, plus secrets `MODEL_API_KEY` and optionally `BASETEN_API_KEY`. Trigger manually with a symptom description. For a safe first demonstration use a copy of `targets/orders` as the target project.

The workflow runs the actual CLI in Docker and uploads `run.json`, `report.md`, `pr.md` and a patch when one exists. It never applies, commits or opens a PR. CLI exit 0 means verified **or no-code-change**; inspect `outcome` and `verification` in JSON before treating it as a code fix. Exit 1 means unverified; exit 2 means invalid input. Early failures can produce no report.

Maven default tests are discovered automatically. Add `--logs project/path/to/sanitized.log`, `--tests` or `--test-args` only when needed for your service. Do not include secret or customer data in artifacts. Repository access controls govern who can download them; retention is three days in this example.

Only run trusted repository code with provider secrets. Do not add `pull_request_target`, execute arbitrary fork commits or grant write permissions to turn this into a bot. Dependency preparation is networked; Docker's offline execution boundary starts after preparation. See `SECURITY.md`. A GitHub App with scoped installations and explicit human review is future work.

This file is a copyable integration example, not a claim of an installed GitHub App or a measured CI deployment in a third-party project.
