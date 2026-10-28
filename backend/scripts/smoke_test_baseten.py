"""Smoke test for Muse Spark Open (Meta open weights) served by Baseten.

Same three checks as smoke_test.py, over the Chat Completions API:
basic call, tool calling, and structured output.

Run from the repo root:  .venv/Scripts/python backend/scripts/smoke_test_baseten.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.llm import extract_json, get_client, json_instruction  # noqa: E402
from smoke_test import HYPOTHESIS_SCHEMA, READ_LOG_TOOL, SYNTHETIC_LOG  # noqa: E402

# Chat Completions nests function metadata under "function".
CHAT_READ_LOG_TOOL = {
    "type": "function",
    "function": {k: READ_LOG_TOOL[k] for k in ("name", "description", "parameters")},
}


def reasoning_note(message) -> str:
    reasoning = getattr(message, "reasoning_content", None) or getattr(message, "reasoning", None)
    return f", reasoning: {len(reasoning)} chars" if reasoning else ""


def check_basic(client, model) -> None:
    resp = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": "Reply with exactly: TracePilot online"}]
    )
    msg = resp.choices[0].message
    print(f"  reply: {(msg.content or '').strip()!r}  (tokens: {resp.usage.total_tokens}{reasoning_note(msg)})")


def check_tool_calling(client, model) -> None:
    messages = [
        {
            "role": "user",
            "content": "GET /orders/9/total is returning 500 in orders_api. Look at the logs and tell me what failed.",
        }
    ]
    resp = client.chat.completions.create(model=model, messages=messages, tools=[CHAT_READ_LOG_TOOL])
    msg = resp.choices[0].message
    if not msg.tool_calls:
        raise AssertionError(f"model did not call a tool; replied: {(msg.content or '')[:200]!r}")
    call = msg.tool_calls[0]
    print(f"  model called: {call.function.name}({call.function.arguments})")

    messages.append(
        {
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        }
    )
    messages.extend({"role": "tool", "tool_call_id": tc.id, "content": SYNTHETIC_LOG} for tc in msg.tool_calls)
    resp = client.chat.completions.create(model=model, messages=messages, tools=[CHAT_READ_LOG_TOOL])
    print(f"  answer after tool result: {(resp.choices[0].message.content or '').strip()[:300]!r}")


def check_structured_output(client, model) -> None:
    # Prompt-based JSON: constrained decoding (response_format) on Baseten pads the output with whitespace.
    resp = client.chat.completions.create(
        model=model,
        max_tokens=4000,
        messages=[
            {
                "role": "system",
                "content": "You are a debugging agent. Form one testable root-cause hypothesis. "
                + json_instruction(HYPOTHESIS_SCHEMA),
            },
            {"role": "user", "content": f"Logs from orders_api:\n{SYNTHETIC_LOG}"},
        ],
    )
    hypothesis = extract_json(resp.choices[0].message.content or "", HYPOTHESIS_SCHEMA)
    print(f"  (completion tokens: {resp.usage.completion_tokens})")
    print("  " + json.dumps(hypothesis, indent=2).replace("\n", "\n  "))


def main() -> int:
    client, model = get_client("baseten")
    print(f"Provider: baseten  Model: {model}\n")
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
