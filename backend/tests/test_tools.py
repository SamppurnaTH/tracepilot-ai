import json
import subprocess
import sys

import pytest

from app.config import REPO_ROOT
from app.tools import Workspace, execute_tool

SAMPLE_APP = REPO_ROOT / "sample_app"


@pytest.fixture(scope="module")
def ws() -> Workspace:
    # Fresh synthetic logs so read_log has known content.
    subprocess.run([sys.executable, "simulate_traffic.py"], cwd=SAMPLE_APP, check=True, capture_output=True)
    return Workspace(SAMPLE_APP)


def call(ws: Workspace, name: str, **args) -> dict:
    return json.loads(execute_tool(ws, name, json.dumps(args)))


# --- read_log -------------------------------------------------------------


def test_read_log_filters_errors(ws):
    result = call(ws, "read_log", level="ERROR")
    assert result["matched"] == 2
    assert all(e["status"] == 500 for e in result["entries"])
    assert "TypeError" in result["entries"][0]["error"]


def test_read_log_scrubs_local_paths(ws):
    text = json.dumps(call(ws, "read_log", level="ERROR"))
    assert str(REPO_ROOT) not in text
    assert str(REPO_ROOT).replace("\\", "\\\\") not in text


def test_read_log_rejects_bad_service_name(ws):
    assert "error" in call(ws, "read_log", service="../../etc/passwd")


# --- read_file ------------------------------------------------------------


def test_read_file_returns_numbered_lines(ws):
    result = call(ws, "read_file", path="orders_api/app.py", start_line=1, end_line=3)
    assert result["lines"].startswith("1-3")
    assert result["content"].splitlines()[0].strip().startswith("1")


def test_read_file_lists_directory(ws):
    files = call(ws, "read_file", path=".")["files"]
    assert "orders_api/app.py" in files
    assert "tests/test_orders.py" in files


@pytest.mark.parametrize("path", ["../.env", "../backend/app/config.py", "..", "C:/Windows/win.ini"])
def test_read_file_blocks_escape(ws, path):
    assert "error" in call(ws, "read_file", path=path)


def test_read_file_blocks_env_inside_workspace(ws, tmp_path):
    (tmp_path / ".env").write_text("MODEL_API_KEY=secret")
    assert "error" in call(Workspace(tmp_path), "read_file", path=".env")


# --- send_request ---------------------------------------------------------


def test_send_request_reproduces_500(ws):
    result = call(ws, "send_request", method="GET", path="/orders/9/total", headers={"Authorization": "Bearer token-bob"})
    assert result["status"] == 500


def test_send_request_shows_idor(ws):
    result = call(ws, "send_request", method="GET", path="/orders/7", headers={"Authorization": "Bearer token-bob"})
    assert result["status"] == 200
    assert result["body"]["owner_id"] == 1


@pytest.mark.parametrize("path", ["http://example.com/", "orders/7"])
def test_send_request_rejects_external_or_bad_paths(ws, path):
    assert "error" in call(ws, "send_request", method="GET", path=path)


# --- run_tests ------------------------------------------------------------


def test_run_tests_reports_planted_failures(ws):
    result = call(ws, "run_tests")
    assert result["exit_code"] == 1
    assert "2 failed" in result["summary"] and "3 passed" in result["summary"]


def test_run_tests_single_node(ws):
    result = call(ws, "run_tests", selector="tests/test_orders.py::test_total_with_coupon")
    assert result["exit_code"] == 0


@pytest.mark.parametrize("selector", ["../backend", "tests; rm -rf /", "-k x"])
def test_run_tests_rejects_unsafe_selector(ws, selector):
    assert "error" in call(ws, "run_tests", selector=selector)


# --- dispatcher -----------------------------------------------------------


def test_unknown_tool(ws):
    assert "error" in call(ws, "rm_rf")


def test_private_methods_are_not_tools(ws):
    assert "error" in call(ws, "_resolve", rel_path="..")
