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
| `inventory` | `POST /reservations` never checks `qty > 0`, so a negative quantity adds phantom stock | Correctness | A-100 shows more than the 100 units the warehouse counted |
| `inventory` | Cancelling doesn't check the reservation is still active, so a double cancel returns stock twice | Correctness | C-300 was oversold: 5 reserved, 3 exist |
| `refunds` | *No code bug:* the payment provider's API key expired at 08:00, eight minutes after a deploy | External | Refunds fail since this morning's deploy; on-call suspects the release |
| `checkout` | Percent coupons sum 10% of each line's unit price, ignoring quantity | Correctness | A customer's screenshot shows the wrong discount; the ticket text has no numbers |

Note that the `notes` incident never mentions security. The agent has to discover that a quoting error is really an injection that leaks other users' notes. The test suite checks this, so escaping only the apostrophe isn't enough.

In `checkout`, the specifics are only in the customer's screenshot (`demo/screenshots/checkout-customer.png`, drawn by `demo/make_checkout_screenshot.py`): 2× LAMP-20 and 1× MUG-08 with SAVE10, a $2.80 discount where $4.80 is right. The request logs don't record bodies, and all 5 tests pass because none uses a quantity above 1.

In `refunds`, the right answer is **no code change**. The recorded production logs (`demo/logs/refunds_api.log`) show three key-expiry warnings before the deploy, a successful refund after it, then `401 api_key_expired` from 08:03. The fix is to issue a new key at the provider.

In `inventory`, all 5 existing tests pass ("CI is green"). The agent has to write reproducing tests with `write_regression_test`, which the harness keeps only if they fail before the fix; they must then pass after it.

`backend/tests/test_scenarios.py` proves each scenario is fair. The seed traffic reproduces the symptoms, exactly the expected tests fail (with the reference regression tests added for `inventory`), a reference fix verifies, and no target contains hint words. `backend/scripts/eval.py` reuses the reference fixes, and adds a test-gaming fix per scenario, to benchmark the reviewer.

```bash
.venv/Scripts/python backend/scripts/investigate.py --scenario notes   # run one investigation from the CLI
```
