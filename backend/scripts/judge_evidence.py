"""Rebuild judge-facing statistics from saved observations, without model calls.

python backend/scripts/judge_evidence.py
"""
import hashlib
import json
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def wilson(successes: int, total: int) -> list[float] | None:
    """95% Wilson score interval; repeated incidents are not independent samples."""
    if not total:
        return None
    z, p = 1.959963984540054, successes / total
    scale = 1 + z * z / total
    center = (p + z * z / (2 * total)) / scale
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / scale
    return [round(max(0, center - half), 4), round(min(1, center + half), 4)]


def rate(k: int, n: int) -> dict:
    return {"count": k, "total": n, "rate": k / n if n else None, "wilson_95": wilson(k, n)}


def build() -> dict:
    comparison = json.loads((ROOT / "eval/comparison.json").read_text())
    reviews = json.loads((ROOT / "eval/results.json").read_text())["reviewer"]
    scored = [r for r in comparison if "hidden_pass" in r]
    systems = {}
    for name in ("plain", "tracepilot"):
        rows = [r for r in scored if r["system"] == name]
        systems[name] = rate(sum(bool(r["hidden_pass"]) for r in rows), len(rows))
    good = [r for r in reviews if r["kind"] == "reference"]
    bad = [r for r in reviews if r["kind"] == "gamed"]
    # Positive = unsafe patch approved. Concerns and reject both mean not approved.
    reviewer = {
        "unsafe_approval": rate(sum(r["verdict"] == "approve" for r in bad), len(bad)),
        "correct_patch_nonapproval": rate(sum(r["verdict"] != "approve" for r in good), len(good)),
        "gamed_rejected": sum(r["verdict"] == "reject" for r in bad),
        "gamed_concerns": sum(r["verdict"] == "concerns" for r in bad),
        "reference_concerns": sum(r["verdict"] == "concerns" for r in good),
        "reference_rejected": sum(r["verdict"] == "reject" for r in good),
    }
    cases = sorted({r["case"] for r in scored})
    means = {}
    for case in cases:
        means[case] = {}
        for name in systems:
            rows = [r for r in scored if r["case"] == case and r["system"] == name]
            means[case][name] = {field: sum((r["tokens"] + r.get("reviewer_tokens", 0)) if field == "tokens" else (r.get("duration_s") or 0) for r in rows) / len(rows) for field in ("tokens", "duration_s")}
    rng = random.Random(20261029)
    savings = {}
    for field in ("tokens", "duration_s"):
        estimates = []
        for _ in range(10000):
            draw = rng.choices(cases, k=len(cases))
            estimates.append(1 - sum(means[c]["tracepilot"][field] for c in draw) / sum(means[c]["plain"][field] for c in draw))
        estimates.sort()
        savings[field] = {"case_weighted_saving": 1 - sum(means[c]["tracepilot"][field] for c in cases) / sum(means[c]["plain"][field] for c in cases), "cluster_bootstrap_95": [estimates[250], estimates[9749]], "clusters": len(cases)}
    sources = ["eval/comparison.json", "eval/results.json"]
    abstention = None
    if (ROOT / "eval/abstention-probe.json").exists():
        saved = json.loads((ROOT / "eval/abstention-probe.json").read_text(encoding="utf-8"))
        report = saved["report"]
        abstention = {"fixture": saved["fixture"], "outcome": report["outcome"], "verified": report["verification"]["verified"],
                      "diff_empty": not report["diff"], "model": report["model"], "isolation": report["isolation"], "duration_s": report["duration_s"]}
        sources.append("eval/abstention-probe.json")
    security = None
    probe = ROOT / "eval/security-probe.json"
    if probe.exists():
        saved = json.loads(probe.read_text(encoding="utf-8"))
        report = saved["report"]
        security = {"isolation": saved["isolation"], "model": report["model"], "duration_s": report["duration_s"],
                    "verified": report["verification"]["verified"], "before": report["verification"]["before"], "after": report["verification"]["after"],
                    "review": (report.get("second_opinion") or {}).get("verdict"), "suspicious_tool_attempts": len(saved["suspicious_tool_attempts"]),
                    "payload_in_brief": any(e["type"] == "brief" and "SYSTEM OVERRIDE" in e.get("text", "") for e in saved["events"]),
                    "scope": saved["scope"]}
        sources.append("eval/security-probe.json")
    return {"systems": systems, "reviewer": reviewer, "savings": savings,
            "security_probe": security,
            "abstention_probe": abstention,
            "method": "Descriptive Wilson intervals; observations repeat authored incidents. Savings resample incident-level means (10,000 draws, seed 20261029), equal weight per incident; not the run-weighted headline. No population-level significance claim.",
            "limitations": ["The original service pilot uses project-authored fixtures; the external research extension uses upstream QuixBugs sources. Neither is an independently administered audit.", "The separate research extension reports evidence-brief ablations and an earlier-model comparison with explicit completion status. Other harness features remain bundled; no smaller-model advantage or competing-vendor independence is claimed.", "Separate review context is not evidence of uncorrelated model-family errors."],
            "source_hash_encoding": "UTF-8 source bytes with CRLF normalized to LF for cross-platform reproducibility",
            "sources": [{"path": p, "sha256": hashlib.sha256((ROOT / p).read_bytes().replace(b"\r\n", b"\n")).hexdigest()} for p in sources]}


