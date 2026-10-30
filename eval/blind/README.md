# Model-blinded real-bug study

Read [RESULTS.md](RESULTS.md) for every recorded outcome, separated by round.

## What is hidden

The investigator receives a clean Git archive of the first parent of each pinned fix, without `.git`, plus the incident in `backend/scripts/blind_study.py`. It is not given the fix diff, fix SHA, future test files, or test-oracle labels. Tool execution has no network in the Docker sandbox. The judge applies the candidate diff to another clean parent tree, replaces the specified test files with their upstream fixed-revision versions, and checks every target test plus other failures in those files.

Study authors selected the bugs while knowing the upstream fixes. This is model-blinded, not double-blind or independently administered. Five incidents were adapted from PR descriptions, and the original inflect issue includes a root-cause hint. Neither recent dates nor hidden test files establish that a public bug is absent from model training.

One study attempt means one invocation of `Investigation.run()`, including the normal built-in fix/reproduction rounds and reviewer-rejection loop. It does not mean a single model call or a single candidate edit. Those internal rounds are visible in the event trace; no investigator was restarted after seeing its hidden score.

## Files

- `manifest.json`: pinned parent/fix revisions, image tags, target test IDs and oracle validation counts. Prepared before the recorded attempts; never overwritten during this follow-up.
- `source-verification.json`: GitHub PR metadata confirms the pinned merge commits and dates.
- `oracle-hashes.json`: SHA-256 values for the parent and fixed test files.
- `observations.jsonl`: append-only outcome rows; missing `round` means round 1. Errors remain in the denominator. Missing usage on a failed attempt means unknown, not zero cost.
- `round-1/`: original reports recovered from the cache before replacement. The original API-crash attempt has no cached report.
- `round-2-protocol.json`, `round-2-harness/`: local follow-up protocol and software snapshot; not a public preregistration. Runner persistence/reporting was hardened during setup; the inference modules are snapshotted. Protocol and `sha256.json` hashes preserve the original Windows working-tree bytes; use `sha256-lf.json` after normalizing CRLF to LF when checking a Git checkout on another platform.
- `round-2/<case>/`: progressively saved events, report, patch and held-out per-test outcomes when available. An API failure can have events without a final report or patch.
- `trace-index.json`: compact phase/verification index and trace hashes. The unabridged Packaging trace is large because it retains the oversized test feedback; download it if the repository viewer truncates it.
- `licenses/`: upstream license notices for code excerpts in saved traces.

## Commands

Use `.venv/Scripts/python` and running Docker Desktop. Configure credentials locally; do not put credentials in command arguments or evidence files.

```powershell
.venv/Scripts/python backend/scripts/blind_study.py run
.venv/Scripts/python backend/scripts/blind_study.py summarize
```

`run` resumes only cases without an observation or an attempt directory in round 2. It never retries a completed failure. `summarize` makes no model calls. `prepare` refuses to replace an existing oracle manifest. To independently reproduce, use a separate matching checkout and cache, restore the snapshotted inference modules there, and collect a new labelled study; do not overwrite these observations. Cache location is `~/.cache/tracepilot-blind/`.

## Scope

The hidden score covers only the test files named in the manifest. Existing collection errors may exclude unrelated test files from the investigator's verification; those exclusions are reported. A test-green result is not a formal proof, a production guarantee, or permission to apply a patch with unresolved reviewer objections. No case is repeated to improve its score. Round 2 is explicitly a follow-up after round-1 harness failures, not seven independent fresh cases.

This study has no paired plain-agent control, so it does not establish an advantage over another coding agent. The cases are selected public Python libraries, not a representative sample of private repositories or production incidents.

Result-table token counts cover the investigator only; reviewer usage is separate in completed reports. Missing usage after an API failure is unknown, not zero. Investigation durations exclude the initial cached dependency-image preparation and post-run hidden scoring. Shared-host times are descriptive, not a controlled latency comparison.
