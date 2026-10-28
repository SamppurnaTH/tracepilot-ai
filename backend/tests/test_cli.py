"""Running TracePilot on an arbitrary project: app detection, plain-text logs, git-applicable patches, hand-off docs."""

import subprocess
from pathlib import Path

import pytest

from app.cli import detect_app, main
from app.handoff import markdown_report, pr_description
from app.sandbox import Sandbox
from app.tools import Workspace, parse_log, tools_for, INVESTIGATION_TOOLS
from conftest import ORDERS_TARGET

PLAIN_LOG = """2026-10-23 09:14:02,118 INFO worker: order 5512 promised 2026-10-24
2026-10-23 09:14:02,377 ERROR notify: failed to schedule courier for order 5512
Traceback (most recent call last):
  File "/srv/venv/lib/python3.11/site-packages/carrierkit/client.py", line 88, in book
    raise ValueError("no slots")
  File "/srv/shipping/notify.py", line 41, in schedule
    slot = carrier.book(promised)
ValueError: no slots on 2026-10-24
2026-10-23 11:40:51,004 ERROR notify: failed to schedule courier for order 5530
2026-10-23 11:41:00,000 WARN worker: retrying order 5530
"""


def test_detect_app_finds_fastapi_and_skips_tests(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "conftest.py").write_text("app = FastAPI()\n")
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc" / "main.py").write_text("from fastapi import FastAPI\n\napi: FastAPI = FastAPI(title='x')\n")
    assert detect_app(tmp_path) == "svc.main:api"
    assert detect_app(ORDERS_TARGET) == "orders_api.app:app"


def test_plain_text_logs_group_tracebacks_with_their_line():
    entries = parse_log(PLAIN_LOG)
    assert [e["level"] for e in entries] == ["INFO", "ERROR", "ERROR", "WARNING"]
    assert entries[1]["traceback"].startswith("Traceback") and "ValueError: no slots" in entries[1]["traceback"]


def test_user_logs_become_evidence_with_compact_tracebacks(tmp_path):
    log = tmp_path / "worker.log"
    log.write_text(PLAIN_LOG)
    with Sandbox(ORDERS_TARGET, isolation="process", logs=[log]) as sb:
        ws = Workspace(sb)
        errors = ws.read_log(level="ERROR")  # one log file: no service name needed
        assert errors["matched"] == 2
        assert "site-packages" not in errors["entries"][0]["traceback"]
        assert "/srv/shipping/notify.py:41 in schedule" in errors["entries"][0]["traceback"]
        digest = "\n".join(ws.log_digest())
        assert "ERROR x2: ERROR notify: failed to schedule courier for order #" in digest


def test_no_app_means_no_request_tool(tmp_path):
    names = {t["name"] for t in tools_for(None, INVESTIGATION_TOOLS)}
    assert "send_request" not in names and "read_log" in names
    with Sandbox(ORDERS_TARGET, isolation="process", app=None) as sb:
        assert "error" in Workspace(sb).send_batch([{"method": "GET", "path": "/"}])


def test_patch_applies_with_git_including_new_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text("x = 1\ny = 2")  # no final newline: needs git's marker
    git = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)  # noqa: E731
    git("init", "-q")
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "init")
    with Sandbox(repo, isolation="process", app=None) as sb:
        sb.edit_file("mod.py", "y = 2", "y = 3")
        (sb.root / "test_new.py").write_text("def test_y():\n    assert True\n")
        diff = sb.diff()
    assert "--- /dev/null" in diff
    patch = tmp_path / "fix.patch"
    patch.write_text(diff, newline="\n")
    git("apply", str(patch))
    assert (repo / "mod.py").read_text() == "x = 1\ny = 3" and (repo / "test_new.py").exists()


def test_handoff_documents_from_a_report():
    report = {
        "incident": "Friday orders are promised on Saturday.",
        "model": "muse-spark-1.3",
        "findings": {"summary": "Off by one.", "issues": [
            {"title": "Saturday counted", "severity": "high", "category": "correctness", "root_cause": "weekday() < 6",
             "evidence": ["delivery.py:22"], "fix": "use < 5", "hypothesis_ids": ["H1"]}]},  # fmt: skip
        "diff": "--- a/x.py\n+++ b/x.py\n",
        "verification": {"verified": True, "before": {"passed": 4, "failed": 1}, "after": {"passed": 5},
                         "fixed": ["tests/t.py::test_friday"], "regressions": [], "still_failing": []},  # fmt: skip
        "second_opinion": {"verdict": "approve", "model": "open", "confidence": "high", "summary": "Good.", "risks": []},
        "usage": {"model_calls": 3, "input_tokens": 10, "output_tokens": 5},
        "duration_s": 12.0,
    }
    md = markdown_report(report, "Friday orders")
    assert "Fix verified (tests 4/5 passing -> 5/5 passing, 0 regressions); independent review: approve" in md
    assert "```diff" in md and "**Root cause:** weekday() < 6" in md
    pr = pr_description(report)
    assert pr.startswith("Fix: Saturday counted") and "Now passing: `tests/t.py::test_friday`" in pr


@pytest.mark.parametrize("argv", [["investigate", "--repo", "does-not-exist", "--incident", "x"]])
def test_cli_rejects_a_missing_repo(argv, capsys):
    assert main(argv) == 2
    assert "not a directory" in capsys.readouterr().err
