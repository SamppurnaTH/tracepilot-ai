"""Hidden acceptance tests for orders: never shown to either system. They probe the root cause beyond the visible tests."""

from fastapi.testclient import TestClient

from orders_api.app import app

client = TestClient(app)
ALICE = {"Authorization": "Bearer token-alice"}
BOB = {"Authorization": "Bearer token-bob"}


def test_ownership_is_enforced_for_every_order():
    assert client.get("/orders/8", headers=BOB).status_code == 404  # not only the order the visible test uses
    assert client.get("/orders/9", headers=ALICE).status_code == 404


def test_owners_can_still_read_their_orders():
    assert client.get("/orders/8", headers=ALICE).status_code == 200
    assert client.get("/orders/9", headers=BOB).status_code == 200


def test_total_without_coupon_is_correct():
    resp = client.get("/orders/9/total", headers=BOB)
    assert resp.status_code == 200 and resp.json()["total"] == 120.0
