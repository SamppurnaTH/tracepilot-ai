# Build log

TracePilot's work below was built during the hackathon building period (Oct 27 – Nov 4, 2026). Times are IST. ShipSpace itself is the author's pre-existing public project; only the planted bug, TracePilot investigation and evaluation are new. Existing libraries/frameworks are reused dependencies, not newly authored hackathon work.

## Oct 30 — model-blinded real-bug study

- Completed the seven-case follow-up on pinned public Python fixes merged Aug–Oct 2026: **2/7 fixed by the upstream hidden tests**, three not fixed and two errors. Inflect and Tomlkit passed; More-itertools was locally verified and reviewer-approved but failed hidden edge cases; Pyparsing and Click were not fixed; Marshmallow had a connection error and Packaging exceeded the model context window. All observations are retained, with no score-seeking restarts.
- Preserved round 1 (1/4 recorded cases fixed) separately. Repaired unanswered chained tool calls at phase boundaries, continued pytest after collection errors, exposed unchanged unloadable files in the report scope, and added common pyproject test dependencies and src-layout imports. The runner persists per-case traces, records exceptions including exit codes, and refuses silent retries or oracle replacement. The original unrecorded process exit is not retrospectively diagnosed.
- Published `eval/blind/`: both rounds, candidate diffs, hidden per-test outcomes, partial error traces, pinned source verification, oracle hashes, source licenses, and the measured inference-module snapshot. Disclosed PR-derived incidents, the existing Inflect hint, author knowledge, possible training familiarity, internal fix loops and the absence of a paired control. Previous evaluation numbers rebuild unchanged.
- Local validation: 176 backend tests passed, one skipped; frontend lint and production build passed. Bookkeeping tests cover retained exits, continued execution, retry refusal, frozen oracles and separate round reporting.

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

**UI redesign to a product dashboard** (from a reference mockup):

