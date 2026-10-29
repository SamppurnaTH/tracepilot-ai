"""Summarize all observations; missing cells and null results remain visible."""
import json
import csv
import io
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend/scripts"))
from judge_evidence import rate  # noqa: E402

BASE = ROOT / "eval/research"


def read_all(folder):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((BASE / folder).glob("*.json"))]


def total_tokens(row):
    return sum(row.get("usage", {}).get(k, 0) for k in ("input_tokens", "output_tokens")) + row.get("reviewer_tokens", 0)


def contrast(rows, model, treatment, control, successful_only=False):
    lookup = {(r["case"], r["repeat"], r["condition"]): r for r in rows if r["model"] == model}
    pairs = []
    for case, repeat, condition in lookup:
        if condition != treatment or (case, repeat, control) not in lookup:
            continue
        a, b = lookup[(case, repeat, treatment)], lookup[(case, repeat, control)]
        if successful_only and not (a["heldout_pass"] and b["heldout_pass"]):
            continue
        pairs.append((case, a, b))
    if not pairs:
        return {"pairs": 0}
    clusters = sorted({p[0] for p in pairs})
    effects = {}
    for field in ("tokens", "duration_s", "success"):
        measure = total_tokens if field == "tokens" else (lambda r: float(bool(r["heldout_pass"]))) if field == "success" else (lambda r: r.get("duration_s") or 0)
        grouped = {c: [(measure(a), measure(b)) for case, a, b in pairs if c == case] for c in clusters}
        means = {c: (sum(a for a, _ in values) / len(values), sum(b for _, b in values) / len(values)) for c, values in grouped.items()}
        def effect(draw):
            aa, bb = sum(means[c][0] for c in draw), sum(means[c][1] for c in draw)
            return (aa - bb) / len(draw) if field == "success" else (1 - aa / bb if bb else 0)
        rng = random.Random(20261029)
        draws = sorted(effect(rng.choices(clusters, k=len(clusters))) for _ in range(10000))
        effects[field] = {"effect": effect(clusters), "cluster_bootstrap_95": [draws[250], draws[9749]],
                          "meaning": "treatment minus control success rate" if field == "success" else "fraction saved by treatment vs control"}
    return {"pairs": len(pairs), "case_clusters": len(clusters), "treatment": treatment, "control": control,
            "successful_pairs_only": successful_only, "effects": effects}


def model_interaction(rows):
    """Does harness benefit differ between earlier and newer versions on matched quartets?"""
    lookup = {(r["case"], r["repeat"], r["model"], r["condition"]): r for r in rows}
    by_case = {}
    count = 0
    for case, repeat in sorted({(r["case"], r["repeat"]) for r in rows}):
        keys = [(case, repeat, model, cond) for model in ("muse-spark-1.1", "muse-spark-1.3") for cond in ("tracepilot", "plain")]
        if not all(key in lookup for key in keys):
            continue
        old_full, old_plain, new_full, new_plain = [lookup[key] for key in keys]
        old_saving = 1 - total_tokens(old_full) / max(1, total_tokens(old_plain))
        new_saving = 1 - total_tokens(new_full) / max(1, total_tokens(new_plain))
        success = (float(bool(old_full["heldout_pass"])) - float(bool(old_plain["heldout_pass"]))) - (float(bool(new_full["heldout_pass"])) - float(bool(new_plain["heldout_pass"])))
        by_case.setdefault(case, []).append((success, old_saving - new_saving))
        count += 1
    if not count:
        return {"matched_quartets": 0}
    means = {case: [sum(row[i] for row in values) / len(values) for i in (0, 1)] for case, values in by_case.items()}
    cases = sorted(means)
    result = {"matched_quartets": count, "case_clusters": len(cases), "interpretation": "Earlier-version harness benefit minus newer-version benefit; earlier does not mean smaller. Token effect averages within-pair fractional savings, unlike the ratio-of-means primary contrast."}
    for i, metric in enumerate(("success_benefit_difference", "fractional_token_saving_difference")):
        rng = random.Random(20261029)
        draws = sorted(sum(means[c][i] for c in rng.choices(cases, k=len(cases))) / len(cases) for _ in range(10000))
        result[metric] = {"effect": sum(means[c][i] for c in cases) / len(cases), "cluster_bootstrap_95": [draws[250], draws[9749]]}
    return result


