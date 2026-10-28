"""Client for the external payment provider's refund API."""

import os

import httpx

PROVIDER_URL = os.environ.get("PAYMENTS_URL", "https://api.payments.example.com")


class ProviderError(Exception):
    def __init__(self, status: int, code: str, detail: dict | None = None):
        super().__init__(f"provider returned {status}: {code}")
        self.status, self.code, self.detail = status, code, detail or {}


def create_refund(charge_id: str, amount_cents: int) -> dict:
    resp = httpx.post(
        f"{PROVIDER_URL}/v1/refunds",
        json={"charge": charge_id, "amount": amount_cents},
        headers={"Authorization": f"Bearer {os.environ.get('PAYMENTS_API_KEY', '')}"},
        timeout=5,
    )
    expires = resp.headers.get("x-api-key-expires")
    if expires:
        from .app import log_event

        log_event(level="WARNING", event="provider_key_expiring", expires_at=expires)
    if resp.status_code >= 400:
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        raise ProviderError(resp.status_code, body.get("error", "unknown"), body)
    return resp.json()
