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

**Multiple scenarios**, to show TracePilot isn't tuned to one app:

- `sample_app/` moved to `targets/orders/`. Two new targets were added:
  - `targets/notes`: an f-string SQL search, so an apostrophe gives a 500 and the same flaw is SQL injection leaking other users' notes. Slow-export WARNINGs act as a red herring.
  - `targets/billing`: float math with `round()` loses a cent on tax (54.12 vs 54.13), plus a pagination offset off by one page.
- `backend/app/scenarios.py`: each scenario is a target, a symptom-only incident report, and seed traffic. The harness replays the traffic **inside each sandbox** with one batched in-process runner, so every run gets fresh logs and no log files ship with the targets.
- `backend/tests/test_scenarios.py` proves each scenario is fair: the seed traffic reproduces the symptoms, exactly the expected tests fail, a reference fix verifies, and no target contains hint words. The answer key moved to `demo/README.md`.

**API** (`backend/app/main.py`):

- Start investigations, stream every event live over server-sent events, fetch reports, and list or replay saved runs.
- Runs execute in background threads with a concurrency limit and missing-key and bad-input checks. Failures surface as `error` events.
- On boot it pre-warms Docker. Sandbox startup is now under a second; the earlier 24 seconds was a cold Docker start.
- 10 API tests with a fake investigation. 77 backend tests in total, all passing (Docker tests included).

**Real run through the API: notes scenario** (`muse-spark-1.3`, Docker, about 3.7 minutes, 19 model calls, 21 tool calls):
the incident only said "apostrophe search fails". The agent proposed H1 (f-string SQL) and H2 (the warnings are unrelated slow exports).
It **exploited the flaw itself to prove impact**: `' OR 1=1 --` as Alice returned Bob's notes. It rated the issue critical/security and classified the warnings as unrelated, low priority.
It replaced the query with a parameterized one, and the harness verified **3/5 → 5/5, no regressions**.

**Robustness fix from a real failure:** the first billing run found both root causes and applied correct edits, then crashed with `400 referenced response not found or expired`. The Meta API had lost the `previous_response_id` chain mid-run.
The agent now keeps its own transcript. If the chain is lost, it replays the full history once without `previous_response_id` and emits a `recovered` event. This is covered by a test that drops the chain at the start of the fix phase.

**Real run through the API: billing scenario** (about 3 minutes, 15 model calls, 18 tool calls): the agent confirmed both root causes, switched to `Decimal` with half-up tax rounding, and fixed the page offset. Verified **2/5 → 5/5, no regressions**.
**All three scenarios have now been solved end to end by `muse-spark-1.3`.**

**Frontend** (`frontend/`, Next.js 15, React 19):

- A flight-recorder view of an investigation:
  - a flight log of every check, grouped by phase
  - hypothesis cards that move from open to confirmed or rejected, with their evidence
  - a verification gauge (per-test cells before and after, plus fixed, broke and still-failing lists)
  - the patch as a colored diff
  - findings with severity and category
- **Replay mode** plays real recorded runs at 4×, 10× or 25×, with "skip to result". **Live mode** starts a run on the API and streams events over SSE. Both feed the same reducer.
- `backend/scripts/export_recordings.py` exports the latest verified run per scenario, without raw tool output. All three scenarios are recorded from real runs. A fresh orders run verified 3/5 → 5/5 in 3.6 minutes (13 model calls).
- Checked in the browser at desktop and phone widths, in dark and light themes, with no horizontal overflow. The production build prerenders as a static page, so it can be hosted without a backend.

**Full local check before deploying:**

- 77/77 backend tests with Docker, and the Meta and Baseten smoke tests passed.
- Frontend lint, type-check and build were clean, and all three replays completed.
- A live run from the UI (orders) verified 3/5 → 5/5 in 2.5 minutes with 89K tokens, streamed over SSE.
- Fixed one issue: deployed builds no longer probe `localhost:8000`, which caused a console error for every visitor.

