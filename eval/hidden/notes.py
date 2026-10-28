"""Hidden acceptance tests for notes: a different injection payload than the visible tests use."""

from fastapi.testclient import TestClient

from notes_api.app import app

client = TestClient(app)
ALICE = {"Authorization": "Bearer token-alice"}
BOB = {"Authorization": "Bearer token-bob"}


def test_union_injection_cannot_read_other_users_notes():
    resp = client.get("/notes/search", params={"q": "a'b' UNION SELECT id, title FROM notes --"}, headers=ALICE)
    assert resp.status_code == 200
    assert all(n["id"] in (1, 2) for n in resp.json())


def test_apostrophes_still_match():
    resp = client.get("/notes/search", params={"q": "Bob's"}, headers=BOB)
    assert resp.status_code == 200 and [n["id"] for n in resp.json()] == [3]
