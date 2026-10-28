"""Send HTTP requests to the target app in-process and print the results as JSON.

Executed inside the sandbox (python -c <this file>). Reads a JSON spec from stdin:
{"app": "orders_api.app:app", "requests": [{"method": "GET", "path": "/orders/7", "headers": {}, "body": null}, ...]}
All requests in one spec share one app instance, like real traffic to a running service.
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
results = []
for req in spec["requests"]:
    resp = client.request(req["method"], req["path"], headers=req.get("headers") or {}, json=req.get("body"))
    try:
        body = resp.json()
    except ValueError:
        body = resp.text[:2000]
    results.append({"status": resp.status_code, "body": body})
print(json.dumps(results))
