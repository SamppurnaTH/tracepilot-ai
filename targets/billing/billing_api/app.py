"""Billing API: invoices with sales tax, and a paginated invoice list. All data is synthetic."""

import json
import logging
import time
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

LOG_FILE = Path(__file__).resolve().parents[1] / "logs" / "billing_api.log"
TAX_RATE = 0.0825  # 8.25% sales tax, applied to the invoice subtotal

logger = logging.getLogger("billing_api")
logger.setLevel(logging.INFO)
if not logger.handlers:
    LOG_FILE.parent.mkdir(exist_ok=True)
    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


def log_event(**fields) -> None:
    fields = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **fields}
    logger.info(json.dumps(fields))


INVOICES = {
    1001: {"id": 1001, "customer": "acme", "lines": [{"sku": "WID-1", "unit_price": 9.99, "qty": 2}]},
    1002: {"id": 1002, "customer": "globex", "lines": [{"sku": "GAD-7", "unit_price": 120.00, "qty": 1}]},
    1003: {
        "id": 1003,
        "customer": "initech",
        "lines": [{"sku": "TPS-2", "unit_price": 12.50, "qty": 2}, {"sku": "STP-9", "unit_price": 25.00, "qty": 1}],
    },
    1004: {"id": 1004, "customer": "acme", "lines": [{"sku": "WID-1", "unit_price": 9.99, "qty": 5}]},
    1005: {"id": 1005, "customer": "umbrella", "lines": [{"sku": "VAX-3", "unit_price": 199.00, "qty": 1}]},
}

app = FastAPI(title="Billing API")


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or f"r-{uuid.uuid4().hex[:8]}"
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        log_event(
            level="ERROR", request_id=request_id, method=request.method, path=request.url.path, status=500,
            error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc(),
        )  # fmt: skip
        return JSONResponse({"detail": "Internal Server Error"}, status_code=500)
    log_event(
        level="INFO", request_id=request_id, method=request.method, path=request.url.path,
        query=str(request.url.query), status=response.status_code,
        duration_ms=round((time.perf_counter() - start) * 1000, 1),
    )  # fmt: skip
    return response


def invoice_totals(invoice: dict) -> dict:
    subtotal = sum(line["unit_price"] * line["qty"] for line in invoice["lines"])
    total = round(subtotal + subtotal * TAX_RATE, 2)
    tax = round(total - subtotal, 2)
    return {"subtotal": round(subtotal, 2), "tax": tax, "total": total}


@app.get("/invoices/{invoice_id}")
def read_invoice(invoice_id: int) -> dict:
    invoice = INVOICES.get(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="invoice not found")
    totals = invoice_totals(invoice)
    log_event(level="INFO", event="invoice_totals", invoice_id=invoice_id, **totals)
    return {**invoice, **totals}


@app.get("/invoices")
def list_invoices(page: int = Query(1, ge=1), size: int = Query(2, ge=1, le=50)) -> dict:
    ordered = [INVOICES[k] for k in sorted(INVOICES)]
    offset = page * size
    items = ordered[offset : offset + size]
    return {"page": page, "size": size, "total_invoices": len(ordered), "items": [i["id"] for i in items]}
