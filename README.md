# TracePilot AI

An evidence-driven software reliability and security investigation agent, built for the Meta Global AI Developer Hackathon (Indie Developer track, problem statement: Push the Frontier).

**Live demo: [tracepilot-ai.vercel.app](https://tracepilot-ai.vercel.app)**, which replays real recorded investigations of all three scenarios.

> Status: project started during the hackathon building period (Oct 27 to Nov 4, 2026). See `BUILD_LOG.md` for what was built and when.

## The problem

Developers spend hours investigating failures: reading logs, replaying API calls, tracing errors back to source code, and checking whether a fix really works. Most AI coding assistants jump straight to generating code. TracePilot investigates first.

## What TracePilot does

1. **Ingest evidence:** application logs, API responses, error traces, and relevant source files.
2. **Correlate:** links log lines, failing requests, and code paths.
3. **Hypothesize:** produces ranked, testable root-cause hypotheses with the evidence behind each.
4. **Check:** proposes diagnostic steps and runs only authorized, read-only checks in a sandbox.
5. **Verify:** applies a proposed fix in the sandbox and confirms the failure is gone.
6. **Report:** outputs a clear investigation report with evidence, root cause, fix, and verification result.

## Meta tooling

TracePilot's agent loop runs on Meta's models through the Meta Model API: multi-step reasoning, tool calling, and structured output. It currently uses `muse-spark-1.3` through the Responses API.

Muse Spark Open (Meta open weights), served by Baseten, passes the same tool-calling and structured-output checks (`backend/scripts/smoke_test_baseten.py`).

## How it works

1. **Sandbox:** the target app is copied into a fresh, locked-down Docker container. Realistic traffic is replayed inside it to produce logs.
2. **Investigate:** the model registers hypotheses (`propose_hypothesis`), gathers evidence with tools (`read_log`, `read_file`, `send_request`, `run_tests`), and confirms or rejects each one (`resolve_hypothesis`). A confirmation without evidence is refused.
3. **Fix:** with confirmed root causes, the model edits the sandbox copy (`edit_file`). Tests can't be edited.
4. **Verify:** the harness, not the model, compares every test's outcome before and after. A fix counts only if all failures are fixed and nothing regressed. Otherwise the model gets one more attempt.
5. **Report:** a structured report (issues, severity, root cause, evidence, fix), the diff, and the verification result. Every step streams live as an event.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/scenarios` | Demo scenarios (incident text only) |
| `POST /api/investigations` `{"scenario": "notes"}` | Start an investigation |
| `GET /api/investigations/{id}/events` | Live event stream (server-sent events) |
| `GET /api/investigations/{id}` | Status and final report |
| `GET /api/runs`, `GET /api/runs/{name}` | Saved runs, for replay |

## Tech stack

- Backend: Python, FastAPI
- Frontend: Next.js
- Models: Meta Model API
- Sandbox: Docker container per investigation, running a disposable copy of the target app, with a process fallback when Docker isn't available

## Safety principles

- Only investigates systems the user owns or is authorized to test.
- All checks run in a sandbox: a disposable copy of the app in a Docker container with no network, a read-only root filesystem, no capabilities, a non-root user, and CPU, memory, PID and time limits. The original code is never modified.
- Tools are phase-gated: the investigation phase can read and test, but only the fix phase can edit, and only the sandbox copy.
- Secrets are stripped from the sandbox environment, and local paths are scrubbed from everything sent to the model.
- Fixes are verified before being suggested as final.
- API keys are read from environment variables and never committed.

## Setup (to be completed during the build)

```bash
# Backend
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt   # .venv/bin/python on macOS/Linux
cp .env.example .env          # then set MODEL_API_KEY in .env (never commit it)
.venv/Scripts/python backend/scripts/smoke_test.py   # checks the Meta Model API
docker build -t tracepilot-sandbox:1 sandbox          # optional; built automatically on first use
.venv/Scripts/python backend/scripts/investigate.py --scenario orders   # one full run from the CLI
cd backend && ../.venv/Scripts/python -m pytest && cd ..   # backend tests
cd backend && ../.venv/Scripts/uvicorn app.main:app --reload   # API on http://localhost:8000

# Frontend (replays recorded runs; runs live when the API is up)
cd frontend
npm install
npm run dev                   # http://localhost:3000
```

## The interface

The frontend (`frontend/`) shows each investigation as a flight log: every check the agent runs, hypotheses moving from open to confirmed or rejected, a before/after test gauge, the patch, and the findings.
It replays real recorded runs (`frontend/public/recordings/`), so the hosted demo works without a backend. With the API running, it can start live investigations and stream them.

## Build plan

| Day | Goal |
|---|---|
| Oct 27 | Foundation: first Meta API call, repo structure, sandbox, sample app |
| Oct 28 | Evidence ingestion and tools |
| Oct 29 | Hypothesis generation with structured output |
| Oct 30 | Sandbox check runner with tool calling |
| Oct 31 | Agent loop: hypothesis, check, update, next step |
| Nov 1 | Fix and verify step; security scenario |
| Nov 2 | Next.js UI: live view and report |
| Nov 3 | Hardening, tests, feature freeze, backup demo |
| Nov 4 | Final demo recording and submission |

## Demo scenarios

Three synthetic services in `targets/`, covering five planted defects plus a red herring:

- **orders:** a 500 from a missing null check (reliability), and a missing ownership check (IDOR, security)
- **notes:** search breaks on apostrophes, which is really SQL injection (security); slow-export warnings are a red herring
- **billing:** a disputed cent from float rounding, and a pagination off-by-one (correctness)

The answer key is in `demo/README.md`, outside the sandbox. The agent only sees code, logs and a symptom-only incident report.

## What was built during the hackathon

Everything in this repository was built during the hackathon building period. Third-party libraries are listed in the dependency files and credited in the submission.

## License

[MIT](LICENSE)
