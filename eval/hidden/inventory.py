"""Hidden acceptance tests for inventory: other SKUs than the ones in the tickets."""

from fastapi.testclient import TestClient

from inventory_api import app as inventory
from inventory_api.app import app

client = TestClient(app)
BOB = {"Authorization": "Bearer token-bob"}


def setup_function():
    inventory.STOCK.update({"A-100": 100, "B-200": 20, "C-300": 3})
    inventory.RESERVATIONS.clear()


def available(sku: str) -> int:
    return client.get(f"/stock/{sku}").json()["available"]


def test_negative_quantity_never_adds_stock():
    resp = client.post("/reservations", json={"sku": "B-200", "qty": -4}, headers=BOB)
    assert resp.status_code >= 400 and available("B-200") == 20


def test_zero_quantity_is_rejected():
    assert client.post("/reservations", json={"sku": "B-200", "qty": 0}, headers=BOB).status_code >= 400


def test_cancel_twice_returns_stock_once():
    rid = client.post("/reservations", json={"sku": "B-200", "qty": 6}, headers=BOB).json()["id"]
    client.delete(f"/reservations/{rid}", headers=BOB)
    client.delete(f"/reservations/{rid}", headers=BOB)
    assert available("B-200") == 20
