"""Hidden acceptance tests for checkout: other carts than the screenshot shows."""

from fastapi.testclient import TestClient

from checkout_api.app import app

client = TestClient(app)


def quote(lines, coupon=None):
    return client.post("/checkout/quote", json={"lines": lines, "coupon": coupon}).json()


def test_percent_coupon_on_quantity():
    assert quote([{"sku": "NOTE-12", "qty": 3}], "SAVE10") == {"subtotal": 36.0, "discount": 3.6, "total": 32.4}


def test_percent_coupon_on_a_mixed_cart():
    lines = [{"sku": "MUG-08", "qty": 4}, {"sku": "NOTE-12", "qty": 2}]
    assert quote(lines, "SAVE10")["discount"] == 5.6


def test_fixed_coupon_is_unchanged():
    assert quote([{"sku": "LAMP-20", "qty": 2}], "FLAT5") == {"subtotal": 40.0, "discount": 5.0, "total": 35.0}
