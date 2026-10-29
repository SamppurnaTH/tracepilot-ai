"""A user-requested --apply must not apply a test-green patch with known review objections."""
from app import cli


def test_unresolved_review_blocks_apply_and_ci_success(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "project"
    repo.mkdir()
    (repo / "app.py").write_text("x = 1\n")
    report = {"incident": "x is wrong", "model": "fake", "findings": {"summary": "partial fix", "issues": []},
              "diff": "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n",
              "verification": {"verified": True, "before": {"failed": 1}, "after": {"passed": 1}, "fixed": ["bug"], "still_failing": [], "regressions": []},
              "second_opinion": {"verdict": "concerns", "model": "reviewer", "confidence": "high", "summary": "Valid input hangs", "risks": ["loop"]},
              "outcome": "needs_review", "usage": {"input_tokens": 10, "output_tokens": 5, "model_calls": 1}, "duration_s": 1}
    class ScriptedInvestigation:
        events = []
        def __init__(self, *args, **kwargs):
            pass
        def run(self):
            return report
    monkeypatch.setattr(cli, "Investigation", ScriptedInvestigation)
    monkeypatch.setattr(cli.Reviewer, "from_env", lambda: None)
    def no_git(*args, **kwargs):
        raise AssertionError("git apply must not run while review is unresolved")
    monkeypatch.setattr(cli.subprocess, "run", no_git)
    result = cli.main(["investigate", "--repo", str(repo), "--incident", "x is wrong", "--isolation", "process", "--apply", "--out", str(tmp_path / "output")])
    assert result == 1 and (repo / "app.py").read_text() == "x = 1\n"
    assert "Not applying: resolve the reviewer's concerns" in capsys.readouterr().out
