"""Delivery date estimates for the shipping service. All data is synthetic."""

from datetime import date, timedelta

from dateutil.easter import easter

TRANSIT_DAYS = {"standard": 3, "express": 1}


def holidays(year: int) -> set[date]:
    return {date(year, 1, 1), easter(year) + timedelta(days=1), date(year, 12, 25), date(year, 12, 26)}


def is_business_day(day: date) -> bool:
    return day.weekday() < 5 and day not in holidays(day.year)


def add_business_days(start: date, days: int) -> date:
    current, added = start, 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 6 and current not in holidays(current.year):
            added += 1
    return current


def estimate_delivery(order_date: date, service: str = "standard") -> date:
    return add_business_days(order_date, TRANSIT_DAYS[service])