**Deployed:** [tracepilot-ai.vercel.app](https://tracepilot-ai.vercel.app). It's the Vercel Hobby plan with root directory `frontend`, and it redeploys on every push to `main`.
Verified as a visitor: replay mode works and the console is clean. Live runs need the backend, which requires Docker for the sandbox, so they run locally.

**Independent second opinion from Muse Spark Open** (`backend/app/reviewer.py`):

- After verification, Muse Spark Open (Meta open weights on Baseten) reviews the work cold. It sees the incident, the confirmed hypotheses and their evidence, the patch, the full patched files and the test results, but none of the investigation transcript.
- It returns a verdict (approve, concerns or reject), a confidence, a per-hypothesis assessment (supported, weak or unsupported) and concrete risks. It uses prompt-based JSON with validation and one retry.
- The verdict is advisory: the harness's test comparison still decides "verified". The final report is told about the review, and a reviewer failure never fails the run.
- The UI shows it as a "Second opinion" panel and a flight-log entry.
- 7 new tests with a fake Chat Completions client. Also fixed a race in an API test (the run file is written just after the status flips). 84 backend tests, all passing.
- Real orders run: verified 3/5 → 5/5, and Muse Spark Open **approved in 5 seconds**, noting the ownership check now matches the `/total` endpoint.
- **Can it catch a gamed fix?** `backend/scripts/check_reviewer.py` builds a patch that passes all 5 tests but only blocks order 7, the one the IDOR test requests. Muse Spark Open **rejected it with high confidence**, saying the IDOR remains for every other order. Passing tests alone would have called that patch verified.

**Token economy** (input tokens are ~95% of spend, since every call re-sends the conversation):

- Found that each logged 500 carried a ~5,000-character traceback, almost all starlette and anyio frames, re-billed on every later call. `compact_traceback` keeps only the app's own frames and the exception.
- The harness now builds a free evidence brief: the workspace files, grouped log warnings and errors with example request ids (taken before any test run pollutes the log), and each failing test with its full assertion message. pytest is run with a wide virtual terminal so the messages aren't truncated.
- Green test runs return only the summary. The report is written in a fresh context from the recorded facts and the patch. The system prompt asks for batched tool calls. Usage is now tracked by phase, along with cached tokens.
- First real runs, all verified 5/5 and approved by Muse Spark Open: orders 95K → 48K, notes 117K → 55K, billing 117K → 67K tokens. Later repeated eval runs averaged 49K, 75K and 95K, so the honest saving is **about 34%** (see below).

**UI redesign:** the "flight recorder" look is replaced with a calm developer-tool design (Geist type, neutral palette, one blue accent) built outcome-first.

- **Landing page:** a hero with a clear promise; proof metrics computed from the recordings (3/3 verified, 6 root causes, average time, tokens per run and the saving); incident cards with severity tags and results; how it works in six steps; and a "spend less, get more" section.
- **Run page:** a progress stepper (sandbox → investigate → patch → verify → second opinion → report). An outcome card shows tests before and after, the reviewer verdict, time and tokens. Then root causes with collapsible evidence, hypotheses, verification, the second opinion and the patch. A sticky activity log and a token-spend-by-phase chart sit in the sidebar.
- **Hand-off, zero tokens:** copy the patch, copy a PR description, or download a Markdown incident report, all generated in the browser.
- Test credentials are hidden from the displayed tickets (only the agent needs them). Checked at desktop and 375 px, in dark and light, with no horizontal overflow. 89 backend tests pass.

**The agent proves fixes even when no test catches the bug:**

- New `write_regression_test` tool (investigation phase only). It adds `tests/test_regression_<name>.py`. The harness runs it at once and keeps it only if every test in it **fails on the current code**; a test that passes, or crashes, reproduces nothing and is deleted. Kept tests join the baseline as failures the fix must turn green. They ship in the patch, and existing tests stay read-only.
- Verification now also requires that something which failed now passes. A green suite with nothing reproduced proves nothing.
- New `inventory` scenario with green CI: negative reservations create phantom stock, and a double cancel returns stock twice (oversell). All 5 existing tests pass. In a real run, Muse Spark wrote 2 reproducing tests, the harness confirmed both failed, and the patch went 5/7 → 7/7, approved by Muse Spark Open.
- `send_request` now accepts a JSON body sent as a string. The model did this in a real run, and each resulting 422 was a wasted round trip.

**The two models now work together:** if Muse Spark Open *rejects* a patch, its summary and risks go back to Muse Spark for one more fix round (`review_retry` event), then the patch is reviewed again. Covered by a test with a scripted reject-then-approve reviewer.

**Evaluation** (`backend/scripts/eval.py`, results in `eval/`):

- **8/8 end-to-end runs verified** (2 per incident). In both inventory runs the agent wrote its own reproducing tests (3 in total). The reviewer approved 7/8 runs.
- **Reviewer benchmark:** for each incident, the reference fix and a test-gaming fix that passes the full suite, run twice. **8/8 gamed patches caught; 7/8 reference fixes approved** (one "concerns" on inventory). About 4K tokens per review.
- In one billing run the reviewer flagged a real latent crash the tests missed: `sum()` over an empty invoice returns the int `0`, which has no `.quantize()`.
- The landing page shows an Evaluation section generated from the same data, and the token saving is computed per incident from the eval averages.
- 98 backend tests pass.

**TracePilot on your own project** (`tracepilot.py`, `backend/app/cli.py`):

- `python tracepilot.py investigate --repo <path> --incident "..." [--logs ...] [--apply]` runs the full loop on any Python project with pytest tests. It writes a hand-off folder: `fix.patch`, `pr.md`, `report.md` and `run.json`.
- **Sandbox:** the project's `requirements.txt` is installed into a cached derived image, so the network is used only at build time. Copies skip VCS data, virtualenvs, caches and build output, with a file-count guard. User log files are copied in as evidence.
- **Logs:** plain-text logs are parsed too. Indented lines and tracebacks attach to their entry, and repeated lines are grouped with numbers, ids and timestamps masked.
- **No HTTP app:** without one, `send_request` is withdrawn instead of failing.
- **Patches:** they now apply with `git apply`, using `/dev/null` for new files and "No newline at end of file" markers. `--apply` applies only a verified patch.
- **Real test on an unseen project:** a non-web shipping module with plain-text logs, `python-dateutil` and green CI. Muse Spark wrote the reproducing test, found `weekday() < 6` counting Saturdays as business days, and fixed it: 4/5 → 5/5, approved by Muse Spark Open. It cost 62K tokens (about $0.08) in 131 s, and `--apply` put the fix and the new test into the working tree.
- 7 new tests (`test_cli.py`). 105 backend tests pass.

**Sharing and cost:**

- A link-preview card for X, Discord and Slack (`opengraph-image.tsx`), with numbers drawn from `eval.json`. Open Graph and Twitter metadata were added.
- An estimated cost is shown per run, in the eval table and on the landing page. It uses $1.25 per million tokens, measured from the billing page ($2.51 for about 2.0M tokens).
- The README now leads with a 3-command quickstart for your own project and a Mermaid architecture diagram.

**Java / Maven support, tested on a real Spring Boot codebase** ([ShipSpace](https://github.com/SamppurnaTH/ShipeSpace), the author's own project: about 260 Java files, 102 test classes):

- **Sandbox image:** the project type is detected from `pom.xml`. A JDK 17 + Maven image is built per project, cached by a hash of `pom.xml`. The build compiles the project and runs one trivial warm-up test, because Surefire downloads its JUnit 5 provider only when a test runs (found the hard way: the first image lacked `surefire-junit-platform`). After that, every run is offline (`mvn -o`) against a read-only repository.
- **Resource limits** are set per project type: 3 GB, 2 CPUs and 1,024 PIDs for the JVM.
- **Per-test results** come from Surefire's XML reports. Assertion failures, and exceptions from the code under test, count as failures. Errors from a missing environment (Mongo timeouts, refused connections, Spring contexts that fail to load) are environment errors and are never accepted as reproductions.
- **Excluded tests:** test classes needing a database, network or Docker are excluded, listed in the brief, and emitted as an event.
- **JUnit regression tests:** the agent writes them as new files under `src/test/java`, with the class name checked against the file. Existing tests under `src/test/` are read-only.
- **Found in ShipSpace:** its CI runs a curated list of 19 test classes with the `test` profile. Outside that list, some tests fail today: `ScoringHooksIntegrationTest` has 4 failures with "Wanted but not invoked". So the CLI gained `--tests` (which tests define green) and `--test-args` (for example `-Dspring.profiles.active=test`). With CI's list, the sandbox baseline is 232/232 passing in about 4 minutes.
- **First real run** on a copy with a planted bug (edit window `ChronoUnit.HOURS` instead of `MINUTES`): the agent found and fixed the right line, and the reviewer approved. But it was **not verified**, and it **cost 1.02M tokens**. It had proved the bug with an existing out-of-scope test the harness didn't count, then a confusing retry sent it reading the project docs.
- **Fixes that came out of that run:**
  - An existing test the agent sees fail while investigating now counts as reproduction and is re-run during verification.
  - If a cause is confirmed but nothing fails, the agent gets one short "reproduce first" step, and there's no pointless second attempt.
  - Each run has a 400K token budget, and a single file read is capped at 16K characters.
  - The `--test-args "-D..."` parsing bug is fixed (argparse took the value for an option).
- **Second real run: verified.** The agent reproduced the bug with ShipSpace's own `ShipServiceTest`, fixed the line, and went 232 → 251 passing with no regressions. It also explained why CI stayed green (the covering test isn't in CI's list, and the in-CI controller test mocks the service). Muse Spark Open approved and flagged backfilling ships already stored with a 10-hour window. It cost **335K tokens (about $0.42) in 12 minutes**. The patch passes `git apply --check`.
- **One imprecision:** the generated PR description lists "include ShipServiceTest in CI" under "What changed", but the patch only changes `ShipService.java`. It's a recommendation, not an applied change.
- 8 new Java tests (`test_java.py`), plus 1 new and 1 rewritten agent test. 115 backend tests pass.

**Knowing when not to patch:**

- `resolve_hypothesis` now records where a confirmed cause's fix belongs: `fix_in` = code, config, data or external. If no confirmed cause is in the code, the harness skips the fix phase. The outcome is "no code change needed", and the report says what to change instead.
- New `refunds` incident: refunds fail right after a deploy, and on-call suspects the release. The recorded production logs show the provider's API key expiring at 08:00, eight minutes after the deploy, with a successful refund in between.
- In a real run, Muse Spark rejected the deploy hypothesis with that evidence, confirmed the expired key as an external cause, and made no patch. It cost 43K tokens. The landing page and run view show this outcome as "No code change needed".

**Positioning and a fair comparison** (prompted by a competitor analysis: Cursor, Copilot, OpenHands, Devin and Sentry Seer all overlap with parts of TracePilot):

- New tagline: "a verification-first debugging agent". The README gains a "How it compares" section that names those tools and what overlaps with them.
- OpenHands was considered for a head-to-head. Meta's API does serve chat completions, but current OpenHands needs Python 3.12 and multi-gigabyte runtime images. It was dropped in favour of a cleaner experiment: the same model with and without TracePilot.
- `backend/app/baseline.py` is a plain coding agent: same model, sandbox, logs, tools and total step budget, a standard prompt, test edits allowed, and it decides for itself whether it's done.
- `backend/scripts/compare.py` applies every patch to a fresh copy and judges it with hidden acceptance tests (`eval/hidden/`) that neither system sees. They probe beyond the visible tests: other orders, invoices, SKUs, dates and injection payloads. The judge was validated before any model run: every reference fix passes, every unchanged copy fails, and every test-gaming fix fails.
- **Results, 13 runs per system** (5 demo incidents, the shipping module, ShipSpace):

  | | Plain agent | TracePilot |
  |---|---|---|
  | Actually fixed | 12/13 | 13/13 |
  | False successes | 0 | 0 |
  | Reproducing tests written | 0 | 5 |
  | Average tokens | 138K | 94K (31% fewer) |
  | Average time | 293 s | 191 s (35% less) |

  The model is strong on its own. The plain agent's one miss was refunds, where it changed logging code during an external-cause incident (356K tokens).
- **Bugs found while building this:**
  - Two comparison processes appending to one results file would have overwritten each other. Fixed: the file is re-read before every append.
  - Older patches mark new files as `--- a/…` followed by `@@ -0,0`, so the test counter first reported TracePilot as editing tests, which it can't do. Fixed.
- **Cost:** about 2.0M tokens, roughly $2.50. That's well above the $0.75 estimate, mostly the plain agent's own spend (505K tokens on ShipSpace alone).