def summarize():
    manifest = json.loads((BASE / "manifest.json").read_text())
    rows = read_all("observations")
    audits = {r["id"]: r for r in read_all("score-audits")}
    for row in rows:
        a = audits.get(row["id"])
        row["scoring_status"] = a["status"] if a else "pending_audit"
        if a:
            row["heldout_pass"] = a["heldout_pass"]
        row["false_success"] = bool(row.get("claimed_fixed") and row["heldout_pass"] is False and row["scoring_status"] == "valid")
    groups = {}
    for model in manifest["models"]:
        for condition in manifest["conditions"]:
            rs = [r for r in rows if r["model"] == model and r["condition"] == condition]
            n = len(rs)
            phases = sorted({phase for r in rs for phase in r.get("usage", {}).get("by_phase", {})})
            groups[f"{model}/{condition}"] = {"completed": n, "expected": len(manifest["cases"]) * manifest["repeats"],
                "success": rate(sum(bool(r["heldout_pass"]) for r in rs), n), "false_success": sum(r.get("false_success", False) for r in rs),
                "scoring_unavailable": sum(r["scoring_status"] == "scoring_unavailable" for r in rs),
                "errors": sum(bool(r.get("error")) for r in rs), "mean_total_tokens": round(sum(map(total_tokens, rs)) / n) if n else None,
                "mean_cached_input_tokens": round(sum(r.get("usage", {}).get("cached_tokens", 0) for r in rs) / n) if n else None,
                "mean_uncached_input_tokens": round(sum(max(0, r.get("usage", {}).get("input_tokens", 0) - r.get("usage", {}).get("cached_tokens", 0)) for r in rs) / n) if n else None,
                "mean_investigator_output_tokens": round(sum(r.get("usage", {}).get("output_tokens", 0) for r in rs) / n) if n else None,
                "mean_reviewer_tokens": round(sum(r.get("reviewer_tokens", 0) for r in rs) / n) if n else None,
                "mean_tokens_by_phase": {phase: round(sum(r.get("usage", {}).get("by_phase", {}).get(phase, 0) for r in rs) / n) for phase in phases},
                "mean_duration_s": round(sum(r.get("duration_s") or 0 for r in rs) / n, 1) if n else None}
    contrasts = {}
    for model in manifest["models"]:
        for a, b in [("plain_brief", "plain"), ("tracepilot", "tracepilot_no_brief"), ("tracepilot", "plain_brief"), ("tracepilot", "plain")]:
            for successful in (False, True):
                contrasts[f"{model}/{a}-vs-{b}/{'matched-success' if successful else 'all'}"] = contrast(rows, model, a, b, successful)
    pilot_review_rows = read_all("review-observations")
    review_rows = read_all("review-clean-observations")
    reviewer = {}
    for model in sorted({r["reviewer"] for r in review_rows}):
        rr = [r for r in review_rows if r["reviewer"] == model]
        good = [r for r in rr if r["label_correct_patch"] and not r["error"]]
        bad = [r for r in rr if not r["label_correct_patch"] and not r["error"]]
        reviewer[model] = {"attempts": len(rr), "unavailable": sum(bool(r["error"]) for r in rr),
                           "unsafe_approval": rate(sum(r["opinion"]["verdict"] == "approve" for r in bad), len(bad)),
                           "correct_nonapproval": rate(sum(r["opinion"]["verdict"] != "approve" for r in good), len(good)),
                           "reference_hard_rejects": sum(r["opinion"]["verdict"] == "reject" for r in good),
                           "reference_concerns": sum(r["opinion"]["verdict"] == "concerns" for r in good),
                           "verdicts": dict(Counter(r["opinion"]["verdict"] for r in rr if not r["error"]))}
    paired_reviews = {}
    for row in review_rows:
        paired_reviews.setdefault((row["case"], row["kind"], row["repeat"]), []).append(row)
    valid = [rr for rr in paired_reviews.values() if len(rr) == 2 and all(not r["error"] for r in rr)]
    agreement = {"paired_observations": len(valid), "same_verdict": sum(rr[0]["opinion"]["verdict"] == rr[1]["opinion"]["verdict"] for rr in valid),
                 "both_wrong": sum(all(r["wrong"] for r in rr) for rr in valid), "either_wrong": sum(any(r["wrong"] for r in rr) for rr in valid),
                 "interpretation": "Observed joint functional-label disagreements, not proof of independent blind spots or wrong merge decisions. No error correlation coefficient when a reviewer has zero error variance."}
    attacks = read_all("generated-attacks")
    extended_rows = read_all("extended-checks")
    extended_groups = {}
    for condition in manifest["conditions"]:
        rs = [r for r in extended_rows if r["condition"] == condition]
        extended_groups[condition] = {"passes": sum(r["passes"] for r in rs), "total": len(rs), "timeouts": sum(r["timed_out"] for r in rs), "errors": sum(bool(r.get("error")) for r in rs)}
    discovery_path = BASE / "reviewer-discovery.json"
    discovery = json.loads(discovery_path.read_text()) if discovery_path.exists() else None
    triage = {}
    if discovery and discovery["counterexample"]["timed_out"] and discovery["control"]["exit_code"] == 0:
        for model in reviewer:
            rs = [r for r in review_rows if r["reviewer"] == model and not r["error"]]
            known_bad = [r for r in rs if r["kind"] == "gamed" or r["case"] == "wrap"]
            other_refs = [r for r in rs if r["kind"] == "reference" and r["case"] != "wrap"]
            triage[model] = {"known_bad_approved": rate(sum(r["opinion"]["verdict"] == "approve" for r in known_bad), len(known_bad)),
                             "other_references_approved": rate(sum(r["opinion"]["verdict"] == "approve" for r in other_refs), len(other_refs)),
                             "qualification": "Post-hoc secondary triage after verifying wrap's hang; not a replacement for the pre-specified functional-oracle labels or a proof all other references are defect-free."}
    expected = len(manifest["cases"]) * len(manifest["models"]) * len(manifest["conditions"]) * manifest["repeats"]
    return {"complete": len(rows) == expected and len(audits) == expected and len(review_rows) == 48,
            "repair_matrix_complete": len(rows) == expected, "score_audits": len(audits), "scoring_corrections": sum(r.get("changed_from_initial", False) for r in audits.values()),
            "pilot_reviewer_observations": len(pilot_review_rows), "clean_reviewer_observations": len(review_rows),
            "reviewer_discovery": discovery,
            "posthoc_reviewer_triage": triage,
            "posthoc_wrap_checks": extended_groups,
            "reviewer_label_qualification": "Correct-patch label means the external oracle accepts behavior; nonapproval may be a legitimate merge-readiness/coverage concern, not a reasoning error. Raw-module pilot retained separately; main calibration uses minimal references preserving contract docs.",
            "repair_observations": len(rows), "expected_repair_observations": expected,
            "groups": groups, "contrasts": contrasts, "reviewers": reviewer, "reviewer_agreement": agreement,
            "model_interaction": model_interaction(rows),
            "generated_attacks": {"attempted": len(attacks), "eligible": sum(r["eligible"] for r in attacks), "errors": sum(bool(r["error"]) for r in attacks)},
            "manifest": manifest, "limitations": manifest["limits"], "bootstrap": "10,000 incident-cluster resamples; seed 20261029. Up to six case clusters; exact counts are reported per contrast in JSON. Exploratory only."}


