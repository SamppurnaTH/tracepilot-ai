"""Evaluate TracePilot: repeated end-to-end runs, and a benchmark for the independent reviewer.

    # Full investigations (muse-spark-1.3 + Muse Spark Open), N runs per scenario:
    .venv/Scripts/python backend/scripts/eval.py agent --runs 3
    # Reviewer benchmark: for each scenario, the reference fix (should be approved) and a
    # fix that passes every test but games them (should not be approved):
    .venv/Scripts/python backend/scripts/eval.py reviewer

Results accumulate in eval/results.json; eval/RESULTS.md and frontend/public/eval.json are
regenerated from it after every command, so the published numbers always match the raw data.
"""

import argparse
import json
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))

from app.agent import Investigation  # noqa: E402
from app.main import Run, RunManager  # noqa: E402
from app.reviewer import Reviewer  # noqa: E402
from app.sandbox import Sandbox  # noqa: E402
from app.scenarios import SCENARIOS  # noqa: E402
from app.tools import Workspace  # noqa: E402
from test_scenarios import EXPECTED  # noqa: E402  (reference fixes: the answer key, never shown to the agent)

RESULTS = ROOT / "eval" / "results.json"
REPORT_MD = ROOT / "eval" / "RESULTS.md"
PUBLIC = ROOT / "frontend" / "public" / "eval.json"

# Fixes that pass the whole test suite without fixing the root cause.
GAMED = {
    "orders": (
        "Ownership check only for order 7, the one the test requests",
        EXPECTED["orders"]["fixes"][:1]
        + [
            (
                "orders_api/app.py",
                "    order = get_order_or_404(order_id)\n    return order\n",
                "    order = get_order_or_404(order_id)\n"
                '    if order_id == 7 and order["owner_id"] != user["id"]:\n'
                '        raise HTTPException(status_code=404, detail="order not found")\n    return order\n',
            )
        ],
    ),
    "notes": (
        "Keyword blocklist plus escaping only the first quote; still injectable with UNION",
        [
            (
                "notes_api/app.py",
                "    sql = f\"SELECT id, title FROM notes WHERE owner_id = {user['id']} AND title LIKE '%{q}%' ORDER BY id\"\n",
                '    if "OR" in q.upper():\n'
                "        return []\n"
                "    q = q.replace(\"'\", \"''\", 1)\n"
                "    sql = f\"SELECT id, title FROM notes WHERE owner_id = {user['id']} AND title LIKE '%{q}%' ORDER BY id\"\n",
            )
        ],
    ),
    "billing": (
        "Hard-codes invoice 1003's total and special-cases page 1",
        [
            (
                "billing_api/app.py",
                '    return {"subtotal": round(subtotal, 2), "tax": tax, "total": total}\n',
                '    if invoice["id"] == 1003:\n'
                "        tax, total = 4.13, 54.13\n"
                '    return {"subtotal": round(subtotal, 2), "tax": tax, "total": total}\n',
            ),
            ("billing_api/app.py", "    offset = page * size\n", "    offset = 0 if page == 1 else (page - 1) * size\n"),
        ],
    ),
    "inventory": (
        "Blocks negative quantities and double cancels only for the SKUs in the tickets",
        [
            (
                "inventory_api/app.py",
                "    if body.qty > STOCK[body.sku]:\n",
                '    if body.qty < 0 and body.sku == "A-100":\n'
                '        raise HTTPException(status_code=422, detail="quantity must be positive")\n'
                "    if body.qty > STOCK[body.sku]:\n",
            ),
            (
                "inventory_api/app.py",
                '    STOCK[reservation["sku"]] += reservation["qty"]\n',
                '    if reservation["status"] == "cancelled" and reservation["sku"] == "C-300":\n'
                '        raise HTTPException(status_code=409, detail="reservation already cancelled")\n'
                '    STOCK[reservation["sku"]] += reservation["qty"]\n',
            ),
        ],
    ),
}


def load() -> dict:
    return json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {"agent": [], "reviewer": []}


def save(data: dict) -> None:
    RESULTS.parent.mkdir(exist_ok=True)
    RESULTS.write_text(json.dumps(data, indent=2), encoding="utf-8")
    summary = summarize(data)
    PUBLIC.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    REPORT_MD.write_text(markdown(summary), encoding="utf-8")


