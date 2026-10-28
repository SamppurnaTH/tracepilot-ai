"""Orders API: read orders and their totals. All data is synthetic."""

import json
import logging
import time
import traceback
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

LOG_FILE = Path(__file__).resolve().parents[1] / "logs" / "orders_api.log"

logger = logging.getLogger("orders_api")
logger.setLevel(logging.INFO)
if not logger.handlers:
    LOG_FILE.parent.mkdir(exist_ok=True)
    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


def log_event(**fields) -> None:
    fields = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **fields}
    logger.info(json.dumps(fields))


# --- synthetic data -------------------------------------------------------

USERS = {
    "token-alice": {"id": 1, "name": "alice"},
    "token-bob": {"id": 2, "name": "bob"},
}

ORDERS = {
    7: {"id": 7, "owner_id": 1, "items": [{"sku": "KB-01", "price": 49.0, "qty": 1}], "coupon": {"percent": 10}},
    8: {"id": 8, "owner_id": 1, "items": [{"sku": "MS-02", "price": 25.0, "qty": 2}], "coupon": {"percent": 0}},
    9: {"id": 9, "owner_id": 2, "items": [{"sku": "HD-03", "price": 120.0, "qty": 1}], "coupon": None},
}

# --- app ------------------------------------------------------------------

app = FastAPI(title="Orders API (sample)")


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or f"r-{uuid.uuid4().hex[:8]}"
    request.state.request_id = request_id
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        log_event(
            level="ERROR",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=500,
            error=f"{type(exc).__name__}: {exc}",
            traceback=traceback.format_exc(),
        )
        return JSONResponse({"detail": "Internal Server Error"}, status_code=500)
    log_event(
        level="INFO",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        user_id=getattr(request.state, "user_id", None),
        duration_ms=round((time.perf_counter() - start) * 1000, 1),
    )
    return response


def current_user(request: Request, authorization: str = Header(default="")) -> dict:
    token = authorization.removeprefix("Bearer ").strip()
    user = USERS.get(token)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid token")
    request.state.user_id = user["id"]
    return user


def get_order_or_404(order_id: int) -> dict:
    order = ORDERS.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return order


@app.get("/orders/{order_id}")
def read_order(order_id: int, user: dict = Depends(current_user)) -> dict:
    order = get_order_or_404(order_id)
    return order


def compute_total(order: dict) -> float:
    subtotal = sum(item["price"] * item["qty"] for item in order["items"])
    discount = subtotal * order["coupon"]["percent"] / 100
    return round(subtotal - discount, 2)


@app.get("/orders/{order_id}/total")
def read_order_total(order_id: int, user: dict = Depends(current_user)) -> dict:
    order = get_order_or_404(order_id)
    if order["owner_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="order not found")
    return {"order_id": order_id, "total": compute_total(order)}
