"""Export the latest verified run of each scenario from runs/ to frontend/public/recordings/.

The hosted demo replays these real recordings when no live backend is available.
Raw tool output is dropped (the UI doesn't show it), which keeps the files small.

Run from the repo root:  .venv/Scripts/python backend/scripts/export_recordings.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import REPO_ROOT  # noqa: E402
from app.scenarios import SCENARIOS  # noqa: E402

RUNS = REPO_ROOT / "runs"
OUT = REPO_ROOT / "frontend" / "public" / "recordings"
DROP_EVENTS = {"tool_result", "message"}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    latest: dict[str, tuple[Path, dict]] = {}
    for path in sorted(RUNS.glob("*.json")):  # names start with a timestamp, so later wins
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("status") == "completed" and data.get("verified") and data.get("scenario") in SCENARIOS:
            latest[data["scenario"]] = (path, data)

    index = []
    for scenario_id in [s for s in SCENARIOS if s in latest]:  # keep the backend's scenario order
        path, data = latest[scenario_id]
        data["events"] = [e for e in data["events"] if e.get("type") not in DROP_EVENTS]
        name = f"{scenario_id}.json"
        (OUT / name).write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        index.append(
            {
                "scenario": SCENARIOS[scenario_id].summary(),
                "file": name,
                "verified": True,
                "duration_s": data["report"]["duration_s"],
            }
        )
        print(f"{scenario_id}: {path.name} -> {name} ({len(data['events'])} events)")
    (OUT / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    missing = sorted(set(SCENARIOS) - set(latest))
    if missing:
        print(f"No verified run yet for: {', '.join(missing)}")


if __name__ == "__main__":
    main()
