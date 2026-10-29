"""Second-opinion reviewer tests with a scripted fake Chat Completions client (no API calls)."""

import json
from types import SimpleNamespace

import pytest

from app.agent import Investigation
from app.reviewer import Reviewer, changed_files
from conftest import ORDERS_TARGET as SAMPLE_APP
from test_agent import REPORT, FakeClient, call, investigation_script
from test_sandbox import COUPON_BUG, COUPON_FIX, IDOR_BUG, IDOR_FIX

APPROVE = {
    "verdict": "approve",
    "confidence": "high",
    "summary": "Both root causes are fixed at the source.",
    "hypotheses": [{"id": "H1", "assessment": "supported", "note": "code cited"}],
    "risks": [],
}


class FakeChat:
    """Returns scripted chat replies in order and records every request."""

    def __init__(self, replies: list):
        self.replies = list(replies)
        self.requests: list[dict] = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **params):
        self.requests.append(params)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=reply))],
            usage=SimpleNamespace(total_tokens=100),
        )


def fix_script() -> list:
    return investigation_script() + [
        [call("edit_file", path="orders_api/app.py", old=COUPON_BUG, new=COUPON_FIX), call("edit_file", path="orders_api/app.py", old=IDOR_BUG, new=IDOR_FIX)],
        "Fixed both.",
        REPORT,
    ]


def run_with(reviewer: Reviewer | None, script: list | None = None) -> tuple[dict, FakeClient]:
    client = FakeClient(script or fix_script())
    inv = Investigation("orders_api has errors", SAMPLE_APP, client=client, model="fake", isolation="process", reviewer=reviewer)
    return inv.run(), client


def test_review_parses_verdict_and_metadata():
    chat = FakeChat([f"Here you go:\n{json.dumps(APPROVE)}"])
    opinion = Reviewer(chat, "open-model").review("incident", [], "diff", {}, {"verified": True})
    assert opinion["verdict"] == "approve" and opinion["model"] == "open-model" and opinion["tokens"] == 100


def test_review_retries_once_on_invalid_json():
    chat = FakeChat(["not json", json.dumps({**APPROVE, "verdict": "concerns"})])
    opinion = Reviewer(chat, "m").review("incident", [], "", {}, {})
    assert opinion["verdict"] == "concerns" and opinion["tokens"] == 200
    assert "not valid" in chat.requests[1]["messages"][-1]["content"]


def test_review_raises_after_two_invalid_replies():
    chat = FakeChat(["nope", json.dumps({**APPROVE, "verdict": "maybe"})])
    with pytest.raises(ValueError):
        Reviewer(chat, "m").review("incident", [], "", {}, {})


def test_changed_files_reads_diff_headers():
    diff = "--- a/app/x.py\n+++ b/app/x.py\n@@ -1 +1 @@\n-a\n+b\n--- a/y.py\n+++ b/y.py\n"
    assert changed_files(diff) == ["app/x.py", "y.py"]


def test_private_meta_reviewer_endpoint_requires_explicit_configuration(monkeypatch):
    monkeypatch.setenv("REVIEWER_BASE_URL", "http://localhost:9000/v1")
    monkeypatch.delenv("REVIEWER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="requires REVIEWER_API_KEY"):
        Reviewer.from_env()
    monkeypatch.setenv("REVIEWER_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("REVIEWER_MODEL", "internal-meta-open-weights")
    reviewer = Reviewer.from_env()
    assert reviewer.provider == "custom" and reviewer.model == "internal-meta-open-weights"


def test_run_includes_second_opinion_with_patched_code():
    chat = FakeChat([json.dumps(APPROVE)])
    report, client = run_with(Reviewer(chat, "open-model"))
    assert report["second_opinion"]["verdict"] == "approve"
    types = [e["type"] for e in report["events"]]
    assert types.index("verification") < types.index("second_opinion") < types.index("report")
    # The reviewer sees the evidence, the patch and the full patched file, but not the investigation transcript.
    prompt = chat.requests[0]["messages"][-1]["content"]
    assert "bob GET /orders/7 -> 200" in prompt and COUPON_FIX in prompt and "orders_api/app.py (after the patch)" in prompt
    assert "Both root causes confirmed." not in prompt
    # The final report is told about the independent review.
    assert "independent_review" in client.requests[-1]["input"][0]["content"]


def test_reviewer_failure_does_not_fail_the_run():
    chat = FakeChat([RuntimeError("baseten down")])
    report, _ = run_with(Reviewer(chat, "open-model"))
    assert report["verification"]["verified"]
    assert report["second_opinion"]["verdict"] == "unavailable" and "baseten down" in report["second_opinion"]["error"]


def test_no_reviewer_means_no_second_opinion():
    report, _ = run_with(None)
    assert report["second_opinion"] is None
    assert "second_opinion" not in [e["type"] for e in report["events"]]


def test_green_tests_with_unresolved_concerns_require_review():
    from app.handoff import markdown_report, pr_description
    concerns = {**APPROVE, "verdict": "concerns", "summary": "A valid input can still hang.", "risks": ["zero-progress loop"]}
    report, _ = run_with(Reviewer(FakeChat([json.dumps(concerns)]), "open-model"))
    assert report["verification"]["verified"]  # bounded test facts remain true
    assert report["outcome"] == "needs_review"
    assert "Tests verified; review required" in markdown_report(report, "incident")
    assert "resolve the reviewer's objections" in pr_description(report)


def test_rejection_sends_the_patch_back_for_another_round():
    reject = {**APPROVE, "verdict": "reject", "summary": "Only order 7 is protected.", "risks": ["IDOR remains for order 8"]}
    chat = FakeChat([json.dumps(reject), json.dumps(APPROVE)])
    script = fix_script()
    script[-1:-1] = ["Checked the objection; the check is already generic."]  # the review-driven fix round
    report, client = run_with(Reviewer(chat, "open-model"), script)
    types = [e["type"] for e in report["events"]]
    assert types.count("second_opinion") == 2 and "review_retry" in types
    assert report["second_opinion"]["verdict"] == "approve"
    retry_prompt = next(r for r in client.requests if "independent reviewer rejected" in str(r.get("input")))
    assert "IDOR remains for order 8" in str(retry_prompt["input"])
    assert [e["attempt"] for e in report["events"] if e["type"] == "verification"] == [1, 2]


def test_exhausted_rejection_does_not_become_a_ready_fix():
    reject = {**APPROVE, "verdict": "reject", "summary": "A valid input still hangs.", "risks": ["zero-progress loop"]}
    script = fix_script()
    script[-1:-1] = ["No additional edit made."]
    report, _ = run_with(Reviewer(FakeChat([json.dumps(reject), json.dumps(reject)]), "open-model"), script)
    assert report["verification"]["verified"] and report["outcome"] == "needs_review"
