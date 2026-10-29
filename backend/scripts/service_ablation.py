"""Focused, separately specified service-domain check of the evidence-brief confound."""
import concurrent.futures
import hashlib
import json
import random
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend/scripts"))
from app.agent import Investigation  # noqa: E402
from app.baseline import PlainAgent  # noqa: E402
from app.llm import get_client  # noqa: E402
from app.reviewer import Reviewer  # noqa: E402
from app.sandbox import Sandbox  # noqa: E402
from app.scenarios import SCENARIOS  # noqa: E402
from app.tools import Workspace  # noqa: E402
from research import save, digest, CONDITIONS  # noqa: E402

BASE = ROOT / "eval/service-ablation"
CASES = ["orders", "inventory"]


def freeze():
    dest = BASE / "manifest.json"
    if dest.exists():
        return
    files = [*[(ROOT / "eval/hidden" / f"{case}.py") for case in CASES], ROOT / "backend/app/scenarios.py"]
    for case in CASES:
        files.extend(p for p in SCENARIOS[case].target.rglob("*.py") if "__pycache__" not in p.parts)
    save(dest, {"frozen_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "cases": CASES, "model": "muse-spark-1.3",
                "conditions": CONDITIONS, "repeats": 2, "expected": 16, "seed": 20261031, "max_workers": 2,
                "investigator_token_budget": 400000, "rationale": "Orders starts with failing tests; Inventory starts green. Test the original service-domain brief question, without replacing external-study results.",
                "oracle_provenance": "Original project-authored hidden tests, not independent-source tests",
                "files_sha256_lf": {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(set(files))},
                "latency_limit": "Runs overlap on shared infrastructure. No isolated latency or dollar-cost inference.",
                "budget_limit": "Same production token threshold/base phase budgets; full workflow may add reproduction, verification and review retry rounds."})


def check():
    manifest = json.loads((BASE / "manifest.json").read_text())
    for file, value in manifest["files_sha256_lf"].items():
        assert digest(ROOT / file) == value, file
    return manifest


def score(case, diff):
    with Sandbox(SCENARIOS[case].target, isolation="docker", app=None) as sandbox:
        if diff:
            patch = sandbox.root / ".score.patch"
            patch.write_text(diff, encoding="utf-8", newline="\n")
            applied = subprocess.run(["git", "apply", "--whitespace=nowarn", str(patch)], cwd=sandbox.root, capture_output=True, text=True)
            patch.unlink()
            if applied.returncode:
                return {"heldout_pass": False, "score_error": "patch did not apply", "heldout_tests": {}}
        sandbox.resolve("tests/test_service_oracle.py").write_text((ROOT / "eval/hidden" / f"{case}.py").read_text(), encoding="utf-8")
        workspace = Workspace(sandbox)
        outcomes, reasons = workspace.test_report("tests/test_service_oracle.py")
        if not outcomes:
            time.sleep(1)
            outcomes, reasons = workspace.test_report("tests/test_service_oracle.py")
        return {"heldout_pass": bool(outcomes) and all(value == "passed" for value in outcomes.values()),
                "score_error": None if outcomes else "no test outcomes", "heldout_tests": outcomes, "heldout_reasons": reasons}


def one(job):
    case, condition, repeat = job
    key = f"{case}__muse-spark-1.3__{condition}__{repeat}"
    path = BASE / "observations" / f"{key}.json"
    if path.exists():
        return
    sc = SCENARIOS[case]
    client, model = get_client("meta")
    result = {"id": key, "case": case, "model": model, "condition": condition, "repeat": repeat, "error": None,
              "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    klass = PlainAgent if condition.startswith("plain") else Investigation
    agent = klass(sc.incident, sc.target, client=client, model=model, isolation="docker", app=sc.app, seed_requests=sc.seed_requests(),
                  logs=sc.logs(), images=sc.screenshot_paths(), include_brief=condition in ("plain_brief", "tracepilot"),
                  reviewer=Reviewer.from_env() if klass is Investigation else None)
    try:
        report = agent.run()
        save(BASE / "traces" / f"{key}.json", report)
        result.update({"diff": report["diff"], "usage": report["usage"], "reviewer_tokens": (report.get("second_opinion") or {}).get("tokens", 0) or 0,
                       "duration_s": report["duration_s"], "claimed_fixed": report.get("claimed_fixed", bool(report.get("verification", {}).get("verified")))})
        result.update(score(case, report["diff"]))
    except Exception as exc:
        result.update({"error": f"{type(exc).__name__}: {exc}"[:500], "heldout_pass": False, "score_error": None,
                       "usage": agent.usage, "reviewer_tokens": 0, "duration_s": None, "claimed_fixed": False})
        save(BASE / "traces" / f"{key}.json", {"error": result["error"], "events": agent.events})
    result["false_success"] = bool(result["claimed_fixed"] and not result["heldout_pass"] and not result["score_error"])
    save(path, result)
    print(key, "heldout=", result["heldout_pass"], "error=", result["error"], flush=True)


def main():
    if "--freeze" in sys.argv:
        freeze()
        return
    manifest = check()
    jobs = [(case, cond, rep) for case in CASES for cond in CONDITIONS for rep in (1, 2)]
    random.Random(manifest["seed"]).shuffle(jobs)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(one, jobs))


if __name__ == "__main__":
    main()
