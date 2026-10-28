"""Run a full TracePilot investigation (investigate -> fix -> verify -> report) and stream events.

Run from the repo root:  .venv/Scripts/python backend/scripts/investigate.py --scenario orders|notes|billing
The full run (report + every event) is saved to runs/ in the same format the API replays.
"""

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent import Investigation  # noqa: E402
from app.cli import print_event  # noqa: E402
from app.main import Run, RunManager  # noqa: E402
from app.scenarios import SCENARIOS  # noqa: E402


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
