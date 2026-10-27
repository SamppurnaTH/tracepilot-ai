"""Send one HTTP request to the target app in-process and print the result as JSON.

Executed inside the sandbox (python -c <this file>). Reads a JSON spec from stdin:
{"app": "orders_api.app:app", "method": "GET", "path": "/orders/7", "headers": {}, "body": null}
"""

import importlib
import json
import sys

sys.path.insert(0, ".")
spec = json.loads(sys.stdin.read())

from fastapi.testclient import TestClient  # noqa: E402

module_name, _, attr = spec["app"].partition(":")
app = getattr(importlib.import_module(module_name), attr or "app")

client = TestClient(app, raise_server_exceptions=False)
resp = client.request(spec["method"], spec["path"], headers=spec.get("headers") or {}, json=spec.get("body"))
try:
    body = resp.json()
except ValueError:
    body = resp.text[:2000]
print(json.dumps({"status": resp.status_code, "body": body}))
