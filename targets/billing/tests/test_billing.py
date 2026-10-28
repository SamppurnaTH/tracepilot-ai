"""Tests for the Billing API.

Billing rules: amounts are in dollars with cent precision; sales tax (8.25%) is computed on the
invoice subtotal and rounded half-up to the cent, as shown on customer statements.
"""

from fastapi.testclient import TestClient

from billing_api.app import app

client = TestClient(app)


def total_of(invoice_id: int) -> float:
    resp = client.get(f"/invoices/{invoice_id}")
    assert resp.status_code == 200
    return resp.json()["total"]


def test_simple_invoice_total():
    assert total_of(1002) == 129.90


def test_invoice_total_rounds_tax_half_up():
    # Subtotal 50.00, tax 4.125 -> 4.13 (half-up), total 54.13.
    resp = client.get("/invoices/1003")
    assert resp.json()["subtotal"] == 50.00
    assert resp.json()["tax"] == 4.13
    assert resp.json()["total"] == 54.13


def test_unknown_invoice_is_404():
    assert client.get("/invoices/9999").status_code == 404


def test_first_page_starts_with_first_invoice():
    resp = client.get("/invoices", params={"page": 1, "size": 2})
    assert resp.json()["items"] == [1001, 1002]


def test_pages_cover_every_invoice_once():
    seen = []
    for page in (1, 2, 3):
        seen += client.get("/invoices", params={"page": page, "size": 2}).json()["items"]
    assert seen == [1001, 1002, 1003, 1004, 1005]
