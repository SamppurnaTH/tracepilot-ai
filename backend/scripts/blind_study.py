"""Blind study: can TracePilot fix fresh, real bugs in projects it has never been tuned on?

Each case is a real bug fixed in a public open-source project between Aug and Oct 2026. TracePilot gets the
project as it was just before the fix and the bug report, nothing else. The fix's own tests (the "hidden
tests") are never shown to it; they judge the patch afterwards, exactly as they judged the real fix.

    python backend/scripts/blind_study.py prepare     # clone, and check each oracle on the real fix
    python backend/scripts/blind_study.py run         # investigate each case, judge with the hidden tests
    python backend/scripts/blind_study.py summarize   # rebuild eval/blind/RESULTS.md from observations

Every observation is kept, including failures and setup problems. Nothing is rerun for a better score.
"""

import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.agent import Investigation  # noqa: E402
from app.reviewer import Reviewer  # noqa: E402
from app.sandbox import Sandbox, docker_available, project_image  # noqa: E402

OUT = ROOT / "eval" / "blind"
OBSERVATIONS = OUT / "observations.jsonl"
ROUND = 2
CACHE = Path.home() / ".cache" / "tracepilot-blind"

# Incidents are the real issue text where one exists. Otherwise they are written from the fix PR's bug
# description, keeping only what a bug report would say: the symptom, a reproduction and the expected result,
# never the cause or the fix.
CASES = [
    {
        "id": "inflect-172", "fix": "a58a8a3571f2f3595e59faa1644002fda328713d", "repo": "jaraco/inflect", "pr": 282, "merged": "2026-10-21", "source": "issue #172 (verbatim; traceback shortened to the library's own frames)",
        "tests": ["tests/test_pwd.py"],
        "incident": (
            "`engine.plural` raises unexpected `IndexError`\n\n"
            "This might be considered invalid input, but `engine.plural` accepts multiple words. When doing so, it can raise an "
            "unexpected `IndexError`:\n\n>>> import inflect\n>>> engine = inflect.engine()\n"
            ">>> engine.plural(\"I'm only here for a minute, John.\")\nTraceback (most recent call last):\n"
            "  File \"inflect/__init__.py\", line 2403, in plural\n    plural = self.postprocess(\n"
            "  File \"inflect/__init__.py\", line 2375, in postprocess\n    result[index] = result[index].capitalize()\n"
            "IndexError: list index out of range\n\n"
            "This seems to be because `engine.postprocess` expects the `inflected` it's passed to be the same number of words "
            "as the `orig` it's passed, but that's not necessarily the case."
        ),
    },
    {
        "id": "more-itertools-1279", "fix": "b2f3aff7633057d234ec9186c18a53f4df306d08", "repo": "more-itertools/more-itertools", "pr": 1279, "merged": "2026-09-14", "source": "written from PR #1279's bug description",
        "tests": ["tests/test_more.py"],
        "incident": (
            "one() and only() ignore a custom exception when the exception object is falsy\n\n"
            "Passing a custom exception instance as `too_long` (or `too_short`) to `one()` or `only()` normally raises that "
            "exception. But if the exception's class defines `__bool__` returning False, the custom exception is discarded and "
            "the default ValueError is raised instead. Expected: the custom exception is raised whatever its truthiness."
        ),
    },
    {
        "id": "tomlkit-599", "fix": "8c30fc17d91aee7469c0287e509300e78aa15227", "repo": "sdispater/tomlkit", "pr": 599, "merged": "2026-10-12", "source": "written from PR #599's bug description",
        "tests": ["tests/test_items.py"],
        "incident": (
            "Deleting a slice from an array corrupts the rendered TOML\n\n"
            "After deleting a slice from an Array, the list contents are right but as_string()/dumps() disagree with them:\n\n"
            "    import tomlkit\n    doc = tomlkit.parse(\"a = [1, 2, 3]\\n\")\n    del doc[\"a\"][:0]   # deletes nothing\n"
            "    tomlkit.dumps(doc)  # 'a = []\\n'  -- expected 'a = [1, 2, 3]\\n'\n\n"
            "Other cases: `del arr[-1:]` leaves list(arr) == [1, 2] but renders `[]`; `del arr[:-1]` leaves [3] but the "
            "rendering doesn't match either. Expected: the rendered array always matches the list contents."
        ),
    },
    {
        "id": "pyparsing-560", "fix": "efd56db4e59f36b1673ce0eb0823e3afaa9d1201", "repo": "pyparsing/pyparsing", "pr": 653, "merged": "2026-08-18", "source": "issue #560 (verbatim; its Stack Overflow link is not reachable from the sandbox)",
        "tests": ["tests/test_unit.py"],
        "incident": (
            "match_previous_expr does not handle nested expressions\n\n"
            "See this SO post (https://stackoverflow.com/questions/78574784/how-to-make-sure-element-has-parsing-precedence-before-other-elements-in-pyparsi), "
            "should be able to use match_previous_expr to enforce matching of opening and closing tags. Does not work for nested tags."
        ),
    },
    {
        "id": "marshmallow-3082", "fix": "5761beab3985d654d712f9326e08bfb2e2ec9c4c", "repo": "marshmallow-code/marshmallow", "pr": 3082, "merged": "2026-10-19", "source": "written from PR #3074's bug description",
        "tests": ["tests/test_fields.py"],
        "incident": (
            "fields.Pluck with data_key=\"\" fails to load and dump\n\n"
            "A Pluck field whose nested field has `data_key=\"\"` treats the empty key as unset. Loading a valid plucked value "
            "raises ValidationError, and dumping it raises KeyError. Ordinary schema fields accept an empty data_key; Pluck "
            "should behave the same, for single and many=True nested values."
        ),
    },
    {
        "id": "click-3884", "fix": "8c73ff134480f436faa0d041bd19aaf949aac22c", "repo": "pallets/click", "pr": 3884, "merged": "2026-10-06", "source": "written from PR #3884's bug description",
        "tests": ["tests/test_options.py"],
        "incident": (
            "show_envvar renders sequences and empty envvars badly\n\n"
            "With show_envvar=True, the env var hint in error messages and help is wrong for some envvar values:\n\n"
            "- envvar=\"\": the error hint shows `(env var: '')` and help shows `[env var: ]`; expected: no hint at all.\n"
            "- envvar=[]: the error hint shows `(env var: '[]')` and help shows `[env var: ]`; expected: no hint at all.\n"
            "- envvar=[\"WEATHER_UNITS\", \"UNITS\"]: the error hint shows `(env var: '['WEATHER_UNITS', 'UNITS']')`; "
            "expected: `(env var: 'WEATHER_UNITS', 'UNITS')`."
        ),
    },
    {
        "id": "packaging-1430", "fix": "2aada00b158feb36109d77dc91d62baa91f7d400", "repo": "pypa/packaging", "pr": 1430, "merged": "2026-10-06", "source": "written from PR #1430's bug description",
        "tests": ["tests/test_requirements.py", "tests/test_specifiers.py"],
        "incident": (
            "Empty arbitrary-equality versions are accepted\n\n"
            "`Requirement(\"foo===\")` parses without error, and so do `Specifier(\"===\")` and `SpecifierSet(\"===\")`. An "
            "arbitrary-equality (===) clause with no version is invalid. Expected: Requirement raises InvalidRequirement, "
            "and Specifier/SpecifierSet raise InvalidSpecifier."
        ),
    },
]


