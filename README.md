# TracePilot AI

An evidence-driven software reliability and security investigation agent, built for the Meta Global AI Developer Hackathon (Indie Developer track).

## The problem

Developers spend hours investigating failures: reading logs, replaying API calls, tracing errors back to source code, and checking whether a fix really works. Most AI coding assistants jump straight to generating code. TracePilot investigates first.

## What TracePilot does

1. **Ingest evidence**: application logs, API responses, error traces, and relevant source files.
2. **Correlate**: links log lines, failing requests, and code paths.
3. **Hypothesize**: produces ranked, testable root-cause hypotheses with the evidence behind each.
4. **Check**: proposes diagnostic steps and runs only authorized, read-only checks in a sandbox.
5. **Verify**: applies a proposed fix in the sandbox and confirms the failure is gone.
6. **Report**: outputs a clear investigation report with evidence, root cause, fix, and verification result.

## Tech stack

- Backend: Python, FastAPI
- Frontend: Next.js
- Models: Meta Model API (model choice to be confirmed from the docs)
- Sandbox: containerized, no access to real production systems

## Safety principles

- Only investigates systems the user owns or is authorized to test.
- All checks run in a controlled sandbox and are logged.
- Fixes are verified before being suggested as final.
- API keys are read from environment variables and never committed.

## Setup (to be completed)

```bash
# Backend
cd backend
pip install -r requirements.txt
export META_API_KEY="<your key>"   # never commit this
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## 10-day build plan

| Day | Goal |
|---|---|
| 1 | Test the API with one call. Pick the models. Create repo structure. Define the sample "broken app" for the demo. |
| 2 | Build the evidence ingestion (logs, traces, source files). |
| 3 | Build the hypothesis generator with a structured output schema. |
| 4 | Build the sandbox check runner (read-only, logged). |
| 5 | Connect the loop: hypothesis, check, update confidence. |
| 6 | Build the fix and verify step with automated tests. |
| 7 | Build the Next.js UI: evidence view, hypotheses, report. |
| 8 | Polish the demo scenario. Add error handling and tests. |
| 9 | Record the demo video. Write the submission text. |
| 10 | Final checks, upload to the submission portal, submit early. |

## Demo scenario (MVP)

A small sample API with a seeded bug (for example, an authorization check that returns 500 on one route). TracePilot reads the logs and trace, forms hypotheses, runs a check, applies a fix, and shows the verified result.

## Judging criteria alignment

- **Impact (30%)**: saves developer time on real failures and security issues.
- **Use of Meta AI tooling (25%)**: tool calling, structured output, and multi-step reasoning, not a basic chat wrapper.
- **Technical depth (20%)**: evidence correlation, sandboxed execution, verification loop.
- **Demo (25%)**: one tight, reliable end-to-end flow.

## License

To be decided.
