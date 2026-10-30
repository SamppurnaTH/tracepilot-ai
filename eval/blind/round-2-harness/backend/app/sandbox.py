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
import tomllib
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
    ".git", ".hg", "dist", "build", "target", ".gradle", ".idea", "*.egg-info", "*.log", "*.pyc", "*.class", "*.jar",
    "tracepilot-out",
)  # fmt: skip
# Maven's dependencies are baked into the project image, read-only, so runs never need the network.
M2_REPO = "/opt/m2"
# Resource limits per project kind: a JVM running Spring tests needs far more than a Python test run.
LIMITS = {"python": ("512m", "1", "128", "64m"), "maven": ("3g", "2", "1024", "512m")}
TEXT_SUFFIXES = {".py", ".md", ".ini", ".txt", ".json", ".toml", ".cfg", ".yaml", ".yml", ".sql", ".java", ".kt", ".xml", ".properties"}
MAX_COPY_FILES = 5000
# Build output and harness files inside the copy: never part of a patch, never listed to the model.
GENERATED_PARTS = {"__pycache__", ".pytest_cache", "target"}
HARNESS_FILES = {".tracepilot-surefire-excludes"}


def is_generated(rel: Path) -> bool:
    return bool(GENERATED_PARTS.intersection(rel.parts)) or rel.name in HARNESS_FILES
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


def detect_kind(source: Path) -> str:
    """Detect supported projects before building images or calling a model."""
    if (source / "pom.xml").is_file():
        return "maven"
    unsupported_root = any((source / name).is_file() for name in ("package.json", "go.mod", "Cargo.toml", "build.gradle", "build.gradle.kts"))
    python_root = any((source / name).is_file() for name in ("pyproject.toml", "setup.py", "requirements.txt", "pytest.ini")) or any((source / "tests").glob("test_*.py"))
    if (not unsupported_root or python_root) and any(p.is_file() and not is_generated(p.relative_to(source)) for p in source.rglob("*.py")):
        return "python"
    raise ValueError("Unsupported project: TracePilot supports Python with pytest or Java with Maven (pom.xml). Upload the service folder; Node, Go, Gradle and other build systems are not supported.")


def _build(tag: str, files: dict[str, Path | str], dockerfile: str, what: str) -> str:
    if _docker("image", "inspect", tag).returncode == 0:
        return tag
    with tempfile.TemporaryDirectory(prefix="tracepilot-image-") as ctx:
        for name, src in files.items():
            dest = Path(ctx) / name
            if isinstance(src, Path) and src.is_dir():
                shutil.copytree(src, dest, ignore=COPY_IGNORE)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(src if isinstance(src, str) else src.read_text(encoding="utf-8"), encoding="utf-8")
        (Path(ctx) / "Dockerfile").write_text(dockerfile, encoding="utf-8")
        build = _docker("build", "-t", tag, ctx, timeout=2400)
    if build.returncode != 0:
        raise RuntimeError(f"failed to {what}:\n{(build.stdout + build.stderr)[-3000:]}")
    return tag


def maven_image(source: Path) -> str:
    """A JDK + Maven image with the project's dependencies and test plugins downloaded, cached by pom.xml.

    The build compiles the project once (the only time the network is used) so that every plugin and
    surefire provider is in the local repository; the sources are discarded and only /opt/m2 is kept.
    """
    pom = (source / "pom.xml").read_text(encoding="utf-8")
    files: dict[str, Path | str] = {"pom.xml": pom}
    if (source / "src").is_dir():
        files["src"] = source / "src"
    # Surefire downloads its JUnit provider only when a test actually runs, so one trivial test runs at build time.
    files["src/test/java/TracePilotWarmupTest.java"] = "class TracePilotWarmupTest { @org.junit.jupiter.api.Test void warmup() {} }\n"
    dockerfile = (
        "FROM maven:3.9.9-eclipse-temurin-17\n"
        "RUN useradd --create-home --uid 10001 sandbox\n"
        "COPY . /build\n"
        f"RUN cd /build && mvn -B -q -Dmaven.repo.local={M2_REPO} test -Dtest=TracePilotWarmupTest "
        "-Dsurefire.failIfNoSpecifiedTests=false -DfailIfNoTests=false; "
        f"mvn -B -q -Dmaven.repo.local={M2_REPO} dependency:resolve-plugins dependency:go-offline; "
        f"rm -rf /build && chmod -R a+rX {M2_REPO}\n"
        "USER sandbox\nWORKDIR /workspace\n"
    )
    tag = f"tracepilot-sandbox-maven:{hashlib.sha256((pom + dockerfile).encode()).hexdigest()[:12]}"
    return _build(tag, files, dockerfile, "download the project's Maven dependencies into the sandbox image")


TEST_EXTRAS = ("test", "tests", "testing", "dev")
REQUIREMENT_FILES = ("requirements.txt", "requirements-test.txt", "requirements-dev.txt", "test-requirements.txt", "requirements/test.txt")


