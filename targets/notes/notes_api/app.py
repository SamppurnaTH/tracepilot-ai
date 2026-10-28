"""Notes API: private notes per user, with title search and export. All data is synthetic."""

import json
import logging
import sqlite3
import time
import traceback
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

LOG_FILE = Path(__file__).resolve().parents[1] / "logs" / "notes_api.log"
SLOW_REQUEST_MS = 500

logger = logging.getLogger("notes_api")
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

db = sqlite3.connect(":memory:", check_same_thread=False)
db.executescript(
    """
    CREATE TABLE notes (id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL);
    INSERT INTO notes VALUES (1, 1, 'Groceries', 'eggs, milk');
    INSERT INTO notes VALUES (2, 1, 'Project ideas', 'tracing for agents');
    INSERT INTO notes VALUES (3, 2, 'Bob''s passwords', 'wifi: hunter2');
    INSERT INTO notes VALUES (4, 2, 'Meeting notes', 'Q4 planning');
    """
)

app = FastAPI(title="Notes API")


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or f"r-{uuid.uuid4().hex[:8]}"
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        log_event(
            level="ERROR", request_id=request_id, method=request.method, path=request.url.path,
            query=str(request.url.query), status=500, user_id=getattr(request.state, "user_id", None),
            error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc(),
        )  # fmt: skip
        return JSONResponse({"detail": "Internal Server Error"}, status_code=500)
    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    log_event(
        level="WARNING" if duration_ms > SLOW_REQUEST_MS else "INFO", request_id=request_id,
        method=request.method, path=request.url.path, query=str(request.url.query), status=response.status_code,
        user_id=getattr(request.state, "user_id", None), duration_ms=duration_ms,
    )  # fmt: skip
    return response


def current_user(request: Request, authorization: str = Header(default="")) -> dict:
    user = USERS.get(authorization.removeprefix("Bearer ").strip())
    if user is None:
        raise HTTPException(status_code=401, detail="invalid token")
    request.state.user_id = user["id"]
    return user


@app.get("/notes")
def list_notes(user: dict = Depends(current_user)) -> list[dict]:
    rows = db.execute("SELECT id, title FROM notes WHERE owner_id = ? ORDER BY id", (user["id"],)).fetchall()
    return [{"id": r[0], "title": r[1]} for r in rows]


@app.get("/notes/search")
def search_notes(q: str, user: dict = Depends(current_user)) -> list[dict]:
    sql = f"SELECT id, title FROM notes WHERE owner_id = {user['id']} AND title LIKE '%{q}%' ORDER BY id"
    rows = db.execute(sql).fetchall()
    return [{"id": r[0], "title": r[1]} for r in rows]


@app.get("/notes/export")
def export_notes(user: dict = Depends(current_user)) -> dict:
    # Exports are rendered in full; large accounts take a while.
    time.sleep(0.6)
    rows = db.execute("SELECT id, title, body FROM notes WHERE owner_id = ? ORDER BY id", (user["id"],)).fetchall()
    return {"notes": [{"id": r[0], "title": r[1], "body": r[2]} for r in rows]}
