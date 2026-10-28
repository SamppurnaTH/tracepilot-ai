"""Tests for the Inventory API.

Stock rules: a reservation takes units out of available stock; cancelling a reservation
returns its units. Available stock can never exceed what the warehouse holds.
"""

from fastapi.testclient import TestClient

from inventory_api import app as inventory
from inventory_api.app import app

client = TestClient(app)
ALICE = {"Authorization": "Bearer token-alice"}
BOB = {"Authorization": "Bearer token-bob"}


def setup_function():
    inventory.STOCK.update({"A-100": 100, "B-200": 20, "C-300": 3})
    inventory.RESERVATIONS.clear()


def available(sku: str) -> int:
    return client.get(f"/stock/{sku}").json()["available"]


def test_reservation_takes_stock():
    resp = client.post("/reservations", json={"sku": "B-200", "qty": 5}, headers=ALICE)
    assert resp.status_code == 201
    assert available("B-200") == 15


def test_cannot_reserve_more_than_available():
    resp = client.post("/reservations", json={"sku": "C-300", "qty": 4}, headers=ALICE)
    assert resp.status_code == 409
    assert available("C-300") == 3


def test_cancel_returns_stock():
    rid = client.post("/reservations", json={"sku": "B-200", "qty": 5}, headers=ALICE).json()["id"]
    assert client.delete(f"/reservations/{rid}", headers=ALICE).status_code == 200
    assert available("B-200") == 20


def test_cannot_cancel_someone_elses_reservation():
    rid = client.post("/reservations", json={"sku": "B-200", "qty": 5}, headers=ALICE).json()["id"]
    assert client.delete(f"/reservations/{rid}", headers=BOB).status_code == 404


def test_unknown_sku_is_404():
    assert client.get("/stock/Z-999").status_code == 404
