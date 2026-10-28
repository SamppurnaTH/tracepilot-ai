"""Authenticated administration of local accounts and investigation operations."""
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from .config import REPO_ROOT

router = APIRouter(prefix="/api/admin", tags=["admin"])
workspace_router = APIRouter(prefix="/api/workspace", tags=["workspace"])
PERMISSIONS = {
    "admin": ["dashboard.read", "investigations.read", "investigations.stop", "reports.read", "users.manage", "roles.read", "settings.manage", "health.read", "audit.read"],
    "operator": ["dashboard.read", "investigations.read", "investigations.stop", "reports.read", "health.read"],
    "viewer": ["dashboard.read", "investigations.read", "reports.read", "health.read"],
}


def audit(db, actor: str, event: str, target: str = "", detail: str = ""):
    db.execute("INSERT INTO audit (at,actor,event,target,detail) VALUES (?,?,?,?,?)", (time.time(), actor, event, target, detail))


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()
    return f"{salt}:{digest}"


@contextmanager
def database():
    path = Path(os.environ.get("TRACEPILOT_ADMIN_DB", str(REPO_ROOT / "runs" / "admin.sqlite3")))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, password TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires REAL NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS login_attempts (email TEXT PRIMARY KEY, started REAL NOT NULL, attempts INTEGER NOT NULL)")
    columns = {r[1] for r in db.execute("PRAGMA table_info(users)")}
    if "workspace_access" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN workspace_access INTEGER NOT NULL DEFAULT 1")
        db.execute("UPDATE users SET workspace_access=0 WHERE role='admin'")
        db.commit()
    db.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, actor TEXT NOT NULL, event TEXT NOT NULL, target TEXT NOT NULL, detail TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS workspace_settings (id INTEGER PRIMARY KEY CHECK(id=1), name TEXT NOT NULL, description TEXT NOT NULL)")
    db.execute("INSERT OR IGNORE INTO workspace_settings VALUES (1,'TracePilot Workspace','Verification-first AI debugging')")
    db.commit()
    email, password = os.environ.get("TRACEPILOT_ADMIN_EMAIL"), os.environ.get("TRACEPILOT_ADMIN_PASSWORD")
    if email and password and len(password) >= 12 and not db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        db.execute("INSERT OR IGNORE INTO users (id,email,name,role,active,password,workspace_access) VALUES (?,?,?,?,?,?,0)", (secrets.token_hex(12), email.strip().lower(), "Administrator", "admin", 1, password_hash(password)))
        db.commit()
    try:
        yield db
    finally:
        db.close()


def public(user):
    return {**{k: user[k] for k in ("id", "email", "name", "role")}, "active": bool(user["active"]), "workspace_access": bool(user["workspace_access"]), "permissions": PERMISSIONS[user["role"]]}


