"""Inventory API: warehouse stock with reservations and cancellations. All data is synthetic."""

import itertools
import json
import logging
import time
import traceback
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

LOG_FILE = Path(__file__).resolve().parents[1] / "logs" / "inventory_api.log"

logger = logging.getLogger("inventory_api")
logger.setLevel(logging.INFO)
if not logger.handlers:
    LOG_FILE.parent.mkdir(exist_ok=True)
    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


def log_event(**fields) -> None:
    fields = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **fields}
    logger.info(json.dumps(fields))


USERS = {"token-alice": {"id": 1, "name": "alice"}, "token-bob": {"id": 2, "name": "bob"}}
STOCK = {"A-100": 100, "B-200": 20, "C-300": 3}
RESERVATIONS: dict[int, dict] = {}
_ids = itertools.count(1)

app = FastAPI(title="Inventory API")


class ReservationIn(BaseModel):
    sku: str
    qty: int


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
        status=response.status_code, duration_ms=round((time.perf_counter() - start) * 1000, 1),
    )  # fmt: skip
    return response


def current_user(authorization: str = Header(default="")) -> dict:
    user = USERS.get(authorization.removeprefix("Bearer ").strip())
    if user is None:
        raise HTTPException(status_code=401, detail="unauthorized")
    return user


@app.get("/stock/{sku}")
def read_stock(sku: str) -> dict:
    if sku not in STOCK:
        raise HTTPException(status_code=404, detail="unknown sku")
    return {"sku": sku, "available": STOCK[sku]}


@app.post("/reservations", status_code=201)
def reserve(body: ReservationIn, user: dict = Depends(current_user)) -> dict:
    if body.sku not in STOCK:
        raise HTTPException(status_code=404, detail="unknown sku")
    if body.qty > STOCK[body.sku]:
        raise HTTPException(status_code=409, detail="insufficient stock")
    STOCK[body.sku] -= body.qty
    reservation = {"id": next(_ids), "sku": body.sku, "qty": body.qty, "user_id": user["id"], "status": "active"}
    RESERVATIONS[reservation["id"]] = reservation
    log_event(level="INFO", event="reserved", reservation_id=reservation["id"], sku=body.sku, qty=body.qty,
              user_id=user["id"], available_after=STOCK[body.sku])  # fmt: skip
    return reservation


@app.delete("/reservations/{reservation_id}")
def cancel(reservation_id: int, user: dict = Depends(current_user)) -> dict:
    reservation = RESERVATIONS.get(reservation_id)
    if reservation is None or reservation["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="reservation not found")
    STOCK[reservation["sku"]] += reservation["qty"]
    reservation["status"] = "cancelled"
    log_event(level="INFO", event="cancelled", reservation_id=reservation_id, sku=reservation["sku"],
              qty=reservation["qty"], user_id=user["id"], available_after=STOCK[reservation["sku"]])  # fmt: skip
    return reservation
