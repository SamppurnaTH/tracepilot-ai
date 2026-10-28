from datetime import date

import pytest

from shipping.delivery import estimate_delivery, is_business_day


def test_standard_from_monday():
    assert estimate_delivery(date(2026, 10, 19)) == date(2026, 10, 22)


def test_express_from_tuesday():
    assert estimate_delivery(date(2026, 10, 20), "express") == date(2026, 10, 21)


def test_weekends_are_not_business_days():
    assert not is_business_day(date(2026, 10, 24))
    assert not is_business_day(date(2026, 10, 25))


def test_unknown_service():
    with pytest.raises(KeyError):
        estimate_delivery(date(2026, 10, 19), "teleport")
