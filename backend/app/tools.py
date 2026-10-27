"""Evidence tools the TracePilot agent can call.

Every tool operates on a Sandbox: a disposable copy of the target application. Code from the
target only runs inside the sandbox, and edits never touch the original source.
Tools never raise to the model: failures come back as {"error": ...} so the agent can adjust.
Local absolute paths are scrubbed from all output before it reaches the model.
"""

import json
import re
from pathlib import Path
from typing import Any

from .config import REPO_ROOT
from .sandbox import TEXT_SUFFIXES, Sandbox

MAX_OUTPUT_CHARS = 8000
MAX_FILE_LINES = 400
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
REQUEST_RUNNER = (REPO_ROOT / "sandbox" / "request_runner.py").read_text(encoding="utf-8")


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} chars]"


class Workspace:
    """The tools, bound to one open sandbox."""

    def __init__(self, sandbox: Sandbox):
        self.sandbox = sandbox
        self.root = sandbox.root
        # Longest first, so the most specific base is stripped before its parents.
        bases = {str(self.root), str(sandbox.source), str(REPO_ROOT), str(Path.home())}
        self._scrub_bases = sorted(bases, key=len, reverse=True)

    def scrub(self, value: Any) -> Any:
        """Remove absolute local paths from a string, or from every string inside a JSON-like value."""
        if isinstance(value, dict):
            return {k: self.scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.scrub(v) for v in value]
        if not isinstance(value, str):
            return value
        for base in self._scrub_bases:
            value = value.replace(base + "\\", "").replace(base + "/", "").replace(base, ".")
        return value.replace("/workspace/", "")

    # --- investigation tools ------------------------------------------------

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
        return {"matched": len(entries), "shown": len(shown), "entries": self.scrub(shown)}

    def read_file(self, path: str, start_line: int = 1, end_line: int | None = None) -> dict:
        target = self.sandbox.resolve(path)
        if target.is_dir():
            files = sorted(
                p.relative_to(self.root).as_posix()
                for p in target.rglob("*")
                if p.is_file() and p.suffix in TEXT_SUFFIXES and "__pycache__" not in p.parts
            )
            return {"directory": path, "files": files}
        if not target.exists():
            return {"error": f"file not found: {path}"}
        if target.suffix not in TEXT_SUFFIXES:
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

        spec = {"app": self.sandbox.app, "method": method, "path": path, "headers": headers or {}, "body": body}
        result = self.sandbox.python(["-c", REQUEST_RUNNER], stdin=json.dumps(spec), timeout=30)
        if result.timed_out:
            return {"error": "request timed out after 30s"}
        if result.exit_code != 0:
            return {"error": "the app failed to handle the request", "stderr": _truncate(self.scrub(result.stderr), 3000)}
        return self.scrub(json.loads(result.stdout.strip().splitlines()[-1]))

    def run_tests(self, selector: str | None = None) -> dict:
        args = ["-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider"]
        if selector:
            if ".." in selector or not re.fullmatch(r"[\w/.:\-\[\]]+", selector):
                raise ValueError("selector must be a test path or node id, e.g. tests/test_orders.py::test_x")
            args.append(selector)
        result = self.sandbox.python(args, timeout=120)
        if result.timed_out:
            return {"error": "tests timed out after 120s"}

        output = self.scrub(result.stdout + result.stderr)
        summary = next(
            (line.strip("= ") for line in reversed(output.splitlines()) if re.search(r"\d+ (passed|failed|error)", line)),
            "no summary",
        )
        return {"exit_code": result.exit_code, "summary": summary, "output": _truncate(output[-MAX_OUTPUT_CHARS:])}

    # --- fix tools ----------------------------------------------------------

    def edit_file(self, path: str, old: str, new: str) -> dict:
        return self.sandbox.edit_file(path, old, new)

    def show_diff(self) -> dict:
        return {"diff": self.sandbox.diff() or "(no changes)"}


# --- tool definitions for the Responses API ----------------------------------

INVESTIGATION_TOOLS: list[dict] = [
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
        "description": "Send an HTTP request to the application under investigation (runs in the sandbox, no network) and return status and body. Use it to reproduce a failure or test an authorization rule.",
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
        "description": "Run the application's pytest suite (or one test file / node id) in the sandbox and return the pass/fail summary and output.",
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

FIX_TOOLS: list[dict] = [
    {
        "type": "function",
        "name": "edit_file",
        "description": "Edit a file in the sandbox copy (never the original): replace one exact occurrence of `old` with `new`. Include enough surrounding lines for `old` to be unique.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old": {"type": "string"},
                "new": {"type": "string"},
            },
            "required": ["path", "old", "new"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "show_diff",
        "description": "Show the unified diff of all edits made in the sandbox so far.",
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
]


def execute_tool(workspace: Workspace, name: str, arguments: str | dict, allowed: list[dict] = INVESTIGATION_TOOLS) -> str:
    """Run one tool call from the model and return its result as a JSON string.

    Only tools in `allowed` can run, so the investigation phase cannot edit code.
    """
    if name not in {spec["name"] for spec in allowed}:
        return json.dumps({"error": f"tool not available: {name}"})
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        result = getattr(workspace, name)(**(args or {}))
    except (PermissionError, ValueError, TypeError) as exc:
        result = {"error": str(exc)}
    return json.dumps(result, default=str)
