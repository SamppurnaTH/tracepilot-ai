"""Validate split/provenance logic without model calls or running downloaded code on the host."""
import importlib.util
import json
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("research", SCRIPTS / "research.py")
research = importlib.util.module_from_spec(spec)
spec.loader.exec_module(research)


def test_external_split_never_copies_hidden_or_reference_into_project():
    manifest = research.check_manifest()
    assert manifest["repeats"] == 2 and len(manifest["cases"]) == 6
    for name in manifest["cases"]:
        rows = research.rows_for(name)
        public = research.test_code(name, rows[:2])
        marker = "CASES = json.loads("
        # Parse only the literal data in the adapter; never execute imported algorithm code.
        import ast
        call = ast.parse(public).body[3].value
        assert isinstance(call, ast.Call) and json.loads(ast.literal_eval(call.args[0])) == rows[:2]
        assert marker in public and len(rows[2:]) >= 3
        if research.project(name).exists():
            assert not (research.project(name) / "tests/test_heldout.py").exists()
            assert not (research.project(name) / "correct_python_programs").exists()


def test_pairing_does_not_compare_unmatched_runs():
    import sys
    sys.path.insert(0, str(SCRIPTS))
    from research_summary import contrast
    def row(case, condition, tokens, success=True):
        return {"case": case, "condition": condition, "model": "model", "repeat": 1, "heldout_pass": success,
                "usage": {"input_tokens": tokens}, "reviewer_tokens": 0, "duration_s": 10}
    rows = [row("a", "full", 50), row("a", "plain", 100), row("unmatched", "full", 999)]
    result = contrast(rows, "model", "full", "plain")
    assert result["pairs"] == 1 and result["effects"]["tokens"]["effect"] == .5
    rows[0]["heldout_pass"] = False
    assert contrast(rows, "model", "full", "plain", successful_only=True) == {"pairs": 0}


def test_minimal_reference_preserves_upstream_executable_function():
    import ast
    for name in research.CASES:
        original = (research.VENDOR / "python_programs" / f"{name}.py").read_text()
        gold = (research.VENDOR / "correct_python_programs" / f"{name}.py").read_text()
        minimal = research.minimal_reference(name)
        gold_fn = next(n for n in ast.parse(gold).body if isinstance(n, ast.FunctionDef))
        minimal_fn = next(n for n in ast.parse(minimal).body if isinstance(n, ast.FunctionDef))
        assert ast.dump(gold_fn) == ast.dump(minimal_fn)
        original_fn = next(n for n in ast.parse(original).body if isinstance(n, ast.FunctionDef))
        assert "".join(original.splitlines(keepends=True)[original_fn.end_lineno:]) in minimal


def test_measured_harness_snapshot_matches_recorded_fingerprints():
    snapshot = research.BASE / "harness-snapshot/backend/app"
    rows = [json.loads(path.read_text()) for path in (research.BASE / "observations").glob("*.json")]
    assert rows
    for row in rows:
        for name, expected in row.get("harness_sha256_lf", {}).items():
            assert research.digest(snapshot / name) == expected
