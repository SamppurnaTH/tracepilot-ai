"""A plain coding agent, the baseline TracePilot is compared against.

Same model, same sandbox, same seeded logs and the same basic tools (read files and logs, send
requests, run tests, edit files). What it does not get is TracePilot's method: no hypothesis
tracking, no evidence brief, no reproducing-test rule, no harness verification and no reviewer.
Like a typical coding agent, it may edit tests, and it decides for itself whether it fixed the problem.
"""

import time

from .agent import MAX_FIX_STEPS, MAX_INVESTIGATION_STEPS, Investigation, compare_outcomes
from .sandbox import Sandbox
from .tools import FIX_TOOLS, INVESTIGATION_TOOLS, Workspace, tools_for

PLAIN_PROMPT = """You are a coding agent working in a repository. Fix the problem described by the user.
You can read files and logs, send requests to the app, run the tests and edit files.
When you are done, reply with a short summary and end with exactly one line: RESULT: FIXED or RESULT: NOT FIXED."""


class PlainAgent(Investigation):
    def run(self) -> dict:
        self._started = time.monotonic()
        self.protect_tests = False
        extra = {"image": self.image} if self.image else {}
        extra.update(test_scope=self.test_scope, test_args=self.test_args)
        with Sandbox(self.source, isolation=self.isolation, app=self.app, logs=self.logs, kind=self.kind, **extra) as sandbox:
            workspace = Workspace(sandbox)
            self._emit("start", incident=self.incident, model=self.model, isolation=sandbox.isolation, system="plain")
            if self.seed_requests:
                workspace.send_batch(self.seed_requests)
            before = workspace.test_outcomes()  # for scoring only; the agent never sees it
            text = self._run_phase(
                workspace,
                "agent",
                [{"role": "system", "content": PLAIN_PROMPT}, {"role": "user", "content": self.incident}],
                tools_for(self.app, INVESTIGATION_TOOLS) + FIX_TOOLS,
                MAX_INVESTIGATION_STEPS + MAX_FIX_STEPS,  # the same total step budget TracePilot gets
            )
            after = workspace.test_outcomes()
            diff = sandbox.diff()
        last = text.strip().splitlines()[-1].upper() if text.strip() else ""
        return {
            "claimed_fixed": "RESULT: FIXED" in last,
            "summary": text,
            "diff": diff,
            "visible_tests": compare_outcomes(before, after),
            "usage": self.usage,
            "duration_s": round(time.monotonic() - self._started, 1),
            "events": self.events,
        }
