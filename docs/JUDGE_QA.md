# Judge Q&A: answers with evidence

See [official rubric alignment](HACKATHON_ALIGNMENT.md). This is an evidence map, not a claim that every proposed feature is implemented. Paths below are repository-relative and point to auditable source or saved observations.

## First-time visitor

| Question | Answer | Evidence |
|---|---|---|
| What does it do, and why not Cursor/Copilot? | TracePilot proves a proposed fix against reproduced failures and a regression suite, or abstains from code changes when the evidence points elsewhere. It complements an editor; we have not benchmarked either commercial product. | Landing hero; `frontend/public/recordings/checkout.json`, `refunds.json`; `backend/app/agent.py::compare_outcomes` |
| Is the three-minute wait broken? | Live progress shows the current phase, elapsed time and a typical 2–4 minute Python-demo estimate. Custom/Java runs can take longer. The event log streams model notes and tool evidence. | `frontend/src/components/Console.tsx`; event recordings |
| Which scenario first? | Refunds for honest abstention; Checkout for multimodal reproduction. Both cards say Start here. | `/examples` |
| Backend down or capped? | A 429, server failure, unavailable backend or start timeout opens a clearly labelled saved recording automatically. Authentication/validation failures stay errors. A timed-out POST can have started a server run; we do not retry it automatically. | `lib/api.ts::recordingFallback`, examples and run pages |

## Developer or SRE

| Question | Answer | Evidence |
|---|---|---|
| My messy repository? | Python/pytest and Java/Maven only; single-service folders work best. Unsupported projects are refused before a model call/image build. Missing dependencies, unconventional builds and monorepos can still fail; no universal-repo claim. | `sandbox.py::detect_kind`, `main.py::start_custom_investigation`, `cli.py`; `test_uploads.py` |
| No reproducing test? | A passing/erroring generated test is deleted. If no failure is available, a patch cannot be verified. The real synthetic no-reproduction probe returned no_root_cause, no patch and verified=false. A specific assertion must match the incident; the harness enforces fail→pass, not semantic truth. Unrelated assertions remain a limitation requiring evidence review. | `eval/abstention-probe.json`; `test_regression_test_must_fail_first_and_then_proves_the_fix`, `test_green_suite_gets_one_reproduce_step_and_no_pointless_retry`; Inventory recording |
| Why Java flags? | Maven defaults are automatic: detect `pom.xml`, run its default test scope and report infrastructure exclusions. `--tests` optionally matches a team's existing CI list; `--test-args` optionally selects an application-specific profile. Guessing profiles can change behavior, so they remain explicit. | `tools.py::_mvn`, `sandbox.py::detect_kind`; `test_java.py` |
| CI or PR bot? | A manually triggered sample Actions workflow produces a patch, report and JSON artifact. No GitHub App or automatic PR publication exists. CLI exit 0 means a verified patch **or** no-code-change outcome; inspect JSON to distinguish them. `--apply` only applies verified patches. | `examples/github-actions/tracepilot.yml`, `cli.py`; `test_cli.py` |
| Database/network/Docker bugs? | Investigation containers have no network. Java classes marked as requiring those services are excluded and named in events/new reports. Python service-dependent tests can error rather than be excluded. We cannot quantify production coverage lost from this small benchmark. | `tools.py::NETWORK_TEST_MARKERS`, `excluded_tests` events; `SECURITY.md` |

## Security and enterprise

| Question | Answer | Evidence |
|---|---|---|
| Who sees code/logs? | Selected investigator evidence goes to Meta; reviewer facts, patch and changed files go to Baseten. Provider access/retention follows the account contract. Logs/screenshots may contain secrets despite environment filtering. Self-hosted Meta review moves only reviewer traffic, not investigator traffic. | Data flow and provider qualifications in `SECURITY.md`; `llm.py`, `reviewer.py` |
| Prompt injection? | Inputs are labelled untrusted; tool permissions are checked outside the model, test edits are guarded, and verification is computed by the harness. Offline runtime limits exfiltration. These are layered defenses, not proof of prompt-injection immunity. | `test_judge_safety.py`, `security_probe.py`; saved probe if executed |
| Escape or secret leaks? | Docker non-root/read-only root/no network/capability and resource limits; disposable workspace. Process fallback is not containment. Dependency preparation is networked. No hostile-upload hosting or kernel-escape guarantee. | `SECURITY.md`; Docker isolation tests in `test_sandbox.py` |
| Private repository access for a team? | CLI reads a local authorized checkout. Hosted custom runs require an access key or signed-in operator with workspace grant. Viewer is read-only; admin permissions are enforced in APIs. This is one shared workspace, not repository-level authorization or tenant isolation. | `admin.py`, `main.py`, `test_admin.py`, `test_api.py` |

## ML and evaluation