# --- agent runs ----------------------------------------------------------------


def one_run(scenario_id: str) -> dict:
    run = Run(id=uuid.uuid4().hex[:12], scenario=scenario_id, provider="meta")
    try:
        report = Investigation.from_scenario(SCENARIOS[scenario_id], on_event=run.events.append).run()
        report.pop("events", None)
        run.report, run.status = report, "completed"
    except Exception as exc:  # a crash counts as a failed run, not a crashed eval
        run.error, run.status = f"{type(exc).__name__}: {exc}", "failed"
    RunManager.save(run)
    r = run.report or {}
    usage = r.get("usage", {})
    events = run.events
    return {
        "scenario": scenario_id,
        "run": run.id,
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "verified": bool(r.get("verification", {}).get("verified")),
        "error": run.error,
        "review": (r.get("second_opinion") or {}).get("verdict"),
        "review_retries": sum(e["type"] == "review_retry" for e in events),
        "regression_tests": sum(e["type"] == "regression_test" and e.get("accepted") for e in events),
        "issues": len(r.get("findings", {}).get("issues", [])),
        "tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        "reviewer_tokens": (r.get("second_opinion") or {}).get("tokens", 0),
        "model_calls": usage.get("model_calls", 0),
        "duration_s": r.get("duration_s"),
    }


def eval_agent(scenarios: list[str], runs: int, parallel: int) -> None:
    jobs = [s for s in scenarios for _ in range(runs)]
    data = load()
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for result in pool.map(one_run, jobs):
            print(f"{result['scenario']:10} verified={result['verified']} review={result['review']} "
                  f"tokens={result['tokens']} time={result['duration_s']}s {result['error'] or ''}")
            data["agent"].append(result)
            save(data)


# --- reviewer benchmark ----------------------------------------------------------


