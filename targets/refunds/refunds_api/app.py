"""Refunds API: refunds a charge through the payment provider. All data is synthetic."""

import json
import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from . import provider

LOG_FILE = Path(__file__).resolve().parents[1] / "logs" / "refunds_api.log"
VERSION = "2.14.0"

logger = logging.getLogger("refunds_api")
logger.setLevel(logging.INFO)
if not logger.handlers:
    LOG_FILE.parent.mkdir(exist_ok=True)
    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


def log_event(**fields) -> None:
    fields = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **fields}
    logger.info(json.dumps(fields))


app = FastAPI(title="Refunds API", version=VERSION)


class RefundIn(BaseModel):
    charge_id: str
    amount_cents: int = Field(gt=0)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or f"r-{uuid.uuid4().hex[:8]}"
    start = time.perf_counter()
    response = await call_next(request)
    log_event(
        level="INFO" if response.status_code < 500 else "ERROR", request_id=request_id, method=request.method,
        path=request.url.path, status=response.status_code, duration_ms=round((time.perf_counter() - start) * 1000, 1),
    )  # fmt: skip
    return response


@app.post("/refunds", status_code=201)
def refund(body: RefundIn) -> dict:
    try:
        result = provider.create_refund(body.charge_id, body.amount_cents)
    except provider.ProviderError as exc:
        log_event(level="ERROR", event="provider_error", charge_id=body.charge_id, provider_status=exc.status,
                  provider_error=exc.code, provider_detail=exc.detail)  # fmt: skip
        raise HTTPException(status_code=502, detail="payment provider rejected the refund") from exc
    return {"refund_id": result["id"], "status": result["status"]}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": VERSION}
