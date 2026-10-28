"""Hidden acceptance tests for billing: another invoice and other page sizes than the visible tests use."""

from fastapi.testclient import TestClient

from billing_api.app import app, invoice_totals

client = TestClient(app)


def test_tax_rounds_half_up_on_any_invoice():
    # 10.00 * 8.25% = 0.825 -> 0.83 half-up (float rounding gives 0.82)
    totals = invoice_totals({"id": 1, "lines": [{"sku": "X", "unit_price": 10.0, "qty": 1}]})
    assert totals["tax"] == 0.83 and totals["total"] == 10.83


def test_pagination_with_other_page_sizes():
    assert client.get("/invoices", params={"page": 2, "size": 3}).json()["items"] == [1004, 1005]
    assert client.get("/invoices", params={"page": 1, "size": 5}).json()["items"] == [1001, 1002, 1003, 1004, 1005]
