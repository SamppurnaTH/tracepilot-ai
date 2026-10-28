"""Every scenario must be fair and solvable.

Its seed traffic reproduces the reported symptoms, exactly the expected tests fail,
a known-good fix makes the whole suite pass, and the target contains no hints.
The reference fixes below are the answer key; they live here, never in a target.
"""

import pytest

from app.agent import compare_outcomes
from app.scenarios import SCENARIOS, TARGETS
from app.tools import Workspace
from conftest import open_seeded

INVENTORY_REGRESSION = """from fastapi.testclient import TestClient

from inventory_api import app as inventory
from inventory_api.app import app

client = TestClient(app)
ALICE = {"Authorization": "Bearer token-alice"}


def setup_function():
    inventory.STOCK.update({"A-100": 100, "B-200": 20, "C-300": 3})
    inventory.RESERVATIONS.clear()


def test_negative_quantity_cannot_add_stock():
    client.post("/reservations", json={"sku": "A-100", "qty": -5}, headers=ALICE)
    assert client.get("/stock/A-100").json()["available"] == 100


def test_cancelling_twice_returns_stock_once():
    rid = client.post("/reservations", json={"sku": "C-300", "qty": 2}, headers=ALICE).json()["id"]
    client.delete(f"/reservations/{rid}", headers=ALICE)
    client.delete(f"/reservations/{rid}", headers=ALICE)
    assert client.get("/stock/C-300").json()["available"] == 3
"""

CHECKOUT_REGRESSION = """from fastapi.testclient import TestClient

from checkout_api.app import app

client = TestClient(app)


def test_percent_coupon_counts_every_unit():
    lines = [{"sku": "LAMP-20", "qty": 2}, {"sku": "MUG-08", "qty": 1}]
    resp = client.post("/checkout/quote", json={"lines": lines, "coupon": "SAVE10"})
    assert resp.json() == {"subtotal": 48.0, "discount": 4.8, "total": 43.2}
"""

EXPECTED = {
    "orders": {
        "seed_statuses": [200, 200, 200, 200, 500, 200, 200, 401, 500],
        "failing": {
            "tests/test_orders.py::test_user_cannot_read_someone_elses_order",
            "tests/test_orders.py::test_total_without_coupon",
        },
        "fixes": [
            (
                "orders_api/app.py",
                'discount = subtotal * order["coupon"]["percent"] / 100',
                'discount = subtotal * (order["coupon"] or {}).get("percent", 0) / 100',
            ),
            (
                "orders_api/app.py",
                "    order = get_order_or_404(order_id)\n    return order\n",
                '    order = get_order_or_404(order_id)\n    if order["owner_id"] != user["id"]:\n'
                '        raise HTTPException(status_code=404, detail="order not found")\n    return order\n',
            ),
        ],
    },
    "notes": {
        "seed_statuses": [200, 200, 200, 200, 500, 200, 200, 500],
        "failing": {
            "tests/test_notes.py::test_search_with_apostrophe",
            "tests/test_notes.py::test_search_only_returns_own_notes",
        },
        "fixes": [
            (
                "notes_api/app.py",
                "    sql = f\"SELECT id, title FROM notes WHERE owner_id = {user['id']} AND title LIKE '%{q}%' ORDER BY id\"\n"
                "    rows = db.execute(sql).fetchall()\n",
                '    sql = "SELECT id, title FROM notes WHERE owner_id = ? AND title LIKE ? ORDER BY id"\n'
                '    rows = db.execute(sql, (user["id"], f"%{q}%")).fetchall()\n',
            ),
        ],
    },
    "billing": {
        "seed_statuses": [200] * 7,
        "failing": {
            "tests/test_billing.py::test_invoice_total_rounds_tax_half_up",
            "tests/test_billing.py::test_first_page_starts_with_first_invoice",
            "tests/test_billing.py::test_pages_cover_every_invoice_once",
        },
        "fixes": [
            (
                "billing_api/app.py",
                "    subtotal = sum(line[\"unit_price\"] * line[\"qty\"] for line in invoice[\"lines\"])\n"
                "    total = round(subtotal + subtotal * TAX_RATE, 2)\n"
                "    tax = round(total - subtotal, 2)\n"
                '    return {"subtotal": round(subtotal, 2), "tax": tax, "total": total}\n',
                "    from decimal import ROUND_HALF_UP, Decimal\n\n"
                "    cent = Decimal(\"0.01\")\n"
                "    subtotal = sum(Decimal(str(line[\"unit_price\"])) * line[\"qty\"] for line in invoice[\"lines\"])\n"
                "    tax = (subtotal * Decimal(str(TAX_RATE))).quantize(cent, ROUND_HALF_UP)\n"
                "    total = subtotal + tax\n"
                '    return {"subtotal": float(subtotal.quantize(cent)), "tax": float(tax), "total": float(total.quantize(cent))}\n',
            ),
            ("billing_api/app.py", "    offset = page * size\n", "    offset = (page - 1) * size\n"),
        ],
    },
    # The cause is outside the code (an expired provider API key): the right answer is no patch.
    "refunds": {"seed_statuses": [201] * 5 + [502] * 4, "failing": set(), "no_code_fix": True, "fixes": []},
    # The specifics (cart, coupon, wrong discount) are only in the customer's screenshot; CI is green.
    "checkout": {
        "seed_statuses": [200, 200, 200, 200],
        "failing": set(),
        "regression": CHECKOUT_REGRESSION,
        "fixes": [
            (
                "checkout_api/app.py",
                '    return sum(CATALOG[line.sku]["price"] * coupon["value"] / 100 for line in lines)\n',
                '    return subtotal * coupon["value"] / 100\n',
            )
        ],
    },
    # No existing test catches these bugs: a reproducing regression test must be written first.
    "inventory": {
        "seed_statuses": [200, 201, 201, 200, 201, 200, 200, 200, 201],
        "failing": set(),
        "regression": INVENTORY_REGRESSION,
        "fixes": [
            (
                "inventory_api/app.py",
                "    if body.qty > STOCK[body.sku]:\n",
                "    if body.qty <= 0:\n"
                '        raise HTTPException(status_code=422, detail="quantity must be positive")\n'
                "    if body.qty > STOCK[body.sku]:\n",
            ),
            (
                "inventory_api/app.py",
                '    STOCK[reservation["sku"]] += reservation["qty"]\n',
                '    if reservation["status"] == "cancelled":\n'
                '        raise HTTPException(status_code=409, detail="reservation already cancelled")\n'
                '    STOCK[reservation["sku"]] += reservation["qty"]\n',
            ),
        ],
    },
}


