"""Same model, with and without TracePilot: a fair comparison scored by hidden acceptance tests.

Both systems use muse-spark-1.3, the same sandbox, the same seeded or recorded logs and the same basic
tools. "plain" is a typical coding agent (backend/app/baseline.py); "tracepilot" is the full method.
Each patch is then applied to a fresh copy and judged by hidden tests in eval/hidden/ that neither
system ever sees. They probe the root cause beyond the visible tests, so a test-gaming fix fails them.

    .venv/Scripts/python backend/scripts/compare.py run --system plain --runs 2
    .venv/Scripts/python backend/scripts/compare.py run --system tracepilot --cases refunds shipping --runs 2
    .venv/Scripts/python backend/scripts/compare.py import-eval          # TracePilot runs from eval/results.json
    .venv/Scripts/python backend/scripts/compare.py score                # writes eval/COMPARISON.md

ShipSpace (a real Spring Boot codebase) is included with --shipspace PATH, pointing at a local copy with the
planted bug committed (see BUILD_LOG.md). It is skipped otherwise.
"""

import argparse
import json
import re
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.agent import Investigation  # noqa: E402
from app.baseline import PlainAgent  # noqa: E402
from app.reviewer import Reviewer  # noqa: E402
from app.sandbox import Sandbox, project_image  # noqa: E402
from app.scenarios import SCENARIOS  # noqa: E402
from app.tools import Workspace  # noqa: E402

DATA = ROOT / "eval" / "comparison.json"
REPORT_MD = ROOT / "eval" / "COMPARISON.md"
PUBLIC = ROOT / "frontend" / "public" / "comparison.json"
HIDDEN = ROOT / "eval" / "hidden"
SHIPSPACE_CI_TESTS = (
    "AdminControllerTest,AdminSecurityRouteTest,AuthControllerTest,AuthServiceRbacTest,BannedUserWriteFilterTest,"
    "EngagementControllerTest,EngagementServiceTest,FeedControllerTest,GitHubOAuthServiceTest,HealthControllerTest,JwtUtilTest,"
    "MongoIndexInitializerTest,MultibaseServiceTest,NotificationServiceTest,ProjectControllerTest,ShipControllerTest,"
    "SocialControllerTest,UserControllerTest,UserServiceTest"
).split(",")


def cases(shipspace: str | None) -> dict[str, dict]:
    out = {}
    for sid in ("orders", "notes", "billing", "inventory", "refunds", "checkout"):
        sc = SCENARIOS[sid]
        out[sid] = {
            "source": sc.target, "incident": sc.incident, "app": sc.app, "seed": sc.seed_requests(), "logs": sc.logs(),
            "images": sc.screenshot_paths(), "kind": "python",
        }  # fmt: skip
    out["shipping"] = {
        "source": ROOT / "bench" / "shipping",
        "incident": "Customers who order express on Fridays are promised delivery on Saturday, but our carrier does not deliver "
        "on weekends, so courier booking fails for those orders. CI is green.",
        "app": None, "seed": [], "logs": [ROOT / "bench" / "shipping-worker.log"], "kind": "python",
    }  # fmt: skip
    if shipspace:
        out["shipspace"] = {
            "source": Path(shipspace),
            "incident": "Users can still edit their ships hours after posting. Ship s-9001 was rewritten about 3 hours after it was "
            "created, after it had collected 40 likes. Product rule (Requirement 4.4): a ship can only be edited for 10 minutes "
            "after creation. CI is green.",
            "app": None, "seed": [], "logs": [Path(shipspace).parent / "shipspace-app.log"], "kind": "maven",
            "test_scope": SHIPSPACE_CI_TESTS, "test_args": ["-Dspring.profiles.active=test"],
        }  # fmt: skip
    return out


def load() -> list[dict]:
    return json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else []


def save(rows: list[dict]) -> None:
    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def tracepilot_row(case_id: str, report: dict, run_id: str) -> dict:
    findings = report.get("findings") or {}
    text = " ".join([findings.get("summary", "")] + [f"{i.get('root_cause', '')} {i.get('fix', '')}" for i in findings.get("issues", [])])
    review = report.get("second_opinion") or {}
    return {
        "system": "tracepilot", "case": case_id, "run": run_id,
        "claimed_fixed": bool(report["verification"]["verified"]) or report.get("outcome") == "no_code_change",
        "summary": text, "diff": report.get("diff", ""),
        "tokens": report["usage"]["input_tokens"] + report["usage"]["output_tokens"],
        "reviewer_tokens": review.get("tokens", 0) or 0, "duration_s": report.get("duration_s"),
    }  # fmt: skip


