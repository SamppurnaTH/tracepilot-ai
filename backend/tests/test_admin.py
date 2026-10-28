"""Admin authentication and authorization use an isolated account database."""
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACEPILOT_ADMIN_DB", str(tmp_path / "admin.sqlite3"))
    monkeypatch.setenv("TRACEPILOT_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("TRACEPILOT_ADMIN_PASSWORD", "admin-secret-12345")
    return TestClient(app)


def sign_in(client, email="admin@example.com", password="admin-secret-12345"):
    response = client.post("/api/admin/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["token"]}


def test_authentication_and_last_admin(client):
    assert client.get("/api/admin/users").status_code == 401
    assert client.post("/api/admin/login", json={"email": "admin@example.com", "password": "wrong"}).status_code == 401
    headers = sign_in(client)
    users = client.get("/api/admin/users", headers=headers).json()
    assert len(users) == 1 and "password" not in users[0]
    assert client.patch(f"/api/admin/users/{users[0]['id']}", headers=headers, json={"role": "viewer", "active": True}).status_code == 409
    assert client.get("/api/admin/overview", headers=headers).status_code == 200
    assert client.post("/api/admin/logout", headers=headers).status_code == 200
    assert client.get("/api/admin/overview", headers=headers).status_code == 401


def test_roles_suspension_and_session_revocation(client):
    headers = sign_in(client)
    account = {"name": "Reader", "email": "reader@example.com", "password": "reader-secret-12345", "role": "viewer"}
    response = client.post("/api/admin/users", headers=headers, json=account)
    assert response.status_code == 201
    uid = response.json()["id"]
    assert client.post("/api/admin/users", headers=headers, json=account).status_code == 409
    viewer = sign_in(client, account["email"], account["password"])
    assert client.get("/api/admin/overview", headers=viewer).status_code == 200
    assert client.get("/api/admin/users", headers=viewer).status_code == 403
    assert client.post("/api/admin/runs/missing/cancel", headers=viewer).status_code == 403
    assert client.patch(f"/api/admin/users/{uid}", headers=headers, json={"role": "operator", "active": True}).status_code == 200
    assert client.get("/api/admin/overview", headers=viewer).status_code == 401
    operator = sign_in(client, account["email"], account["password"])
    assert client.post("/api/admin/runs/missing/cancel", headers=operator).status_code == 404
    assert client.patch(f"/api/admin/users/{uid}", headers=headers, json={"role": "operator", "active": False}).status_code == 200
    assert client.get("/api/admin/overview", headers=operator).status_code == 401
    assert client.post("/api/admin/login", json={"email": account["email"], "password": account["password"]}).status_code == 401


def test_rate_limit_and_no_default_admin(client, monkeypatch, tmp_path):
    for _ in range(5):
        assert client.post("/api/admin/login", json={"email": "unknown@example.com", "password": "wrong"}).status_code == 401
    assert client.post("/api/admin/login", json={"email": "unknown@example.com", "password": "wrong"}).status_code == 429
    monkeypatch.setenv("TRACEPILOT_ADMIN_DB", str(tmp_path / "unconfigured.sqlite3"))
    monkeypatch.delenv("TRACEPILOT_ADMIN_PASSWORD")
    assert client.post("/api/admin/login", json={"email": "admin@example.com", "password": "admin-secret-12345"}).status_code == 401

def test_expired_session_and_cors(client):
    from app.admin import database
    headers = sign_in(client)
    with database() as db:
        db.execute("UPDATE sessions SET expires=0")
        db.commit()
    assert client.get("/api/admin/overview", headers=headers).status_code == 401
    response = client.options("/api/admin/users/test", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "PATCH", "Access-Control-Request-Headers": "authorization,content-type"})
    assert response.status_code == 200
