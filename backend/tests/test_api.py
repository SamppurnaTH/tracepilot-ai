"""API tests with a fake investigation (no model calls, no sandbox)."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from app import main


class FakeInvestigation:
    def __init__(self, scenario, provider, on_event, fail=False, delay=0.0):
        self.scenario, self.on_event, self.fail, self.delay = scenario, on_event, fail, delay

    def run(self) -> dict:
        self.on_event({"seq": 1, "type": "start"})
        time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("sandbox exploded")
        self.on_event({"seq": 2, "type": "verification", "verified": True})
        return {"verification": {"verified": True}, "findings": {"summary": "ok", "issues": []}, "events": ["dropped"]}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "RUNS_DIR", tmp_path)
    monkeypatch.setenv("MODEL_API_KEY", "test-key")
    manager = main.RunManager(factory=lambda s, provider, on_event: FakeInvestigation(s, provider, on_event))
    monkeypatch.setattr(main, "manager", manager)
    return TestClient(main.app)


def wait_done(client, run_id: str) -> dict:
    for _ in range(100):
        data = client.get(f"/api/investigations/{run_id}").json()
        if data["status"] != "running":
            return data
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def stream(client, run_id: str) -> list[tuple[str, dict]]:
    events, kind = [], "message"
    with client.stream("GET", f"/api/investigations/{run_id}/events") as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        for line in resp.iter_lines():
            if line.startswith("event: "):
                kind = line[7:]
            elif line.startswith("data: "):
                events.append((kind, json.loads(line[6:])))
                kind = "message"
    return events


def test_lists_scenarios(client):
    ids = {s["id"] for s in client.get("/api/scenarios").json()}
    assert ids == {"orders", "notes", "billing"}


def test_scenario_summaries_hide_traffic(client):
    # Seed traffic comments describe the defects; only the incident text is public.
    for scenario in client.get("/api/scenarios").json():
        assert set(scenario) == {"id", "title", "service", "incident"}


def test_run_streams_events_and_ends(client):
    started = client.post("/api/investigations", json={"scenario": "orders"})
    assert started.status_code == 202
    run_id = started.json()["id"]
    events = stream(client, run_id)
    assert [e["type"] for kind, e in events if kind == "message"] == ["start", "verification"]
    assert events[-1][0] == "end" and events[-1][1]["verified"] is True
    final = wait_done(client, run_id)
    assert final["status"] == "completed" and "events" not in final["report"]


def test_run_is_saved_for_replay(client):
    run_id = client.post("/api/investigations", json={"scenario": "notes"}).json()["id"]
    wait_done(client, run_id)
    for _ in range(100):  # the file is written just after the status flips to completed
        saved = client.get("/api/runs").json()
        if saved:
            break
        time.sleep(0.05)
    assert saved[0]["scenario"] == "notes" and saved[0]["verified"] is True
    replay = client.get(f"/api/runs/{saved[0]['name']}").json()
    assert [e["type"] for e in replay["events"]] == ["start", "verification"]


def test_failed_run_reports_error(client, monkeypatch):
    main.manager.factory = lambda s, provider, on_event: FakeInvestigation(s, provider, on_event, fail=True)
    run_id = client.post("/api/investigations", json={"scenario": "billing"}).json()["id"]
    final = wait_done(client, run_id)
    assert final["status"] == "failed" and "sandbox exploded" in final["error"]
    assert stream(client, run_id)[-2][1]["type"] == "error"


def test_concurrency_limit(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_CONCURRENT", 1)
    main.manager.factory = lambda s, provider, on_event: FakeInvestigation(s, provider, on_event, delay=0.5)
    first = client.post("/api/investigations", json={"scenario": "orders"})
    second = client.post("/api/investigations", json={"scenario": "orders"})
    assert first.status_code == 202 and second.status_code == 429
    wait_done(client, first.json()["id"])


@pytest.mark.parametrize(
    "body, status",
    [({"scenario": "nope"}, 404), ({"scenario": "orders", "provider": "openai"}, 400)],
)
def test_rejects_bad_requests(client, body, status):
    assert client.post("/api/investigations", json=body).status_code == status


def test_missing_api_key_is_503(client, monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY")
    assert client.post("/api/investigations", json={"scenario": "orders"}).status_code == 503


def test_saved_run_path_traversal_blocked(client):
    assert client.get("/api/runs/..%2F.env").status_code == 404
    assert client.get("/api/investigations/nope").status_code == 404
