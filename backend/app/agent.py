"""TracePilot agent: investigate -> fix -> verify -> report.

The model drives investigation and fixing through tools. The harness owns the facts:
it records hypotheses, enforces which tools each phase may use, protects the tests,
and decides whether a fix is verified by comparing per-test outcomes before and after.
"""

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from .llm import get_client
from .sandbox import Sandbox
from .tools import FIX_TOOLS, INVESTIGATION_TOOLS, Workspace, execute_tool

EventSink = Callable[[dict], None]

MAX_INVESTIGATION_STEPS = 16
MAX_FIX_STEPS = 10
MAX_FIX_ATTEMPTS = 2
REPEAT_LIMIT = 2
PROTECTED_PREFIXES = ("tests/", "tests\\")

SYSTEM_PROMPT = """You are TracePilot, an evidence-driven software investigation agent.
You investigate failures in an application running in an isolated sandbox, then fix and verify them.

Rules:
- Work hypothesis-first. Before chasing a possible cause, register it with propose_hypothesis.
- Resolve every hypothesis with resolve_hypothesis as confirmed or rejected, citing concrete evidence
  you gathered with tools: log request ids, file paths with line numbers, reproduced request results, test names.
- Never confirm a hypothesis from intuition alone. If evidence contradicts it, reject it and form a better one.
- Look for the cause of every reported symptom, and note any closely related defect you discover.
- Tests are the ground truth: never weaken or edit them."""

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
            },
            "required": ["id", "status", "evidence", "reason"],
            "additionalProperties": False,
        },
    },
]

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


