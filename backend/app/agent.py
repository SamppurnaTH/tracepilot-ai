"""TracePilot agent: investigate -> fix -> verify -> report.

The model drives investigation and fixing through tools. The harness owns the facts:
it records hypotheses, enforces which tools each phase may use, protects the tests,
and decides whether a fix is verified by comparing per-test outcomes before and after.
"""

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import openai

from .llm import get_client
from .reviewer import Reviewer, changed_files
from .sandbox import Sandbox
from .scenarios import Scenario
from .tools import FIX_TOOLS, INVESTIGATION_TOOLS, Workspace, execute_tool, tools_for

EventSink = Callable[[dict], None]

MAX_INVESTIGATION_STEPS = 16
MAX_FIX_STEPS = 10
MAX_FIX_ATTEMPTS = 2
REVIEW_RETRIES = 1  # extra fix rounds when the independent reviewer rejects the patch
MAX_REPRODUCE_STEPS = 6
TOKEN_BUDGET = 400_000  # per investigation; past it, the model must stop calling tools and wrap up
REPEAT_LIMIT = 2
# Existing tests are ground truth. Python: tests/; Java (Maven layout): src/test/.
PROTECTED_PREFIXES = ("tests/", "tests\\", "src/test/", "src\\test\\")
JAVA_TEST_PATH = re.compile(r"src/test/java/(?:[A-Za-z_]\w*/)*[A-Z]\w*Test\.java")
REGRESSION_NAME = re.compile(r"[a-z0-9_]{1,40}")

SYSTEM_PROMPT = """You are TracePilot, an evidence-driven software investigation agent.
You investigate failures in an application running in an isolated sandbox, then fix and verify them.

Rules:
- Work hypothesis-first. Before chasing a possible cause, register it with propose_hypothesis.
- Resolve every hypothesis with resolve_hypothesis as confirmed or rejected, citing concrete evidence
  you gathered with tools: log request ids, file paths with line numbers, reproduced request results, test names.
- Never confirm a hypothesis from intuition alone. If evidence contradicts it, reject it and form a better one.
- Look for the cause of every reported symptom, and note any closely related defect you discover.
- Tests are the ground truth: never weaken or edit them.
- Not every incident is a code bug. If the cause is configuration, data, or something outside the system (an expired
  credential, a third-party outage), confirm it with fix_in set accordingly. No code change is then the right answer:
  a patch that papers over an external failure is worse than none.
- A fix is proven by a test that fails before it and passes after. An existing test you run that fails counts;
  if no failing test demonstrates a confirmed root cause, write one with write_regression_test before you
  finish investigating. It must fail on the current code.
- Be economical: every round trip re-sends the whole conversation. Batch independent tool calls into one turn
  (several reads, requests or hypotheses at once), use the evidence brief instead of re-discovering it,
  and read only the code you need."""

HYPOTHESIS_TOOLS: list[dict] = [
    {
        "type": "function",
        "name": "propose_hypothesis",
        "description": "Register a testable root-cause hypothesis before investigating it. Returns its id.",
        "parameters": {
            "type": "object",
            "properties": {
                "claim": {"type": "string", "description": "One-sentence root-cause claim"},
                "symptom": {"type": "string", "description": "Which reported symptom this would explain"},
                "next_check": {"type": "string", "description": "The check that will confirm or reject it"},
            },
            "required": ["claim", "symptom", "next_check"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "resolve_hypothesis",
        "description": "Mark a hypothesis confirmed or rejected, with the concrete evidence that decided it.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Hypothesis id, e.g. H1"},
                "status": {"type": "string", "enum": ["confirmed", "rejected"]},
                "evidence": {"type": "array", "items": {"type": "string"}},
                "reason": {"type": "string"},
                "fix_in": {
                    "type": "string",
                    "enum": ["code", "config", "data", "external"],
                    "description": "For a confirmed cause, where the fix belongs: this repository's code, deployment "
                    "configuration, stored data, or outside the system (a third party, credentials, infrastructure). Default code.",
                },
            },
            "required": ["id", "status", "evidence", "reason"],
            "additionalProperties": False,
        },
    },
]

