"""Study bookkeeping must retain crashes and prevent score-seeking retries; no inference."""

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def study(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts" / "blind_study.py"
    spec = importlib.util.spec_from_file_location("blind_study_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "OUT", tmp_path)
    monkeypatch.setattr(module, "OBSERVATIONS", tmp_path / "observations.jsonl")
    monkeypatch.setattr(module, "CASES", [{"id": "first"}, {"id": "second"}])
    monkeypatch.setattr(module, "git", lambda *a, **kw: "test-commit")
    (tmp_path / "manifest.json").write_text(json.dumps([{"id": name, "target_tests": ["test_bug"]} for name in ("first", "second")]))
    return module


def test_runner_keeps_exit_and_continues_without_retry(study, monkeypatch):
    attempts = []

    def investigate(case, entry):
        attempts.append(case["id"])
        if case["id"] == "first":
            raise SystemExit(4)
        return {"id": case["id"], "result": "fixed"}

    monkeypatch.setattr(study, "investigate", investigate)
    monkeypatch.setattr(study, "summarize", lambda: None)
    study.run(None)
    rows = [json.loads(line) for line in study.OBSERVATIONS.read_text().splitlines()]
    assert rows[0]["result"] == "error" and "SystemExit: 4" in rows[0]["error"]
    assert rows[1]["result"] == "fixed"
    assert all(row["round"] == 2 for row in rows)
    preserved = study.OBSERVATIONS.read_bytes()
    study.run(None)
    assert attempts == ["first", "second"]
    assert study.OBSERVATIONS.read_bytes() == preserved


def test_interrupted_attempt_cannot_be_silently_restarted(study):
    (study.OUT / "round-2" / "first").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="do not silently rerun"):
        study.run(None)


def test_prepared_oracle_cannot_be_overwritten(study):
    with pytest.raises(RuntimeError, match="preserve it"):
        study.prepare()


def test_summary_keeps_rounds_separate(study):
    study.OBSERVATIONS.write_text("\n".join(json.dumps(row) for row in [
        {"id": "first", "result": "not fixed"},
        {"id": "first", "round": 2, "result": "fixed"},
        {"id": "second", "round": 2, "result": "error", "error": "SystemExit: 4"},
    ]))
    study.summarize()
    result = (study.OUT / "RESULTS.md").read_text(encoding="utf-8")
    assert "## Round 1" in result and "## Round 2" in result
    assert "0/1 recorded cases fixed" in result and "1/2 recorded cases fixed" in result
    assert "Round 2, second: SystemExit: 4" in result
