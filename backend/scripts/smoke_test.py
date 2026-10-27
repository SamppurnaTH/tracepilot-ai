"""Day-1 smoke test for the Meta Model API.

Checks the three capabilities TracePilot depends on:
  1. a basic Responses API call
  2. tool calling (model asks to read a log, we return synthetic lines)
  3. structured output (model returns a root-cause hypothesis as JSON)

Run from the repo root:  .venv/Scripts/python backend/scripts/smoke_test.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm import get_client  # noqa: E402

SYNTHETIC_LOG = "\n".join(
    [
        '{"ts":"2026-10-27T10:01:12Z","level":"INFO","request_id":"r-101","method":"GET","path":"/orders/7/total","status":200}',
        '{"ts":"2026-10-27T10:01:15Z","level":"ERROR","request_id":"r-102","method":"GET","path":"/orders/9/total","status":500,'
        '"error":"TypeError: \'NoneType\' object is not subscriptable","where":"orders_api/app.py:compute_total"}',
    ]
)

READ_LOG_TOOL = {
    "type": "function",
    "name": "read_log",
    "description": "Return recent log lines for a service in the sandboxed sample app.",
    "parameters": {
        "type": "object",
        "properties": {"service": {"type": "string", "description": "Service name, e.g. 'orders_api'"}},
        "required": ["service"],
        "additionalProperties": False,
    },
}

HYPOTHESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "claim": {"type": "string", "description": "One-sentence root-cause hypothesis"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "next_check": {"type": "string", "description": "The diagnostic step that would confirm or reject the claim"},
    },
    "required": ["claim", "evidence", "confidence", "next_check"],
    "additionalProperties": False,
}


def check_basic(client, model) -> None:
    resp = client.responses.create(model=model, input="Reply with exactly: TracePilot online")
    print(f"  reply: {resp.output_text.strip()!r}  (tokens: {resp.usage.total_tokens})")


def check_tool_calling(client, model) -> None:
    resp = client.responses.create(
        model=model,
        input="GET /orders/9/total is returning 500 in orders_api. Look at the logs and tell me what failed.",
        tools=[READ_LOG_TOOL],
    )
    calls = [item for item in resp.output if item.type == "function_call"]
    if not calls:
        raise AssertionError(f"model did not call a tool; replied: {resp.output_text[:200]!r}")
    call = calls[0]
    print(f"  model called: {call.name}({call.arguments})")

    resp = client.responses.create(
        model=model,
        input=[{"type": "function_call_output", "call_id": call.call_id, "output": SYNTHETIC_LOG}],
        previous_response_id=resp.id,
        tools=[READ_LOG_TOOL],
    )
    print(f"  answer after tool result: {resp.output_text.strip()[:300]!r}")


def check_structured_output(client, model) -> None:
    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": "You are a debugging agent. Form one testable root-cause hypothesis."},
            {"role": "user", "content": f"Logs from orders_api:\n{SYNTHETIC_LOG}"},
        ],
        text={"format": {"type": "json_schema", "name": "Hypothesis", "schema": HYPOTHESIS_SCHEMA, "strict": True}},
    )
    hypothesis = json.loads(resp.output_text)
    missing = set(HYPOTHESIS_SCHEMA["required"]) - hypothesis.keys()
    if missing:
        raise AssertionError(f"missing fields: {missing}")
    print("  " + json.dumps(hypothesis, indent=2).replace("\n", "\n  "))


def main() -> int:
    client, model = get_client()
    print(f"Model: {model}\n")
    failed = 0
    for name, check in [
        ("basic call", check_basic),
        ("tool calling", check_tool_calling),
        ("structured output", check_structured_output),
    ]:
        print(f"[{name}]")
        try:
            check(client, model)
            print("  PASS\n")
        except Exception as exc:  # report every check, don't stop at the first failure
            failed += 1
            print(f"  FAIL: {type(exc).__name__}: {exc}\n")
    print("All checks passed." if not failed else f"{failed} check(s) failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