def compare_outcomes(before: dict[str, str], after: dict[str, str]) -> dict:
    """Decide verification from per-test outcomes: every failing test fixed, nothing newly broken."""
    fixed = sorted(t for t, o in before.items() if o != "passed" and after.get(t) == "passed")
    still_failing = sorted(t for t, o in after.items() if o != "passed" and before.get(t, "failed") != "passed")
    regressions = sorted(t for t, o in before.items() if o == "passed" and after.get(t) != "passed")
    missing = sorted(t for t in before if t not in after)
    verified = bool(before) and not still_failing and not regressions and not missing
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
    ):
        self.incident = incident
        self.source = source
        self.provider = provider
        self.on_event = on_event or (lambda event: None)
        self.isolation = isolation
        if client is None:
            client, model = get_client(provider)
        self.client, self.model = client, model
        self.hypotheses: dict[str, Hypothesis] = {}
        self.events: list[dict] = []
        self.usage = {"input_tokens": 0, "output_tokens": 0, "model_calls": 0, "tool_calls": 0}
        self._previous_id: str | None = None
        self._call_counts: dict[str, int] = {}
        self._started = 0.0

    # --- plumbing -----------------------------------------------------------

    def _emit(self, type_: str, **data) -> None:
        event = {"seq": len(self.events) + 1, "t": round(time.monotonic() - self._started, 2), "type": type_, **data}
        self.events.append(event)
        self.on_event(event)

    def _create(self, input_items: list, tools: list[dict] | None = None, **kwargs):
        params: dict[str, Any] = {"model": self.model, "input": input_items, **kwargs}
        if tools:
            params["tools"] = tools
        if self._previous_id:
            params["previous_response_id"] = self._previous_id
        response = self.client.responses.create(**params)
        self._previous_id = response.id
        self.usage["model_calls"] += 1
        if getattr(response, "usage", None):
            self.usage["input_tokens"] += response.usage.input_tokens or 0
            self.usage["output_tokens"] += response.usage.output_tokens or 0
        for item in response.output:
            if item.type == "reasoning":
                summary = " ".join(getattr(part, "text", "") for part in (getattr(item, "summary", None) or []))
                if summary.strip():
                    self._emit("thinking", text=summary.strip())
        return response

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
        if name == "edit_file" and str(args.get("path", "")).startswith(PROTECTED_PREFIXES):
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
        hyp.status, hyp.evidence, hyp.reason = status, evidence, str(args.get("reason", ""))
        self._emit("hypothesis_update", **asdict(hyp))
        return {"id": hyp.id, "status": hyp.status}

    def _run_phase(self, workspace: Workspace, phase: str, prompt_items: list, tools: list[dict], max_steps: int) -> str:
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
            if step == max_steps:
                self._emit("budget", phase=phase, steps=max_steps)
                outputs.append({"role": "user", "content": "Step budget reached. Stop calling tools and summarize what you established."})
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
        with Sandbox(self.source, isolation=self.isolation) as sandbox:
            workspace = Workspace(sandbox)
            self._emit("start", incident=self.incident, provider=self.provider, model=self.model, isolation=sandbox.isolation)

            baseline = workspace.test_outcomes()
            self._emit("baseline", tests=baseline, tally=_tally(baseline))

            investigate_tools = INVESTIGATION_TOOLS + HYPOTHESIS_TOOLS
            self._run_phase(
                workspace,
                "investigate",
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Incident:\n{self.incident}\n\nInvestigate now. Do not change any code in this phase. "
                        "When every reported symptom has a confirmed root cause, or you have exhausted your options, "
                        "reply with a short summary and no tool calls.",
                    },
                ],
                investigate_tools,
                MAX_INVESTIGATION_STEPS,
            )

            confirmed = [h for h in self.hypotheses.values() if h.status == "confirmed"]
            verification = compare_outcomes(baseline, baseline)
            if confirmed:
                fix_tools = INVESTIGATION_TOOLS + FIX_TOOLS
                prompt = (
                    "Fix phase. For each confirmed root cause, make the smallest correct change to the application code with edit_file. "
                    "Do not modify tests. Run the relevant tests after editing, then reply with a short summary."
                )
                for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
                    self._run_phase(workspace, "fix", [{"role": "user", "content": prompt}], fix_tools, MAX_FIX_STEPS)
                    after = workspace.test_outcomes()
                    verification = compare_outcomes(baseline, after)
                    self._emit("verification", attempt=attempt, tests=after, **verification)
                    if verification["verified"]:
                        break
                    prompt = (
                        "Verification failed. Still failing: "
                        f"{verification['still_failing'] or 'none'}; regressions: {verification['regressions'] or 'none'}. "
                        "Investigate why and correct the fix. Do not modify tests."
                    )
            else:
                self._emit("skip_fix", reason="no confirmed root cause")

            findings = self._final_report(verification)
            report = {
                "incident": self.incident,
                "provider": self.provider,
                "model": self.model,
                "isolation": sandbox.isolation,
                "hypotheses": [asdict(h) for h in self.hypotheses.values()],
                "findings": findings,
                "diff": sandbox.diff(),
                "verification": verification,
                "usage": self.usage,
                "duration_s": round(time.monotonic() - self._started, 1),
            }
            self._emit("report", report=dict(report))  # a copy, so the saved events don't contain themselves
        report["events"] = self.events
        return report

    def _final_report(self, verification: dict) -> dict:
        self._emit("phase", phase="report")
        facts = {
            "hypotheses": [asdict(h) for h in self.hypotheses.values()],
            "verification": {k: verification[k] for k in ("verified", "fixed", "still_failing", "regressions")},
        }
        response = self._create(
            [
                {
                    "role": "user",
                    "content": "Write the final investigation report. Base it only on what you established. "
                    f"Recorded facts:\n{json.dumps(facts, indent=2)}",
                }
            ],
            text={"format": {"type": "json_schema", "name": "InvestigationReport", "schema": REPORT_SCHEMA, "strict": True}},
        )
        try:
            return json.loads(response.output_text)
        except (json.JSONDecodeError, TypeError):
            return {"summary": (response.output_text or "").strip(), "issues": []}


def _names(tools: list[dict]) -> set[str]:
    return {tool["name"] for tool in tools}
