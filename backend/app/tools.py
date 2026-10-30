"""Evidence tools the TracePilot agent can call.

Every tool operates on a Sandbox: a disposable copy of the target application. Code from the
target only runs inside the sandbox, and edits never touch the original source.
Tools never raise to the model: failures come back as {"error": ...} so the agent can adjust.
Local absolute paths are scrubbed from all output before it reaches the model.
"""

import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .config import REPO_ROOT
from .sandbox import M2_REPO, TEXT_SUFFIXES, Sandbox, is_generated

MAX_OUTPUT_CHARS = 8000
MAX_TEST_OUTPUT_CHARS = 4000
MAX_FILE_LINES = 400
MAX_FILE_CHARS = 16_000  # one read of a huge file (docs, generated code) must not flood the context
MAX_LISTED_FILES = 80

# Java test classes that need services the sandbox deliberately lacks (network, a database, Docker).
# They are excluded from every Maven run, and the exclusion is reported, never hidden.
NETWORK_TEST_MARKERS = ("Testcontainers", "@Container", "flapdoodle", "EmbeddedMongo", "@SpringBootTest", "@DataMongoTest", "GenericContainer")
EXCLUDES_FILE = ".tracepilot-surefire-excludes"
# JUnit "errors" that mean the environment, not the code under test, failed.
INFRA_ERRORS = ("Failed to load ApplicationContext", "Connection refused", "MongoTimeout", "UnknownHost", "ContainerLaunch", "DockerClient", "RedisConnection")
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
REQUEST_RUNNER = (REPO_ROOT / "sandbox" / "request_runner.py").read_text(encoding="utf-8")


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} chars]"


_FRAME = re.compile(r'^\s*File "(?P<path>[^"]+)", line (?P<line>\d+), in (?P<func>.+)$')
# Matched against the frame's path with forward slashes.
_LIBRARY_MARKERS = ("site-packages/", "dist-packages/", "/lib/python3", "/Lib/", "<frozen")


def compact_traceback(tb: str) -> str:
    """Keep only the application's own frames and the final exception line.

    Framework frames (starlette, anyio, ...) make up most of a web traceback and say nothing
    about the bug, yet every later model call would pay for them again.
    """
    lines = tb.rstrip().splitlines()
    kept: list[str] = []
    for i, line in enumerate(lines):
        match = _FRAME.match(line)
        if not match or any(m in match["path"].replace("\\", "/") for m in _LIBRARY_MARKERS):
            continue
        code = lines[i + 1].strip() if i + 1 < len(lines) and not _FRAME.match(lines[i + 1]) else ""
        kept.append(f'{match["path"]}:{match["line"]} in {match["func"]}: {code}')
    final = next((line for line in reversed(lines) if line and not line.startswith(" ")), "")
    return "\n".join(kept + [final])


_LEVEL = re.compile(r"\b(CRITICAL|FATAL|ERROR|WARN(?:ING)?|INFO|DEBUG)\b")
_NOISE = re.compile(r"\d{4}-\d{2}-\d{2}[T ][\d:.,]+Z?|\b[0-9a-f]{8,}\b|\d+")


def parse_log(text: str) -> list[dict]:
    """Log entries from JSON lines or plain text. Indented lines and tracebacks join the entry above them."""
    entries: list[dict] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if isinstance(entry, dict):
                entries.append(entry)
                continue
        except json.JSONDecodeError:
            pass
        level = _LEVEL.search(line)
        continuation = line[:1].isspace() or line.startswith("Traceback") or (entries and "traceback" in entries[-1] and not level)
        if continuation and entries and "line" in entries[-1]:
            entries[-1]["traceback"] = entries[-1].get("traceback", "") + line + "\n"
            continue
        name = level.group(1).upper() if level else "INFO"
        entries.append({"level": {"WARN": "WARNING", "FATAL": "CRITICAL"}.get(name, name), "line": line})
    return entries


