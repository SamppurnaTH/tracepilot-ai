"""Agent loop tests driven by a scripted fake model (no API calls)."""

import json
from types import SimpleNamespace

from app.agent import Investigation, compare_outcomes
from conftest import ORDERS_TARGET as SAMPLE_APP
from test_sandbox import COUPON_BUG, COUPON_FIX, IDOR_BUG, IDOR_FIX

COUPON_TEST = "tests/test_orders.py::test_total_without_coupon"
IDOR_TEST = "tests/test_orders.py::test_user_cannot_read_someone_elses_order"


# --- fake Responses API -----------------------------------------------------


def call(name: str, /, **args) -> SimpleNamespace:
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


def test_new_phase_answers_unexecuted_chained_calls():
    pending = call("read_file", path="README.md")
    client = FakeClient([[pending], "next phase"])
    inv = Investigation("incident", SAMPLE_APP, client=client, model="fake")
    inv._call_model([{"role": "user", "content": "summarize"}], None, True)
    inv._call_model([{"role": "user", "content": "next phase"}], None, True)
    request = client.requests[1]
    assert request["previous_response_id"] == "resp-1"
    output = request["input"][0]
    assert output["call_id"] == pending.call_id
    assert output["type"] == "function_call_output"
    assert "not executed" in output["output"]
    assert output in inv._history


def test_chained_tool_output_is_not_duplicated():
    pending = call("read_file", path="README.md")
    client = FakeClient([[pending], "done"])
    inv = Investigation("incident", SAMPLE_APP, client=client, model="fake")
    inv._call_model([], None, True)
    answered = {"type": "function_call_output", "call_id": pending.call_id, "output": "file contents"}
    inv._call_model([answered], None, True)
    assert client.requests[1]["input"] == [answered]


def test_unchanged_collection_error_is_reported_as_unloadable():
    result = compare_outcomes({"tests/test_x.py": "error", "bug": "failed"}, {"tests/test_x.py": "error", "bug": "passed"})
    assert result["verified"]
    assert result["unloadable"] == ["tests/test_x.py"]
    assert not result["still_failing"]
    assert not compare_outcomes({"bug": "failed"}, {"bug": "passed", "tests/test_x.py": "error"})["verified"]


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


def test_run_reports_where_the_time_went():
    import time

    client = FakeClient(
        investigation_script()
        + [
            [call("edit_file", path="orders_api/app.py", old=COUPON_BUG, new=COUPON_FIX), call("edit_file", path="orders_api/app.py", old=IDOR_BUG, new=IDOR_FIX)],
            "Fixed both.",
            REPORT,
        ]
    )
    # Started 3 seconds ago, as when the API spends that long preparing the sandbox image first.
    inv = Investigation("orders_api has errors", SAMPLE_APP, client=client, model="fake", isolation="process", started_at=time.time() - 3)
    report = inv.run()
    timing = report["timing"]
    assert 2.9 <= timing["prepare_s"] <= 4 and report["duration_s"] >= timing["prepare_s"]
    assert set(timing["by_phase"]) == {"investigate", "fix", "report"}
    assert timing["sandbox_s"] > 0 and timing["verify_s"] > 0
    assert inv.timing["tools_s"] > 0  # many sub-millisecond tool calls still add up: nothing is rounded away
    # The parts never add up to more than the run itself.
    parts = timing["prepare_s"] + timing["sandbox_s"] + sum(timing["by_phase"].values())
    assert parts <= report["duration_s"] + 0.2
    assert timing["model_s"] + timing["tools_s"] + timing["verify_s"] <= sum(timing["by_phase"].values()) + 0.2
    # Event times count from when the user started, so the first event comes after the preparation.
    assert report["events"][0]["t"] >= 2.9


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


