"""Sandbox guarantees: the original is never touched, edits are verifiable, and code can't escape."""

import json

import pytest

from app.sandbox import Sandbox
from app.tools import Workspace
from conftest import ORDERS_TARGET as SAMPLE_APP

COUPON_BUG = 'discount = subtotal * order["coupon"]["percent"] / 100'
COUPON_FIX = 'discount = subtotal * (order["coupon"] or {}).get("percent", 0) / 100'
IDOR_BUG = "    order = get_order_or_404(order_id)\n    return order\n"
IDOR_FIX = (
    "    order = get_order_or_404(order_id)\n"
    '    if order["owner_id"] != user["id"]:\n'
    '        raise HTTPException(status_code=404, detail="order not found")\n'
    "    return order\n"
)


def test_copy_is_isolated_and_removed():
    original = (SAMPLE_APP / "orders_api" / "app.py").read_text(encoding="utf-8")
    with Sandbox(SAMPLE_APP, isolation="process") as sb:
        root = sb.root
        assert root != SAMPLE_APP and (root / "orders_api" / "app.py").exists()
        assert sb.edit_file("orders_api/app.py", COUPON_BUG, COUPON_FIX) == {"edited": "orders_api/app.py"}
    assert (SAMPLE_APP / "orders_api" / "app.py").read_text(encoding="utf-8") == original
    assert not root.exists()


def test_fixes_verified_by_tests(sandbox):
    ws = Workspace(sandbox)
    assert ws.run_tests()["exit_code"] == 1
    sandbox.edit_file("orders_api/app.py", COUPON_BUG, COUPON_FIX)
    sandbox.edit_file("orders_api/app.py", IDOR_BUG, IDOR_FIX)
    result = ws.run_tests()
    assert result["exit_code"] == 0, result["output"]
    assert "5 passed" in result["summary"]
    diff = sandbox.diff()
    assert "-    " + COUPON_BUG in diff and "+    " + COUPON_FIX in diff


def test_send_request_sees_patched_code(sandbox):
    ws = Workspace(sandbox)
    req = {"method": "GET", "path": "/orders/9/total", "headers": {"Authorization": "Bearer token-bob"}}
    assert ws.send_request(**req)["status"] == 500
    sandbox.edit_file("orders_api/app.py", COUPON_BUG, COUPON_FIX)
    assert ws.send_request(**req) == {"status": 200, "body": {"order_id": 9, "total": 120.0}}


@pytest.mark.parametrize(
    "old, expected",
    [("this text does not exist", "not found"), ("order_id", "times")],
)
def test_edit_requires_unique_match(sandbox, old, expected):
    assert expected in sandbox.edit_file("orders_api/app.py", old, "x")["error"]


@pytest.mark.parametrize("path", ["../outside.py", "../../backend/app/config.py", ".env"])
def test_edit_blocks_escape_and_secrets(sandbox, path):
    with pytest.raises(PermissionError):
        sandbox.edit_file(path, "a", "b")


def test_secrets_not_visible_to_sandboxed_code(sandbox, monkeypatch):
    code = "import os, json; print(json.dumps(sorted(k for k in os.environ if 'KEY' in k.upper())))"
    assert json.loads(sandbox.python(["-c", code]).stdout) == []


def test_timeout_is_enforced(sandbox):
    result = sandbox.python(["-c", "import time; time.sleep(10)"], timeout=2)
    assert result.timed_out


# --- Docker isolation -----------------------------------------------------


def test_docker_runs_tests(docker_sandbox):
    assert docker_sandbox.isolation == "docker"
    result = Workspace(docker_sandbox).run_tests()
    assert "2 failed" in result["summary"] and "3 passed" in result["summary"]


def test_docker_has_no_network(docker_sandbox):
    code = "import socket; socket.create_connection(('1.1.1.1', 53), timeout=3)"
    result = docker_sandbox.python(["-c", code], timeout=20)
    assert result.exit_code != 0
    assert "Network is unreachable" in result.stderr or "OSError" in result.stderr


def test_docker_root_filesystem_is_read_only(docker_sandbox):
    result = docker_sandbox.python(["-c", "open('/etc/tracepilot', 'w')"], timeout=20)
    assert result.exit_code != 0


def test_docker_runs_as_non_root(docker_sandbox):
    assert docker_sandbox.python(["-c", "import os; print(os.getuid())"], timeout=20).stdout.strip() == "10001"


def test_docker_send_request(docker_sandbox):
    ws = Workspace(docker_sandbox)
    result = ws.send_request("GET", "/orders/7", headers={"Authorization": "Bearer token-bob"})
    assert result["status"] == 200


def test_python_requirements_reads_pyproject_extras_groups_and_files(tmp_path):
    from app.sandbox import python_requirements

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "My_Lib"\ndependencies = ["attrs>=23"]\n'
        '[project.optional-dependencies]\ntest = ["pytest-mock", "my-lib[extra]"]\ndocs = ["sphinx"]\n'
        '[dependency-groups]\ndev = ["hypothesis", {include-group = "test"}]\n',
        encoding="utf-8",
    )
    (tmp_path / "requirements-test.txt").write_text("pretend  # comment\n-r other.txt\n-e .\nattrs>=23\n", encoding="utf-8")
    reqs = python_requirements(tmp_path)
    # Test and dev needs are installed; docs extras, includes, editable installs and the project itself are not.
    assert reqs == ["pretend", "attrs>=23", "pytest-mock", "hypothesis"]


def test_src_layout_is_importable_without_installing(tmp_path):
    from app.sandbox import Sandbox

    (tmp_path / "src" / "mylib").mkdir(parents=True)
    (tmp_path / "src" / "mylib" / "__init__.py").write_text("VALUE = 42\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "mylib"\n', encoding="utf-8")
    with Sandbox(tmp_path, isolation="process", app=None) as sb:
        result = sb.python(["-c", "import mylib; print(mylib.VALUE)"])
    assert result.stdout.strip() == "42"