REGRESSION_TOOL: dict = {
    "type": "function",
    "name": "write_regression_test",
    "description": "Add a new pytest file, tests/test_regression_<name>.py, that reproduces a confirmed root cause. "
    "The harness runs it at once and keeps it only if every test in it fails on the current code; "
    "after the fix, it must pass. Existing tests can't be changed. Import the app the way the existing tests do.",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Short snake_case name, e.g. negative_quantity"},
            "code": {"type": "string", "description": "The complete pytest file"},
        },
        "required": ["name", "code"],
        "additionalProperties": False,
    },
}

JAVA_REGRESSION_TOOL: dict = {
    "type": "function",
    "name": "write_regression_test",
    "description": "Add a new JUnit 5 test class under src/test/java that reproduces a confirmed root cause. "
    "The harness runs it at once and keeps it only if every test in it fails on the current code; after the fix, it must pass. "
    "Existing tests can't be changed. The sandbox has no network, database or Docker: write a plain unit test "
    "(or @WebMvcTest with mocks), never @SpringBootTest or Testcontainers.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "New file, e.g. src/test/java/com/acme/feed/FeedRegressionTest.java; the class name must match"},
            "code": {"type": "string", "description": "The complete Java file, including its package line"},
        },
        "required": ["path", "code"],
        "additionalProperties": False,
    },
}

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "category": {"type": "string", "enum": ["security", "reliability", "performance", "correctness", "other"]},
                    "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                    "root_cause": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                    "fix": {"type": "string"},
                    "hypothesis_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "category", "severity", "root_cause", "evidence", "fix", "hypothesis_ids"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "issues"],
    "additionalProperties": False,
}


@dataclass
class Hypothesis:
    id: str
    claim: str
    symptom: str
    next_check: str
    status: str = "open"
    evidence: list[str] = field(default_factory=list)
    reason: str = ""
    fix_in: str = "code"  # where a confirmed cause's fix belongs: code, config, data or external


def compare_outcomes(before: dict[str, str], after: dict[str, str]) -> dict:
    """Decide verification from per-test outcomes: every failing test fixed, nothing newly broken."""
    fixed = sorted(t for t, o in before.items() if o != "passed" and after.get(t) == "passed")
    still_failing = sorted(t for t, o in after.items() if o != "passed" and before.get(t, "failed") != "passed")
    regressions = sorted(t for t, o in before.items() if o == "passed" and after.get(t) != "passed")
    missing = sorted(t for t in before if t not in after)
    # Something that failed must now pass: a run that fixed nothing proved nothing.
    verified = bool(fixed) and not still_failing and not regressions and not missing
    return {
        "verified": verified,
        "fixed": fixed,
        "still_failing": still_failing,
        "regressions": regressions,
        "missing": missing,
        "before": _tally(before),
        "after": _tally(after),
    }


