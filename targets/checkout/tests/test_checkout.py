"""Tests for the Checkout API."""

from fastapi.testclient import TestClient

from checkout_api.app import app

client = TestClient(app)


def quote(lines, coupon=None):
    resp = client.post("/checkout/quote", json={"lines": lines, "coupon": coupon})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_quote_without_coupon():
    assert quote([{"sku": "MUG-08", "qty": 3}]) == {"subtotal": 24.0, "discount": 0.0, "total": 24.0}


def test_percent_coupon():
    assert quote([{"sku": "LAMP-20", "qty": 1}], "SAVE10") == {"subtotal": 20.0, "discount": 2.0, "total": 18.0}


def test_fixed_coupon():
    assert quote([{"sku": "NOTE-12", "qty": 1}], "FLAT5") == {"subtotal": 12.0, "discount": 5.0, "total": 7.0}


def test_coupon_codes_are_case_insensitive():
    assert quote([{"sku": "MUG-08", "qty": 1}], "save10")["discount"] == 0.8


def test_unknown_coupon_is_rejected():
    resp = client.post("/checkout/quote", json={"lines": [{"sku": "MUG-08", "qty": 1}], "coupon": "FREE"})
    assert resp.status_code == 400
