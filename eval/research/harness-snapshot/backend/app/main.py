"""TracePilot API: start investigations, stream their events live (SSE), and replay saved runs."""

import asyncio
import hmac
import json
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import shutil
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .admin import current_user, router as admin_router, workspace_router, workspace_user, workspace_writer
from .agent import Cancelled, Investigation
from .cli import detect_app
from .reviewer import Reviewer
from .config import REPO_ROOT, get_settings
from .sandbox import Sandbox, detect_kind, docker_available, ensure_image, project_image
from .uploads import UploadError, clone_repo, extract_zip, save_attachment, workdir
from .scenarios import SCENARIOS

RUNS_DIR = REPO_ROOT / "runs"
MAX_CONCURRENT = int(os.environ.get("TRACEPILOT_MAX_CONCURRENT", "2"))
# Public-server guards, all off by default: a daily run cap (0 = none), a key for investigating
# uploaded or cloned code, and refusing to run at all without Docker isolation.
DAILY_LIMIT = int(os.environ.get("TRACEPILOT_DAILY_LIMIT", "0"))
SUPPORTED_PROVIDERS = {"meta"}
STREAM_POLL_S = 0.25


@dataclass
class Run:
    id: str
    scenario: str
    provider: str
    status: str = "running"  # running | completed | failed | cancelled
    title: str = ""
    started_at: float = field(default_factory=time.time)
    events: list[dict] = field(default_factory=list)
    report: dict | None = None
    error: str | None = None
    stop: threading.Event = field(default_factory=threading.Event, repr=False)

    def summary(self) -> dict:
        verification = (self.report or {}).get("verification", {})
        return {
            "id": self.id,
            "scenario": self.scenario,
            "provider": self.provider,
            "status": self.status,
            "title": self.title,
            "outcome": (self.report or {}).get("outcome"),
            "started_at": self.started_at,
            "events": len(self.events),
            "verified": verification.get("verified"),
            "error": self.error,
        }


class RunManager:
    """Runs investigations in background threads and keeps their events for streaming."""

    def __init__(self, factory=Investigation.from_scenario, custom_factory=Investigation):
        self.factory = factory
        self.custom_factory = custom_factory  # builds investigations of uploaded or cloned projects
        self.runs: dict[str, Run] = {}
        self.lock = threading.Lock()
        self.day, self.started_today = "", 0

    def active(self) -> int:
        return sum(1 for r in self.runs.values() if r.status == "running")

    def _reserve(self, scenario: str, provider: str, title: str) -> Run:
        with self.lock:
            if (RUNS_DIR / ".deployment-draining").exists():
                raise HTTPException(503, "a deployment is draining investigations; try again shortly")
            if self.active() >= MAX_CONCURRENT:
                raise HTTPException(429, f"{MAX_CONCURRENT} investigations already running; try again shortly")
            today = time.strftime("%Y-%m-%d", time.gmtime())
            if today != self.day:
                self.day, self.started_today = today, 0
            if DAILY_LIMIT and self.started_today >= DAILY_LIMIT:
                raise HTTPException(429, "today's live runs are used up; replay a recorded run or try again tomorrow (UTC)")
            self.started_today += 1
            run = Run(id=uuid.uuid4().hex[:12], scenario=scenario, provider=provider, title=title)
            self.runs[run.id] = run
        return run

    def start(self, scenario_id: str, provider: str) -> Run:
        run = self._reserve(scenario_id, provider, SCENARIOS[scenario_id].title)
        build = lambda: self.factory(SCENARIOS[run.scenario], provider=run.provider, on_event=run.events.append)  # noqa: E731
        threading.Thread(target=self._execute, args=(run, build), daemon=True).start()
        return run

    def start_custom(self, title: str, build, cleanup=None) -> Run:
        """Run an investigation of an uploaded or cloned project; build(run) returns the Investigation."""
        run = self._reserve("custom", "meta", title)
        threading.Thread(target=self._execute, args=(run, lambda: build(run), cleanup), daemon=True).start()
        return run

    def _execute(self, run: Run, build, cleanup=None) -> None:
        # The final status is published only after cleanup, so a finished run never has uploads left on disk.
        status, report, error = "failed", None, None
        try:
            investigation = build()
            investigation.should_stop = run.stop.is_set
            # Time spent preparing (such as building a project's sandbox image) counts toward the run's duration.
            investigation.started_at = run.started_at
            report = investigation.run()
            report.pop("events", None)  # already in run.events
            status = "completed"
        except Cancelled:
            status, error = "cancelled", "stopped by the user"
            run.events.append({"seq": len(run.events) + 1, "type": "cancelled", "message": error})
        except Exception as exc:  # surface any failure to the client instead of dying silently
            error = f"{type(exc).__name__}: {exc}"
            run.events.append({"seq": len(run.events) + 1, "type": "error", "message": error})
        finally:
            if cleanup:
                cleanup()
            run.report, run.error, run.status = report, error, status
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
app.include_router(admin_router)
app.include_router(workspace_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("TRACEPILOT_CORS_ORIGINS", "*").split(",")],
    allow_methods=["GET", "POST", "PATCH"],  # uploads are multipart POSTs
    allow_headers=["*"],
)
manager = RunManager()


