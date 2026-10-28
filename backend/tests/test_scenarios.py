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
    ws = Workspace(sb)
    before = ws.test_outcomes()
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