def test_every_scenario_has_expectations():
    assert set(EXPECTED) == set(SCENARIOS)


@pytest.fixture(params=sorted(SCENARIOS))
def scenario_sandbox(request):
    scenario = SCENARIOS[request.param]
    sb = open_seeded(scenario, "process")
    yield scenario, sb
    sb.__exit__(None, None, None)


def test_seed_traffic_reproduces_symptoms(scenario_sandbox):
    scenario, sb = scenario_sandbox
    entries = Workspace(sb).read_log(service=scenario.service, limit=200)["entries"]
    statuses = [e["status"] for e in entries if "status" in e]
    assert statuses == EXPECTED[scenario.id]["seed_statuses"]


def test_exactly_the_expected_tests_fail(scenario_sandbox):
    scenario, sb = scenario_sandbox
    outcomes = Workspace(sb).test_outcomes()
    failing = {t for t, o in outcomes.items() if o != "passed"}
    assert failing == EXPECTED[scenario.id]["failing"]
    assert len(outcomes) > len(failing), "each target needs passing tests too"


def test_reference_fix_verifies(scenario_sandbox):
    scenario, sb = scenario_sandbox
    if EXPECTED[scenario.id].get("no_code_fix"):
        pytest.skip("the correct outcome for this scenario is no code change")
    ws = Workspace(sb)
    if "regression" in EXPECTED[scenario.id]:
        (sb.root / "tests" / "test_regression_ref.py").write_text(EXPECTED[scenario.id]["regression"], encoding="utf-8")
    before = ws.test_outcomes()
    assert any(o != "passed" for o in before.values()), "the reproducing tests must fail before the fix"
    for path, old, new in EXPECTED[scenario.id]["fixes"]:
        assert sb.edit_file(path, old, new) == {"edited": path}
    result = compare_outcomes(before, ws.test_outcomes())
    assert result["verified"], result


@pytest.mark.parametrize("target", sorted(p.name for p in TARGETS.iterdir() if p.is_dir()))
def test_targets_contain_no_answer_key(target):
    # The agent must investigate without hints: nothing in a target may describe its planted defects.
    for path in (TARGETS / target).rglob("*"):
        if path.is_file() and path.suffix in {".py", ".md", ".ini", ".txt"} and "__pycache__" not in path.parts:
            text = path.read_text(encoding="utf-8").lower()
            for hint in ("planted", "deliberate", "bug", "tracepilot", "idor", "on purpose", "injection", "vulnerab"):
                assert hint not in text, f"{target}/{path.relative_to(TARGETS / target)} mentions '{hint}'"