class StartRequest(BaseModel):
    scenario: str
    provider: str = "meta"


def _upload_key() -> str:
    return os.environ.get("TRACEPILOT_UPLOAD_KEY", "")


def _require_docker() -> None:
    if os.environ.get("TRACEPILOT_REQUIRE_DOCKER") == "1" and not docker_available():
        raise HTTPException(503, "the sandbox is unavailable; try again shortly")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "active_investigations": manager.active(), "uploads_need_key": bool(_upload_key()), "release": os.environ.get("TRACEPILOT_RELEASE")}


@app.get("/api/scenarios")
def list_scenarios() -> list[dict]:
    return [s.summary() for s in SCENARIOS.values()]


# The built-in example scenarios are the public demo: anyone can run and watch them (within the
# concurrency and daily limits). A signed-in caller is held to their workspace role. Investigations
# of uploaded or cloned code need a workspace operator or the upload access key.
def optional_user(authorization: str = Header("")) -> dict | None:
    return workspace_user(current_user(authorization)) if authorization else None


def optional_writer(authorization: str = Header("")) -> dict | None:
    return workspace_writer(workspace_user(current_user(authorization))) if authorization else None


def _require_user_for_custom(scenario: str, user: dict | None) -> None:
    if scenario == "custom" and user is None:
        raise HTTPException(401, "sign in to the workspace to see investigations of uploaded code")


@app.post("/api/investigations", dependencies=[Depends(optional_writer)], status_code=202)
def start_investigation(body: StartRequest) -> dict:
    if body.scenario not in SCENARIOS:
        raise HTTPException(404, f"unknown scenario '{body.scenario}'")
    if body.provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(400, f"provider must be one of {sorted(SUPPORTED_PROVIDERS)}")
    try:
        get_settings(body.provider)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    _require_docker()
    return manager.start(body.scenario, body.provider).summary()


