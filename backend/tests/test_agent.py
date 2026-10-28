"""Agent loop tests driven by a scripted fake model (no API calls)."""

import json
from types import SimpleNamespace

from app.agent import Investigation, compare_outcomes
from conftest import ORDERS_TARGET as SAMPLE_APP
from test_sandbox import COUPON_BUG, COUPON_FIX, IDOR_BUG, IDOR_FIX

COUPON_TEST = "tests/test_orders.py::test_total_without_coupon"
IDOR_TEST = "tests/test_orders.py::test_user_cannot_read_someone_elses_order"


# --- fake Responses API -----------------------------------------------------


def call(name: str, **args) -> SimpleNamespace:
    return SimpleNamespace(type="function_call", name=name, arguments=json.dumps(args), call_id=f"c-{name}-{id(args)}")


class FakeClient:
    """Returns scripted responses in order and records every request."""

    def __init__(self, script: list):
        self.script = list(script)
        self.requests: list[dict] = []
        self.responses = self

    def create(self, **params):
        self.requests.append(params)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        if isinstance(step, str):
            output, text = [], step
        else:
            output, text = step, ""
        return SimpleNamespace(
            id=f"resp-{len(self.requests)}",
            output=output,
            output_text=text,
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )


REPORT = json.dumps(
    {
        "summary": "Two issues found and fixed.",
        "issues": [
            {
                "title": "Missing coupon crashes totals",
                "category": "reliability",
                "severity": "high",
                "root_cause": "compute_total assumes a coupon",
                "evidence": ["r-105 TypeError"],
                "fix": "default to no discount",
                "hypothesis_ids": ["H1"],
            }
        ],
    }
)


def run(script: list) -> tuple[dict, FakeClient]:
    client = FakeClient(script)
    report = Investigation("orders_api has errors", SAMPLE_APP, client=client, model="fake", isolation="process").run()
    return report, client


def investigation_script() -> list:
    return [
        [call("propose_hypothesis", claim="coupon None crashes totals", symptom="500 on /total", next_check="read compute_total")],
        [
            call("read_file", path="orders_api/app.py"),
            call("resolve_hypothesis", id="H1", status="confirmed", evidence=["app.py compute_total subscripts coupon"], reason="seen in code"),
            call("propose_hypothesis", claim="read_order lacks ownership check", symptom="cross-user reads", next_check="request as bob"),
        ],
        [call("resolve_hypothesis", id="H2", status="confirmed", evidence=["bob GET /orders/7 -> 200"], reason="reproduced")],
        "Both root causes confirmed.",
    ]


# --- verification logic -----------------------------------------------------


def test_compare_outcomes_verified():
    before = {"a": "passed", "b": "failed"}
    result = compare_outcomes(before, {"a": "passed", "b": "passed"})
    assert result["verified"] and result["fixed"] == ["b"]


def test_compare_outcomes_regression_fails_verification():
    result = compare_outcomes({"a": "passed", "b": "failed"}, {"a": "failed", "b": "passed"})
    assert not result["verified"] and result["regressions"] == ["a"]


def test_compare_outcomes_deleted_test_fails_verification():
    result = compare_outcomes({"a": "passed", "b": "failed"}, {"a": "passed"})
    assert not result["verified"] and result["missing"] == ["b"]


# --- end-to-end with the fake model ----------------------------------------


def test_full_run_verifies_fix():
    report, client = run(
        investigation_script()
        + [
            [call("edit_file", path="orders_api/app.py", old=COUPON_BUG, new=COUPON_FIX), call("edit_file", path="orders_api/app.py", old=IDOR_BUG, new=IDOR_FIX)],
            "Fixed both.",
            REPORT,
        ]
    )
    assert [h["status"] for h in report["hypotheses"]] == ["confirmed", "confirmed"]
    assert report["verification"]["verified"]
    assert set(report["verification"]["fixed"]) == {COUPON_TEST, IDOR_TEST}
    assert "+    " + COUPON_FIX in report["diff"]
    assert report["findings"]["issues"][0]["category"] == "reliability"
    json.dumps(report)  # the saved run must be serializable (no self-references)
    types = [e["type"] for e in report["events"]]
    assert types.index("baseline") < types.index("hypothesis") < types.index("patch") < types.index("verification")
    # The investigation phase must not offer edit tools.
    first_tools = {t["name"] for t in client.requests[0]["tools"]}
    assert "edit_file" not in first_tools and "propose_hypothesis" in first_tools


