# Sample app: Orders API

A small FastAPI service that TracePilot investigates in the demo. All data is synthetic.

It contains two deliberately planted bugs:

| Bug | Type | Symptom |
|---|---|---|
| Missing ownership check on `GET /orders/{id}` | Security (IDOR) | Any signed-in user can read any order |
| `compute_total` assumes every order has a coupon | Reliability | `GET /orders/9/total` returns 500 |

`tests/test_orders.py` contains one failing test for each bug. TracePilot's job is to find the root causes from the logs and code, then prove its fix by turning those tests green.

```bash
cd sample_app
../.venv/Scripts/python -m pytest          # 2 tests fail until the bugs are fixed
../.venv/Scripts/python simulate_traffic.py  # writes logs/orders_api.log
```