def main():
    result = summarize()
    data = json.dumps(result, indent=2) + "\n"
    (BASE / "summary.json").write_text(data, encoding="utf-8")
    audit_lookup = {a["id"]: a for a in read_all("score-audits")}
    stream = io.StringIO()
    fields = ["id", "case", "model", "condition", "repeat", "claimed_fixed", "initial_heldout_pass", "audited_heldout_pass", "scoring_status", "investigator_tokens", "reviewer_tokens", "total_tokens", "cached_input_tokens", "duration_s", "error"]
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in read_all("observations"):
        a = audit_lookup.get(row["id"], {})
        writer.writerow({**{k: row.get(k, "") for k in ("id", "case", "model", "condition", "repeat", "claimed_fixed", "reviewer_tokens", "duration_s", "error")},
                         "initial_heldout_pass": row["heldout_pass"], "audited_heldout_pass": a.get("heldout_pass", ""), "scoring_status": a.get("status", "pending"),
                         "investigator_tokens": total_tokens(row) - row.get("reviewer_tokens", 0), "total_tokens": total_tokens(row), "cached_input_tokens": row.get("usage", {}).get("cached_tokens", 0)})
    (BASE / "observations.csv").write_text(stream.getvalue(), encoding="utf-8")
    if BASE == ROOT / "eval/research":
        (ROOT / "frontend/public/research.json").write_text(data, encoding="utf-8")
        (ROOT / "frontend/public/research.csv").write_text(stream.getvalue(), encoding="utf-8")
        if result["reviewer_discovery"]:
            (ROOT / "frontend/public/reviewer-discovery.json").write_text(json.dumps(result["reviewer_discovery"], indent=2) + "\n", encoding="utf-8")
    lines = ["# External-source research results", "", f"Status: {'complete repair matrix' if result['complete'] else 'INCOMPLETE — do not present as a finished study'}. {result['repair_observations']}/{result['expected_repair_observations']} repair observations.", "",
             "Raw observations, full traces, fixed protocol and source fingerprints are in `eval/research/`. The original 13-run comparison is not overwritten.", "",
             "| Model / condition | Observations | Held-out success | False success | Errors | Mean total tokens | Reviewer tokens | Mean seconds |", "|---|---|---|---|---|---|---|---|"]
    for key, r in result["groups"].items():
        lines.append(f"| {key} | {r['completed']}/{r['expected']} | {r['success']['count']}/{r['success']['total']} | {r['false_success']} | {r['errors']} | {r['mean_total_tokens']} | {r['mean_reviewer_tokens']} | {r['mean_duration_s']} |")
    lines += ["", "## Paired ablations", "", result["bootstrap"], "", "Positive token/time values mean treatment saved resources; success effect is treatment minus control. Examine accuracy before treating token reductions as beneficial.", ""]
    lines += ["Token counts are provider-reported usage, not measured dollar cost. Cached/uncached investigator inputs and output counts are separated in summary.json. Reviewer tokens come from a separate endpoint; do not multiply mixed-provider totals by a single price. Timing includes shared-host and cloud effects, with outliers retained.", ""]
    for key, c in result["contrasts"].items():
        lines.append(f"- **{key}**: {c['pairs']} paired observations" + (f", {c['case_clusters']} cases." if c["pairs"] else "."))
        for field, e in c.get("effects", {}).items():
            low, high = e["cluster_bootstrap_95"]
            lines.append(f"  - {field}: {e['effect']:.1%}; exploratory 95% interval {low:.1%}–{high:.1%}.")
    lines += ["", "## Earlier-model interaction", "", str(result["model_interaction"]), "",
              f"Scoring audits: {result['score_audits']}; initial empty-output corrections: {result['scoring_corrections']}. Original scores remain unchanged in the raw observations.", "",
              "## Reviewer calibration and joint label disagreement", "", "Concerns counts as nonapproval, not a hard rejection. Errors/unavailable are reported separately from verdict accuracy.", result["reviewer_label_qualification"],
              f"Raw-module pilot: {result['pilot_reviewer_observations']} observations; corrected reference-format follow-up: {result['clean_reviewer_observations']}.", ""]
    for model, r in result["reviewers"].items():
        lines.append(f"- {model}: unsafe approvals {r['unsafe_approval']['count']}/{r['unsafe_approval']['total']}; correct-patch nonapprovals {r['correct_nonapproval']['count']}/{r['correct_nonapproval']['total']} ({r['reference_hard_rejects']} rejects, {r['reference_concerns']} concerns); unavailable {r['unavailable']}/{r['attempts']}; verdicts {r['verdicts']}.")
    lines += ["", f"Generated attacks: {result['generated_attacks']}", "", f"Matched reviewer observations: {result['reviewer_agreement']}", "", "## Limits", "", *[f"- {s}" for s in result["limitations"]],
              "- Same-model/context and different-Meta-model/context reviews cannot establish cross-family independence.",
              "- Evidence brief effects are isolated. Remaining harness components are a bundled comparison, not an individual attribution."]
    if result["reviewer_discovery"]:
        finding = result["reviewer_discovery"]
        lines += ["", "## Reviewer finding beyond the external oracle", "", "Both cold reviewers identified a zero-progress loop left in the upstream wrap reference. This reference passes the frozen dataset tests, so nonapproval cannot automatically be classified as a reviewer mistake.",
                  f"Input: `{finding['input']}`. Terminating control: `{finding['control']['stdout'].strip()}`. Counterexample timed out in Docker: `{finding['counterexample']['timed_out']}` (3-second limit).",
                  "For a leading space and no other space inside the column window, rfind returns zero and text[0:] leaves the loop input unchanged. This is an observed reviewer finding, not a claim of first discovery in the research literature."]
        for model, r in result["posthoc_reviewer_triage"].items():
            lines += [f"- Secondary triage, {model}: {r['known_bad_approved']['count']}/{r['known_bad_approved']['total']} known-bad observations approved; {r['other_references_approved']['count']}/{r['other_references_approved']['total']} other references approved. {r['qualification']}"]
        lines += ["", f"Separate post-hoc wrap check of all available repairs: {result['posthoc_wrap_checks']}. This new counterexample is not added retroactively to the primary success metric."]
    report = "\n".join(lines) + "\n"
    (BASE / "RESULTS.md").write_text(report, encoding="utf-8")
    if BASE == ROOT / "eval/research":
        (ROOT / "frontend/public/judge/RESEARCH_RESULTS.md").write_text(report, encoding="utf-8")
    print(f"Summarized {result['repair_observations']}/{result['expected_repair_observations']} repairs; {result['score_audits']} audits; {result['clean_reviewer_observations']} clean / {result['pilot_reviewer_observations']} pilot reviews")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--study-dir")
    args = parser.parse_args()
    if args.study_dir:
        BASE = Path(args.study_dir).resolve()
    main()
