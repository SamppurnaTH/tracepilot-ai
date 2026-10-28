"""Run a full TracePilot investigation (investigate -> fix -> verify -> report) and stream events.

Run from the repo root:  .venv/Scripts/python backend/scripts/investigate.py --scenario orders|notes|billing
The full run (report + every event) is saved to runs/ in the same format the API replays.
"""

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent import Investigation  # noqa: E402
from app.main import Run, RunManager  # noqa: E402
from app.scenarios import SCENARIOS  # noqa: E402


def print_event(event: dict) -> None:
    t, kind = f"{event['t']:6.1f}s", event["type"]
    if kind == "start":
        print(f"{t}  START  model={event['model']} sandbox={event['isolation']}")
    elif kind == "seeded":
        print(f"{t}  SEEDED {event['requests']} requests, statuses {event['statuses']}")
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
    elif kind == "second_opinion":
        if event["verdict"] == "unavailable":
            print(f"{t}  SECOND OPINION unavailable: {event.get('error', '')}")
        else:
            print(f"{t}  SECOND OPINION ({event['model']}): {event['verdict'].upper()} [{event['confidence']}] {event['summary']}")
            for risk in event.get("risks", []):
                print(f"{t}    risk: {risk}")
    elif kind == "skip_fix":
        print(f"{t}  no fix attempted: {event['reason']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="orders", choices=sorted(SCENARIOS))
    parser.add_argument("--isolation", default="auto", choices=["auto", "docker", "process"])
    args = parser.parse_args()

    run = Run(id=uuid.uuid4().hex[:12], scenario=args.scenario, provider="meta")

    def on_event(event: dict) -> None:
        run.events.append(event)
        print_event(event)

    investigation = Investigation.from_scenario(SCENARIOS[args.scenario], on_event=on_event, isolation=args.isolation)
    report = investigation.run()
    report.pop("events", None)
    run.report, run.status = report, "completed"

    print("\n=== FINDINGS ===")
    print(report["findings"].get("summary", ""))
    for issue in report["findings"].get("issues", []):
        print(f"- [{issue['severity']}/{issue['category']}] {issue['title']}: {issue['root_cause']}")
    v = report["verification"]
    print(f"\nVerified: {v['verified']}  fixed={len(v['fixed'])} still_failing={v['still_failing']} regressions={v['regressions']}")
    u = report["usage"]
    print(f"Usage: {u['model_calls']} model calls, {u['tool_calls']} tool calls, "
          f"{u['input_tokens'] + u['output_tokens']} tokens, {report['duration_s']}s")

    RunManager.save(run)
    print(f"Saved run {run.id} to runs/")


if __name__ == "__main__":
    main()