def current_user(authorization: str = Header(default="")):
    token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
    with database() as db:
        row = db.execute("SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token=? AND s.expires>? AND u.active=1", (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
    if not row:
        raise HTTPException(401, "Sign in to the admin plane")
    return public(row)


def administrator(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Administrator role required")
    return user


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class Account(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    name: str = Field(min_length=1, max_length=100)
    role: Literal["admin", "operator", "viewer"] = "viewer"
    password: str = Field(min_length=12, max_length=256)
    workspace_access: bool | None = None


class Access(BaseModel):
    workspace_access: bool | None = None
    role: Literal["admin", "operator", "viewer"]
    active: bool


@router.post("/login")
def login(body: Login):
    with database() as db:
        email = body.email.strip().lower()
        now = time.time()
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM login_attempts WHERE started<?", (now - 60,))
        attempts = db.execute("SELECT attempts FROM login_attempts WHERE email=?", (email,)).fetchone()
        if attempts and attempts[0] >= 5:
            raise HTTPException(429, "Too many sign-in attempts. Try again in one minute.")
        db.execute("INSERT INTO login_attempts VALUES (?,?,1) ON CONFLICT(email) DO UPDATE SET attempts=attempts+1", (email, now))
        db.commit()
        row = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        # Pay the same password derivation cost for unknown accounts.
        stored = row["password"] if row else password_hash("invalid-account", "00" * 16)
        valid = hmac.compare_digest(stored, password_hash(body.password, stored.split(":")[0]))
        if not row or not valid or not row["active"]:
            audit(db, email, "auth.failed", email, "Invalid credentials or inactive account")
            db.commit()
            raise HTTPException(401, "Invalid email or password")
        db.execute("DELETE FROM login_attempts WHERE email=?", (email,))
        token = secrets.token_urlsafe(48)
        db.execute("DELETE FROM sessions WHERE expires<=?", (time.time(),))
        db.execute("INSERT INTO sessions VALUES (?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), row["id"], time.time() + 8 * 3600))
        db.commit()
        audit(db, row["email"], "auth.signed_in", row["id"])
        db.commit()
        return {"token": token, "user": public(row)}


@router.post("/logout")
def logout(authorization: str = Header(default=""), user=Depends(current_user)):
    with database() as db:
        audit(db, user["email"], "auth.signed_out", user["id"])
        db.execute("DELETE FROM sessions WHERE token=?", (hashlib.sha256(authorization.removeprefix("Bearer ").encode()).hexdigest(),))
        db.commit()
    return {"ok": True}


@router.get("/users")
def users(user=Depends(administrator)):
    with database() as db:
        return [public(r) for r in db.execute("SELECT * FROM users ORDER BY name")]


@router.post("/users", status_code=201)
def create_user(body: Account, user=Depends(administrator)):
    with database() as db:
        try:
            uid = secrets.token_hex(12)
            db.execute("INSERT INTO users (id,email,name,role,active,password,workspace_access) VALUES (?,?,?,?,?,?,?)", (uid, body.email.strip().lower(), body.name.strip(), body.role, 1, password_hash(body.password), int(body.workspace_access if body.workspace_access is not None else body.role != "admin")))
            audit(db, user["email"], "user.created", body.email.strip().lower(), f"Role: {body.role}")
            db.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(409, "An account with this email already exists")
        return public(db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())


@router.patch("/users/{uid}")
def update_user(uid: str, body: Access, user=Depends(administrator)):
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not row:
            raise HTTPException(404, "User not found")
        if row["role"] == "admin" and row["active"] and (body.role != "admin" or not body.active):
            if db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0] <= 1:
                raise HTTPException(409, "Keep at least one active administrator")
        workspace_access = row["workspace_access"] if body.workspace_access is None else int(body.workspace_access)
        db.execute("UPDATE users SET role=?, active=?, workspace_access=? WHERE id=?", (body.role, int(body.active), workspace_access, uid))
        audit(db, user["email"], "user.access_updated", row["email"], f"Role: {body.role}; active: {body.active}; workspace: {bool(workspace_access)}")
        db.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        db.commit()
        return public(db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())


@router.get("/overview")
def overview(user=Depends(current_user)):
    from . import main
    with database() as db:
        total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        active_users = db.execute("SELECT COUNT(DISTINCT user_id) FROM sessions WHERE expires>?", (time.time(),)).fetchone()[0]
        recent_events = db.execute("SELECT COUNT(*) FROM audit WHERE at>? AND event='auth.failed'", (time.time() - 86400,)).fetchone()[0]
        workspace = dict(db.execute("SELECT name,description FROM workspace_settings WHERE id=1").fetchone())
    return {"workspace": workspace, "total_users": total_users, "active_users": active_users, "security_events": recent_events if user["role"] == "admin" else None, "user": user, "active": main.manager.active(), "max_concurrent": main.MAX_CONCURRENT, "daily_limit": main.DAILY_LIMIT, "uploads_need_key": bool(main._upload_key()), "require_docker": os.environ.get("TRACEPILOT_REQUIRE_DOCKER") == "1", "runs": main.list_investigations()}


@router.post("/runs/{run_id}/cancel")
def stop_run(run_id: str, user=Depends(current_user)):
    if user["role"] not in ("admin", "operator"):
        raise HTTPException(403, "Operator or administrator role required")
    from .main import cancel_investigation
    result = cancel_investigation(run_id)
    with database() as db:
        audit(db, user["email"], "investigation.stop_requested", run_id)
        db.commit()
    return result



def workspace_user(user=Depends(current_user)):
    if not user["workspace_access"]:
        raise HTTPException(403, "User workspace access has not been granted to this account")
    return user


def workspace_writer(user=Depends(workspace_user)):
    if user["role"] not in ("admin", "operator"):
        raise HTTPException(403, "Read-only workspace access: an operator or administrator must start or stop investigations")
    return user


@workspace_router.get("/me")
def workspace_me(user=Depends(workspace_user)):
    with database() as db:
        workspace = dict(db.execute("SELECT name,description FROM workspace_settings WHERE id=1").fetchone())
    return {"user": user, "workspace": workspace, "can_write": user["role"] in ("admin", "operator")}


@router.get("/roles")
def roles(user=Depends(administrator)):
    return [{"role": role, "permissions": permissions} for role, permissions in PERMISSIONS.items()]


class WorkspaceSettings(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(max_length=240)


@router.get("/settings")
def settings(user=Depends(administrator)):
    with database() as db:
        return dict(db.execute("SELECT name,description FROM workspace_settings WHERE id=1").fetchone())


@router.patch("/settings")
def update_settings(body: WorkspaceSettings, user=Depends(administrator)):
    if not body.name.strip():
        raise HTTPException(422, "Workspace name cannot be blank")
    with database() as db:
        db.execute("UPDATE workspace_settings SET name=?,description=? WHERE id=1", (body.name.strip(), body.description.strip()))
        audit(db, user["email"], "workspace.settings_updated", body.name.strip())
        db.commit()
    return {"name": body.name.strip(), "description": body.description.strip()}


@router.get("/audit")
def audit_logs(user=Depends(administrator)):
    with database() as db:
        return [dict(row) for row in db.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 200")]


@router.get("/health")
def system_health(user=Depends(current_user)):
    from . import main
    docker = main.docker_available()
    with database() as db:
        db.execute("SELECT 1").fetchone()
    return {"checked_at": time.time(), "services": [
        {"name": "Backend API", "status": "healthy", "detail": "Authenticated API request succeeded"},
        {"name": "Account database", "status": "healthy", "detail": "SQLite read/write connection available"},
        {"name": "Docker sandbox", "status": "healthy" if docker else "unavailable", "detail": "Docker is available" if docker else "Docker is not reachable"},
        {"name": "Meta Model API", "status": "configured" if os.environ.get("MODEL_API_KEY") else "not configured", "detail": "Configuration check; no model request sent"},
        {"name": "AI reviewer", "status": "configured" if os.environ.get("BASETEN_API_KEY") else "not configured", "detail": "Configuration check; no model request sent"},
    ]}


@router.get("/reports")
def reports(user=Depends(current_user)):
    from .main import list_saved_runs
    return list_saved_runs()


@router.get("/reports/{name}")
def report(name: str, user=Depends(current_user)):
    from .main import get_saved_run
    return get_saved_run(name)


@router.get("/runs/{run_id}")
def run_detail(run_id: str, user=Depends(current_user)):
    from .main import get_investigation
    return get_investigation(run_id)