- Dark navy sidebar and a bright main column, in Plus Jakarta Sans with an indigo-to-violet accent. The hero reads "From errors to verified fixes", with five colour-coded steps and a "Proven results" card. The card's numbers come from `comparison.json`.
- Scenario cards open an inline investigation console that's always dark, like an IDE panel. It has:
  - a six-step stepper (steps that weren't needed show as "Not needed")
  - a terminal log with real timestamps from each recording
  - an outcome card with the recommended action
  - tabs for root causes, the evidence brief, reproducing tests, the patch, test results and the second opinion
  - an investigation summary with report, PR-description and patch hand-off
- The page opens on a finished run. Clicking a card replays it step by step, and `#scenario` links open a specific run.
- Comparison bar charts with key takeaways; the reviewer benchmark; a "Run it on your own code" section.
- The mockup's illustrative numbers were replaced with real data. For example, the refunds run wrote no test and analysed no "24 files", and ShipSpace's bug is the edit window, not delivery dates.
- Checked at 1536 px and at 375 px (no overflow), and in light and dark themes.

**Screenshot evidence (multimodal Muse Spark):**

- Incidents can carry screenshots (`Investigation(images=...)`, scenario `screenshots`, CLI `--screenshot`). They're sent to `muse-spark-1.3` as `input_image` parts of the first message, with a note asking the agent to cite what it reads. Only PNG, JPEG, WebP and GIF up to 5 MB are accepted. Each one is emitted as an `evidence_image` event.
- A quick check confirmed the Meta Model API reads text from images: a 420×160 test image cost 114 input tokens.
- New `checkout` incident. The ticket says only that a customer's screenshot shows the wrong discount. The screenshot (`demo/make_checkout_screenshot.py`) is the only place the cart, coupon and amounts appear. The logs have no request bodies, and all 5 tests pass.
- **Real run:** Muse Spark rebuilt the exact cart from the image (2× LAMP-20 and 1× MUG-08 with SAVE10) and sent it to the app. It cited quote Q-20417 and "$2.80 vs $4.80" in its findings, wrote a reproducing test, and fixed the missing `line.qty`: 5/6 → 6/6, approved by Muse Spark Open, 62K tokens (about $0.08).
- **The site:** the Evidence tab shows the screenshot, captioned as given to the model as an image. Scenario cards get a "Screenshot" badge, and the exporter publishes screenshots next to the recordings.
- **Also fixed:** the reviewer benchmark now only covers scenarios that have a test-gaming fix. It would have crashed on refunds, which has no code fix. A checkout gaming fix was added, and a checkout hidden test is in `eval/hidden/`.
- 125 backend tests pass (1 skipped by design: refunds has no reference code fix).

**Full product UI (10 screens, from a reference mockup) and bring-your-own-project from the browser:**

- **New routes:**
  - `/` (marketing landing with a 3D workflow stack and measured stats)
  - `/examples` (filters; Run live and View details)
  - `/investigate` (upload a ZIP, a Git repository or an example; logs, screenshots and Java options)
  - `/run` (the live console while running; a light summary when done; separate views for a verified fix and for no code change)
  - `/results` (charts plus a per-incident table)
  - `/runs` (recordings plus the backend's saved runs, with search)
  - `/docs`
- **Backend:**
  - `POST /api/investigations/custom` accepts a ZIP up to 50 MB, or a shallow clone of a public `https://` repository on GitHub, GitLab or Bitbucket, plus logs and screenshots. Uploads are guarded: path traversal and symlinks are rejected, sizes and file counts are capped, and everything is deleted when the run ends.
  - `POST /api/investigations/{id}/cancel` stops a run before its next model call; the run status becomes `cancelled`.
  - `python-multipart` 0.0.32 was added.
  - 11 new tests.
- **Replays for external projects:** the shipping module and ShipSpace (Java) runs are stored in `bench/runs/` and published as recordings. The comparison summary now carries per-incident averages for the detailed table.
- **Honest deviations from the mockup:**
  - No `pip install` (TracePilot isn't published), so the docs show the real install steps.
  - "Copy PR description" instead of "Create Pull Request", since there's no GitHub integration.
  - A Markdown report instead of a PDF.
  - All numbers are real.
- **Verified in the browser:** every screen; a live run started from the New investigation page and stopped with Stop (the backend reported `cancelled`); and phone width on every route. One fix came out of that: a visually hidden table label could widen the page.
- 136 backend tests pass.

**Brand:** the TracePilot AI mark (an "A" with a flight-path swoosh and a star for the verified fix) in indigo, sky and violet, with Inter for UI text and JetBrains Mono for code. Added to the sidebar, landing nav, favicon and the link-preview card. The card shows real results: 13/13 incidents fixed against hidden tests, 8/8 test-gaming patches caught, and 31% fewer tokens.

**Live backend on AWS (EC2, Mumbai):**

- `deploy/setup.sh` sets up a fresh Ubuntu server in one command. It installs Docker, Python and Caddy, runs the API as a systemd service on `127.0.0.1`, builds the sandbox image, and serves HTTPS at `<ip>.sslip.io` with a Let's Encrypt certificate.
- Guards for a public server:
  - 2 investigations at a time and 40 a day;
  - Docker-only mode (never falls back to process isolation);
  - CORS limited to the Vercel site;
  - an access key for investigating uploaded code.
- The site is connected (`NEXT_PUBLIC_API_URL`). The first live run, Orders API, ran in Docker on the server: fixed and verified, approved by Muse Spark Open (Baseten) with high confidence, in 85K tokens and 3.2 minutes.
- Cost: the server is about $1.29 a day, covered by AWS credits. Model calls are about $0.05–0.11 a run on the Meta credits.

**Admin console and signed-in workspace:**

- `/admin`: email and password sign-in with PBKDF2-hashed passwords, hashed session tokens, per-email rate limiting and 8-hour sessions. Admin, operator and viewer roles; team management; workspace settings; an audit log; and stopping runs.
- `/app/*`: a signed-in workspace that reuses the product pages. Viewers are read-only.
- **The demo stays public.** Anyone can start, watch, stop and replay the example scenarios without an account; the concurrency and daily limits still apply. Investigations of uploaded code need a signed-in operator or the access key, and are hidden from signed-out visitors.
- Shared pages link within the area they're shown in: `/app/…` inside the workspace, public pages outside it.
- Checked on the live site: a signed-out visitor ran Refunds API live and got the correct "no code change" outcome, in 49K tokens and 1.8 minutes.

## Oct 29

**Continuous delivery without inbound SSH:**

- GitHub Actions runs the backend tests, lint, type checks and a production build on every pull request and push.
- GitHub-hosted runners couldn't reach EC2, because SSH is restricted to the owner's IP. So the server deploys itself instead: every 2 minutes it checks `main`, asks GitHub whether CI passed for the newest commit, and then runs the release-based update. That update creates a new release, waits for running investigations, backs up accounts, checks health and rolls back on failure.
- No SSH keys or AWS credentials are stored in GitHub. The first automatic deploy (`213e1e7`) went live, and `/health` reports that exact release.
- Fixed a race that CI caught: a run was marked completed before its uploaded project was deleted. The final status is now published only after cleanup.
- 147 backend tests pass.

**Live reasoning:**

- Each model step now streams a `thinking` event: Muse Spark's own note alongside its tool calls, plus its reasoning summary.
- Summaries are requested with `reasoning: {summary: "auto"}`. Measured side by side, this costs no extra tokens: the model reasons either way.
- The activity log shows the notes as quoted lines between the tool calls, and while a run is live the outcome card shows "Muse Spark is thinking" with the latest one.
- Checked live on the hosted backend (Docker): Orders API went from 3/5 to 5/5 tests, verified and approved by Muse Spark Open, in 61K tokens and 1.7 minutes, with 6 notes from "Fixing your order totals and privacy reports — tracing the 500s and cross-user reads" to "Edits applied — now verifying the fixes hold".

**Judge evidence and demo hardening (Oct 29):**

- Read the organizer Official Rules and mapped evidence to Impact (30%), Meta AI tooling (25%), Technical execution (20%) and Demo (25%). Meta remains the investigator and reviewer; no competing-vendor result is implied.
- Added labelled automatic recording fallback for backend/capacity/start failures, current-phase and timing guidance, Refunds and Checkout starter labels, and early unsupported-project refusals.
- Added report patch-size/scope notes, named infrastructure exclusions, assertion reasons in the reproduction view, and a configurable private Meta reviewer endpoint (not a claim of a demonstrated fully private deployment).
- Published deterministic Wilson intervals, exploratory incident-cluster bootstrap intervals, separate reviewer error rates, source hashes, authored-fixture provenance and unrun-study limitations. Original comparison observations remain unchanged.
- One real Meta-model adversarial-log run in Docker: payload present in the evidence brief, 3/5 to 5/5 tests, reviewer approval, zero suspicious tool attempts detected, 136.6 seconds; saved in eval/security-probe.json outside the comparison.
- Added a copyable manual GitHub Actions investigation workflow, judge Q&A, honest failure/abstention case studies, threat model and a 90-second presentation script. No installed GitHub App, fabricated retry recording or contest ranking claim.

- Recorded a separate real Meta/Docker no-reproduction boundary case: deliberately under-specified synthetic invoice incident, no confirmed root cause, empty diff and verified=false, 72.4 seconds. Preserved outside the comparison benchmark.

**Research closure and a post-study review safeguard:**

- Completed 96 locally pre-specified external-source repair trials (six pinned QuixBugs algorithms, two Meta versions, four configurations, two repetitions), with separate audits for all outcomes. 95 passed the frozen oracle; one Meta API 500 was retained as an end-to-end failure. No model trial was rerun for a better score.
- Completed a separate 16-trial Orders/Inventory ablation, all passing the original hidden oracles. The brief reduced tokens 28.4% in plain and 37.4% in TracePilot; full TracePilot used 31.5% more than equally briefed plain. The original 31% is not a universal gain.
- Preserved 48 raw-reference pilot reviews and a separately frozen 48-review minimal-reference follow-up. Both cold Meta reviewers rejected 12/12 model-generated gaming observations and approved 10/12 oracle-accepted references; both flagged wrap, whose remaining loop was confirmed with a bounded Docker counterexample.
- Archived the 14 measured application modules with source fingerprints before changing software behavior. Current product marks unresolved concerns/rejection as needs_review and blocks --apply/CI success even when tests pass. Unit/CLI checks and deterministic replay of the unchanged recorded failure validate this separate safeguard.
- Published real wrap-review replay, per-trial CSVs, paired case-cluster analyses, source provenance, independent-replication instructions, and a question-by-question research closure report. Changed historical 13/13 wording to correct outcomes because it includes abstention diagnoses, not 13 code patches.

**Accurate timing, and a speed experiment:**

- Every run records where its time goes. In live runs, waiting for Muse Spark is about 85–90% of the total; tools, the sandbox and the harness's own test runs take the rest.
- The live clock now ticks, durations are exact to the second, and timings use the high-resolution clock. Windows' 15.6 ms monotonic tick had been rounding short tool calls to zero.
- Tried two speed-ups over 24 interleaved runs (`eval/speed/RESULTS.md`): not asking the model to run tests itself, and low reasoning effort. Both cut the median time by about 15% (175 s → 148–149 s), and every run still passed the tests. But the reviewer approved fewer patches: 6/8 and 7/8, against 8/8. The concerns were all on Billing, whose empty-invoice trap no test covers. Kept the current behaviour: speed doesn't buy back a weaker fix.