def test_recovers_when_server_loses_conversation():
    import httpx
    import openai

    expired = openai.BadRequestError(
        "referenced response not found or expired",
        response=httpx.Response(400, request=httpx.Request("POST", "https://api.example/v1/responses")),
        body=None,
    )
    script = investigation_script()
    # Lose the chain right when the fix phase starts; the retry gets the edit response.
    fix = [call("edit_file", path="orders_api/app.py", old=COUPON_BUG, new=COUPON_FIX), call("edit_file", path="orders_api/app.py", old=IDOR_BUG, new=IDOR_FIX)]
    report, client = run(script + [expired, fix, "Fixed both.", REPORT])
    assert report["verification"]["verified"]
    assert any(e["type"] == "recovered" for e in report["events"])
    retry = client.requests[5]
    assert "previous_response_id" not in retry
    replayed = retry["input"]
    assert replayed[0]["role"] == "system" and any(i.get("type") == "function_call" for i in replayed)
    assert any(i.get("type") == "function_call_output" for i in replayed)


def test_tests_cannot_be_edited():
    report, _ = run(
        investigation_script()
        + [
            [call("edit_file", path="tests/test_orders.py", old="assert resp.status_code == 404", new="assert True")],
            "Done.",
            # attempt 2 after failed verification
            [call("edit_file", path="orders_api/app.py", old=COUPON_BUG, new=COUPON_FIX), call("edit_file", path="orders_api/app.py", old=IDOR_BUG, new=IDOR_FIX)],
            "Fixed properly.",
            REPORT,
        ]
    )
    assert any(e["type"] == "blocked" for e in report["events"])
    assert "tests/test_orders.py" not in report["diff"]
    attempts = [e for e in report["events"] if e["type"] == "verification"]
    assert [a["verified"] for a in attempts] == [False, True]


def test_no_confirmed_hypothesis_skips_fix():
    report, client = run(
        [
            [call("propose_hypothesis", claim="db is down", symptom="500", next_check="logs")],
            [call("resolve_hypothesis", id="H1", status="rejected", evidence=["no db in app"], reason="no database")],
            "Could not find the cause.",
            json.dumps({"summary": "Inconclusive.", "issues": []}),
        ]
    )
    assert any(e["type"] == "skip_fix" for e in report["events"])
    assert report["diff"] == "" and not report["verification"]["verified"]


def test_confirm_without_evidence_is_refused():
    report, client = run(
        [
            [call("propose_hypothesis", claim="x", symptom="y", next_check="z")],
            [call("resolve_hypothesis", id="H1", status="confirmed", evidence=[], reason="trust me")],
            "Done.",
            json.dumps({"summary": "-", "issues": []}),
        ]
    )
    assert report["hypotheses"][0]["status"] == "open"
    tool_output = client.requests[2]["input"][0]["output"]
    assert "needs at least one piece of evidence" in tool_output


def test_repeated_calls_get_a_nudge():
    same = [call("read_file", path="orders_api/app.py")]
    report, client = run([same, same, same, "Stopped.", json.dumps({"summary": "-", "issues": []})])
    third_output = client.requests[3]["input"][0]["output"]
    assert "Try a different check" in third_output


def test_step_budget_forces_summary(monkeypatch):
    monkeypatch.setattr("app.agent.MAX_INVESTIGATION_STEPS", 2)
    loop = [call("read_file", path=".")]
    report, client = run([loop, loop, "Summary after budget.", json.dumps({"summary": "-", "issues": []})])
    assert any(e["type"] == "budget" for e in report["events"])
    assert "tools" not in client.requests[2]