def _tally(outcomes: dict[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for outcome in outcomes.values():
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


class Investigation:
    """One end-to-end run against one sandboxed copy of the target."""

    def __init__(
        self,
        incident: str,
        source: Path,
        provider: str = "meta",
        on_event: EventSink | None = None,
        client: Any = None,
        model: str | None = None,
        isolation: str = "auto",
        kind: str = "python",
        app: str | None = "orders_api.app:app",
        seed_requests: list[dict] | None = None,
        logs: list[Path] | None = None,
        image: str | None = None,
        test_scope: list[str] | None = None,
        test_args: list[str] | None = None,
        reviewer: Reviewer | None = None,
    ):
        self.incident = incident
        self.source = source
        self.provider = provider
        self.on_event = on_event or (lambda event: None)
        self.isolation = isolation
        self.kind = kind
        self.app = app
        self.seed_requests = seed_requests or []
        self.logs = logs or []
        self.image = image
        self.test_scope = test_scope
        self.test_args = test_args
        self.reviewer = reviewer
        if client is None:
            client, model = get_client(provider)
        self.client, self.model = client, model
        self.hypotheses: dict[str, Hypothesis] = {}
        self.regression_tests: dict[str, str] = {}  # node id -> "failed", for tests the agent added that reproduce a bug
        self._regression_files: dict[str, list[str]] = {}  # file the agent wrote -> its test ids
        self.observed_failures: dict[str, str] = {}  # existing tests the agent saw fail during the investigation
        self.token_budget = TOKEN_BUDGET
        self.protect_tests = True  # existing tests are ground truth (the plain baseline turns this off)
        self._attempts = 0
        self.events: list[dict] = []
        self.usage = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "model_calls": 0, "tool_calls": 0, "by_phase": {}}
        self._phase = "investigate"
        self._previous_id: str | None = None
        self._history: list = []
        self._call_counts: dict[str, int] = {}
        self._started = 0.0

    @classmethod
    def from_scenario(cls, scenario: Scenario, **kwargs) -> "Investigation":
        """A scenario run, with the Muse Spark Open reviewer whenever a Baseten key is configured."""
        kwargs.setdefault("reviewer", Reviewer.from_env())
        kwargs.setdefault("logs", scenario.logs())
        return cls(scenario.incident, scenario.target, app=scenario.app, seed_requests=scenario.seed_requests(), **kwargs)

    # --- plumbing -----------------------------------------------------------

    def _emit(self, type_: str, **data) -> None:
        event = {"seq": len(self.events) + 1, "t": round(time.monotonic() - self._started, 2), "type": type_, **data}
        self.events.append(event)
        self.on_event(event)

    def _create(self, input_items: list, tools: list[dict] | None = None, chain: bool = True, **kwargs):
        """One model call. With chain=False it runs in a fresh context: cheaper, and the transcript is untouched."""
        params: dict[str, Any] = {"model": self.model, "input": input_items, **kwargs}
        if tools:
            params["tools"] = tools
        if not chain:
            response = self.client.responses.create(**params)
            self._count(response)
            return response
        if self._previous_id:
            params["previous_response_id"] = self._previous_id
        # Keep our own transcript so a run survives the server losing the response chain.
        self._history.extend(input_items)
        try:
            response = self.client.responses.create(**params)
        except openai.BadRequestError as exc:
            if not self._previous_id or "referenced response" not in str(exc):
                raise
            self._emit("recovered", reason="the server lost the conversation; replaying it from the local transcript")
            params.pop("previous_response_id")
            params["input"] = list(self._history)
            response = self.client.responses.create(**params)
        self._previous_id = response.id
        self._history.extend(item for item in map(_as_input_item, response.output) if item)
        self._count(response)
        for item in response.output:
            if item.type == "reasoning":
                summary = " ".join(getattr(part, "text", "") for part in (getattr(item, "summary", None) or []))
                if summary.strip():
                    self._emit("thinking", text=summary.strip())
        return response

    def _count(self, response) -> None:
        self.usage["model_calls"] += 1
        usage = getattr(response, "usage", None)
        if not usage:
            return
        spent = (usage.input_tokens or 0) + (usage.output_tokens or 0)
        self.usage["input_tokens"] += usage.input_tokens or 0
        self.usage["output_tokens"] += usage.output_tokens or 0
        self.usage["cached_tokens"] += getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0
        self.usage["by_phase"][self._phase] = self.usage["by_phase"].get(self._phase, 0) + spent

    def _dispatch(self, workspace: Workspace, name: str, arguments: str, allowed: list[dict]) -> str:
        self.usage["tool_calls"] += 1
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return json.dumps({"error": "arguments must be valid JSON"})

        if name == "propose_hypothesis" and name in _names(allowed):
            return json.dumps(self._propose(args))
        if name == "resolve_hypothesis" and name in _names(allowed):
            return json.dumps(self._resolve(args))
        if name == "write_regression_test" and name in _names(allowed):
            return json.dumps(self._regression_test(workspace, args))
        if self.protect_tests and name == "edit_file" and str(args.get("path", "")).startswith(PROTECTED_PREFIXES):
            result = json.dumps({"error": "tests are the ground truth and cannot be modified; fix the application code"})
            self._emit("blocked", tool=name, args=args, reason="protected path")
            return result

        key = f"{name}:{json.dumps(args, sort_keys=True)}"
        self._call_counts[key] = self._call_counts.get(key, 0) + 1
        self._emit("tool_call", tool=name, args=args)
        result = execute_tool(workspace, name, args, allowed=allowed)
        if self._call_counts[key] > REPEAT_LIMIT:
            note = f"You have run this exact call {self._call_counts[key]} times. Try a different check."
            result = json.dumps({"result": json.loads(result), "note": note})
        self._emit("tool_result", tool=name, preview=result[:2000])
        if name == "edit_file" and "edited" in result:
            self._emit("patch", path=args.get("path"), diff=workspace.sandbox.diff())
        if name == "run_tests" and self._phase == "investigate":
            # An existing test that fails before any change is reproducing evidence: verification re-runs it.
            failed = json.loads(result).get("failed_tests", []) if result.startswith("{") else []
            new = [t for t in failed if t not in self.observed_failures]
            if new:
                self.observed_failures.update({t: "failed" for t in new})
                for cls in sorted({t.split("#")[0].rsplit(".", 1)[-1] for t in new}):
                    if cls not in workspace.extra_tests:
                        workspace.extra_tests.append(cls)
                self._emit("reproduced", tests=new)
        return result

    def _propose(self, args: dict) -> dict:
        hyp_id = f"H{len(self.hypotheses) + 1}"
        hyp = Hypothesis(
            id=hyp_id,
            claim=str(args.get("claim", "")),
            symptom=str(args.get("symptom", "")),
            next_check=str(args.get("next_check", "")),
        )
        self.hypotheses[hyp_id] = hyp
        self._emit("hypothesis", **asdict(hyp))
        return {"id": hyp_id}

    def _resolve(self, args: dict) -> dict:
        hyp = self.hypotheses.get(str(args.get("id", "")))
        if hyp is None:
            return {"error": f"unknown hypothesis id: {args.get('id')}; known: {sorted(self.hypotheses)}"}
        status = args.get("status")
        if status not in ("confirmed", "rejected"):
            return {"error": "status must be 'confirmed' or 'rejected'"}
        evidence = [str(e) for e in args.get("evidence") or []]
        if status == "confirmed" and not evidence:
            return {"error": "a confirmed hypothesis needs at least one piece of evidence"}
        fix_in = str(args.get("fix_in") or "code")
        if fix_in not in ("code", "config", "data", "external"):
            return {"error": "fix_in must be one of code, config, data, external"}
        hyp.status, hyp.evidence, hyp.reason, hyp.fix_in = status, evidence, str(args.get("reason", "")), fix_in
        self._emit("hypothesis_update", **asdict(hyp))
        return {"id": hyp.id, "status": hyp.status}

    def _regression_test(self, workspace: Workspace, args: dict) -> dict:
        """Add a test that reproduces a bug. It is kept only if it fails now, so it can prove the fix later."""
        code = str(args.get("code", ""))
        if workspace.kind == "maven":
            path = str(args.get("path", "")).replace("\\", "/")
            if not JAVA_TEST_PATH.fullmatch(path):
                return {"error": "path must be a new file like src/test/java/com/acme/FooRegressionTest.java"}
            if f"class {Path(path).stem}" not in code or "@Test" not in code:
                return {"error": f"code must declare class {Path(path).stem} with at least one @Test method"}
        else:
            name = str(args.get("name", ""))
            if not REGRESSION_NAME.fullmatch(name):
                return {"error": "name must be 1-40 lowercase letters, digits or underscores"}
            if "def test_" not in code:
                return {"error": "code must define at least one test function (def test_...)"}
            path = f"tests/test_regression_{name}.py"
        target = workspace.sandbox.resolve(path)
        if target.exists() and path not in self._regression_files:
            return {"error": f"{path} already exists and is not one of your regression tests"}
        self._emit("tool_call", tool="write_regression_test", args={"path": path})
        for node in self._regression_files.pop(path, []):
            self.regression_tests.pop(node, None)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code, encoding="utf-8")
        outcomes, reasons = workspace.test_report(path)
        outcomes = {k: v for k, v in outcomes.items() if k != "(build)"}
        if not outcomes or any(o != "failed" for o in outcomes.values()):
            target.unlink()
            self._emit("regression_test", path=path, accepted=False, tests=outcomes)
            return {
                "accepted": False,
                "outcomes": outcomes or {"(none)": "no tests collected"},
                "reasons": reasons,
                "note": "Not kept: every test must FAIL on the current code (an error or a pass doesn't reproduce the bug).",
            }
        self.regression_tests.update(outcomes)
        self._regression_files[path] = list(outcomes)
        if workspace.kind == "maven" and Path(path).stem not in workspace.extra_tests:
            workspace.extra_tests.append(Path(path).stem)
        self._emit("regression_test", path=path, accepted=True, tests=outcomes, reasons=reasons)
        return {"accepted": True, "path": path, "failing_now": reasons or list(outcomes)}

    def _fix(self, workspace: Workspace, baseline: dict, prompt: str, attempts: int) -> dict:
        """Fix rounds until the harness verifies the patch or the attempts run out."""
        fix_tools = tools_for(self.app, INVESTIGATION_TOOLS) + FIX_TOOLS
        verification = compare_outcomes(baseline, baseline)
        for _ in range(attempts):
            self._attempts += 1
            self._run_phase(workspace, "fix", [{"role": "user", "content": prompt}], fix_tools, MAX_FIX_STEPS)
            after = workspace.test_outcomes()
            verification = compare_outcomes(baseline, after)
            self._emit("verification", attempt=self._attempts, tests=after, **verification)
            if verification["verified"]:
                break
            if not any(o != "passed" for o in baseline.values()):
                break  # nothing failed before the fix, so another attempt can't prove anything either
            prompt = (
                "Verification failed. Still failing: "
                f"{verification['still_failing'] or 'none'}; regressions: {verification['regressions'] or 'none'}. "
                "Investigate why and correct the fix. Do not modify tests."
            )
        return verification

    def _run_phase(self, workspace: Workspace, phase: str, prompt_items: list, tools: list[dict], max_steps: int) -> str:
        self._phase = phase
        self._emit("phase", phase=phase)
        response = self._create(prompt_items, tools)
        for step in range(1, max_steps + 1):
            calls = [item for item in response.output if item.type == "function_call"]
            if not calls:
                text = (response.output_text or "").strip()
                if text:
                    self._emit("message", phase=phase, text=text)
                return text
            outputs: list = [
                {"type": "function_call_output", "call_id": call.call_id, "output": self._dispatch(workspace, call.name, call.arguments, tools)}
                for call in calls
            ]
            spent = self.usage["input_tokens"] + self.usage["output_tokens"]
            if step == max_steps or spent > self.token_budget:
                self._emit("budget", phase=phase, steps=step, tokens=spent)
                outputs.append({"role": "user", "content": "Budget reached. Stop calling tools and summarize what you established."})
                response = self._create(outputs)
                break
            response = self._create(outputs, tools)
        text = (response.output_text or "").strip()
        if text:
            self._emit("message", phase=phase, text=text)
        return text

    # --- the run ------------------------------------------------------------

    def run(self) -> dict:
        self._started = time.monotonic()
        extra = {"image": self.image} if self.image else {}
        extra.update(test_scope=self.test_scope, test_args=self.test_args)
        with Sandbox(self.source, isolation=self.isolation, app=self.app, logs=self.logs, kind=self.kind, **extra) as sandbox:
            workspace = Workspace(sandbox)
            self._emit("start", incident=self.incident, provider=self.provider, model=self.model, isolation=sandbox.isolation)

            if self.seed_requests:
                seeded = workspace.send_batch(self.seed_requests)
                if isinstance(seeded, dict):  # the target failed to start: nothing to investigate against
                    raise RuntimeError(f"seeding traffic failed: {seeded}")
                self._emit("seeded", requests=len(seeded), statuses=[r["status"] for r in seeded])

            log_digest = workspace.log_digest()  # before the test runs add their own log entries
            baseline, reasons = workspace.test_report()
            self._emit("baseline", tests=baseline, tally=_tally(baseline))
            brief = workspace.brief(log_digest, baseline, reasons)
            self._emit("brief", text=brief)

            if workspace.excluded:
                self._emit("excluded_tests", classes=workspace.excluded, reason="they need a database, network or Docker, which the sandbox blocks")
            regression_tool = JAVA_REGRESSION_TOOL if self.kind == "maven" else REGRESSION_TOOL
            investigate_tools = tools_for(self.app, INVESTIGATION_TOOLS) + HYPOTHESIS_TOOLS + [regression_tool]
            self._run_phase(
                workspace,
                "investigate",
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Incident:\n{self.incident}\n\nEvidence brief (computed by the harness):\n{brief}\n\n"
                        "Investigate now. Do not change application code in this phase. "
                        "When every reported symptom has a confirmed root cause, or you have exhausted your options, "
                        "reply with a short summary and no tool calls.",
                    },
                ],
                investigate_tools,
                MAX_INVESTIGATION_STEPS,
            )

            confirmed = [h for h in self.hypotheses.values() if h.status == "confirmed"]
            code_causes = [h for h in confirmed if h.fix_in == "code"]
            reproduced = lambda: any(o != "passed" for o in {**baseline, **self.regression_tests, **self.observed_failures}.values())  # noqa: E731
            if code_causes and not reproduced():
                # A fix that nothing failed before can't be verified: ask once for a reproducing test.
                self._run_phase(
                    workspace,
                    "investigate",
                    [{"role": "user", "content": "No test fails yet, so no fix could be proven. Before any change, reproduce each confirmed "
                      "root cause: run an existing test that fails because of it, or write one with write_regression_test. "
                      "Reply with a short summary when done."}],  # fmt: skip
                    investigate_tools,
                    MAX_REPRODUCE_STEPS,
                )
            # Reproducing tests (written by the agent, or existing ones it saw fail) join the baseline:
            # the fix must turn them green.
            baseline = {**baseline, **self.regression_tests, **self.observed_failures}
            verification = compare_outcomes(baseline, baseline)
            second_opinion = None
            outcome = "no_root_cause"
            if code_causes:
                verification = self._fix(
                    workspace,
                    baseline,
                    "Fix phase. For each confirmed root cause, make the smallest correct change to the application code with edit_file. "
                    "Do not modify tests. Run the relevant tests after editing, then reply with a short summary.",
                    MAX_FIX_ATTEMPTS,
                )
                second_opinion = self._second_opinion(sandbox, verification)
                for _ in range(REVIEW_RETRIES):
                    if not second_opinion or second_opinion.get("verdict") != "reject":
                        break
                    # The models disagree: the reviewer's objections go back to the investigator for one more round.
                    self._emit("review_retry", summary=second_opinion.get("summary", ""), risks=second_opinion.get("risks", []))
                    risks = "\n".join(f"- {r}" for r in second_opinion.get("risks", []))
                    verification = self._fix(
                        workspace,
                        baseline,
                        "An independent reviewer rejected your patch even though the tests pass:\n"
                        f"{second_opinion.get('summary', '')}\n{risks}\n"
                        "Check each objection against the code. Fix the ones that are real, then run the tests and reply with a short summary.",
                        1,
                    )
                    second_opinion = self._second_opinion(sandbox, verification)
                outcome = "fixed" if verification["verified"] else "not_verified"
            elif confirmed:
                # Knowing when not to patch: the cause is real, but the fix doesn't belong in this code.
                outcome = "no_code_change"
                where = ", ".join(sorted({h.fix_in for h in confirmed}))
                self._emit("skip_fix", reason=f"root cause is outside the code ({where}); no code change is the right fix")
            else:
                self._emit("skip_fix", reason="no confirmed root cause")

            findings = self._final_report(verification, second_opinion, sandbox.diff())
            report = {
                "incident": self.incident,
                "provider": self.provider,
                "model": self.model,
                "isolation": sandbox.isolation,
                "hypotheses": [asdict(h) for h in self.hypotheses.values()],
                "findings": findings,
                "diff": sandbox.diff(),
                "verification": verification,
                "outcome": outcome,
                "second_opinion": second_opinion,
                "usage": self.usage,
                "duration_s": round(time.monotonic() - self._started, 1),
            }
            self._emit("report", report=dict(report))  # a copy, so the saved events don't contain themselves
        report["events"] = self.events
        return report

    def _second_opinion(self, sandbox: Sandbox, verification: dict) -> dict | None:
        """Have an independent model review the confirmed causes and the patch. Never fails the run."""
        if self.reviewer is None:
            return None
        self._phase = "review"
        self._emit("phase", phase="review")
        diff = sandbox.diff()
        files = {}
        for path in changed_files(diff):
            try:
                files[path] = sandbox.resolve(path).read_text(encoding="utf-8")
            except (OSError, ValueError):
                continue
        try:
            opinion = self.reviewer.review(self.incident, [asdict(h) for h in self.hypotheses.values()], diff, files, verification)
        except Exception as exc:  # the reviewer is advisory: report the failure and carry on
            opinion = {"verdict": "unavailable", "error": f"{type(exc).__name__}: {exc}"[:300], "model": self.reviewer.model}
        self._emit("second_opinion", **opinion)
        return opinion

    def _final_report(self, verification: dict, second_opinion: dict | None = None, diff: str = "") -> dict:
        """Write the report from the recorded facts in a fresh context, not the whole investigation transcript."""
        self._phase = "report"
        self._emit("phase", phase="report")
        facts = {
            "incident": self.incident,
            "hypotheses": [asdict(h) for h in self.hypotheses.values()],
            "verification": {k: verification[k] for k in ("verified", "fixed", "still_failing", "regressions")},
            "patch": diff or "(no changes)",
        }
        if second_opinion and second_opinion.get("verdict") != "unavailable":
            facts["independent_review"] = {k: second_opinion[k] for k in ("verdict", "summary", "risks")}
        response = self._create(
            [
                {
                    "role": "user",
                    "content": "Write the final report of a software incident investigation. Base it only on these recorded facts; "
                    "each issue's evidence must come from the hypotheses' evidence. For a cause whose fix_in is not code, the fix field "
                    "must say exactly what to change outside the code and who should do it. For a code cause, the fix field describes only "
                    "what the patch below actually changes; anything else you advise (CI, data backfills, monitoring) must start with "
                    "'Recommended, not in this patch:'.\n"
                    f"Recorded facts:\n{json.dumps(facts, indent=2)}",
                }
            ],
            chain=False,
            text={"format": {"type": "json_schema", "name": "InvestigationReport", "schema": REPORT_SCHEMA, "strict": True}},
        )
        try:
            return json.loads(response.output_text)
        except (json.JSONDecodeError, TypeError):
            return {"summary": (response.output_text or "").strip(), "issues": []}


def _names(tools: list[dict]) -> set[str]:
    return {tool["name"] for tool in tools}


def _as_input_item(item: Any) -> dict | None:
    """Turn a response output item into an input item for replaying the transcript."""
    data = item.model_dump(exclude_none=True) if hasattr(item, "model_dump") else dict(vars(item))
    kind = data.get("type")
    if kind == "function_call":
        return {k: data[k] for k in ("type", "call_id", "name", "arguments") if k in data}
    if kind == "message":
        return {"type": "message", "role": "assistant", "content": data.get("content", [])}
    if kind == "reasoning" and data.get("encrypted_content"):
        return {k: data[k] for k in ("type", "id", "summary", "encrypted_content") if k in data}
    return None  # reasoning without replayable content, or unknown items
