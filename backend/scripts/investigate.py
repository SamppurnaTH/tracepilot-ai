"""Run a full TracePilot investigation (investigate -> fix -> verify -> report) and stream events.

Run from the repo root:  .venv/Scripts/python backend/scripts/investigate.py [--provider meta|baseten]
The full run (report + every event) is saved to runs/<timestamp>.json for replay.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "demo"))

from app.agent import Investigation  # noqa: E402
from app.config import REPO_ROOT  # noqa: E402
from incidents import ORDERS_API  # noqa: E402


def print_event(event: dict) -> None:
    t, kind = f"{event['t']:6.1f}s", event["type"]
    if kind == "start":
        print(f"{t}  START  model={event['model']} sandbox={event['isolation']}")
    elif kind == "baseline":
        print(f"{t}  BASELINE tests: {event['tally']}")
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
    elif kind == "patch":
        print(f"{t}  PATCH {event['path']}")
    elif kind == "blocked":
        print(f"{t}  BLOCKED {event['tool']} ({event['reason']})")
    elif kind == "verification":
        status = "VERIFIED" if event["verified"] else "NOT VERIFIED"
        print(f"{t}  {status} (attempt {event['attempt']}): before {event['before']} -> after {event['after']}")
    elif kind == "budget":
        print(f"{t}  step budget reached in {event['phase']}")
    elif kind == "skip_fix":
        print(f"{t}  no fix attempted: {event['reason']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="meta", choices=["meta", "baseten"])
    parser.add_argument("--isolation", default="auto", choices=["auto", "docker", "process"])
    args = parser.parse_args()

    investigation = Investigation(
        ORDERS_API, REPO_ROOT / "sample_app", provider=args.provider, on_event=print_event, isolation=args.isolation
    )
    report = investigation.run()

    print("\n=== FINDINGS ===")
    print(report["findings"].get("summary", ""))
    for issue in report["findings"].get("issues", []):
        print(f"- [{issue['severity']}/{issue['category']}] {issue['title']}: {issue['root_cause']}")
    v = report["verification"]
    print(f"\nVerified: {v['verified']}  fixed={len(v['fixed'])} still_failing={v['still_failing']} regressions={v['regressions']}")
    u = report["usage"]
    print(f"Usage: {u['model_calls']} model calls, {u['tool_calls']} tool calls, "
          f"{u['input_tokens'] + u['output_tokens']} tokens, {report['duration_s']}s")

    runs = REPO_ROOT / "runs"
    runs.mkdir(exist_ok=True)
    out = runs / f"{time.strftime('%Y%m%d-%H%M%S')}-{args.provider}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
