# Demo scenarios (answer key)

TracePilot investigates the apps in `targets/`. Each one is a small synthetic FastAPI service with planted defects. This file is the answer key, and it never enters the sandbox: the agent only sees the target's code, its logs (seeded fresh inside each sandbox), and a symptom-only incident report (`backend/app/scenarios.py`).

| Scenario | Defect | Class | Symptom the agent is given |
|---|---|---|---|
| `orders` | `compute_total` assumes every order has a coupon | Reliability | `GET /orders/9/total` sometimes returns 500 |
| `orders` | `read_order` has no ownership check (IDOR) | Security | A reviewer suspects users can see others' orders |
| `notes` | Search builds SQL with an f-string (SQL injection) | Security | Searching for a title with an apostrophe fails |
| `notes` | *Red herring:* slow export logs WARNINGs | (none) | On-call asks whether the WARNINGs are related |
| `billing` | Float math and `round()` lose a cent on tax | Correctness | Customer disputes 54.12 vs 54.13 |
| `billing` | Pagination offset is `page * size` (off by one page) | Correctness | First page never shows the earliest invoices |

Note that the `notes` incident never mentions security. The agent has to discover that a quoting error is really an injection that leaks other users' notes. The test suite checks this, so escaping only the apostrophe isn't enough.

`backend/tests/test_scenarios.py` proves each scenario is fair. The seed traffic reproduces the symptoms, exactly the expected tests fail, a reference fix verifies, and no target contains hint words.

```bash
.venv/Scripts/python backend/scripts/investigate.py --scenario notes   # run one investigation from the CLI
```
