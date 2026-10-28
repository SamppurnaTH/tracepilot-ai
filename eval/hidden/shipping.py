"""Hidden acceptance tests for the shipping module: other dates and services than the incident mentions."""

from datetime import date

from shipping.delivery import estimate_delivery


def test_express_from_any_friday_lands_on_monday():
    assert estimate_delivery(date(2026, 10, 30), "express") == date(2026, 11, 2)


def test_standard_never_counts_saturday():
    assert estimate_delivery(date(2026, 10, 22)) == date(2026, 10, 27)  # Thu -> Fri, Mon, Tue