def python_requirements(source: Path) -> list[str]:
    """What a Python project needs to run its tests: requirements files, plus pyproject.toml's dependencies
    and its test or dev extras and dependency groups. The project itself is not installed; tests import it
    from the workspace (and from src/ in a src layout)."""
    reqs: list[str] = []
    for name in REQUIREMENT_FILES:
        path = source / name
        if path.is_file():
            # Plain requirements only: includes, constraints, editable installs and options need files we don't copy.
            reqs += [line.split(" #")[0].strip() for line in path.read_text(encoding="utf-8").splitlines()
                     if line.strip() and not line.lstrip().startswith(("#", "-", "."))]  # fmt: skip
    pyproject = source / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            data = {}
        project = data.get("project", {})
        reqs += project.get("dependencies", [])
        for extra in TEST_EXTRAS:
            reqs += project.get("optional-dependencies", {}).get(extra, [])
            # PEP 735 groups may include other groups as tables; only plain requirement strings are installable.
            reqs += [r for r in data.get("dependency-groups", {}).get(extra, []) if isinstance(r, str)]
    name = str(data.get("project", {}).get("name", "")).lower() if pyproject.is_file() else ""
    # A project's extras can name the project itself (e.g. "click[dev]"); that's the workspace copy, not a download.
    return list(dict.fromkeys(r for r in reqs if not name or not r.lower().replace("_", "-").startswith(name.replace("_", "-"))))


def project_image(source: Path, kind: str = "python") -> str:
    """The sandbox image for a project: the base image plus the project's own dependencies.

    Dependencies are installed once, at build time (the only time the network is used), and the image
    is cached by a hash of the dependency file. Investigations still run with no network.
    """
    if kind == "maven":
        return maven_image(source)
    ensure_image()
    reqs = python_requirements(source)
    if not reqs:
        return IMAGE
    text = "\n".join(reqs) + "\n"
    tag = f"tracepilot-sandbox-project:{hashlib.sha256(text.encode()).hexdigest()[:12]}"
    dockerfile = (
        f"FROM {IMAGE}\nUSER root\nCOPY requirements.txt /tmp/requirements.txt\n"
        "RUN pip install -r /tmp/requirements.txt pytest httpx && rm /tmp/requirements.txt\nUSER sandbox\n"
    )
    return _build(tag, {"requirements.txt": text}, dockerfile, "install the project's dependencies in the sandbox image")


class LocalRunner:
    isolation = "process"

    def __init__(self, root: Path):
        self.root = root
        self.env = {k: v for k, v in os.environ.items() if not any(m in k.upper() for m in SECRET_MARKERS)}
        self.env["PYTHONDONTWRITEBYTECODE"] = "1"
        if (root / "src").is_dir():  # src layout: tests import the package from the workspace, not an install
            self.env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(root / "src"), self.env.get("PYTHONPATH")]))

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def python(self, args: list[str], stdin: str | None, timeout: int) -> RunResult:
        return self.run([sys.executable, *args], stdin, timeout)

    def run(self, argv: list[str], stdin: str | None, timeout: int) -> RunResult:
        if argv[0] == "mvn" and not shutil.which("mvn"):
            return RunResult(127, "", "Maven is not installed; Java projects need Docker isolation")
        try:
            proc = subprocess.run(
                [shutil.which(argv[0]) or argv[0], *argv[1:]],
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

    def __init__(self, root: Path, image: str = IMAGE, kind: str = "python"):
        self.root = root
        self.image = image
        self.limits = LIMITS.get(kind, LIMITS["python"])
        self.name = f"tracepilot-sbx-{uuid.uuid4().hex[:10]}"

    def start(self) -> None:
        if self.image == IMAGE:
            ensure_image()
        memory, cpus, pids, tmp = self.limits
        run = _docker(
            "run", "-d", "--rm",
            "--name", self.name,
            "--network", "none",
            "--read-only",
            "--tmpfs", f"/tmp:rw,exec,size={tmp}",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", pids,
            "--memory", memory,
            "--cpus", cpus,
            "-e", "HOME=/tmp",
            *(["-e", "PYTHONPATH=/workspace/src"] if (self.root / "src").is_dir() else []),
            "-v", f"{self.root}:/workspace:rw",
            self.image, "sleep", "infinity",
        )  # fmt: skip
        if run.returncode != 0:
            raise RuntimeError(f"failed to start sandbox container: {run.stderr.strip()}")

    def stop(self) -> None:
        _docker("rm", "-f", self.name, timeout=30)

    def python(self, args: list[str], stdin: str | None, timeout: int) -> RunResult:
        return self.run(["python", *args], stdin, timeout)

    def run(self, argv: list[str], stdin: str | None, timeout: int) -> RunResult:
        try:
            proc = _docker("exec", "-i", self.name, *argv, stdin=stdin, timeout=timeout)
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
        kind: str = "python",
        test_scope: list[str] | None = None,
        test_args: list[str] | None = None,
    ):
        if isolation not in {"auto", "docker", "process"}:
            raise ValueError("isolation must be 'auto', 'docker' or 'process'")
        self.source = source.resolve()
        self.requested_isolation = isolation
        self.app = app  # "module:attribute" of an ASGI app to send requests to, or None
        self.logs = logs or []
        self.image = image
        self.kind = kind  # "python" (pytest) or "maven" (JUnit via Maven)
        # The tests that define "green" (e.g. the classes CI runs), and extra test-runner flags. None = whole suite.
        self.test_scope = test_scope
        self.test_args = test_args or []
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
        self.runner = DockerRunner(self.root, self.image, self.kind) if use_docker else LocalRunner(self.root)
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

    def run(self, argv: list[str], stdin: str | None = None, timeout: int = 120) -> RunResult:
        if self.runner is None:
            raise RuntimeError("sandbox is not open")
        return self.runner.run(argv, stdin, timeout)

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
            if not copy.is_file() or copy.suffix not in TEXT_SUFFIXES or is_generated(rel):
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
