# Demo scenario (answer key)

The target app is `sample_app/`, a synthetic Orders API. It contains two deliberately planted bugs:

| Bug | Type | Symptom |
|---|---|---|
| Missing ownership check on `GET /orders/{id}` | Security (IDOR) | Any signed-in user can read any order |
| `compute_total` assumes every order has a coupon | Reliability | `GET /orders/9/total` returns 500 |

`sample_app/tests/test_orders.py` has one failing test per bug. TracePilot must find the root causes from logs, code and requests, then prove its fix by turning those tests green.

This file and `simulate_traffic.py` live outside `sample_app/`, so neither is copied into the sandbox. The agent investigates without an answer key.

```bash
.venv/Scripts/python demo/simulate_traffic.py      # writes sample_app/logs/orders_api.log
cd sample_app && ../.venv/Scripts/python -m pytest  # 2 tests fail until the bugs are fixed
```
