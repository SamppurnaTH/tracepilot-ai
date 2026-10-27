"""Generate synthetic traffic against the Orders API so it writes realistic logs.

Run from sample_app/:  ../.venv/Scripts/python simulate_traffic.py
Output: sample_app/logs/orders_api.log (JSON lines)
"""

from fastapi.testclient import TestClient

from orders_api.app import LOG_FILE, app

ALICE = {"Authorization": "Bearer token-alice"}
BOB = {"Authorization": "Bearer token-bob"}

TRAFFIC = [
    ("/orders/7", ALICE),
    ("/orders/7/total", ALICE),
    ("/orders/8/total", ALICE),
    ("/orders/9", BOB),
    ("/orders/9/total", BOB),  # 500: order without a coupon
    ("/orders/7", BOB),  # 200: bob reads alice's order
    ("/orders/8", BOB),  # 200: bob reads alice's order
    ("/orders/7", {}),  # 401
    ("/orders/9/total", BOB),  # 500 again
]


def main() -> None:
    LOG_FILE.write_text("", encoding="utf-8")
    client = TestClient(app, raise_server_exceptions=False)
    for i, (path, headers) in enumerate(TRAFFIC, start=1):
        resp = client.get(path, headers={**headers, "x-request-id": f"r-{100 + i}"})
        print(f"{resp.status_code}  GET {path}")
    print(f"\nWrote {LOG_FILE}")


if __name__ == "__main__":
    main()