def _check_key() -> None:
    try:
        get_settings("meta")
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/investigations/custom", status_code=202)
async def start_custom_investigation(
    incident: str = Form(..., min_length=10, max_length=4000),
    project: UploadFile | None = File(None),
    repo_url: str | None = Form(None),
    logs: list[UploadFile] = File([]),
    screenshots: list[UploadFile] = File([]),
    tests: str | None = Form(None),
    test_args: str | None = Form(None),
    x_tracepilot_key: str = Header(""),
    user: dict | None = Depends(optional_writer),
) -> dict:
    """Investigate your own project: upload a ZIP or give a public repository URL, plus optional logs and screenshots."""
    key = _upload_key()
    if user is None and key and not hmac.compare_digest(x_tracepilot_key.encode(), key.encode()):
        raise HTTPException(401, "investigating your own code needs an access key")
    _check_key()
    _require_docker()
    if bool(project) == bool(repo_url):
        raise HTTPException(400, "provide either a project ZIP or a repository URL")
    base = workdir()
    try:
        if project:
            root = extract_zip(await project.read(), base / "project")
            title = Path(project.filename or "project").stem
        else:
            root = clone_repo(repo_url or "", base / "project")
            title = (repo_url or "").rstrip("/").removesuffix(".git").rsplit("/", 1)[-1]
        log_paths = [save_attachment(f.filename or "app.log", await f.read(), base / "logs", {".log", ".txt", ".json", ".jsonl"}) for f in logs]
        shot_paths = [save_attachment(f.filename or "shot.png", await f.read(), base / "shots", {".png", ".jpg", ".jpeg", ".webp", ".gif"}) for f in screenshots]
    except UploadError as exc:
        shutil.rmtree(base, ignore_errors=True)
        raise HTTPException(400, str(exc)) from exc
    try:
        kind = detect_kind(root)
    except ValueError as exc:
        shutil.rmtree(base, ignore_errors=True)
        raise HTTPException(400, str(exc)) from exc
    scope = [t.strip() for t in (tests or "").split(",") if t.strip()] or None

    def build(run: Run):
        image = project_image(root, kind) if docker_available() else None
        if kind == "maven" and image is None:
            raise RuntimeError("Java projects need Docker")
        return manager.custom_factory(
            incident.strip(), root, on_event=run.events.append, kind=kind, app=detect_app(root) if kind == "python" else None,
            logs=log_paths, images=shot_paths, image=image, test_scope=scope, test_args=(test_args or "").split() or None,
            reviewer=Reviewer.from_env(),
        )  # fmt: skip

    return manager.start_custom(title, build, cleanup=lambda: shutil.rmtree(base, ignore_errors=True)).summary()


@app.post("/api/investigations/{run_id}/cancel")
def cancel_investigation(run_id: str, user: dict | None = Depends(optional_writer)) -> dict:
    """Ask a running investigation to stop; it ends before its next model call."""
    run = _get_run(run_id)
    _require_user_for_custom(run.scenario, user)
    if run.status == "running":
        run.stop.set()
    return run.summary()


@app.get("/api/investigations", dependencies=[Depends(workspace_user)])
def list_investigations() -> list[dict]:
    return [r.summary() for r in sorted(manager.runs.values(), key=lambda r: r.started_at, reverse=True)]


def _get_run(run_id: str) -> Run:
    run = manager.runs.get(run_id)
    if run is None:
        raise HTTPException(404, "investigation not found")
    return run


@app.get("/api/investigations/{run_id}")
def get_investigation(run_id: str, user: dict | None = Depends(optional_user)) -> dict:
    run = _get_run(run_id)
    _require_user_for_custom(run.scenario, user)
    return {**run.summary(), "report": run.report}


@app.get("/api/investigations/{run_id}/events")
async def stream_events(run_id: str, user: dict | None = Depends(optional_user)) -> StreamingResponse:
    """Server-sent events: replays everything so far, then streams new events until the run ends."""
    run = _get_run(run_id)
    _require_user_for_custom(run.scenario, user)

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
def list_saved_runs(user: dict | None = Depends(optional_user)) -> list[dict]:
    """Saved runs on disk, newest first, for replay. Without sign-in, only example-scenario runs."""
    if not RUNS_DIR.exists():
        return []
    runs = []
    for path in sorted(RUNS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if user is None and data.get("scenario") == "custom":
            continue
        report = data.get("report") or {}
        usage = report.get("usage") or {}
        runs.append({
            "name": path.stem,
            **{k: data.get(k) for k in ("scenario", "provider", "status", "verified", "title", "started_at")},
            "outcome": report.get("outcome"),
            "duration_s": report.get("duration_s"),
            "tokens": (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0),
        })  # fmt: skip
    return runs


@app.get("/api/runs/{name}")
def get_saved_run(name: str, user: dict | None = Depends(optional_user)) -> dict:
    path = (RUNS_DIR / f"{name}.json").resolve()
    if not path.is_relative_to(RUNS_DIR.resolve()) or not path.exists():
        raise HTTPException(404, "run not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    _require_user_for_custom(data.get("scenario", ""), user)
    return data
