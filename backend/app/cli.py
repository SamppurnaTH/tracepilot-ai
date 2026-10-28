"""TracePilot on your own project: investigate an incident, fix it in a sandbox, and hand over the patch.

    python tracepilot.py investigate --repo path/to/service --incident "Checkout returns 500 when..."

The project is copied into a locked-down sandbox (Docker when available: no network, read-only root,
non-root user). Its requirements.txt is installed into a cached sandbox image first. Your files are
never modified unless you pass --apply, and then only with a verified patch, through `git apply`.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from .agent import Investigation
from .handoff import markdown_report, pr_description
from .reviewer import Reviewer
from .sandbox import detect_kind, docker_available, project_image

SKIP_DIRS = {"tests", "test", "venv", "node_modules", "build", "dist", "__pycache__", "tracepilot-out"}
APP_ASSIGNMENT = re.compile(r"^(\w+)\s*(?::\s*\w+\s*)?=\s*(?:fastapi\.)?(?:FastAPI|Starlette)\(", re.MULTILINE)


def detect_app(repo: Path) -> str | None:
    """Find a FastAPI/Starlette app ("module:attribute") so the agent can send requests to it."""
    for path in sorted(repo.rglob("*.py")):
        rel = path.relative_to(repo)
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts[:-1]) or rel.name.startswith("test"):
            continue
        match = APP_ASSIGNMENT.search(path.read_text(encoding="utf-8", errors="ignore"))
        if match:
            return f"{'.'.join(rel.with_suffix('').parts)}:{match.group(1)}"
    return None


def print_event(event: dict) -> None:
    t, kind = f"{event.get('t', 0):6.1f}s", event["type"]
    if kind == "start":
        print(f"{t}  START  model={event['model']} sandbox={event['isolation']}")
    elif kind == "seeded":
        print(f"{t}  SEEDED {event['requests']} requests, statuses {event['statuses']}")
    elif kind == "baseline":
        print(f"{t}  BASELINE tests: {event['tally']}")
        if event["tally"].get("failed") or event["tally"].get("error"):
            print(f"{t}    note: tests already fail before any change; the fix must turn them green. Scope with --tests to match your CI.")
    elif kind == "phase":
        print(f"\n{t}  === {event['phase'].upper()} ===")
    elif kind == "thinking":
        print(f"{t}  (thinking) {event['text'][:200]}")
    elif kind == "hypothesis":
        print(f"{t}  ? {event['id']} proposed: {event['claim']}")
    elif kind == "hypothesis_update":
        mark = "CONFIRMED" if event["status"] == "confirmed" else "REJECTED"
        print(f"{t}  {'+' if mark == 'CONFIRMED' else 'x'} {event['id']} {mark}: {event['reason'][:160]}")
    elif kind == "tool_call":
        print(f"{t}    -> {event['tool']}({json.dumps(event['args'])[:140]})")
    elif kind == "evidence_image":
        print(f"{t}  SCREENSHOT given to the model as evidence: {event['name']}")
    elif kind == "reproduced":
        print(f"{t}  REPRODUCED by existing tests (re-run after the fix): {', '.join(event['tests'][:5])}")
    elif kind == "excluded_tests":
        print(f"{t}  EXCLUDED {len(event['classes'])} test classes ({event['reason']}): {', '.join(event['classes'])}")
    elif kind == "regression_test":
        verdict = "kept: fails on the current code" if event["accepted"] else "not kept: it does not fail"
        print(f"{t}  REPRODUCING TEST {event['path']} ({len(event.get('tests', {}))} tests) {verdict}")
    elif kind == "patch":
        print(f"{t}  PATCH {event['path']}")
    elif kind == "blocked":
        print(f"{t}  BLOCKED {event['tool']} ({event['reason']})")
    elif kind == "verification":
        status = "VERIFIED" if event["verified"] else "NOT VERIFIED"
        print(f"{t}  {status} (attempt {event['attempt']}): before {event['before']} -> after {event['after']}")
    elif kind == "second_opinion":
        if event["verdict"] == "unavailable":
            print(f"{t}  SECOND OPINION unavailable: {event.get('error', '')}")
        else:
            print(f"{t}  SECOND OPINION ({event['model']}): {event['verdict'].upper()} [{event['confidence']}] {event['summary']}")
            for risk in event.get("risks", []):
                print(f"{t}    risk: {risk}")
    elif kind == "review_retry":
        print(f"{t}  REVIEWER REJECTED THE PATCH: sending its objections back for one more fix round")
    elif kind == "recovered":
        print(f"{t}  recovered: {event['reason']}")
    elif kind == "budget":
        print(f"{t}  budget reached in {event['phase']} ({event.get('tokens', 0):,} tokens)")
    elif kind == "skip_fix":
        print(f"{t}  no fix attempted: {event['reason']}")


def investigate(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"error: not a directory: {repo}", file=sys.stderr)
        return 2
    incident = Path(args.incident_file).read_text(encoding="utf-8") if args.incident_file else args.incident
    if not incident or not incident.strip():
        print("error: describe the incident with --incident or --incident-file", file=sys.stderr)
        return 2
    logs = [Path(p).resolve() for p in args.logs]
    images = [Path(p).resolve() for p in args.screenshot]
    for image in images:
        if not image.is_file():
            print(f"error: screenshot not found: {image}", file=sys.stderr)
            return 2
    for log in logs:
        if not log.is_file():
            print(f"error: log file not found: {log}", file=sys.stderr)
            return 2

    kind = detect_kind(repo)
    app = None if args.app == "none" or kind == "maven" else (args.app or detect_app(repo))
    print(f"Project:  {repo} ({'Java/Maven, JUnit' if kind == 'maven' else 'Python, pytest'})")
    print(f"HTTP app: {app or 'none (requests disabled)'}")
    image = None
    if args.isolation != "process" and docker_available():
        print("Sandbox:  preparing the Docker image (dependencies are downloaded once, then cached)...")
        image = project_image(repo, kind)
    elif args.isolation == "docker" or kind == "maven":
        print("error: Docker is not available (Java projects always run in Docker)", file=sys.stderr)
        return 2

    reviewer = None if args.no_review else Reviewer.from_env()
    investigation = Investigation(
        incident.strip(), repo, on_event=print_event, isolation=args.isolation, app=app, logs=logs, image=image, reviewer=reviewer, kind=kind, images=images,
        test_scope=[t.strip() for t in args.tests.split(",") if t.strip()] if args.tests else None,
        test_args=args.test_args.split() if args.test_args else None,
    )
    report = investigation.run()
    report.pop("events", None)

    out = Path(args.out).resolve() if args.out else repo / "tracepilot-out" / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    title = incident.strip().splitlines()[0][:80]
    (out / "report.md").write_text(markdown_report(report, title), encoding="utf-8")
    (out / "pr.md").write_text(pr_description(report), encoding="utf-8")
    (out / "run.json").write_text(json.dumps({**report, "events": investigation.events}, indent=2), encoding="utf-8")
    if report["diff"]:
        (out / "fix.patch").write_text(report["diff"], encoding="utf-8", newline="\n")

    v, u = report["verification"], report["usage"]
    review = (report.get("second_opinion") or {}).get("verdict", "skipped")
    print("\n" + "=" * 72)
    if report.get("outcome") == "no_code_change":
        print("NO CODE CHANGE NEEDED: the root cause is outside the code (see report.md for what to change)")
    else:
        print(f"{'FIX VERIFIED' if v['verified'] else 'NOT VERIFIED'}: tests {v['before']} -> {v['after']}, reviewer: {review}")
    for issue in report["findings"].get("issues", []):
        print(f"  [{issue['severity']}/{issue['category']}] {issue['title']}")
    print(f"Cost: {u['model_calls']} model calls, {u['input_tokens'] + u['output_tokens']:,} tokens, {report['duration_s']} s")
    print(f"Hand-off: {out}  (report.md, pr.md{', fix.patch' if report['diff'] else ''})")

    if report["diff"] and args.apply:
        if not v["verified"]:
            print("Not applying: the patch was not verified.")
        else:
            patch = out / "fix.patch"
            check = subprocess.run(["git", "apply", "--check", str(patch)], cwd=repo, capture_output=True, text=True)
            if check.returncode != 0:
                print(f"Not applying: git apply --check failed:\n{check.stderr.strip()}")
            else:
                subprocess.run(["git", "apply", str(patch)], cwd=repo, check=True)
                print("Applied fix.patch to your working tree. Review it with `git diff`.")
    elif report["diff"]:
        print(f"To apply:  cd \"{repo}\" && git apply \"{out / 'fix.patch'}\"")
    return 0 if v["verified"] or report.get("outcome") == "no_code_change" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tracepilot", description="Investigate an incident in your project, fix it in a sandbox, and prove the fix.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    inv = sub.add_parser("investigate", help="run one investigation")
    inv.add_argument("--repo", required=True, help="the service's folder (Python with pytest tests)")
    group = inv.add_mutually_exclusive_group(required=True)
    group.add_argument("--incident", help="what users are seeing, in plain words")
    group.add_argument("--incident-file", help="a file with the incident text")
    inv.add_argument("--logs", nargs="*", default=[], help="log files to use as evidence (JSON lines or plain text)")
    inv.add_argument("--screenshot", nargs="*", default=[], help="screenshots attached to the incident (PNG, JPEG, WebP or GIF)")
    inv.add_argument("--app", help="ASGI app as module:attribute; detected automatically for FastAPI; 'none' to disable")
    inv.add_argument("--out", help="where to write the hand-off (default: <repo>/tracepilot-out/<time>)")
    inv.add_argument("--tests", help="Java: comma-separated test classes that define green, e.g. the list your CI runs (default: all)")
    inv.add_argument("--test-args", help="Java: extra -D properties for the test run, e.g. \"-Dspring.profiles.active=test\"")
    inv.add_argument("--isolation", default="auto", choices=["auto", "docker", "process"])
    inv.add_argument("--no-review", action="store_true", help="skip the Muse Spark Open second opinion")
    inv.add_argument("--apply", action="store_true", help="apply the patch with git apply, only if it was verified")
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--test-args" in argv[:-1]:  # its value starts with "-D", which argparse would read as another option
        i = argv.index("--test-args")
        argv[i : i + 2] = [f"--test-args={argv[i + 1]}"]
    args = parser.parse_args(argv)
    return investigate(args)


if __name__ == "__main__":
    sys.exit(main())
