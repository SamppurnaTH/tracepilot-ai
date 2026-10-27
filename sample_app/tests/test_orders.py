"""Tests for the sample Orders API.

Two of these fail on purpose until the planted bugs are fixed;
TracePilot uses them to verify its fixes.
"""

from fastapi.testclient import TestClient

from orders_api.app import app

client = TestClient(app)
ALICE = {"Authorization": "Bearer token-alice"}
BOB = {"Authorization": "Bearer token-bob"}


def test_owner_can_read_own_order():
    resp = client.get("/orders/7", headers=ALICE)
    assert resp.status_code == 200
    assert resp.json()["id"] == 7


def test_missing_token_is_rejected():
    assert client.get("/orders/7").status_code == 401


def test_user_cannot_read_someone_elses_order():
    # Bob must not be able to read Alice's order.
    resp = client.get("/orders/7", headers=BOB)
    assert resp.status_code == 404


def test_total_with_coupon():
    resp = client.get("/orders/7/total", headers=ALICE)
    assert resp.status_code == 200
    assert resp.json()["total"] == 44.1


def test_total_without_coupon():
    # Order 9 has no coupon; the total is the plain subtotal.
    resp = client.get("/orders/9/total", headers=BOB)
    assert resp.status_code == 200
    assert resp.json()["total"] == 120.0
