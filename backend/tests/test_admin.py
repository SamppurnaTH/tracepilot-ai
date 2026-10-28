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

def test_portal_permissions_and_audit(client, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "docker_available", lambda: False)
    admin = sign_in(client)
    assert client.get("/api/admin/roles", headers=admin).status_code == 200
    assert client.get("/api/workspace/me", headers=admin).status_code == 403
    assert client.get("/api/investigations", headers=admin).status_code == 403
    # The example scenarios are the public demo: no sign-in needed to list saved runs or start one.
    assert client.get("/api/runs").status_code == 200
    assert client.post("/api/investigations", json={"scenario": "no-such-scenario"}).status_code == 404
    for role in ("operator", "viewer"):
        email = f"{role}@example.com"
        created = client.post("/api/admin/users", headers=admin, json={"name": role, "email": email, "password": "secure-password-123", "role": role})
        assert created.status_code == 201
        headers = sign_in(client, email, "secure-password-123")
        assert client.get("/api/workspace/me", headers=headers).status_code == 200
        assert client.get("/api/investigations", headers=headers).status_code == 200
        assert client.get("/api/admin/health", headers=headers).status_code == 200
        for path in ("/api/admin/audit", "/api/admin/roles", "/api/admin/settings", "/api/admin/users"):
            assert client.get(path, headers=headers).status_code == 403
        assert client.patch("/api/admin/settings", headers=headers, json={"name":"blocked","description":""}).status_code == 403
        if role == "viewer":
            assert client.post("/api/investigations", headers=headers, json={"scenario":"orders"}).status_code == 403
            assert client.post("/api/investigations/missing/cancel", headers=headers).status_code == 403
            assert client.post("/api/investigations/custom", headers=headers, data={"incident":"This is a test incident"}).status_code == 403
        else:
            assert client.post("/api/investigations/missing/cancel", headers=headers).status_code == 404
    saved = client.patch("/api/admin/settings", headers=admin, json={"name":"Engineering","description":"Runtime debugging"})
    assert saved.status_code == 200
    assert client.get("/api/admin/settings", headers=admin).json()["name"] == "Engineering"
    events = client.get("/api/admin/audit", headers=admin).json()
    assert any(event["event"] == "workspace.settings_updated" for event in events)
    assert any(event["event"] == "user.created" for event in events)
    assert "secure-password" not in str(events)


def test_workspace_grant_and_revocation(client):
    admin = sign_in(client)
    user = client.get("/api/admin/users", headers=admin).json()[0]
    assert not user["workspace_access"]
    response = client.patch(f"/api/admin/users/{user['id']}", headers=admin, json={"role":"admin","active":True,"workspace_access":True})
    assert response.status_code == 200
    assert client.get("/api/workspace/me", headers=admin).status_code == 401
    admin = sign_in(client)
    assert client.get("/api/workspace/me", headers=admin).status_code == 200
    client.patch(f"/api/admin/users/{user['id']}", headers=admin, json={"role":"admin","active":True,"workspace_access":False})
    admin = sign_in(client)
    assert client.get("/api/workspace/me", headers=admin).status_code == 403
    assert client.get("/api/investigations", headers=admin).status_code == 403

def test_existing_account_database_migration(client, monkeypatch, tmp_path):
    import sqlite3
    from app.admin import password_hash, database
    legacy = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(legacy) as db:
        db.execute("CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, password TEXT NOT NULL)")
        db.execute("INSERT INTO users VALUES ('legacy','legacy@example.com','Existing Admin','admin',1,?)", (password_hash("existing-secret-12345"),))
        db.commit()
    monkeypatch.setenv("TRACEPILOT_ADMIN_DB", str(legacy))
    with database() as db:
        account = db.execute("SELECT * FROM users WHERE id='legacy'").fetchone()
        assert account["name"] == "Existing Admin"
        assert account["workspace_access"] == 0
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    headers = sign_in(client, "legacy@example.com", "existing-secret-12345")
    assert client.get("/api/admin/overview", headers=headers).status_code == 200
    assert client.get("/api/workspace/me", headers=headers).status_code == 403
