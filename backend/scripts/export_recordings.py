"""Export the latest verified run of each scenario from runs/ to frontend/public/recordings/.

The hosted demo replays these real recordings when no live backend is available.
Raw tool output is dropped (the UI doesn't show it), which keeps the files small.

Run from the repo root:  .venv/Scripts/python backend/scripts/export_recordings.py
Add one blind-study run as a replay (leaves every other recording alone):
    .venv/Scripts/python backend/scripts/export_recordings.py --blind tomlkit-599

Study replays carry a `provenance` record (source, hash) and are kept across full re-exports.
"""

import hashlib

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import REPO_ROOT  # noqa: E402
from app.scenarios import SCENARIOS  # noqa: E402

RUNS = REPO_ROOT / "runs"
OUT = REPO_ROOT / "frontend" / "public" / "recordings"
DROP_EVENTS = {"tool_result", "message"}
BENCH = REPO_ROOT / "bench" / "runs"
# Real CLI runs on projects that aren't demo scenarios (bench/runs/*.json), shown alongside them.
BENCH_SCENARIOS = {
    "shipping": {
        "title": "Shipping module: Friday express orders promised for Saturday",
        "service": "shipping",
        "language": "python",
        "incident": "Customers who order express on Fridays are promised delivery on Saturday, but our carrier does not deliver "
        "on weekends, so courier booking fails for those orders. CI is green.",
    },
    "shipspace": {
        "title": "ShipSpace (Spring Boot): ships stay editable for hours",
        "service": "shipspace",
        "language": "java",
        "incident": "Users can still edit their ships hours after posting. Ship s-9001 was rewritten about 3 hours after it was created, "
        "after it had collected 40 likes. Product rule (Requirement 4.4): a ship can only be edited for 10 minutes after creation. CI is green.",
    },
}


def entry(summary: dict, name: str, data: dict) -> dict:
    report = data["report"]
    usage, verification = report["usage"], report["verification"]
    return {
        "scenario": summary,
        "file": name,
        "verified": bool(data.get("verified")),
        "outcome": report.get("outcome"),
        "duration_s": report["duration_s"],
        "started_at": data.get("started_at"),
        # Headline facts, so the landing page can show results without loading every recording.
        "tests": {"before": verification["before"], "after": verification["after"]},
        "issues": [{k: i[k] for k in ("title", "severity", "category")} for i in report["findings"].get("issues", [])],
        "tokens": usage["input_tokens"] + usage["output_tokens"],
        "model_calls": usage["model_calls"],
        "review": (report.get("second_opinion") or {}).get("verdict"),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    latest: dict[str, tuple[Path, dict]] = {}
    for path in sorted(RUNS.glob("*.json")):  # names start with a timestamp, so later wins
        data = json.loads(path.read_text(encoding="utf-8"))
        # A run is worth showing when its fix was verified, or when it rightly concluded no code change was needed.
        good = data.get("verified") or (data.get("report") or {}).get("outcome") == "no_code_change"
        if data.get("status") == "completed" and good and data.get("scenario") in SCENARIOS:
            latest[data["scenario"]] = (path, data)

    index = []
    for scenario_id in [s for s in SCENARIOS if s in latest]:  # keep the backend's scenario order
        path, data = latest[scenario_id]
        data["events"] = [e for e in data["events"] if e.get("type") not in DROP_EVENTS]
        name = f"{scenario_id}.json"
        (OUT / name).write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        for shot in SCENARIOS[scenario_id].screenshot_paths():  # the UI shows the evidence the model saw
            shutil.copyfile(shot, OUT / shot.name)
        index.append(entry({**SCENARIOS[scenario_id].summary(), "language": "python", "live": True}, name, data))
        print(f"{scenario_id}: {path.name} -> {name} ({len(data['events'])} events)")
    for bench_id, meta in BENCH_SCENARIOS.items():
        path = BENCH / f"{bench_id}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        data["events"] = [e for e in data["events"] if e.get("type") not in DROP_EVENTS]
        name = f"{bench_id}.json"
        (OUT / name).write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        index.append(entry({"id": bench_id, **meta, "screenshots": [], "live": False}, name, data))
        print(f"{bench_id}: bench/runs/{path.name} -> {name} ({len(data['events'])} events)")
    index += kept_study_entries({e["scenario"]["id"] for e in index})
    (OUT / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    missing = sorted(set(SCENARIOS) - set(latest))
    if missing:
        print(f"No verified run yet for: {', '.join(missing)}")


def kept_study_entries(exported: set[str]) -> list[dict]:
    """Study replays (wrap-review, blind-study cases) aren't rebuilt from runs/; keep them as published."""
    index = OUT / "index.json"
    if not index.exists():
        return []
    kept = []
    for e in json.loads(index.read_text(encoding="utf-8")):
        path = OUT / e["file"]
        if e["scenario"]["id"] not in exported and path.exists() and "provenance" in json.loads(path.read_text(encoding="utf-8")):
            kept.append(e)
    return kept


# Blind-study cases published as replays: the real bug report, TracePilot's run and its hidden-test result.
BLIND_SCENARIOS = {
    "tomlkit-599": {
        "title": "tomlkit (real bug, blind): deleting an array slice corrupts the TOML",
        "service": "tomlkit",
        "language": "python",
    },
}


def lf_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def publish_blind(case_id: str) -> None:
    src = REPO_ROOT / "eval" / "blind" / "round-2" / case_id
    report_path, events_path = src / "report.json", src / "events.jsonl"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    report.pop("events", None)
    hidden = json.loads((src / "hidden-outcomes.json").read_text(encoding="utf-8")) if (src / "hidden-outcomes.json").exists() else None
    started = next((json.loads(line)["at"] for line in (REPO_ROOT / "eval/blind/observations.jsonl").read_text(encoding="utf-8").splitlines()
                    if line.strip() and json.loads(line).get("id") == case_id and json.loads(line).get("round") == 2), None)  # fmt: skip
    data = {
        "id": case_id,
        "scenario": case_id,
        "status": "completed",
        "verified": bool(report["verification"].get("verified")),
        "started_at": time.mktime(time.strptime(started, "%Y-%m-%dT%H:%M:%S")) if started else None,
        "report": report,
        "events": [e for e in events if e.get("type") not in DROP_EVENTS],
        "provenance": {
            "source": f"eval/blind/round-2/{case_id}",
            "report_sha256_lf": lf_sha256(report_path),
            "events_sha256_lf": lf_sha256(events_path),
            "hidden_tests": hidden,
            "note": "Blind study, round 2: a real bug fixed upstream after Aug 2026. TracePilot saw the code from before the fix "
            "and the bug report only; the fix's own tests were hidden and judged the patch afterwards. See eval/blind/RESULTS.md.",
        },
    }
    name = f"{case_id}.json"
    (OUT / name).write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    summary = {"id": case_id, **BLIND_SCENARIOS[case_id], "incident": report["incident"], "screenshots": [], "live": False}
    index = [e for e in json.loads((OUT / "index.json").read_text(encoding="utf-8")) if e["scenario"]["id"] != case_id]
    index.append(entry(summary, name, data))
    (OUT / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(f"{case_id}: {src.relative_to(REPO_ROOT)} -> {name} ({len(data['events'])} events)")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--blind":
        publish_blind(sys.argv[2])
    else:
        main()
