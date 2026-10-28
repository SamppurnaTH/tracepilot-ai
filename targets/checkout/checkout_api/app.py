"""Checkout API: prices a cart and applies coupon codes. All data is synthetic."""

import json
import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

LOG_FILE = Path(__file__).resolve().parents[1] / "logs" / "checkout_api.log"

logger = logging.getLogger("checkout_api")
logger.setLevel(logging.INFO)
if not logger.handlers:
    LOG_FILE.parent.mkdir(exist_ok=True)
    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


def log_event(**fields) -> None:
    fields = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **fields}
    logger.info(json.dumps(fields))


CATALOG = {
    "LAMP-20": {"name": "Arc desk lamp", "price": 20.00},
    "MUG-08": {"name": "Stoneware mug", "price": 8.00},
    "NOTE-12": {"name": "Dot-grid notebook", "price": 12.00},
}
COUPONS = {
    "SAVE10": {"kind": "percent", "value": 10},
    "FLAT5": {"kind": "fixed", "value": 5.00},
}

app = FastAPI(title="Checkout API")


class Line(BaseModel):
    sku: str
    qty: int = Field(gt=0)


class QuoteIn(BaseModel):
    lines: list[Line]
    coupon: str | None = None


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


def discount_for(lines: list[Line], coupon: dict | None, subtotal: float) -> float:
    if coupon is None:
        return 0.0
    if coupon["kind"] == "fixed":
        return min(coupon["value"], subtotal)
    return sum(CATALOG[line.sku]["price"] * coupon["value"] / 100 for line in lines)


@app.post("/checkout/quote")
def quote(body: QuoteIn) -> dict:
    for line in body.lines:
        if line.sku not in CATALOG:
            raise HTTPException(status_code=404, detail=f"unknown sku {line.sku}")
    coupon = None
    if body.coupon:
        coupon = COUPONS.get(body.coupon.upper())
        if coupon is None:
            raise HTTPException(status_code=400, detail="unknown coupon")
    subtotal = sum(CATALOG[line.sku]["price"] * line.qty for line in body.lines)
    discount = round(discount_for(body.lines, coupon, subtotal), 2)
    return {"subtotal": round(subtotal, 2), "discount": discount, "total": round(subtotal - discount, 2)}
