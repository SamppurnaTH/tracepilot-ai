"""Sandbox: an isolated, disposable copy of the application under investigation.

Each investigation gets a fresh copy of the target in a temp directory. Code from the target
(its tests, its HTTP handlers, any patch the agent writes) only ever runs against that copy:

- "docker" isolation (preferred): a long-lived container per sandbox with no network,
  a read-only root filesystem, no Linux capabilities, a non-root user, and CPU/memory/PID limits.
- "process" isolation (fallback when Docker is unavailable): a subprocess in the copy,
  with secrets stripped from its environment.

The original source is never modified, and the copy is deleted when the sandbox closes.
"""

import difflib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .config import REPO_ROOT

IMAGE = "tracepilot-sandbox:1"
IMAGE_DIR = REPO_ROOT / "sandbox"
COPY_IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", ".env*", ".venv", "node_modules", ".git")
TEXT_SUFFIXES = {".py", ".md", ".ini", ".txt", ".json", ".toml", ".cfg"}
SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


@dataclass
class RunResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


def _docker(*args: str, timeout: int = 60, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], input=stdin, capture_output=True, text=True, timeout=timeout, encoding="utf-8"
    )


@lru_cache(maxsize=1)
def docker_available() -> bool:
    try:
        return _docker("info", "--format", "{{.ServerVersion}}", timeout=15).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def ensure_image() -> None:
    """Build the sandbox image if it doesn't exist yet."""
    if _docker("image", "inspect", IMAGE).returncode == 0:
        return
    build = _docker("build", "-t", IMAGE, str(IMAGE_DIR), timeout=900)
    if build.returncode != 0:
        raise RuntimeError(f"failed to build sandbox image:\n{build.stderr[-2000:]}")


class LocalRunner:
    isolation = "process"

    def __init__(self, root: Path):
        self.root = root
        self.env = {k: v for k, v in os.environ.items() if not any(m in k.upper() for m in SECRET_MARKERS)}
        self.env["PYTHONDONTWRITEBYTECODE"] = "1"

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def python(self, args: list[str], stdin: str | None, timeout: int) -> RunResult:
        try:
            proc = subprocess.run(
                [sys.executable, *args],
                cwd=self.root,
                env=self.env,
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return RunResult(-1, "", f"timed out after {timeout}s", timed_out=True)
        return RunResult(proc.returncode, proc.stdout, proc.stderr)


class DockerRunner:
    isolation = "docker"

    def __init__(self, root: Path):
        self.root = root
        self.name = f"tracepilot-sbx-{uuid.uuid4().hex[:10]}"

    def start(self) -> None:
        ensure_image()
        run = _docker(
            "run", "-d", "--rm",
            "--name", self.name,
            "--network", "none",
            "--read-only",
            "--tmpfs", "/tmp:rw,size=64m",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", "128",
            "--memory", "512m",
            "--cpus", "1",
            "-v", f"{self.root}:/workspace:rw",
            IMAGE, "sleep", "infinity",
        )  # fmt: skip
        if run.returncode != 0:
            raise RuntimeError(f"failed to start sandbox container: {run.stderr.strip()}")

    def stop(self) -> None:
        _docker("rm", "-f", self.name, timeout=30)

    def python(self, args: list[str], stdin: str | None, timeout: int) -> RunResult:
        try:
            proc = _docker("exec", "-i", self.name, "python", *args, stdin=stdin, timeout=timeout)
        except subprocess.TimeoutExpired:
            # A hung process may still be running: replace the container with a fresh one.
            self.stop()
            self.start()
            return RunResult(-1, "", f"timed out after {timeout}s", timed_out=True)
        return RunResult(proc.returncode, proc.stdout, proc.stderr)


class Sandbox:
    """Use as a context manager: `with Sandbox(path) as sb: ...`."""

    def __init__(self, source: Path, isolation: str = "auto", app: str = "orders_api.app:app"):
        if isolation not in {"auto", "docker", "process"}:
            raise ValueError("isolation must be 'auto', 'docker' or 'process'")
        self.source = source.resolve()
        self.requested_isolation = isolation
        self.app = app
        self._tmp: Path | None = None
        self.runner: LocalRunner | DockerRunner | None = None

    @property
    def root(self) -> Path:
        if self._tmp is None:
            raise RuntimeError("sandbox is not open")
        return self._tmp / "workspace"

    @property
    def isolation(self) -> str:
        return self.runner.isolation if self.runner else "closed"

    def __enter__(self) -> "Sandbox":
        self._tmp = Path(tempfile.mkdtemp(prefix="tracepilot-"))
        shutil.copytree(self.source, self.root, ignore=COPY_IGNORE)
        # The container runs as a non-root user; let it write logs inside its own copy.
        for path in [self.root, *self.root.rglob("*")]:
            path.chmod(path.stat().st_mode | stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)

        use_docker = self.requested_isolation == "docker" or (
            self.requested_isolation == "auto" and docker_available()
        )
        self.runner = DockerRunner(self.root) if use_docker else LocalRunner(self.root)
        try:
            self.runner.start()
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc) -> None:
        if self.runner:
            self.runner.stop()
            self.runner = None
        if self._tmp:
            shutil.rmtree(self._tmp, ignore_errors=True)
            self._tmp = None

    def python(self, args: list[str], stdin: str | None = None, timeout: int = 120) -> RunResult:
        if self.runner is None:
            raise RuntimeError("sandbox is not open")
        return self.runner.python(args, stdin, timeout)

    def resolve(self, rel_path: str) -> Path:
        path = (self.root / rel_path).resolve()
        if not path.is_relative_to(self.root):
            raise PermissionError(f"path is outside the workspace: {rel_path}")
        if any(part.startswith(".env") for part in path.relative_to(self.root).parts):
            raise PermissionError("secret files cannot be accessed")
        return path

    def edit_file(self, path: str, old: str, new: str) -> dict:
        """Replace exactly one occurrence of `old` with `new` in a file of the sandbox copy."""
        target = self.resolve(path)
        if not target.is_file() or target.suffix not in TEXT_SUFFIXES:
            return {"error": f"not an editable text file: {path}"}
        text = target.read_text(encoding="utf-8")
        count = text.count(old) if old else 0
        if count != 1:
            hint = "not found" if count == 0 else f"found {count} times; include more surrounding lines"
            return {"error": f"old text must match exactly once in {path}: {hint}"}
        target.write_text(text.replace(old, new, 1), encoding="utf-8")
        return {"edited": path}

    def diff(self) -> str:
        """Unified diff of every text file changed in the sandbox, relative to the original source."""
        chunks = []
        for copy in sorted(self.root.rglob("*")):
            rel = copy.relative_to(self.root)
            if not copy.is_file() or copy.suffix not in TEXT_SUFFIXES or "__pycache__" in rel.parts:
                continue
            original = self.source / rel
            before = original.read_text(encoding="utf-8").splitlines(keepends=True) if original.exists() else []
            after = copy.read_text(encoding="utf-8").splitlines(keepends=True)
            if before != after:
                name = rel.as_posix()
                chunks.extend(difflib.unified_diff(before, after, f"a/{name}", f"b/{name}"))
        return "".join(chunks)