| Question | Answer | Evidence |
|---|---|---|
| 12/13 vs 13/13 significant? | No such claim. Original descriptive intervals overlap widely. The separate external-source extension uses a locally frozen 96-trial matrix across six cases, two model versions, four workflows and two repetitions; inspect its completion status and paired cluster intervals rather than merging domains. | `eval/STATISTICS.md`, `eval/research/RESULTS.md`, `manifest.json`, raw observations and score audits |
| Who wrote hidden tests/gaming patches? | Original fixtures were project-authored; eight gaming observations repeat four attacks. The extension uses six QuixBugs bugs, fixes and expected-output sets authored upstream. TracePilot supplies the adapter/split. Six additional gaming patches were generated by Muse Spark 1.1 with no held-out/reference access; all pass public tests and fail held-out tests. Public benchmark training contamination remains possible. | `bench/quixbugs/`, pinned source hashes in `eval/research/manifest.json`; `generated-attacks/` with prompts, raw responses and oracle outcomes |
| Correlated reviewers? | We compared cold Muse Spark 1.3 review with cold Muse Spark Open review on identical visible-only patch facts. Both approved 10/12 reference observations and rejected all 12 gaming observations. Both nonapproved wrap, and a Docker check verified a hang missed by the external test oracle. This measures paired behavior; it does not prove independent model-family blind spots. | `eval/research/review-clean-observations/`, `reviewer-discovery.json`, `RESULTS.md` |
| False approvals/rejections? | In the new follow-up, each reviewer approved 0/12 known gaming observations (descriptive interval 0–24.3%) and nonapproved 2/12 oracle-accepted references (4.7–44.8%). Those two references have a verified wrap hang, so calling their nonapproval a false positive would be wrong. Post-hoc triage: 0/14 known-bad observations approved, 10/10 other references approved. Concerns and hard rejects are counted separately; six repeated cases do not establish population error rates. | `eval/research/summary.json`, `reviewer-clean-manifest.json`, raw pilot retained separately; `reviewer-discovery.json` |
| Why 31% fewer tokens? | That is the original service-pilot observation, not a universal gain. The completed service check found brief savings of 28.4% in plain and 37.4% in TracePilot; full TracePilot used 31.5% more than plain+brief, with all 16 trials passing. The external study also compares plain vs plain+brief, and TracePilot vs TracePilot without brief; full TracePilot vs plain+brief tests the remaining bundled method. Use paired results, successful-pair sensitivity and total/investigator/reviewer/cached token counts. Remaining features are not individually causally attributed. | `eval/research/RESULTS.md`, `summary.json`, `observations.csv`; `docs/RESEARCH_PROTOCOL.md` |
| Weaker model? | The external matrix tests both Muse Spark 1.1 and 1.3 under the same cases and workflow controls. Version 1.1 is earlier; its parameter count and relative weakness are not assumed. Matched-quartet interaction estimates test whether harness benefit differs by version. We cannot claim a smaller-model advantage from this experiment. | Model IDs and per-trial usage in `eval/research/observations/`; `model_interaction` in `summary.json` |

## Prize strategy and fit

| Question | Answer | Evidence |
|---|---|---|
| Frontier or API wrapper? | The capability is a verification loop: harness-owned facts, evidence-gated hypotheses, reproduction, independent-context review, and honest abstention. “Proof, not patches” means bounded evidence, not formal correctness. | `agent.py`; Checkout, Inventory and Refunds recordings |
| Why two Meta models/open weights? | Muse Spark investigates with screenshots/tools; Muse Spark Open reviews a compact fact bundle in a fresh context. Open weights offer a path to bring review inside enterprise infrastructure. We support a private compatible reviewer endpoint, but have not demonstrated a fully private deployment and investigation still uses Meta's API. | `reviewer.py::from_env`; `.env.example`; `SECURITY.md` |
| What was reused? | ShipSpace is the author's pre-existing public project. Only its planted bug and the investigation/evaluation are hackathon work. TracePilot's build history is disclosed separately; libraries/frameworks and AI-assisted work are not newly invented components. | `BUILD_LOG.md`, ShipSpace source link in README |
| What's next/who pays? | Target users are engineering teams handling incidents. Next: a GitHub App with scoped installs and human-reviewed incident-to-PR, then tenant/repo authorization and enterprise private inference. Roughly $0.10 is an observed/estimated **model-cost order of magnitude**, not a selling price, margin or all-in cost. Hosted compute, reviewer billing, retries and support must inform actual pricing. Proposed business model: team subscription plus metered investigations, enterprise self-host licensing/support. | README cost caveat; usage/timing in recordings; planned features explicitly not shipped |

## Skeptical user

| Question | Answer | Evidence |
|---|---|---|
| Show a failure | Replay wrap-review: a real pre-safeguard test-green patch with unresolved reviewer-reported hang, now labelled Review required. The archived 96-trial study also retains a Meta API 500 failure. Refunds is a genuine no-code-change outcome, not a failed investigation. The Inventory reference reviewer raises concerns about weak evidence and concurrency; that is an advisory nonapproval, not a fabricated reject→retry. The plain-agent Refunds comparison includes an honest failure. No recorded TracePilot reject→successful-second-round story is claimed without an actual event sequence. | `docs/CASE_STUDIES.md`, `eval/results.json`, `eval/comparison.json` |
| Intermittent/concurrent/production data? | A deterministic local reproduction may miss all three. Supply sanitized reproductions or traces; the prototype cannot prove correctness under unobserved schedules or unavailable production state. | Verification-scope note on results and reports; `SECURITY.md` |
| Minimal patch? | Reports show touched files and added/deleted lines, with tests included. This is a patch-size metric, not proof of minimality; review the diff and semantic scope. | `handoff.py::patch_stats`, result UI and Markdown exports |

## Remaining evidence, not invented results

- External-source authorship, paired brief ablations, an earlier-model comparison and cold-reviewer calibration now have explicit experiments; use their reported completion status. Independent external administration and a smaller-model advantage are not claimed.
- There is no customer adoption, enterprise certification, universal-repo support or formal correctness claim.
- No ranking can be guaranteed. Final video, submission receipt and eligibility checks remain the entrant's responsibility.
