"""Tests for the Notes API."""

from fastapi.testclient import TestClient

from notes_api.app import app

client = TestClient(app)
ALICE = {"Authorization": "Bearer token-alice"}
BOB = {"Authorization": "Bearer token-bob"}


def test_list_own_notes():
    resp = client.get("/notes", headers=ALICE)
    assert [n["id"] for n in resp.json()] == [1, 2]


def test_search_finds_matching_titles():
    resp = client.get("/notes/search", params={"q": "Project"}, headers=ALICE)
    assert resp.status_code == 200
    assert [n["id"] for n in resp.json()] == [2]


def test_search_with_apostrophe():
    resp = client.get("/notes/search", params={"q": "Bob's"}, headers=BOB)
    assert resp.status_code == 200
    assert [n["id"] for n in resp.json()] == [3]


def test_search_only_returns_own_notes():
    # Whatever the query text, a user may only ever see their own notes.
    for q in ["%", "' OR '1'='1", "' OR 1=1 --"]:
        resp = client.get("/notes/search", params={"q": q}, headers=ALICE)
        assert resp.status_code == 200
        assert all(n["id"] in (1, 2) for n in resp.json()), q


def test_export_requires_auth():
    assert client.get("/notes/export").status_code == 401
