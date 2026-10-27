"""Let the model drive the evidence tools against the sample app in a short loop.

A rough preview of the agent loop, used to check that the tools are usable by the model.
Run from the repo root:  .venv/Scripts/python backend/scripts/try_tools.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import REPO_ROOT  # noqa: E402
from app.llm import get_client  # noqa: E402
from app.tools import TOOL_SPECS, Workspace, execute_tool  # noqa: E402

MAX_STEPS = 12

TASK = """You are TracePilot, a software investigation agent. Two reports came in for the orders_api service:
1. Users say GET /orders/9/total sometimes returns 500.
2. A security reviewer suspects users can see other users' orders.

Investigate both with the tools. Valid test tokens: 'token-alice' (user 1) and 'token-bob' (user 2).
Do not guess: confirm each root cause with evidence (logs, code with line numbers, a reproduced request, or a test).
Do not modify any code. Finish with a short report: for each issue, the root cause, the evidence, and the fix you'd propose."""


def main() -> None:
    client, model = get_client()
    workspace = Workspace(REPO_ROOT / "sample_app")

    response = client.responses.create(model=model, input=TASK, tools=TOOL_SPECS)
    for step in range(1, MAX_STEPS + 1):
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            break
        outputs = []
        for call in calls:
            result = execute_tool(workspace, call.name, call.arguments)
            preview = result if len(result) < 160 else result[:160] + "..."
            print(f"[step {step}] {call.name}({call.arguments})\n         -> {preview}")
            outputs.append({"type": "function_call_output", "call_id": call.call_id, "output": result})
        response = client.responses.create(
            model=model, input=outputs, previous_response_id=response.id, tools=TOOL_SPECS
        )
    else:
        print(f"\nStopped after {MAX_STEPS} steps.")

    print("\n=== Report ===\n")
    print(response.output_text)
    print(f"\n(tokens in last call: {response.usage.total_tokens})")


if __name__ == "__main__":
    main()
