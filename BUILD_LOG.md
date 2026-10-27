# Build log

Everything below was built during the hackathon building period (Oct 27 – Nov 4, 2026). Times are IST.

## Oct 27

**10:44: building started.**

- Repo structure: `backend/` (FastAPI), `sample_app/`, `.env.example`, `.gitignore` (secrets and logs excluded).
- `backend/app/llm.py`: a single client factory for the Meta Model API (`https://api.meta.ai/v1`, model `muse-spark-1.3`, OpenAI-compatible Responses API), so every model call goes through one place.
- `backend/scripts/smoke_test.py`: checks the three capabilities the agent depends on: a basic call, tool calling (`read_log`), and structured output (a root-cause hypothesis as JSON).
- `sample_app/`: the demo target, a synthetic Orders API with two planted bugs:
  - security: missing ownership check on `GET /orders/{id}` (IDOR)
  - reliability: `compute_total` crashes with a 500 on orders without a coupon
- `sample_app/tests/`: 5 tests, 2 failing on purpose (one per bug). TracePilot will prove its fixes by turning them green.
- `sample_app/simulate_traffic.py`: generates realistic JSON-line logs, including the 500s and the cross-user reads.
- Smoke test passed against the Meta Model API: basic call, tool calling (`read_log`), and structured output.
  Notable: from logs alone, the model's first hypothesis blamed a missing order. The real cause is a missing coupon.
  That's exactly why TracePilot must check hypotheses against code and tests before trusting them.

**Evidence tools** (`backend/app/tools.py`), all scoped to the target workspace:

- `read_log`: filtered JSON log entries (by level, path, request id).
- `read_file`: source with line numbers, or a directory listing.
- `send_request`: in-process HTTP requests to the target app, so nothing leaves the machine.
- `run_tests`: runs pytest for the whole suite or one test.

Guardrails: no reads outside the workspace or of `.env` files, no external URLs, test selectors validated against shell injection, and local absolute paths scrubbed from all output before it reaches the model. There are 21 unit tests (`backend/tests/test_tools.py`), including escape attempts.

First model-driven run (`backend/scripts/try_tools.py`): in 4 steps the model found both planted bugs.
For each one it gave the root cause with evidence (log entries, code line numbers, a reproduced request, the failing test) and proposed a fix, without modifying code.

**Sandbox** (`backend/app/sandbox.py`, `sandbox/Dockerfile`):

- Each investigation gets a disposable copy of the target app, deleted afterwards; the original is never modified.
- Docker isolation: one container per sandbox with `--network none`, a read-only root filesystem, `--cap-drop ALL`, `no-new-privileges`, a non-root user, and limits of 512 MB memory, 1 CPU and 128 PIDs. A timed-out command gets a fresh container.
- Falls back to process isolation when Docker isn't available. Secrets are stripped from the sandbox environment in both modes.
- All tools now run against the sandbox. New fix-phase tools: `edit_file` (exact, unique-match replacement in the copy only) and `show_diff`. They're phase-gated, so the investigation phase can't edit.
- The model client now retries transient errors and has a request timeout.
- Tests: 39 passing. They cover a fix verified end to end (both fixes applied, then 5/5 sample tests pass with the original untouched), patched code visible to requests, edit guards, secret isolation, timeouts, and Docker checks (no network, read-only root filesystem, non-root user).

**Demo integrity fix:** in a Docker run, the agent read `sample_app/README.md`, which described the planted bugs: an answer key.
The answer key and traffic generator moved to `demo/`, outside the sandbox. App docstrings are now neutral, and a regression test fails if hint words appear anywhere in the sandbox copy.
