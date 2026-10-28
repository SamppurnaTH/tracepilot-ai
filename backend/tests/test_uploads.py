"""Bring-your-own-project API: ZIP uploads, repository URLs, attachments and stopping a run (no model calls)."""

import io
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import main
from app.agent import Cancelled
from app.uploads import UploadError, clone_repo, extract_zip
from conftest import ORDERS_TARGET


def project_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


class FakeCustom:
    """Records how the API built the investigation; can wait for a stop request."""

    built: list[dict] = []

    def __init__(self, incident, root, on_event, wait_for_stop=False, **kw):
        self.incident, self.root, self.on_event, self.kw = incident, root, on_event, kw
        self.should_stop = None
        FakeCustom.built.append({"incident": incident, "root": root, "files": sorted(p.name for p in root.rglob("*") if p.is_file()), **kw})

    def run(self) -> dict:
        self.on_event({"seq": 1, "type": "start"})
        for _ in range(100):
            if self.kw.get("test_args") == ["-Dslow=1"] and self.should_stop and self.should_stop():
                raise Cancelled("stopped")
            if self.kw.get("test_args") != ["-Dslow=1"]:
                break
            time.sleep(0.05)
        return {"verification": {"verified": True}, "findings": {"summary": "ok", "issues": []}, "outcome": "fixed"}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "RUNS_DIR", tmp_path)
    monkeypatch.setenv("MODEL_API_KEY", "test-key")
    monkeypatch.setattr(main, "docker_available", lambda: False)
    FakeCustom.built = []
    manager = main.RunManager(custom_factory=FakeCustom)
    monkeypatch.setattr(main, "manager", manager)
    return TestClient(main.app)


def wait(client, run_id, until=("completed", "failed", "cancelled")) -> dict:
    for _ in range(100):
        data = client.get(f"/api/investigations/{run_id}").json()
        if data["status"] in until:
            return data
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_zip_upload_runs_an_investigation_with_attachments(client):
    files = {"svc/app.py": "from fastapi import FastAPI\napp = FastAPI()\n", "svc/tests/test_x.py": "def test_x():\n    assert True\n"}
    resp = client.post(
        "/api/investigations/custom",
        data={"incident": "Checkout returns 500 for empty carts"},
        files=[
            ("project", ("svc.zip", project_zip(files), "application/zip")),
            ("logs", ("app.log", b'{"level": "ERROR"}\n', "text/plain")),
            ("screenshots", ("cart.png", b"\x89PNG fake", "image/png")),
        ],
    )
    assert resp.status_code == 202, resp.text
    run = wait(client, resp.json()["id"])
    assert run["status"] == "completed" and run["title"] == "svc"
    built = FakeCustom.built[0]
    assert built["root"].name == "svc"  # a single top-level folder is unwrapped
    assert built["app"] == "app:app" and built["kind"] == "python"
    assert [p.name for p in built["logs"]] == ["app.log"] and [p.name for p in built["images"]] == ["cart.png"]
    assert not built["root"].exists()  # the upload is deleted once the run ends


def test_zip_with_path_traversal_is_refused(client):
    resp = client.post(
        "/api/investigations/custom",
        data={"incident": "Something is broken here"},
        files=[("project", ("evil.zip", project_zip({"../escape.py": "x = 1"}), "application/zip"))],
    )
    assert resp.status_code == 400 and "unsafe path" in resp.json()["detail"]


def test_project_or_repo_is_required_and_only_one(client):
    assert client.post("/api/investigations/custom", data={"incident": "Something is broken here"}).status_code == 400
    both = client.post(
        "/api/investigations/custom",
        data={"incident": "Something is broken here", "repo_url": "https://github.com/a/b"},
        files=[("project", ("p.zip", project_zip({"a.py": ""}), "application/zip"))],
    )
    assert both.status_code == 400


@pytest.mark.parametrize("url", ["http://github.com/a/b", "https://evil.example/a/b", "https://github.com/a/b; rm -rf /", "git@github.com:a/b.git"])
def test_only_public_https_repos_on_known_hosts(url, tmp_path):
    with pytest.raises(UploadError):
        clone_repo(url, tmp_path / "clone")


def test_attachments_must_have_expected_types(client):
    resp = client.post(
        "/api/investigations/custom",
        data={"incident": "Something is broken here"},
        files=[("project", ("p.zip", project_zip({"a.py": ""}), "application/zip")), ("screenshots", ("x.exe", b"MZ", "application/octet-stream"))],
    )
    assert resp.status_code == 400 and "expected one of" in resp.json()["detail"]


def test_not_a_zip_is_refused(tmp_path):
    with pytest.raises(UploadError, match="not a valid ZIP"):
        extract_zip(b"plain text", tmp_path / "out")


def test_a_running_investigation_can_be_stopped(client):
    resp = client.post(
        "/api/investigations/custom",
        data={"incident": "Something is broken here", "test_args": "-Dslow=1"},
        files=[("project", ("p.zip", project_zip({"a.py": ""}), "application/zip"))],
    )
    run_id = resp.json()["id"]
    time.sleep(0.2)
    assert client.post(f"/api/investigations/{run_id}/cancel").status_code == 200
    run = wait(client, run_id)
    assert run["status"] == "cancelled" and run["error"] == "stopped by the user"


def test_real_target_zip_detects_python_and_app(client):
    files = {str(p.relative_to(ORDERS_TARGET)).replace("\\", "/"): p.read_text(encoding="utf-8") for p in ORDERS_TARGET.rglob("*.py")}
    resp = client.post(
        "/api/investigations/custom",
        data={"incident": "Orders total fails without a coupon"},
        files=[("project", ("orders.zip", project_zip(files), "application/zip"))],
    )
    wait(client, resp.json()["id"])
    assert FakeCustom.built[0]["app"] == "orders_api.app:app"
