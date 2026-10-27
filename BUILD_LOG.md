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
