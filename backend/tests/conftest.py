import subprocess
import sys

import pytest

from app.config import REPO_ROOT
from app.sandbox import Sandbox, docker_available
from app.tools import Workspace

SAMPLE_APP = REPO_ROOT / "sample_app"


@pytest.fixture(scope="session", autouse=True)
def fresh_logs():
    # Known synthetic logs in the source, copied into every sandbox.
    subprocess.run([sys.executable, str(REPO_ROOT / "demo" / "simulate_traffic.py")], check=True, capture_output=True)


@pytest.fixture
def sandbox():
    with Sandbox(SAMPLE_APP, isolation="process") as sb:
        yield sb


@pytest.fixture
def ws(sandbox) -> Workspace:
    return Workspace(sandbox)


@pytest.fixture(scope="module")
def docker_sandbox():
    if not docker_available():
        pytest.skip("Docker is not available")
    with Sandbox(SAMPLE_APP, isolation="docker") as sb:
        yield sb
