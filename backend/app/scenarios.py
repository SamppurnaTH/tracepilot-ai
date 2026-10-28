"""Demo scenarios: a target app, a symptom-only incident report, and seed traffic.

The harness replays the seed traffic inside each sandbox before the investigation starts,
so every run gets fresh, realistic logs. Nothing here is visible to the agent except the
incident text: this module is never copied into the sandbox.
"""

from dataclasses import dataclass

from .config import REPO_ROOT

TARGETS = REPO_ROOT / "targets"
ALICE = {"Authorization": "Bearer token-alice"}
BOB = {"Authorization": "Bearer token-bob"}


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    service: str
    app: str  # "module:attribute" of the ASGI app inside the target
    incident: str
    traffic: tuple  # (method, path, headers) or (method, path, headers, json_body) tuples, replayed in order
    log_files: tuple = ()  # recorded production logs (paths relative to the repo root, outside the target)

    @property
    def target(self):
        return TARGETS / self.id

    def seed_requests(self) -> list[dict]:
        return [
            {"method": method, "path": path, "headers": {**headers, "x-request-id": f"r-{101 + i}"}, "body": body[0] if body else None}
            for i, (method, path, headers, *body) in enumerate(self.traffic)
        ]

    def logs(self) -> list:
        return [REPO_ROOT / p for p in self.log_files]

    def summary(self) -> dict:
        return {"id": self.id, "title": self.title, "service": self.service, "incident": self.incident}


SCENARIOS: dict[str, Scenario] = {
    s.id: s
    for s in [
        Scenario(
            id="orders",
            title="Orders API: intermittent 500s and a data-exposure report",
            service="orders_api",
            app="orders_api.app:app",
            incident="""Two reports came in for the orders_api service:
1. Users say GET /orders/9/total sometimes returns 500.
2. A security reviewer suspects users can see other users' orders.

Test credentials for the sandbox: 'token-alice' (user 1) and 'token-bob' (user 2), sent as 'Authorization: Bearer <token>'.""",
            traffic=(
                ("GET", "/orders/7", ALICE),
                ("GET", "/orders/7/total", ALICE),
                ("GET", "/orders/8/total", ALICE),
                ("GET", "/orders/9", BOB),
                ("GET", "/orders/9/total", BOB),  # 500: order without a coupon
                ("GET", "/orders/7", BOB),  # 200: bob reads alice's order
                ("GET", "/orders/8", BOB),  # 200: bob reads alice's order
                ("GET", "/orders/7", {}),  # 401
                ("GET", "/orders/9/total", BOB),  # 500 again
            ),
        ),
        Scenario(
            id="notes",
            title="Notes API: search errors and noisy warnings",
            service="notes_api",
            app="notes_api.app:app",
            incident="""Support tickets for the notes_api service:
1. Searching for a note whose title contains an apostrophe (for example "Bob's") fails with a server error.
2. On-call noticed WARNING entries in the logs this morning and wants to know whether they are related.

Test credentials for the sandbox: 'token-alice' (user 1) and 'token-bob' (user 2), sent as 'Authorization: Bearer <token>'.""",
            traffic=(
                ("GET", "/notes", ALICE),
                ("GET", "/notes/search?q=Groceries", ALICE),
                ("GET", "/notes/export", ALICE),  # slow: WARNING, unrelated red herring
                ("GET", "/notes", BOB),
                ("GET", "/notes/search?q=Bob's", BOB),  # 500: quote breaks the SQL string
                ("GET", "/notes/search?q=Meeting", BOB),
                ("GET", "/notes/export", BOB),  # slow again
                ("GET", "/notes/search?q=Bob's%20passwords", BOB),  # 500 again
            ),
        ),
        Scenario(
            id="billing",
            title="Billing API: a disputed invoice and missing invoices",
            service="billing_api",
            app="billing_api.app:app",
            incident="""Two tickets came in for the billing_api service:
1. Customer initech disputes invoice 1003: by their own calculation the total should be 54.13, but the invoice shows 54.12.
2. A customer says the first page of their invoice list never shows their earliest invoices.""",
            traffic=(
                ("GET", "/invoices/1001", {}),
                ("GET", "/invoices/1002", {}),
                ("GET", "/invoices/1003", {}),  # total 54.12, should be 54.13
                ("GET", "/invoices?page=1&size=2", {}),  # returns 1003, 1004
                ("GET", "/invoices?page=2&size=2", {}),
                ("GET", "/invoices?page=3&size=2", {}),  # empty
                ("GET", "/invoices/1003", {}),
            ),
        ),
        Scenario(
            id="inventory",
            title="Inventory API: phantom stock and an oversold item, with green CI",
            service="inventory_api",
            app="inventory_api.app:app",
            incident="""Two tickets came in for the inventory_api service:
1. The warehouse counted 100 units of SKU A-100, but the API reports more than 100 available.
2. SKU C-300 was oversold: customers reserved 5 units, but only 3 exist.
CI is green on the latest deploy, so no existing test catches either problem.

Test credentials for the sandbox: 'token-alice' (user 1) and 'token-bob' (user 2), sent as 'Authorization: Bearer <token>'.""",
            traffic=(
                ("GET", "/stock/A-100", ALICE),
                ("POST", "/reservations", ALICE, {"sku": "A-100", "qty": 10}),
                ("POST", "/reservations", BOB, {"sku": "A-100", "qty": -15}),  # accepted: stock goes up
                ("GET", "/stock/A-100", ALICE),  # 105, more than the warehouse holds
                ("POST", "/reservations", BOB, {"sku": "C-300", "qty": 2}),
                ("DELETE", "/reservations/3", BOB),
                ("DELETE", "/reservations/3", BOB),  # cancelled twice: stock returned twice
                ("GET", "/stock/C-300", ALICE),  # 5, only 3 exist
                ("POST", "/reservations", ALICE, {"sku": "C-300", "qty": 5}),  # oversold
            ),
        ),
        Scenario(
            id="refunds",
            title="Refunds API: refunds failing right after a deploy",
            service="refunds_api",
            app="refunds_api.app:app",
            incident="""Refunds have been failing since this morning: customers get an error and support is escalating.
It started right after this morning's deploy of v2.14.0, so on-call suspects the release.
Find what broke and fix it.""",
            traffic=(),
            log_files=("demo/logs/refunds_api.log",),  # recorded in production; the provider can't be reached from a sandbox
        ),
    ]
}