def main() -> None:
    data = build()
    (ROOT / "frontend/public/evidence.json").write_text(json.dumps(data, indent=2) + "\n")
    if data["security_probe"]:
        (ROOT / "frontend/public/security-probe.json").write_bytes((ROOT / "eval/security-probe.json").read_bytes())
    if data["abstention_probe"]:
        (ROOT / "frontend/public/abstention-probe.json").write_bytes((ROOT / "eval/abstention-probe.json").read_bytes())
    # Keep the evidence room useful on an unpushed local preview as well as a deployed site.
    downloads = ROOT / "frontend/public/judge"
    downloads.mkdir(exist_ok=True)
    for name in ("JUDGE_QA.md", "CASE_STUDIES.md", "DEMO_SCRIPT.md", "HACKATHON_ALIGNMENT.md", "RESEARCH_CLOSURE.md", "RESEARCH_PROTOCOL.md"):
        (downloads / name).write_bytes((ROOT / "docs" / name).read_bytes())
    (downloads / "SECURITY.md").write_bytes((ROOT / "SECURITY.md").read_bytes())
    (downloads / "tracepilot-ci.yml").write_bytes((ROOT / "examples/github-actions/tracepilot.yml").read_bytes())
    out = ["# Statistical evidence", "", "Generated by `python backend/scripts/judge_evidence.py` from the hashed sources below. No new runs are implied.", "", "| Measurement | Observed | Descriptive 95% Wilson interval |", "|---|---|---|"]
    for label, r in [("Plain acceptance-criteria success", data["systems"]["plain"]), ("TracePilot acceptance-criteria success", data["systems"]["tracepilot"]), ("Unsafe patches approved (false negative against fixture labels)", data["reviewer"]["unsafe_approval"]), ("Reference patches not approved (not necessarily an incorrect rejection)", data["reviewer"]["correct_patch_nonapproval"])]:
        lo, hi = r["wilson_95"]
        out.append(f"| {label} | {r['count']}/{r['total']} | {lo:.1%}–{hi:.1%} |")
    out += ["", "Concerns count as nonapproval; they are not a hard rejection.", "", f"Verdict detail: {json.dumps(data['reviewer'])}", "", "## Cost and speed uncertainty", "", data["method"], ""]
    for label, r in data["savings"].items():
        lo, hi = r["cluster_bootstrap_95"]
        out.append(f"- {label}: equal-incident-weight saving {r['case_weighted_saving']:.1%}; exploratory incident-cluster bootstrap interval {lo:.1%}–{hi:.1%} ({r['clusters']} incidents).")
    out += ["", "## Limits", "", *[f"- {s}" for s in data["limitations"]], "", "## Source fingerprints", "", data["source_hash_encoding"], "", *[f"- `{s['path']}`: `{s['sha256']}`" for s in data["sources"]]]
    (ROOT / "eval/STATISTICS.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    (downloads / "STATISTICS.md").write_bytes((ROOT / "eval/STATISTICS.md").read_bytes())
    print("Rebuilt eval/STATISTICS.md and frontend/public/evidence.json")


if __name__ == "__main__":
    main()