def test_model_reasoning_is_streamed_as_thinking_events():
    reasoning = SimpleNamespace(type="reasoning", summary=[SimpleNamespace(type="summary_text", text="Comparing the log and the code.")])
    note = SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text="The 500s point at a missing coupon; checking the code.")])
    report, client = run(
        [
            [reasoning, note, call("propose_hypothesis", claim="db is down", symptom="500", next_check="logs")],
            [reasoning, call("resolve_hypothesis", id="H1", status="rejected", evidence=["no db in app"], reason="no database")],
            "Could not find the cause.",
            json.dumps({"summary": "Inconclusive.", "issues": []}),
        ]
    )
    thoughts = [e for e in report["events"] if e["type"] == "thinking"]
    assert thoughts[0]["text"] == "The 500s point at a missing coupon; checking the code."
    assert thoughts[0]["summary"] == "Comparing the log and the code." and thoughts[0]["phase"] == "investigate"
    assert thoughts[1] == {**thoughts[1], "text": "Comparing the log and the code."} and "summary" not in thoughts[1]
    # The phase's final reply is a message event, not a thought.
    assert not any(e["type"] == "thinking" and "Could not find" in e["text"] for e in report["events"])
    assert all(r.get("reasoning") == {"summary": "auto"} for r in client.requests)


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


def test_report_runs_in_a_fresh_context_and_usage_is_split_by_phase():
    report, client = run(
        investigation_script()
        + [[call("edit_file", path="orders_api/app.py", old=COUPON_BUG, new=COUPON_FIX), call("edit_file", path="orders_api/app.py", old=IDOR_BUG, new=IDOR_FIX)], "Fixed both.", REPORT]
    )
    report_request = client.requests[-1]
    assert "previous_response_id" not in report_request
    assert "bob GET /orders/7 -> 200" in report_request["input"][0]["content"]  # the facts carry the evidence
    # The hand-off may only claim what the patch changes; advice is labelled as such.
    assert "Recommended, not in this patch:" in report_request["input"][0]["content"]
    assert set(report["usage"]["by_phase"]) == {"investigate", "fix", "report"}
    # The first prompt carries the harness's evidence brief.
    assert "Evidence brief" in client.requests[0]["input"][1]["content"]
    assert "brief" in [e["type"] for e in report["events"]]


# --- regression tests written by the agent -----------------------------------

INVENTORY = SAMPLE_APP.parent / "inventory"
NEGATIVE_QTY_TEST = """from fastapi.testclient import TestClient
from inventory_api.app import app

client = TestClient(app)


def test_negative_quantity_is_rejected():
    resp = client.post("/reservations", json={"sku": "A-100", "qty": -5}, headers={"Authorization": "Bearer token-alice"})
    assert resp.status_code == 422
"""
PASSING_TEST = "def test_nothing():\n    assert True\n"
QTY_GUARD = ("    if body.qty > STOCK[body.sku]:\n", "    if body.qty <= 0:\n        raise HTTPException(status_code=422, detail=\"bad qty\")\n    if body.qty > STOCK[body.sku]:\n")


def inventory_run(script: list) -> tuple[dict, FakeClient]:
    client = FakeClient(script)
    inv = Investigation("stock is wrong", INVENTORY, client=client, model="fake", isolation="process", app="inventory_api.app:app")
    return inv.run(), client


def test_regression_test_must_fail_first_and_then_proves_the_fix():
    report, client = inventory_run(
        [
            [call("propose_hypothesis", claim="negative qty accepted", symptom="stock above 100", next_check="read reserve")],
            [
                call("resolve_hypothesis", id="H1", status="confirmed", evidence=["app.py reserve has no qty > 0 check"], reason="code"),
                call("write_regression_test", name="always_green", code=PASSING_TEST),
                call("write_regression_test", name="negative_qty", code=NEGATIVE_QTY_TEST),
            ],
            "Confirmed, with a reproducing test.",
            [call("edit_file", path="inventory_api/app.py", old=QTY_GUARD[0], new=QTY_GUARD[1])],
            "Fixed.",
            REPORT,
        ]
    )
    added = [e for e in report["events"] if e["type"] == "regression_test"]
    assert [e["accepted"] for e in added] == [False, True]  # a test that already passes reproduces nothing
    node = "tests/test_regression_negative_qty.py::test_negative_quantity_is_rejected"
    assert report["verification"]["verified"] and report["verification"]["fixed"] == [node]
    assert "+++ b/tests/test_regression_negative_qty.py" in report["diff"]  # the test ships with the patch
    assert "tests/test_regression_always_green.py" not in report["diff"]