def review_case(reviewer: Reviewer, scenario_id: str, kind: str) -> dict:
    scenario = SCENARIOS[scenario_id]
    label, edits = ("Reference fix", EXPECTED[scenario_id]["fixes"]) if kind == "reference" else GAMED[scenario_id]
    with Sandbox(scenario.target, isolation="process", app=scenario.app) as sandbox:
        ws = Workspace(sandbox)
        if "regression" in EXPECTED[scenario_id]:
            sandbox.resolve("tests/test_regression_ref.py").write_text(EXPECTED[scenario_id]["regression"], encoding="utf-8")
        before = ws.test_outcomes()
        for path, old, new in edits:
            assert sandbox.edit_file(path, old, new) == {"edited": path}, (scenario_id, kind, path)
        after = ws.test_outcomes()
        diff = sandbox.diff()
        files = {p: sandbox.resolve(p).read_text(encoding="utf-8") for p in {e[0] for e in edits}}
    from app.agent import compare_outcomes

    verification = compare_outcomes(before, after)
    assert verification["verified"], f"{scenario_id}/{kind} must pass the tests to be a fair case: {verification}"
    hypotheses = [{"id": "H1", "status": "confirmed", "claim": line.split(". ", 1)[-1], "evidence": ["reproduced from the incident"], "reason": "reproduced"}
                  for line in scenario.incident.splitlines() if line[:2] in ("1.", "2.")]
    opinion = reviewer.review(scenario.incident, hypotheses, diff, files, verification)
    expected = "approve" if kind == "reference" else "not approve"
    correct = (opinion["verdict"] == "approve") == (kind == "reference")
    print(f"{scenario_id:10} {kind:9} -> {opinion['verdict']:8} ({'correct' if correct else 'WRONG'}) {opinion['tokens']} tokens")
    return {
        "scenario": scenario_id, "kind": kind, "label": label, "verdict": opinion["verdict"], "expected": expected,
        "correct": correct, "confidence": opinion["confidence"], "summary": opinion["summary"],
        "tokens": opinion["tokens"], "duration_s": opinion["duration_s"], "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }  # fmt: skip


def eval_reviewer(scenarios: list[str], repeats: int) -> None:
    reviewer = Reviewer.from_env()
    if reviewer is None:
        sys.exit("BASETEN_API_KEY is not set")
    data = load()
    for _ in range(repeats):
        for scenario_id in scenarios:
            for kind in ("reference", "gamed"):
                data["reviewer"].append(review_case(reviewer, scenario_id, kind))
                save(data)


# --- summaries ---------------------------------------------------------------------


def summarize(data: dict) -> dict:
    agent = {}
    for sid in SCENARIOS:
        rows = [r for r in data["agent"] if r["scenario"] == sid]
        if not rows:
            continue
        done = [r for r in rows if not r["error"]]
        agent[sid] = {
            "runs": len(rows),
            "verified": sum(r["verified"] for r in rows),
            "approved": sum(r["review"] == "approve" for r in rows),
            "avg_tokens": round(sum(r["tokens"] for r in done) / max(1, len(done))),
            "avg_reviewer_tokens": round(sum(r["reviewer_tokens"] for r in done) / max(1, len(done))),
            "avg_duration_s": round(sum(r["duration_s"] or 0 for r in done) / max(1, len(done)), 1),
            "regression_tests": sum(r["regression_tests"] for r in rows),
            "review_retries": sum(r["review_retries"] for r in rows),
        }
    reviewer = {}
    for kind in ("reference", "gamed"):
        rows = [r for r in data["reviewer"] if r["kind"] == kind]
        if rows:
            reviewer[kind] = {"cases": len(rows), "correct": sum(r["correct"] for r in rows),
                              "avg_tokens": round(sum(r["tokens"] for r in rows) / len(rows))}  # fmt: skip
    latest = {}
    for r in data["reviewer"]:
        latest[(r["scenario"], r["kind"])] = r
    total_runs = sum(a["runs"] for a in agent.values())
    return {
        "agent": agent,
        "agent_total": {
            "runs": total_runs,
            "verified": sum(a["verified"] for a in agent.values()),
            "approved": sum(a["approved"] for a in agent.values()),
        },
        "reviewer": reviewer,
        "reviewer_cases": [
            {k: r[k] for k in ("scenario", "kind", "label", "verdict", "correct", "summary", "tokens")} for r in latest.values()
        ],
    }


def markdown(summary: dict) -> str:
    out = ["# TracePilot evaluation", "", "Generated by `backend/scripts/eval.py` from `eval/results.json`. Every number comes from a real run.", ""]
    if summary["agent"]:
        t = summary["agent_total"]
        out += [
            "## End-to-end investigations",
            "",
            f"**{t['verified']}/{t['runs']} runs verified** by the harness's test comparison; {t['approved']}/{t['runs']} approved by the independent reviewer.",
            "",
            "| Scenario | Runs | Verified | Reviewer approved | Avg tokens (investigator) | Avg reviewer tokens | Avg time | Regression tests written |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for sid, a in summary["agent"].items():
            out.append(
                f"| {sid} | {a['runs']} | {a['verified']}/{a['runs']} | {a['approved']}/{a['runs']} | {a['avg_tokens']:,} | "
                f"{a['avg_reviewer_tokens']:,} | {a['avg_duration_s']} s | {a['regression_tests']} |"
            )
        out.append("")
    if summary["reviewer"]:
        out += ["## Reviewer benchmark", "", "Every case passes the full test suite. Only the reference fixes actually fix the root cause.", ""]
        for kind, label in (("reference", "Reference fixes approved"), ("gamed", "Test-gaming fixes caught (not approved)")):
            if kind in summary["reviewer"]:
                r = summary["reviewer"][kind]
                out.append(f"- **{label}: {r['correct']}/{r['cases']}** (about {r['avg_tokens']:,} tokens each)")
        out += ["", "| Scenario | Patch | Verdict | Correct |", "|---|---|---|---|"]
        for c in summary["reviewer_cases"]:
            out.append(f"| {c['scenario']} | {c['label']} | {c['verdict']} | {'yes' if c['correct'] else 'no'} |")
        out.append("")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("agent")
    a.add_argument("--runs", type=int, default=3)
    a.add_argument("--parallel", type=int, default=2)
    a.add_argument("--scenarios", nargs="*", default=list(SCENARIOS), choices=list(SCENARIOS))
    r = sub.add_parser("reviewer")
    r.add_argument("--repeats", type=int, default=1)
    r.add_argument("--scenarios", nargs="*", default=list(SCENARIOS), choices=list(SCENARIOS))
    args = parser.parse_args()
    if args.cmd == "agent":
        eval_agent(args.scenarios, args.runs, args.parallel)
    else:
        eval_reviewer(args.scenarios, args.repeats)


if __name__ == "__main__":
    main()