class Workspace:
    """The tools, bound to one open sandbox."""

    def __init__(self, sandbox: Sandbox):
        self.sandbox = sandbox
        self.root = sandbox.root
        # Longest first, so the most specific base is stripped before its parents.
        bases = {str(self.root), str(sandbox.source), str(REPO_ROOT), str(Path.home())}
        self._scrub_bases = sorted(bases, key=len, reverse=True)
        self.kind = getattr(sandbox, "kind", "python")
        self.excluded = self._exclude_network_tests() if self.kind == "maven" else []
        self.extra_tests: list[str] = []  # reproducing test classes the agent added; always part of a scoped run

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
        service: str | None = None,
        level: str | None = None,
        path_contains: str | None = None,
        request_id: str | None = None,
        limit: int = 30,
    ) -> dict:
        available = sorted(p.stem for p in (self.root / "logs").glob("*.log"))
        if service is None:
            if len(available) != 1:
                return {"error": "choose a log with 'service'", "available": available}
            service = available[0]
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", service) or ".." in service:
            raise ValueError("service must be a log name like 'orders_api'")
        log_file = self.root / "logs" / f"{service}.log"
        if not log_file.exists():
            return {"error": f"no log file for service '{service}'", "available": available}

        entries = []
        for entry in parse_log(log_file.read_text(encoding="utf-8", errors="replace")):
            if level and entry.get("level", "").upper() != level.upper():
                continue
            if path_contains and path_contains not in entry.get("path", entry.get("line", "")):
                continue
            if request_id and entry.get("request_id") != request_id and request_id not in entry.get("line", ""):
                continue
            if isinstance(entry.get("traceback"), str):
                entry["traceback"] = compact_traceback(entry["traceback"])
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
                if p.is_file() and p.suffix in TEXT_SUFFIXES and not is_generated(p.relative_to(self.root))
            )
            if len(files) > 300:
                return {"directory": path, "files": files[:300], "note": f"{len(files) - 300} more; list a subdirectory"}
            return {"directory": path, "files": files}
        if not target.exists():
            return {"error": f"file not found: {path}"}
        if target.suffix not in TEXT_SUFFIXES:
            return {"error": f"file type not readable: {target.suffix or '(none)'}"}

        lines = target.read_text(encoding="utf-8").splitlines()
        start = max(1, start_line)
        end = min(len(lines), end_line or len(lines), start + MAX_FILE_LINES - 1)
        numbered, size = [], 0
        for n in range(start, end + 1):
            size += len(lines[n - 1]) + 7
            if size > MAX_FILE_CHARS and numbered:
                end = n - 1
                break
            numbered.append(f"{n:4d}  {lines[n - 1]}")
        result = {"path": path, "lines": f"{start}-{end} of {len(lines)}", "content": "\n".join(numbered)}
        if end < len(lines):
            result["note"] = f"truncated; read more with start_line={end + 1}"
        return result

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
        if isinstance(body, str):  # models often send the JSON body as a string; a wasted 422 costs a round trip
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                pass
        results = self.send_batch([{"method": method, "path": path, "headers": headers or {}, "body": body}], timeout=30)
        return results if isinstance(results, dict) else results[0]

    def send_batch(self, requests: list[dict], timeout: int = 120) -> list[dict] | dict:
        """Send several requests to one app instance in one sandbox process (also used to seed traffic)."""
        if not self.sandbox.app:
            return {"error": "no HTTP app is configured for this project, so requests can't be sent"}
        spec = {"app": self.sandbox.app, "requests": requests}
        result = self.sandbox.python(["-c", REQUEST_RUNNER], stdin=json.dumps(spec), timeout=timeout)
        if result.timed_out:
            return {"error": f"request timed out after {timeout}s"}
        if result.exit_code != 0:
            return {"error": "the app failed to handle the request", "stderr": _truncate(self.scrub(result.stderr), 3000)}
        return self.scrub(json.loads(result.stdout.strip().splitlines()[-1]))

    def run_tests(self, selector: str | None = None) -> dict:
        if self.kind == "maven":
            return self._maven_run_tests(selector)
        # --color=no: FORCE_COLOR or PY_COLORS in the environment would otherwise send escape codes to the model.
        args = ["-m", "pytest", "-q", "--tb=short", "--color=no", "--continue-on-collection-errors", "-p", "no:cacheprovider"]
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
        if result.exit_code == 0:  # all green: the summary says everything
            return {"exit_code": 0, "summary": summary}
        return {"exit_code": result.exit_code, "summary": summary, "output": _truncate(output[-MAX_TEST_OUTPUT_CHARS:], MAX_TEST_OUTPUT_CHARS)}

    def log_digest(self) -> list[str]:
        """Warning and error patterns per log, grouped. Take it before any test run adds entries."""
        out = []
        for log_file in sorted((self.root / "logs").glob("*.log")):
            groups: dict[tuple, list[str]] = {}
            levels: dict[str, int] = {}
            for e in parse_log(log_file.read_text(encoding="utf-8", errors="replace")):
                levels[e.get("level", "?")] = levels.get(e.get("level", "?"), 0) + 1
                if e.get("level") not in ("WARNING", "ERROR", "CRITICAL"):
                    continue
                if "line" in e:  # plain text: group lines that differ only in numbers, ids and timestamps
                    key = (e["level"], None, _NOISE.sub("#", e["line"]).lstrip("#,. ")[:160], None, "")
                    groups.setdefault(key, []).append(e["line"][:40])
                else:
                    key = (e.get("level"), e.get("method"), e.get("path"), e.get("status"), e.get("error", ""))
                    groups.setdefault(key, []).append(str(e.get("request_id")))
            out.append(f"Log {log_file.stem}: " + ", ".join(f"{n} {lvl}" for lvl, n in sorted(levels.items())))
            for (level, method, path, status, error), ids in groups.items():
                if method is None:
                    out.append(f"  {level} x{len(ids)}: {path}")
                    continue
                detail = f" {error}" if error else ""
                out.append(f"  {level} x{len(ids)}: {method} {path} -> {status}{detail} (e.g. {', '.join(ids[:3])})")
        return self.scrub(out)

    def brief(self, log_digest: list[str], outcomes: dict[str, str], reasons: dict[str, str]) -> str:
        """A digest the harness computes for free: files, log patterns and failing tests.

        Handing this over up front saves the model several exploratory round trips,
        each of which would re-send the whole conversation.
        """
        files = sorted(
            p.relative_to(self.root).as_posix()
            for p in self.root.rglob("*")
            if p.is_file() and p.suffix in TEXT_SUFFIXES and not is_generated(p.relative_to(self.root)) and p.parent.name != "logs"
        )
        failing = sorted(t for t, o in outcomes.items() if o != "passed")
        if len(files) <= MAX_LISTED_FILES:
            out = ["Workspace files: " + ", ".join(files)]
        else:  # a big project: directories with file counts, so the model knows where to look
            dirs: dict[str, int] = {}
            for f in files:
                d = "/".join(f.split("/")[:-1][:6]) or "."
                dirs[d] = dirs.get(d, 0) + 1
            out = [f"Workspace: {len(files)} text files. Directories (file count): " + ", ".join(f"{d} ({n})" for d, n in sorted(dirs.items()))]
        if self.kind == "maven":
            out.append("Project: Java/Maven; tests are JUnit, run offline in the sandbox.")
            if self.sandbox.test_scope:
                out.append(f"Test scope (what counts as green, as in CI): {', '.join(self.sandbox.test_scope)}")
            if self.excluded:
                out.append(f"Excluded {len(self.excluded)} test classes that need a database, network or Docker: {', '.join(self.excluded)}")
        out += log_digest
        out.append(f"Tests: {len(outcomes) - len(failing)} passed, {len(failing)} failing")
        out.extend(f"  FAILING {t}" + (f": {reasons[t]}" if t in reasons else "") for t in failing)
        return self.scrub("\n".join(out))

    def test_outcomes(self) -> dict[str, str]:
        """Per-test outcomes ({node_id: "passed" | "failed" | "error"}), for harness-side verification."""
        return self.test_report()[0]

    def test_report(self, selector: str | None = None) -> tuple[dict[str, str], dict[str, str]]:
        """Per-test outcomes, plus pytest's one-line failure message for each failing test."""
        if self.kind == "maven":
            result = self._mvn(self._maven_selector(selector) if selector else None)
            outcomes, reasons = self._surefire_results()
            if not outcomes and result.exit_code != 0:
                reasons["(build)"] = self._build_errors(result)
            return outcomes, reasons
        # --color=no: with FORCE_COLOR or PY_COLORS set, colour codes would hide every result line from the parser.
        args = ["-q", "-rA", "--tb=no", "--color=no", "--continue-on-collection-errors", "-p", "no:cacheprovider"]
        if selector:
            if ".." in selector or not re.fullmatch(r"[\w/.:\-\[\]]+", selector):
                raise ValueError("selector must be a test path or node id")
            args.append(selector)
        # A wide virtual terminal stops pytest from truncating the failure messages.
        code = f"import os, sys; os.environ['COLUMNS'] = '400'; import pytest; sys.exit(pytest.main({args!r}))"
        # Large suites (tens of thousands of parametrized tests) need minutes; a timeout returns no outcomes at all.
        result = self.sandbox.python(["-c", code], timeout=600)
        outcomes, reasons = {}, {}
        if result.timed_out:
            reasons["(test run)"] = "timed out after 600s"
        for line in (result.stdout + result.stderr).splitlines():
            match = re.match(r"^(PASSED|FAILED|ERROR) (\S+)(?: - (.+))?$", line)
            if match:
                outcomes[match.group(2)] = match.group(1).lower()
                if match.group(3):
                    reasons[match.group(2)] = self.scrub(match.group(3))[:240]
        return outcomes, reasons

    # --- Java / Maven ------------------------------------------------------------

    def _exclude_network_tests(self) -> list[str]:
        excluded = []
        for path in sorted((self.root / "src" / "test").rglob("*.java")):
            if any(m in path.read_text(encoding="utf-8", errors="ignore") for m in NETWORK_TEST_MARKERS):
                excluded.append(path.stem)
        (self.root / EXCLUDES_FILE).write_text("".join(f"**/{name}.java\n" for name in excluded), encoding="utf-8")
        return excluded

    @staticmethod
    def _maven_selector(selector: str) -> str:
        """Accept a test class, Class#method, or a path like src/test/java/com/x/FooTest.java."""
        if selector.endswith(".java"):
            selector = Path(selector).stem
        if not re.fullmatch(r"[\w.#*,+]+", selector):
            raise ValueError("selector must be a test class, Class#method, or a path under src/test/java")
        return selector

    def _mvn(self, selector: str | None = None):
        shutil.rmtree(self.root / "target" / "surefire-reports", ignore_errors=True)
        argv = [
            "mvn", "-o", "-B", "-q", f"-Dmaven.repo.local={M2_REPO}", "test",
            f"-Dsurefire.excludesFile={EXCLUDES_FILE}", "-DfailIfNoTests=false",
            "-Dsurefire.failIfNoSpecifiedTests=false", "-DtrimStackTrace=true",
        ]  # fmt: skip
        argv += [a for a in self.sandbox.test_args if a.startswith("-D")]  # only properties, never other goals
        scope = getattr(self.sandbox, "test_scope", None)
        if not selector and scope:
            selector = ",".join([*scope, *self.extra_tests])
        if selector:
            argv.append(f"-Dtest={selector}")
        return self.sandbox.run(argv, timeout=1200)

    def _surefire_results(self) -> tuple[dict[str, str], dict[str, str]]:
        outcomes, reasons = {}, {}
        for report in sorted((self.root / "target" / "surefire-reports").glob("TEST-*.xml")):
            try:
                cases = ET.parse(report).getroot().iter("testcase")
            except ET.ParseError:
                continue
            for case in cases:
                node = f"{case.get('classname')}#{case.get('name')}"
                if case.find("skipped") is not None:
                    continue
                failure, error = case.find("failure"), case.find("error")
                if failure is None and error is None:
                    outcomes[node] = "passed"
                    continue
                bad = failure if failure is not None else error
                message = f"{bad.get('type', '')}: {bad.get('message') or ''}".strip(": ")
                # An exception from the code under test is a failing test, as in pytest; a broken environment is not.
                infra = error is not None and any(m in (message + (error.text or "")) for m in INFRA_ERRORS)
                outcomes[node] = "error" if infra else "failed"
                reasons[node] = self.scrub(message)[:240]
        return outcomes, reasons

    def _build_errors(self, result) -> str:
        lines = [line for line in (result.stdout + result.stderr).splitlines() if "[ERROR]" in line or "error:" in line]
        return _truncate(self.scrub("\n".join(lines[:30]) or (result.stdout + result.stderr)[-1500:]), 2500)

    def _maven_run_tests(self, selector: str | None) -> dict:
        result = self._mvn(self._maven_selector(selector) if selector else None)
        if result.timed_out:
            return {"error": "tests timed out"}
        outcomes, reasons = self._surefire_results()
        if not outcomes:
            return {"exit_code": result.exit_code, "summary": "no tests ran", "build_errors": self._build_errors(result)}
        tally = {o: sum(1 for v in outcomes.values() if v == o) for o in set(outcomes.values())}
        summary = ", ".join(f"{n} {o}" for o, n in sorted(tally.items()))
        failing = {t: reasons.get(t, outcomes[t]) for t, o in outcomes.items() if o != "passed"}
        if not failing:
            return {"exit_code": 0, "summary": summary}
        return {
            "exit_code": result.exit_code,
            "summary": summary,
            "failing": dict(list(failing.items())[:20]),
            "failed_tests": [t for t, o in outcomes.items() if o == "failed"][:50],  # real failures, not environment errors
        }

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
                "service": {"type": "string", "description": "Log name (file name without .log); optional when there is only one log"},
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
                "body": {"description": "Optional JSON body, as an object (not a string)"},
            },
            "required": ["method", "path"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "run_tests",
        "description": "Run the project's test suite in the sandbox, or one test (pytest: a file or node id; Java: a class, Class#method or test file path), and return the pass/fail summary and failures.",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "Optional, e.g. tests/test_orders.py::test_total_without_coupon or OrderServiceTest#totalWithoutCoupon"},
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


def tools_for(app: str | None, tools: list[dict]) -> list[dict]:
    """Drop send_request when the project has no HTTP app to send requests to."""
    return [t for t in tools if app or t["name"] != "send_request"]
