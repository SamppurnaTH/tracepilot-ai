"""TracePilot API: start investigations, stream their events live (SSE), and replay saved runs."""

import asyncio
import json
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .agent import Investigation
from .config import REPO_ROOT, get_settings
from .sandbox import Sandbox, docker_available, ensure_image
from .scenarios import SCENARIOS

RUNS_DIR = REPO_ROOT / "runs"
MAX_CONCURRENT = int(os.environ.get("TRACEPILOT_MAX_CONCURRENT", "2"))
SUPPORTED_PROVIDERS = {"meta"}
STREAM_POLL_S = 0.25


@dataclass
class Run:
    id: str
    scenario: str
    provider: str
    status: str = "running"  # running | completed | failed
    started_at: float = field(default_factory=time.time)
    events: list[dict] = field(default_factory=list)
    report: dict | None = None
    error: str | None = None

    def summary(self) -> dict:
        verification = (self.report or {}).get("verification", {})
        return {
            "id": self.id,
            "scenario": self.scenario,
            "provider": self.provider,
            "status": self.status,
            "started_at": self.started_at,
            "events": len(self.events),
            "verified": verification.get("verified"),
            "error": self.error,
        }


class RunManager:
    """Runs investigations in background threads and keeps their events for streaming."""

    def __init__(self, factory=Investigation.from_scenario):
        self.factory = factory
        self.runs: dict[str, Run] = {}
        self.lock = threading.Lock()

    def active(self) -> int:
        return sum(1 for r in self.runs.values() if r.status == "running")

    def start(self, scenario_id: str, provider: str) -> Run:
        with self.lock:
            if self.active() >= MAX_CONCURRENT:
                raise HTTPException(429, f"{MAX_CONCURRENT} investigations already running; try again shortly")
            run = Run(id=uuid.uuid4().hex[:12], scenario=scenario_id, provider=provider)
            self.runs[run.id] = run
        threading.Thread(target=self._execute, args=(run,), daemon=True).start()
        return run

    def _execute(self, run: Run) -> None:
        try:
            investigation = self.factory(SCENARIOS[run.scenario], provider=run.provider, on_event=run.events.append)
            report = investigation.run()
            report.pop("events", None)  # already in run.events
            run.report, run.status = report, "completed"
        except Exception as exc:  # surface any failure to the client instead of dying silently
            run.error, run.status = f"{type(exc).__name__}: {exc}", "failed"
            run.events.append({"seq": len(run.events) + 1, "type": "error", "message": run.error})
        finally:
            self.save(run)

    @staticmethod
    def save(run: Run) -> None:
        RUNS_DIR.mkdir(exist_ok=True)
        data = {**run.summary(), "report": run.report, "events": run.events}
        (RUNS_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{run.scenario}-{run.id}.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )


def _warm_sandbox() -> None:
    """Pay Docker's cold-start cost at boot rather than in the first investigation."""
    try:
        if docker_available():
            ensure_image()
            with Sandbox(SCENARIOS["orders"].target, isolation="docker", app=SCENARIOS["orders"].app):
                pass
    except Exception:
        pass  # investigations fall back to process isolation


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=_warm_sandbox, daemon=True).start()
    yield


app = FastAPI(title="TracePilot AI", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("TRACEPILOT_CORS_ORIGINS", "*").split(",")],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
manager = RunManager()


class StartRequest(BaseModel):
    scenario: str
    provider: str = "meta"


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "active_investigations": manager.active()}


@app.get("/api/scenarios")
def list_scenarios() -> list[dict]:
    return [s.summary() for s in SCENARIOS.values()]


@app.post("/api/investigations", status_code=202)
def start_investigation(body: StartRequest) -> dict:
    if body.scenario not in SCENARIOS:
        raise HTTPException(404, f"unknown scenario '{body.scenario}'")
    if body.provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(400, f"provider must be one of {sorted(SUPPORTED_PROVIDERS)}")
    try:
        get_settings(body.provider)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return manager.start(body.scenario, body.provider).summary()


@app.get("/api/investigations")
def list_investigations() -> list[dict]:
    return [r.summary() for r in sorted(manager.runs.values(), key=lambda r: r.started_at, reverse=True)]


def _get_run(run_id: str) -> Run:
    run = manager.runs.get(run_id)
    if run is None:
        raise HTTPException(404, "investigation not found")
    return run


@app.get("/api/investigations/{run_id}")
def get_investigation(run_id: str) -> dict:
    run = _get_run(run_id)
    return {**run.summary(), "report": run.report}


@app.get("/api/investigations/{run_id}/events")
async def stream_events(run_id: str) -> StreamingResponse:
    """Server-sent events: replays everything so far, then streams new events until the run ends."""
    run = _get_run(run_id)

    async def generate():
        sent = 0
        while True:
            while sent < len(run.events):
                yield f"data: {json.dumps(run.events[sent], default=str)}\n\n"
                sent += 1
            if run.status != "running" and sent >= len(run.events):
                yield f"event: end\ndata: {json.dumps(run.summary())}\n\n"
                return
            await asyncio.sleep(STREAM_POLL_S)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/runs")
def list_saved_runs() -> list[dict]:
    """Saved runs on disk, newest first, for replay."""
    if not RUNS_DIR.exists():
        return []
    runs = []
    for path in sorted(RUNS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        runs.append({"name": path.stem, **{k: data.get(k) for k in ("scenario", "provider", "status", "verified")}})
    return runs


@app.get("/api/runs/{name}")
def get_saved_run(name: str) -> dict:
    path = (RUNS_DIR / f"{name}.json").resolve()
    if not path.is_relative_to(RUNS_DIR.resolve()) or not path.exists():
        raise HTTPException(404, "run not found")
    return json.loads(path.read_text(encoding="utf-8"))
