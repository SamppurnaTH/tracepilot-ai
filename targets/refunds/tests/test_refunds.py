"""Tests for the Refunds API. The payment provider is mocked: these tests never call it."""

import pytest
from fastapi.testclient import TestClient

from refunds_api import app as refunds
from refunds_api import provider
from refunds_api.app import app

client = TestClient(app)


def test_refund_succeeds(monkeypatch):
    monkeypatch.setattr(provider, "create_refund", lambda charge, amount: {"id": "re_1", "status": "succeeded"})
    resp = client.post("/refunds", json={"charge_id": "ch_1", "amount_cents": 500})
    assert resp.status_code == 201 and resp.json() == {"refund_id": "re_1", "status": "succeeded"}


def test_provider_rejection_is_a_502(monkeypatch):
    def reject(charge, amount):
        raise provider.ProviderError(402, "charge_already_refunded")

    monkeypatch.setattr(provider, "create_refund", reject)
    assert client.post("/refunds", json={"charge_id": "ch_1", "amount_cents": 500}).status_code == 502


def test_amount_must_be_positive():
    assert client.post("/refunds", json={"charge_id": "ch_1", "amount_cents": 0}).status_code == 422


def test_health_reports_version():
    assert client.get("/health").json() == {"status": "ok", "version": refunds.VERSION}


@pytest.mark.parametrize("status", [400, 404])
def test_any_provider_error_is_a_502(monkeypatch, status):
    def reject(charge, amount):
        raise provider.ProviderError(status, "invalid_request")

    monkeypatch.setattr(provider, "create_refund", reject)
    assert client.post("/refunds", json={"charge_id": "ch_2", "amount_cents": 100}).status_code == 502