def run_one(system: str, case_id: str, case: dict) -> dict:
    common = dict(
        app=case["app"], seed_requests=case["seed"], logs=case["logs"], kind=case["kind"], isolation="auto",
        test_scope=case.get("test_scope"), test_args=case.get("test_args"), images=case.get("images"),
    )  # fmt: skip
    common["image"] = project_image(case["source"], case["kind"])  # the project's own dependencies
    run_id = uuid.uuid4().hex[:12]
    try:
        if system == "plain":
            result = PlainAgent(case["incident"], case["source"], **common).run()
            usage = result["usage"]
            row = {
                "system": "plain", "case": case_id, "run": run_id, "claimed_fixed": result["claimed_fixed"],
                "summary": result["summary"], "diff": result["diff"],
                "tokens": usage["input_tokens"] + usage["output_tokens"], "reviewer_tokens": 0, "duration_s": result["duration_s"],
            }  # fmt: skip
        else:
            report = Investigation(case["incident"], case["source"], reviewer=Reviewer.from_env(), **common).run()
            row = tracepilot_row(case_id, report, run_id)
    except Exception as exc:  # a crash is a failed run, not a crashed comparison
        row = {"system": system, "case": case_id, "run": run_id, "claimed_fixed": False, "summary": "", "diff": "",
               "tokens": 0, "reviewer_tokens": 0, "duration_s": None, "error": f"{type(exc).__name__}: {exc}"[:300]}  # fmt: skip
    row["at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    print(f"{system:10} {case_id:10} claimed_fixed={row['claimed_fixed']} tokens={row['tokens']} {row.get('error', '')}", flush=True)
    return row


def cmd_run(args) -> None:
    all_cases = cases(args.shipspace)
    jobs = [(args.system, c) for c in (args.cases or list(all_cases)) for _ in range(args.runs)]
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        for row in pool.map(lambda job: run_one(job[0], job[1], all_cases[job[1]]), jobs):
            save([*load(), row])  # re-read first: another comparison process may be appending too


def cmd_import_eval(args) -> None:
    """Import the TracePilot runs behind eval/RESULTS.md, so both systems are judged the same way."""
    rows = load()
    seen = {(r["system"], r["run"]) for r in rows}
    for r in json.loads((ROOT / "eval" / "results.json").read_text(encoding="utf-8"))["agent"]:
        if ("tracepilot", r["run"]) in seen:
            continue
        saved = list((ROOT / "runs").glob(f"*-{r['run']}.json"))
        if saved:
            data = json.loads(saved[0].read_text(encoding="utf-8"))
            if data.get("report"):
                rows.append({**tracepilot_row(r["scenario"], data["report"], r["run"]), "at": r["at"]})
    for path in args.cli_runs or []:  # run.json files from `tracepilot.py investigate`, as CASE=PATH
        case_id, _, file = path.partition("=")
        data = json.loads(Path(file).read_text(encoding="utf-8"))
        run_id = Path(file).parent.name
        if ("tracepilot", run_id) not in seen:
            rows.append({**tracepilot_row(case_id, data, run_id), "at": run_id})
    save(rows)
    print(f"{len(rows)} rows")


# --- scoring --------------------------------------------------------------------------


def changed_files(diff: str) -> tuple[list[str], list[str]]:
    """(new files, modified files) in a unified diff."""
    new, modified = [], []
    lines = diff.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("+++ b/"):
            # New: "--- /dev/null", or (older diffs) a first hunk that starts from nothing.
            created = lines[i - 1] == "--- /dev/null" or (i + 1 < len(lines) and lines[i + 1].startswith("@@ -0,0 "))
            (new if created else modified).append(line[6:].strip())
    return new, modified


def is_test(path: str) -> bool:
    return path.startswith(("tests/", "src/test/")) or Path(path).name.startswith("test_")


def hidden_pass(case_id: str, case: dict, row: dict) -> bool:
    if case_id == "refunds":  # correct = no change to the service's code, and the expired key identified
        _, modified = changed_files(row["diff"])
        new, _ = changed_files(row["diff"])
        touched_app = any(f.startswith("refunds_api/") for f in modified + new)
        text = row["summary"].lower()
        names_key = re.search(r"api[ _-]?key|credential", text) and re.search(r"expir|rotat|renew|new key|regenerat", text)
        return not touched_app and bool(names_key)
    kind = case["kind"]
    with Sandbox(case["source"], isolation="docker", app=None, kind=kind, test_args=case.get("test_args"),
                 image=project_image(case["source"], kind)) as sb:  # fmt: skip
        if row["diff"]:
            (sb.root / ".fix.patch").write_text(row["diff"], encoding="utf-8", newline="\n")
            applied = subprocess.run(["git", "apply", "--whitespace=nowarn", ".fix.patch"], cwd=sb.root, capture_output=True, text=True)
            (sb.root / ".fix.patch").unlink()
            if applied.returncode != 0:
                return False
        ws = Workspace(sb)
        if kind == "maven":
            outcomes, _ = ws.test_report("ShipServiceTest#shouldCreateShipSuccessfullyWithValidProjectAssociation")
        else:
            (sb.root / "tests").mkdir(exist_ok=True)
            (sb.root / "tests" / "test_hidden_acceptance.py").write_text((HIDDEN / f"{case_id}.py").read_text(encoding="utf-8"), encoding="utf-8")
            outcomes, _ = ws.test_report("tests/test_hidden_acceptance.py")
    return bool(outcomes) and all(o == "passed" for o in outcomes.values())


def cmd_score(args) -> None:
    all_cases = cases(args.shipspace)
    rows = load()
    for row in rows:
        if row["case"] not in all_cases:
            continue
        new, modified = changed_files(row["diff"])
        row["new_tests"] = sum(is_test(f) for f in new)
        row["edited_tests"] = sum(is_test(f) for f in modified)
        if "hidden_pass" not in row or args.rescore:
            row["hidden_pass"] = False if row.get("error") else hidden_pass(row["case"], all_cases[row["case"]], row)
            print(f"{row['system']:10} {row['case']:10} hidden_pass={row['hidden_pass']} claimed={row['claimed_fixed']}", flush=True)
            save(rows)
    summary = summarize(rows)
    PUBLIC.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    REPORT_MD.write_text(markdown(summary), encoding="utf-8")
    print(REPORT_MD.read_text(encoding="utf-8"))


def summarize(rows: list[dict]) -> dict:
    out: dict = {"systems": {}, "cases": {}}
    scored = [r for r in rows if "hidden_pass" in r]
    for system in ("plain", "tracepilot"):
        rs = [r for r in scored if r["system"] == system]
        if not rs:
            continue
        n = len(rs)
        out["systems"][system] = {
            "runs": n,
            "correct": sum(r["hidden_pass"] for r in rs),
            "false_success": sum(r["claimed_fixed"] and not r["hidden_pass"] for r in rs),
            "honest_failure": sum(not r["claimed_fixed"] and not r["hidden_pass"] for r in rs),
            "new_tests": sum(r.get("new_tests", 0) for r in rs),
            "runs_editing_tests": sum(r.get("edited_tests", 0) > 0 for r in rs),
            "avg_tokens": round(sum(r["tokens"] + r.get("reviewer_tokens", 0) for r in rs) / n),
            "avg_duration_s": round(sum(r["duration_s"] or 0 for r in rs) / n, 1),
        }
    for case in dict.fromkeys(r["case"] for r in scored):
        out["cases"][case] = {
            system: {"runs": len(rs), "correct": sum(r["hidden_pass"] for r in rs), "false_success": sum(r["claimed_fixed"] and not r["hidden_pass"] for r in rs)}
            for system in ("plain", "tracepilot")
            if (rs := [r for r in scored if r["system"] == system and r["case"] == case])
        }
    return out


def markdown(summary: dict) -> str:
    label = {"plain": "Plain agent", "tracepilot": "TracePilot"}
    out = [
        "# Same model, with and without TracePilot", "",
        "Both systems use `muse-spark-1.3`, the same sandbox, logs and basic tools. Every patch is applied to a fresh copy and judged by "
        "**hidden acceptance tests** (`eval/hidden/`) that neither system sees. A *false success* is a run that claimed the problem "
        "was fixed when the hidden tests say it wasn't. Generated by `backend/scripts/compare.py` from `eval/comparison.json`.", "",
        "| | Runs | Actually fixed | False successes | Honest failures | Reproducing tests written | Runs that edited existing tests | Avg tokens | Avg time |",
        "|---|---|---|---|---|---|---|---|---|",
    ]  # fmt: skip
    for system, s in summary["systems"].items():
        out.append(
            f"| **{label[system]}** | {s['runs']} | {s['correct']}/{s['runs']} | {s['false_success']} | {s['honest_failure']} | "
            f"{s['new_tests']} | {s['runs_editing_tests']} | {s['avg_tokens']:,} | {s['avg_duration_s']} s |"
        )
    out += ["", "| Incident | Plain agent: fixed (false successes) | TracePilot: fixed (false successes) |", "|---|---|---|"]
    for case, systems in summary["cases"].items():
        cells = [f"{s['correct']}/{s['runs']} ({s['false_success']})" if (s := systems.get(k)) else "not run" for k in ("plain", "tracepilot")]
        out.append(f"| {case} | {cells[0]} | {cells[1]} |")
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shipspace", help="local ShipSpace copy with the planted bug committed (optional)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--system", required=True, choices=["plain", "tracepilot"])
    r.add_argument("--cases", nargs="*")
    r.add_argument("--runs", type=int, default=2)
    r.add_argument("--parallel", type=int, default=2)
    i = sub.add_parser("import-eval")
    i.add_argument("--cli-runs", nargs="*", help="CASE=path/to/run.json from tracepilot.py investigate")
    s = sub.add_parser("score")
    s.add_argument("--rescore", action="store_true")
    args = parser.parse_args()
    {"run": cmd_run, "import-eval": cmd_import_eval, "score": cmd_score}[args.cmd](args)


if __name__ == "__main__":
    main()