def test_green_suite_gets_one_reproduce_step_and_no_pointless_retry():
    report, client = inventory_run(
        [
            [call("propose_hypothesis", claim="negative qty accepted", symptom="stock above 100", next_check="read reserve")],
            [call("resolve_hypothesis", id="H1", status="confirmed", evidence=["app.py reserve"], reason="code")],
            "Confirmed.",
            "I could not write a failing test.",  # the extra reproduce step
            [call("edit_file", path="inventory_api/app.py", old=QTY_GUARD[0], new=QTY_GUARD[1])],
            "Fixed.",
            REPORT,
        ]
    )
    assert not report["verification"]["verified"]  # nothing was failing, so nothing was proven
    phases = [e["phase"] for e in report["events"] if e["type"] == "phase"]
    assert phases[:3] == ["investigate", "investigate", "fix"]
    assert "No test fails yet" in str(client.requests[3]["input"])
    assert sum(e["type"] == "verification" for e in report["events"]) == 1  # a second attempt couldn't prove anything


def test_existing_tests_seen_failing_count_as_reproduction(monkeypatch):
    from app.tools import Workspace

    node = "tests/test_inventory.py::test_reservation_takes_stock"
    monkeypatch.setattr(Workspace, "run_tests", lambda self, selector=None: {"exit_code": 1, "summary": "1 failed", "failed_tests": [node]})
    inv = Investigation("stock is wrong", INVENTORY, client=FakeClient([
        [call("run_tests", selector="tests/test_inventory.py")],
        [call("propose_hypothesis", claim="c", symptom="s", next_check="n")],
        [call("resolve_hypothesis", id="H1", status="confirmed", evidence=["test fails"], reason="r")],
        "Confirmed.",
        "Fixed nothing.",
        REPORT,
    ]), model="fake", isolation="process", app="inventory_api.app:app")  # fmt: skip
    report = inv.run()
    assert inv.observed_failures == {node: "failed"}
    assert "reproduced" in [e["type"] for e in report["events"]]
    phases = [e["phase"] for e in report["events"] if e["type"] == "phase"]
    assert phases.count("investigate") == 1  # already reproduced: no extra step
    # The test passes in reality, so after the (empty) fix it counts as fixed: the harness re-ran it.
    assert node in report["verification"]["fixed"]


def test_regression_tool_is_not_available_while_fixing():
    _, client = run(
        investigation_script()
        + [[call("edit_file", path="orders_api/app.py", old=COUPON_BUG, new=COUPON_FIX), call("edit_file", path="orders_api/app.py", old=IDOR_BUG, new=IDOR_FIX)], "Fixed.", REPORT]
    )
    fix_request = next(r for r in client.requests if r.get("tools") and "edit_file" in {t["name"] for t in r["tools"]})
    assert "write_regression_test" not in {t["name"] for t in fix_request["tools"]}


def test_cause_outside_the_code_means_no_patch():
    report, client = run(
        [
            [call("propose_hypothesis", claim="provider key expired", symptom="refunds fail", next_check="read logs")],
            [call("resolve_hypothesis", id="H1", status="confirmed", evidence=["401 api_key_expired"], reason="logs", fix_in="external")],
            "The provider key expired.",
            REPORT,
        ]
    )
    assert report["outcome"] == "no_code_change" and report["diff"] == ""
    assert "fix" not in [e["phase"] for e in report["events"] if e["type"] == "phase"]
    assert "outside the code (external)" in next(e["reason"] for e in report["events"] if e["type"] == "skip_fix")
    assert "fix_in is not code" in client.requests[-1]["input"][0]["content"]  # the report must say what to do instead


def test_screenshots_reach_the_model_as_images():
    from app.scenarios import SCENARIOS

    checkout = SCENARIOS["checkout"]
    client = FakeClient([[call("propose_hypothesis", claim="c", symptom="s", next_check="n")], "Nothing confirmed.", REPORT])
    inv = Investigation.from_scenario(checkout, client=client, model="fake", isolation="process", reviewer=None)
    report = inv.run()
    first = client.requests[0]["input"][1]["content"]
    assert isinstance(first, list) and first[0]["type"] == "input_text" and "checkout-customer.png" in first[0]["text"]
    assert first[1]["type"] == "input_image" and first[1]["image_url"].startswith("data:image/png;base64,")
    assert [e["name"] for e in report["events"] if e["type"] == "evidence_image"] == ["checkout-customer.png"]


def test_unsupported_screenshot_is_refused(tmp_path):
    import pytest

    bad = tmp_path / "trace.pdf"
    bad.write_bytes(b"%PDF")
    with pytest.raises(ValueError, match="unsupported screenshot type"):
        Investigation("x", SAMPLE_APP, client=object(), model="fake", images=[bad])
