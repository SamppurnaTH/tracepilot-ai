"""Separate summary for the original service-domain brief check. Two clusters only."""
import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend/scripts"))
from research_summary import contrast, total_tokens  # noqa: E402

BASE = ROOT / "eval/service-ablation"


def main():
    manifest = json.loads((BASE / "manifest.json").read_text())
    rows = [json.loads(path.read_text()) for path in sorted((BASE / "observations").glob("*.json"))]
    groups = {}
    for condition in manifest["conditions"]:
        rs = [r for r in rows if r["condition"] == condition]
        n = len(rs)
        groups[condition] = {"observed": n, "expected": 4, "heldout_pass": sum(r["heldout_pass"] for r in rs),
                             "errors": sum(bool(r["error"]) for r in rs), "scoring_unavailable": sum(bool(r["score_error"]) for r in rs),
                             "false_success": sum(r["false_success"] for r in rs),
                             "mean_total_tokens": round(sum(map(total_tokens, rs)) / n) if n else None,
                             "mean_reviewer_tokens": round(sum(r["reviewer_tokens"] for r in rs) / n) if n else None}
    contrasts = {}
    case_contrasts = {}
    for a, b in [("plain_brief", "plain"), ("tracepilot", "tracepilot_no_brief"), ("tracepilot", "plain_brief"), ("tracepilot", "plain")]:
        contrasts[f"{a}-vs-{b}"] = contrast(rows, "muse-spark-1.3", a, b)
        for case in manifest["cases"]:
            case_contrasts[f"{case}/{a}-vs-{b}"] = contrast([r for r in rows if r["case"] == case], "muse-spark-1.3", a, b)
    result = {"complete": len(rows) == manifest["expected"], "observations": len(rows), "expected": manifest["expected"],
              "groups": groups, "paired_contrasts": contrasts, "case_contrasts": case_contrasts, "manifest": manifest,
              "limits": ["Two project-authored service cases only; do not treat two-cluster bootstrap ranges as population confidence intervals.",
                         "This is a new contemporaneous check, not a causal decomposition of the historical 13-run mean.",
                         "Full method includes reviewer and report overhead; only evidence-brief delivery is isolated.",
                         "Cloud/host work is concurrent; no isolated latency claim or token-to-dollar conversion."]}
    (BASE / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (ROOT / "frontend/public/service-ablation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    lines = ["# Original-domain service ablation", "", f"{'Complete' if result['complete'] else 'INCOMPLETE'}: {len(rows)}/{manifest['expected']} observations.", "",
             "Model: Muse Spark 1.3. Cases: Orders (red CI) and Inventory (green CI). Four configurations, two repetitions. Source and oracle hashes were frozen in manifest.json before inference.", "",
             "| Workflow | Observed | Held-out pass | Errors | Score unavailable | False success | Mean total tokens | Mean reviewer tokens |", "|---|---|---|---|---|---|---|---|"]
    for key, r in groups.items():
        lines.append(f"| {key} | {r['observed']}/{r['expected']} | {r['heldout_pass']}/{r['observed']} | {r['errors']} | {r['scoring_unavailable']} | {r['false_success']} | {r['mean_total_tokens']} | {r['mean_reviewer_tokens']} |")
    lines += ["", "## Paired token contrasts", "", "Positive saving means the first workflow used fewer total tokens. A negative value means overhead. With two cases these are descriptive, not population-level causal estimates.", ""]
    for key, c in contrasts.items():
        lines.append(f"- {key}: {c['pairs']} matched pairs" + (f", token saving {c['effects']['tokens']['effect']:.1%}, success difference {c['effects']['success']['effect']:.1%}." if c["pairs"] else "."))
    lines += ["", "## Per-case contrasts", ""]
    for key, c in case_contrasts.items():
        lines.append(f"- {key}: {c['pairs']} pairs" + (f", token saving {c['effects']['tokens']['effect']:.1%}." if c["pairs"] else "."))
    lines += ["", "## Limits", "", *[f"- {line}" for line in result["limits"]]]
    text = "\n".join(lines) + "\n"
    (BASE / "RESULTS.md").write_text(text, encoding="utf-8")
    (ROOT / "frontend/public/judge/SERVICE_ABLATION.md").write_text(text, encoding="utf-8")
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["id", "case", "condition", "repeat", "heldout_pass", "total_tokens", "reviewer_tokens", "error", "score_error"])
    for row in rows:
        writer.writerow([row["id"], row["case"], row["condition"], row["repeat"], row["heldout_pass"], total_tokens(row), row["reviewer_tokens"], row["error"], row["score_error"]])
    (BASE / "observations.csv").write_text(buffer.getvalue(), encoding="utf-8")
    print(f"Summarized service ablation: {len(rows)}/{manifest['expected']}")


if __name__ == "__main__":
    main()
