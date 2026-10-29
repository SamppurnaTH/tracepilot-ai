"""The ablation must change evidence delivery, not verification or source data."""
from app.agent import Investigation
from app.baseline import PlainAgent
from conftest import ORDERS_TARGET
from test_agent import FakeClient, REPORT


def test_no_brief_removes_only_model_brief_delivery():
    client = FakeClient(["No cause established", REPORT])
    result = Investigation("incident", ORDERS_TARGET, client=client, model="fake", isolation="process", include_brief=False).run()
    assert "Evidence brief" not in str(client.requests[0]["input"])
    assert any(e["type"] == "brief" and e["supplied_to_model"] is False for e in result["events"])
    assert not result["verification"]["verified"]


def test_plain_brief_is_an_explicit_control():
    client = FakeClient(["RESULT: NOT FIXED"])
    result = PlainAgent("incident", ORDERS_TARGET, client=client, model="fake", isolation="process", include_brief=True).run()
    assert "Evidence brief" in str(client.requests[0]["input"])
    assert "hypotheses" not in result and not result["claimed_fixed"]
