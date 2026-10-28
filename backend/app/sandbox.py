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
import hashlib
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
# Logs are not copied: each investigation seeds fresh logs inside its own sandbox, or is given
# the user's log files explicitly. Secrets, VCS data, caches and build output never enter the copy.
COPY_IGNORE = shutil.ignore_patterns(
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".env*", ".venv", "venv", "node_modules",
    ".git", ".hg", "dist", "build", "*.egg-info", "*.log", "*.pyc", "tracepilot-out",
)  # fmt: skip
TEXT_SUFFIXES = {".py", ".md", ".ini", ".txt", ".json", ".toml", ".cfg", ".yaml", ".yml", ".sql"}
MAX_COPY_FILES = 5000
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


def project_image(source: Path) -> str:
    """The sandbox image for a project: the base image plus the project's requirements.txt, if it has one.

    Dependencies are installed once, at build time (the only time the network is used), and the image
    is cached by the requirements' hash. Investigations still run with no network.
    """
    ensure_image()
    requirements = source / "requirements.txt"
    if not requirements.is_file():
        return IMAGE
    text = requirements.read_text(encoding="utf-8")
    tag = f"tracepilot-sandbox-project:{hashlib.sha256(text.encode()).hexdigest()[:12]}"
    if _docker("image", "inspect", tag).returncode == 0:
        return tag
    with tempfile.TemporaryDirectory(prefix="tracepilot-image-") as ctx:
        (Path(ctx) / "requirements.txt").write_text(text, encoding="utf-8")
        (Path(ctx) / "Dockerfile").write_text(
            f"FROM {IMAGE}\nUSER root\nCOPY requirements.txt /tmp/requirements.txt\n"
            "RUN pip install -r /tmp/requirements.txt pytest httpx && rm /tmp/requirements.txt\nUSER sandbox\n",
            encoding="utf-8",
        )
        build = _docker("build", "-t", tag, ctx, timeout=1800)
    if build.returncode != 0:
        raise RuntimeError(f"failed to install the project's requirements.txt in the sandbox image:\n{build.stderr[-2000:]}")
    return tag


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

    def __init__(self, root: Path, image: str = IMAGE):
        self.root = root
        self.image = image
        self.name = f"tracepilot-sbx-{uuid.uuid4().hex[:10]}"

    def start(self) -> None:
        if self.image == IMAGE:
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
            self.image, "sleep", "infinity",
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

    def __init__(
        self,
        source: Path,
        isolation: str = "auto",
        app: str | None = "orders_api.app:app",
        logs: list[Path] | None = None,
        image: str = IMAGE,
    ):
        if isolation not in {"auto", "docker", "process"}:
            raise ValueError("isolation must be 'auto', 'docker' or 'process'")
        self.source = source.resolve()
        self.requested_isolation = isolation
        self.app = app  # "module:attribute" of an ASGI app to send requests to, or None
        self.logs = logs or []
        self.image = image
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
        if not self.source.is_dir():
            raise ValueError(f"not a directory: {self.source}")
        self._tmp = Path(tempfile.mkdtemp(prefix="tracepilot-"))
        shutil.copytree(self.source, self.root, ignore=COPY_IGNORE)
        if sum(1 for _ in self.root.rglob("*")) > MAX_COPY_FILES:
            shutil.rmtree(self._tmp, ignore_errors=True)
            self._tmp = None
            raise ValueError(f"the project has more than {MAX_COPY_FILES} files; point TracePilot at the service's own folder")
        if self.logs:
            # The user's log files are evidence: they go in logs/, where read_log looks for them.
            (self.root / "logs").mkdir(exist_ok=True)
            for log in self.logs:
                shutil.copyfile(log, self.root / "logs" / (log.stem + ".log"))
        # The container runs as a non-root user; let it write logs inside its own copy.
        for path in [self.root, *self.root.rglob("*")]:
            path.chmod(path.stat().st_mode | stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)

        use_docker = self.requested_isolation == "docker" or (
            self.requested_isolation == "auto" and docker_available()
        )
        self.runner = DockerRunner(self.root, self.image) if use_docker else LocalRunner(self.root)
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
                # git apply needs /dev/null for new files and an explicit marker for a missing final newline.
                lines = difflib.unified_diff(before, after, f"a/{name}" if original.exists() else "/dev/null", f"b/{name}")
                chunks.extend(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in lines)
        return "".join(chunks)
