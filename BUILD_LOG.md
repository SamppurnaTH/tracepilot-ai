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

**Agent loop** (`backend/app/agent.py`): investigate → fix → verify → report.

- **Hypotheses are first-class.** The model must register each guess with `propose_hypothesis` and settle it with `resolve_hypothesis` (confirmed or rejected). The harness refuses a confirmation that cites no evidence.
- **Phase-gated tools.** Investigation can read, request and test, but not edit. The fix phase can edit the sandbox copy only. Edits under `tests/` are blocked, because tests are the ground truth.
- **The harness decides verification, not the model.** It compares per-test outcomes before and after. A fix is verified only if every failing test now passes, nothing that passed now fails, and no test disappeared. On failure, the model gets the failing tests and one more attempt.
- **Robustness:** step budgets per phase (the model is then forced to summarize), a nudge on repeated identical calls, and token and call accounting.
- **Final report** via structured output (issues with category, severity, root cause, evidence, fix and linked hypotheses), merged with harness facts: hypotheses, diff and verification.
- **Every step is emitted as an event** (`hypothesis`, `tool_call`, `patch`, `verification`, …) for the live UI and for replay. `backend/scripts/investigate.py` streams them and saves the full run to `runs/`.
- Tests: 9 agent tests with a scripted fake model (no API calls), covering a full verified run, blocked test edits followed by a retry, skipping the fix with no confirmed cause, refusing an evidence-free confirmation, the repeat nudge and the step budget. 48 backend tests in total.

**First real end-to-end run** (`muse-spark-1.3`, Docker sandbox, about 4 minutes):
the agent proposed H1 (coupon) and H2 (missing ownership check). It read logs and code, reproduced both bugs (including a control request to the correctly protected `/total` endpoint), and confirmed both with evidence.
It patched `compute_total` and `read_order`, and the harness verified the fix: **3 passed / 2 failed → 5 passed, 0 regressions**. It used 14 model calls, 16 tool calls and about 127K tokens.

**Muse Spark Open via Baseten:** provider support and `backend/scripts/smoke_test_baseten.py` are in place. A live test is pending a reissued key; the first key returned 403.

## Oct 28

- **Muse Spark Open (Meta open weights) on Baseten works:** basic call, tool calling (`read_log`) and structured output all pass with the reissued key.
- Finding: Baseten's constrained decoding (`response_format` with a JSON schema) made Muse Spark Open pad its JSON with thousands of whitespace tokens. One run used 17K completion tokens for a ~700-character answer, and another was cut off as invalid JSON.
  Switched to prompt-based JSON plus validation (`json_instruction` and `extract_json` in `backend/app/llm.py`): 3/3 valid, about 3 seconds and ~600 tokens each.
