"""Evidence tools the TracePilot agent can call.

Every tool is scoped to one target workspace (today: sample_app/). Tools never raise
to the model: failures come back as {"error": ...} so the agent can adjust.
Absolute local paths are scrubbed from all output before it reaches the model.
"""

import importlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import REPO_ROOT

MAX_OUTPUT_CHARS = 8000
MAX_FILE_LINES = 400
READABLE_SUFFIXES = {".py", ".md", ".ini", ".txt", ".json", ".toml", ".cfg"}
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} chars]"


class Workspace:
    """The directory of the application under investigation."""

    def __init__(self, root: Path, app_module: str = "orders_api.app"):
        self.root = root.resolve()
        self.app_module = app_module

    def scrub(self, value: Any) -> Any:
        """Remove absolute local paths from a string, or from every string inside a JSON-like value."""
        if isinstance(value, dict):
            return {k: self.scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.scrub(v) for v in value]
        if not isinstance(value, str):
            return value
        # Longest base first, so the workspace root is stripped before the repo root.
        for base in sorted({str(self.root), str(REPO_ROOT)}, key=len, reverse=True):
            value = value.replace(base + "\\", "").replace(base + "/", "").replace(base, ".")
        return value

    def _resolve(self, rel_path: str) -> Path:
        path = (self.root / rel_path).resolve()
        if not path.is_relative_to(self.root):
            raise PermissionError(f"path is outside the workspace: {rel_path}")
        if any(part.startswith(".env") for part in path.parts):
            raise PermissionError("secret files cannot be read")
        return path

    # --- tools ------------------------------------------------------------

    def read_log(
        self,
        service: str = "orders_api",
        level: str | None = None,
        path_contains: str | None = None,
        request_id: str | None = None,
        limit: int = 50,
    ) -> dict:
        if not re.fullmatch(r"[a-z0-9_]+", service):
            raise ValueError("service must be lowercase letters, digits or underscores")
        log_file = self.root / "logs" / f"{service}.log"
        if not log_file.exists():
            return {"error": f"no log file for service '{service}'"}

        entries = []
        for line in log_file.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if level and entry.get("level", "").upper() != level.upper():
                continue
            if path_contains and path_contains not in entry.get("path", ""):
                continue
            if request_id and entry.get("request_id") != request_id:
                continue
            entries.append(entry)

        limit = max(1, min(limit, 200))
        shown = entries[-limit:]
        return {
            "matched": len(entries),
            "shown": len(shown),
            "entries": self.scrub(shown),
        }

    def read_file(self, path: str, start_line: int = 1, end_line: int | None = None) -> dict:
        target = self._resolve(path)
        if target.is_dir():
            files = sorted(
                str(p.relative_to(self.root)).replace("\\", "/")
                for p in target.rglob("*")
                if p.is_file() and p.suffix in READABLE_SUFFIXES and "__pycache__" not in p.parts
            )
            return {"directory": path, "files": files}
        if not target.exists():
            return {"error": f"file not found: {path}"}
        if target.suffix not in READABLE_SUFFIXES:
            return {"error": f"file type not readable: {target.suffix or '(none)'}"}

        lines = target.read_text(encoding="utf-8").splitlines()
        start = max(1, start_line)
        end = min(len(lines), end_line or len(lines), start + MAX_FILE_LINES - 1)
        numbered = "\n".join(f"{n:4d}  {lines[n - 1]}" for n in range(start, end + 1))
        return {"path": path, "lines": f"{start}-{end} of {len(lines)}", "content": numbered}

    def send_request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: Any = None,
    ) -> dict:
        method = method.upper()
        if method not in HTTP_METHODS:
            raise ValueError(f"method must be one of {sorted(HTTP_METHODS)}")
        if not path.startswith("/") or "://" in path:
            raise ValueError("path must be a relative URL path like /orders/7")

        from fastapi.testclient import TestClient

        # In-process requests: nothing leaves the machine, and a fresh import picks up code changes.
        if str(self.root) not in sys.path:
            sys.path.insert(0, str(self.root))
        module = importlib.import_module(self.app_module)
        module = importlib.reload(module)

        client = TestClient(module.app, raise_server_exceptions=False)
        resp = client.request(method, path, headers=headers or {}, json=body)
        try:
            payload: Any = resp.json()
        except ValueError:
            payload = _truncate(resp.text, 2000)
        return {"status": resp.status_code, "body": payload}

    def run_tests(self, selector: str | None = None) -> dict:
        cmd = [sys.executable, "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider"]
        if selector:
            if ".." in selector or not re.fullmatch(r"[\w/.:\-\[\]]+", selector):
                raise ValueError("selector must be a test path or node id, e.g. tests/test_orders.py::test_x")
            cmd.append(selector)
        try:
            proc = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            return {"error": "tests timed out after 120s"}

        output = self.scrub(proc.stdout + proc.stderr)
        summary = next(
            (line.strip("= ") for line in reversed(output.splitlines()) if re.search(r"\d+ (passed|failed|error)", line)),
            "no summary",
        )
        return {"exit_code": proc.returncode, "summary": summary, "output": _truncate(output[-MAX_OUTPUT_CHARS:])}


# --- tool definitions for the Responses API ----------------------------------

TOOL_SPECS: list[dict] = [
    {
        "type": "function",
        "name": "read_log",
        "description": "Read structured JSON log entries from the application under investigation, with optional filters.",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service name, e.g. 'orders_api'"},
                "level": {"type": "string", "enum": ["INFO", "WARNING", "ERROR"]},
                "path_contains": {"type": "string", "description": "Only entries whose request path contains this text"},
                "request_id": {"type": "string"},
                "limit": {"type": "integer", "description": "Max entries to return (most recent), default 50"},
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "read_file",
        "description": "Read a source file (with line numbers) or list a directory inside the application workspace. Paths are relative to the workspace root, e.g. 'orders_api/app.py' or '.'.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "send_request",
        "description": "Send an HTTP request to the application under investigation (sandboxed, in-process) and return status and body. Use it to reproduce a failure or test an authorization rule.",
        "parameters": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": sorted(HTTP_METHODS)},
                "path": {"type": "string", "description": "URL path, e.g. /orders/9/total"},
                "headers": {"type": "object", "additionalProperties": {"type": "string"}},
                "body": {"description": "Optional JSON body"},
            },
            "required": ["method", "path"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "run_tests",
        "description": "Run the application's pytest suite (or one test file / node id) and return the pass/fail summary and output.",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "Optional, e.g. tests/test_orders.py::test_total_without_coupon"},
            },
            "required": [],
            "additionalProperties": False,
        },
    },
]


def execute_tool(workspace: Workspace, name: str, arguments: str | dict) -> str:
    """Run one tool call from the model and return its result as a JSON string."""
    tool = getattr(workspace, name, None) if name in {spec["name"] for spec in TOOL_SPECS} else None
    if tool is None:
        return json.dumps({"error": f"unknown tool: {name}"})
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        result = tool(**(args or {}))
    except (PermissionError, ValueError, TypeError) as exc:
        result = {"error": str(exc)}
    return json.dumps(result, default=str)
