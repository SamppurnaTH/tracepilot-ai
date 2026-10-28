import pytest

from app.sandbox import Sandbox, docker_available
from app.scenarios import SCENARIOS
from app.tools import Workspace

ORDERS = SCENARIOS["orders"]
ORDERS_TARGET = ORDERS.target


def open_seeded(scenario, isolation: str) -> Sandbox:
    """Open a sandbox for a scenario and replay its seed traffic, as an investigation does."""
    sb = Sandbox(scenario.target, isolation=isolation, app=scenario.app, logs=scenario.logs()).__enter__()
    if scenario.seed_requests():
        seeded = Workspace(sb).send_batch(scenario.seed_requests())
        assert isinstance(seeded, list), seeded
    return sb


@pytest.fixture
def sandbox():
    sb = open_seeded(ORDERS, "process")
    yield sb
    sb.__exit__(None, None, None)


@pytest.fixture
def ws(sandbox) -> Workspace:
    return Workspace(sandbox)


@pytest.fixture(scope="module")
def docker_sandbox():
    if not docker_available():
        pytest.skip("Docker is not available")
    sb = open_seeded(ORDERS, "docker")
    yield sb
    sb.__exit__(None, None, None)