def git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip()


def clone(case: dict) -> Path:
    repo = CACHE / case["id"] / "repo"
    if not repo.exists():
        git("clone", "--quiet", "--filter=blob:none", f"https://github.com/{case['repo']}.git", str(repo))
    return repo


def export(repo: Path, sha: str, dest: Path) -> Path:
    """A clean copy of the tree at a commit, without .git."""
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    data = subprocess.run(["git", "archive", "--format=tar", sha], cwd=repo, check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(dest, filter="data")
    return dest


def run_tests(tree: Path, files: list[str], image: str) -> dict[str, str]:
    """Per-test outcomes for the given test files, in the Docker sandbox."""
    with Sandbox(tree, isolation="docker", app=None, image=image) as sb:
        result = sb.python(["-m", "pytest", "-q", "-rA", "--tb=no", "--color=no", "-p", "no:cacheprovider", *files], timeout=900)
    outcomes = {}
    for line in (result.stdout + result.stderr).splitlines():
        match = re.match(r"^(PASSED|FAILED|ERROR) (\S+)", line)
        if match:
            outcomes[match.group(2)] = match.group(1).lower()
    return outcomes


def with_hidden_tests(tree: Path, fixed: Path, files: list[str]) -> Path:
    for name in files:
        (tree / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fixed / name, tree / name)
    return tree


def prepare() -> None:
    if (OUT / "manifest.json").exists():
        raise RuntimeError("The oracle manifest already exists; preserve it. Replicate in a separate checkout.")
    manifest = []
    for case in CASES:
        repo = clone(case)
        fix = case["fix"]  # the commit that merged the fix PR, pinned so the study never depends on the GitHub API
        git("fetch", "--quiet", "origin", fix, cwd=repo)
        before = git("rev-parse", f"{fix}^1", cwd=repo)
        work = CACHE / case["id"]
        pre = export(repo, before, work / "before")
        fixed = export(repo, fix, work / "fixed")
        image = project_image(pre)
        # The oracle: the fix's tests must fail on the old code and pass on the real fix.
        old = run_tests(with_hidden_tests(export(repo, before, work / "oracle"), fixed, case["tests"]), case["tests"], image)
        new = run_tests(fixed, case["tests"], image)
        target = sorted(t for t, o in new.items() if o == "passed" and old.get(t) in ("failed", "error"))
        entry = {**{k: case[k] for k in ("id", "repo", "pr", "merged", "source", "tests")}, "before": before, "fix": fix,
                 "image": image, "target_tests": target, "passing_after_fix": sum(o == "passed" for o in new.values()), "collected": len(new)}  # fmt: skip
        manifest.append(entry)
        print(f"{case['id']:22} before {before[:10]}  fix {fix[:10]}  oracle: {len(target)} tests fail before and pass after ({len(new)} collected)", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def investigate(case: dict, entry: dict) -> dict:
    work = CACHE / case["id"]
    tree = export(clone(case), entry["before"], work / "run" / time.strftime("%Y%m%d-%H%M%S"))
    events: list[dict] = []
    row = {"id": case["id"], "round": ROUND, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    artifact = OUT / "round-2" / case["id"]
    artifact.mkdir(parents=True, exist_ok=False)
    row["artifact"] = artifact.relative_to(ROOT).as_posix()
    def save_events(event):
        events.append(event)
        with (artifact / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, default=str) + "\n")
    try:
        report = Investigation(
            case["incident"], tree, on_event=save_events, app=None, image=entry["image"], reviewer=Reviewer.from_env(), kind="python", isolation="docker",
        ).run()
    except (Exception, SystemExit) as exc:
        row |= {"result": "error", "error": f"{type(exc).__name__}: {exc}"[:400]}
        return row
    usage, timing = report["usage"], report.get("timing", {})
    row |= {
        "tracepilot_outcome": report.get("outcome"),
        "tracepilot_verified": bool(report["verification"].get("verified")),
        "review": (report.get("second_opinion") or {}).get("verdict"),
        "regression_tests_written": sum(e["type"] == "regression_test" and e.get("accepted") for e in events),
        "duration_s": report["duration_s"], "model_s": timing.get("model_s"),
        "tokens": usage["input_tokens"] + usage["output_tokens"], "model_calls": usage["model_calls"],
        "files_changed": len(re.findall(r"^\+\+\+ b/", report["diff"], re.M)), "summary": report["findings"].get("summary", "")[:400],
    }  # fmt: skip
    (work / "last-report.json").write_text(json.dumps({**report, "events": events}, indent=2, default=str), encoding="utf-8")
    (artifact / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (artifact / "patch.diff").write_text(report["diff"], encoding="utf-8")
    if not report["diff"]:
        row["result"] = "no patch"
        return row
    # Judge: the patch on a fresh copy, plus the fix's hidden tests.
    judged = export(clone(case), entry["before"], work / "judge")
    applied = subprocess.run(["git", "apply", "--whitespace=nowarn", "-"], cwd=judged, input=report["diff"], capture_output=True, text=True, encoding="utf-8")
    if applied.returncode != 0:
        row |= {"result": "patch did not apply", "error": applied.stderr[:300]}
        return row
    outcomes = run_tests(with_hidden_tests(judged, CACHE / case["id"] / "fixed", case["tests"]), case["tests"], entry["image"])
    (artifact / "hidden-outcomes.json").write_text(json.dumps(outcomes, indent=2), encoding="utf-8")
    fixed = [t for t in entry["target_tests"] if outcomes.get(t) == "passed"]
    broken = sorted(t for t, o in outcomes.items() if o != "passed" and t not in entry["target_tests"])
    row |= {"target_passed": f"{len(fixed)}/{len(entry['target_tests'])}", "other_failures": broken[:10]}
    row["result"] = "fixed" if len(fixed) == len(entry["target_tests"]) and not broken else "not fixed"
    return row


def run(only: list[str] | None) -> None:
    manifest = {e["id"]: e for e in json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))}
    previous = [json.loads(line) for line in OBSERVATIONS.read_text(encoding="utf-8").splitlines() if line.strip()] if OBSERVATIONS.exists() else []
    done = {row["id"] for row in previous if row.get("round", 1) == ROUND}
    protocol = OUT / "round-2-protocol.json"
    if not protocol.exists():
        modules = [ROOT / "backend" / "app" / name for name in ("agent.py", "tools.py", "sandbox.py", "reviewer.py", "config.py")]
        protocol.write_text(json.dumps({"round": ROUND, "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "base_commit": git("rev-parse", "HEAD", cwd=ROOT), "cases": CASES,
            "module_sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in modules},
            "changes": ["pyproject test dependencies and src layout", "continue past collection errors; report unchanged unloadable files", "answer unexecuted chained calls before next request", "persist artifacts and catch per-case runner failures"],
            "limits": "Follow-up after inspecting round 1; not a fresh preregistered holdout. No population or training-contamination claim."}, indent=2), encoding="utf-8")
    for case in CASES:
        if only and case["id"] not in only:
            continue
        if case["id"] in done:
            print(f"{case['id']}: round {ROUND} already recorded; skipping", flush=True)
            continue
        if (OUT / "round-2" / case["id"]).exists():
            raise RuntimeError(f"{case['id']}: an attempt directory already exists without an observation; inspect it, do not silently rerun")
        entry = manifest[case["id"]]
        if not entry["target_tests"]:
            row = {"id": case["id"], "result": "skipped: no oracle", "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        else:
            try:
                row = investigate(case, entry)
            except (Exception, SystemExit) as exc:
                row = {"id": case["id"], "round": ROUND, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                       "result": "error", "error": f"{type(exc).__name__}: {exc}"[:400]}
        row["round"] = ROUND
        with OBSERVATIONS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        print(f"{case['id']:22} {row['result']:20} {row.get('target_passed', '')}  TracePilot: {row.get('tracepilot_outcome')}, "
              f"review {row.get('review')}, {row.get('duration_s')} s, {row.get('tokens')} tokens", flush=True)  # fmt: skip
    summarize()


def summarize() -> None:
    manifest = {e["id"]: e for e in json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))}
    rows = [json.loads(line) for line in OBSERVATIONS.read_text(encoding="utf-8").splitlines() if line.strip()] if OBSERVATIONS.exists() else []
    fixed = sum(r["result"] == "fixed" for r in rows)
    out = [
        "# Blind study: fresh, real bugs",
        "",
        "Generated by `backend/scripts/blind_study.py` from `observations.jsonl`. Each case is a real bug fixed in a public "
        "open-source project between Aug and Oct 2026. TracePilot got the code from just before the fix and the bug report; "
        "the fix's own tests were hidden from it and judged the patch afterwards. One attempt per case per round, all kept.",
        "",
        f"Across rounds: **{fixed}/{len(rows)} recorded attempts fixed** by the hidden tests. Rounds are reported separately below; do not treat repeat cases as independent bugs.",
        "",
    ]
    ordered_rows = sorted(rows, key=lambda r: r.get("round", 1))
    for index, r in enumerate(ordered_rows):
        current_round = r.get("round", 1)
        if index == 0 or current_round != ordered_rows[index - 1].get("round", 1):
            group = [x for x in rows if x.get("round", 1) == current_round]
            out += ["", f"## Round {current_round}", "",
                    f"**{sum(x['result'] == 'fixed' for x in group)}/{len(group)} recorded cases fixed** ({len(group)}/7 cases have observations).", "",
                    f"Locally test-verified candidates failing the hidden oracle: {sum(bool(x.get('tracepilot_verified')) and x['result'] == 'not fixed' for x in group)}. "
                    f"Of these, reviewer-approved: {sum(bool(x.get('tracepilot_verified')) and x['result'] == 'not fixed' and x.get('review') == 'approve' for x in group)}.", "",
                    "| Case | Merged | Bug report | Hidden tests passed | Result | TracePilot said | Reviewer | Investigation time | Investigator tokens |",
                    "|---|---|---|---|---|---|---|---|---|"]
        m = manifest.get(r["id"], {})
        said = "verified" if r.get("tracepilot_verified") else (r.get("tracepilot_outcome") or "—")
        time_s = f"{r['duration_s'] / 60:.1f} min" if r.get("duration_s") else "—"
        token_text = f"{r['tokens']:,}" if isinstance(r.get("tokens"), int) else "—"
        out.append(
            f"| [{r['id']}](https://github.com/{m.get('repo')}/pull/{m.get('pr')}) | {m.get('merged', '')} | {m.get('source', '')} | "
            f"{r.get('target_passed', '—')} | **{r['result']}** | {said} | {r.get('review') or '—'} | {time_s} | {token_text} |"
        )  # fmt: skip
    notes = [r for r in rows if r.get("error") or r.get("other_failures")]
    if notes:
        out += ["", "## Notes", ""]
        out += [f"- Round {r.get('round', 1)}, {r['id']}: {r.get('error') or 'other hidden-test failures: ' + ', '.join(r['other_failures'])}" for r in notes]
    out += ["", "## Changes between rounds", "",
            "Round 1 stopped after four recorded cases; the prior process exited during marshmallow without a recorded observation. "
            "The exit status was reported as 4 in the handoff, but its original cause is not established. Round 2 preserves those observations and adds "
            "pyproject dependency/src-layout support, continued collection after import errors, explicit unchanged-unloadable-file reporting, "
            "and outputs for chained tool calls left pending at a phase budget. The runner now persists traces and records per-case exceptions. "
            "Round 2 is a harness-fix follow-up after inspecting round 1, not seven untouched holdout attempts."]
    out += [
        "",
        "## Limits",
        "",
        "Seven cases, at most one attempt per case per round: a small sample, not a broad benchmark. The projects are public, so older versions of "
        "their code or fixes may be in the model's training data; merge dates do not establish a training cutoff. Five bug reports "
        "were written from the fix PRs' descriptions (symptom, reproduction and expected result only); two are the real "
        "issue text. Projects run without being installed: tests import them from the workspace.",
        "The model is not deliberately supplied the fix commit or its new tests. Study authors selected cases while knowing the fixes; "
        "this is model-blinded evaluation, not a double-blind or independently administered study. The inflect issue itself contains a root-cause hint. "
        "Passing the upstream tests is bounded evidence, not proof of correctness for every input. A hidden-test pass is distinct from the agent's own verified/approved status.",
        "An attempt is one invocation of the standard investigation workflow, including its built-in fix and reviewer loops; "
        "the events preserve each internal round. There is no investigator restart after seeing a hidden score.",
        "Token columns cover the investigator only, not separate reviewer usage. Missing usage after an API error is unknown, not zero. "
        "Durations cover the investigation, excluding initial project-image preparation and post-run hidden scoring. Shared-host times are descriptive, not an isolated speed benchmark.",
        "There is no paired plain-agent control in this study, so these outcomes do not establish an advantage over another coding agent. "
        "Selected public Python libraries do not represent all private repositories or production incidents.",
    ]
    (OUT / "RESULTS.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    if not docker_available():
        sys.exit("Docker is required: the study runs every project in the sandbox.")
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare")
    r = sub.add_parser("run")
    r.add_argument("--only", nargs="*")
    sub.add_parser("summarize")
    args = parser.parse_args()
    {"prepare": prepare, "run": lambda: run(args.only), "summarize": summarize}[args.cmd]()
