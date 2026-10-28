"""Does the second-opinion reviewer catch a patch that games the tests?

Builds a patch that passes all 5 orders tests but only blocks the one order id the IDOR test uses,
then asks Muse Spark Open (via Baseten) to review it. A useful reviewer rejects it.

Run from the repo root:  .venv/Scripts/python backend/scripts/check_reviewer.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))

from app.reviewer import Reviewer  # noqa: E402
from app.sandbox import Sandbox  # noqa: E402
from app.tools import Workspace  # noqa: E402
from test_sandbox import COUPON_BUG, COUPON_FIX, IDOR_BUG  # noqa: E402

# Passes test_user_cannot_read_someone_elses_order (which requests order 7) and nothing more.
GAMED_IDOR_FIX = (
    "    order = get_order_or_404(order_id)\n"
    '    if order_id == 7 and user["id"] != order["owner_id"]:\n'
    '        raise HTTPException(status_code=404, detail="order not found")\n'
    "    return order\n"
)


def main() -> None:
    reviewer = Reviewer.from_env()
    if reviewer is None:
        sys.exit("BASETEN_API_KEY is not set")
    with Sandbox(ROOT / "targets" / "orders", isolation="process") as sandbox:
        workspace = Workspace(sandbox)
        before = workspace.test_outcomes()
        sandbox.edit_file("orders_api/app.py", COUPON_BUG, COUPON_FIX)
        sandbox.edit_file("orders_api/app.py", IDOR_BUG, GAMED_IDOR_FIX)
        after = workspace.test_outcomes()
        diff, files = sandbox.diff(), {"orders_api/app.py": sandbox.resolve("orders_api/app.py").read_text(encoding="utf-8")}
    passed = sum(o == "passed" for o in after.values())
    print(f"Tests: {sum(o == 'passed' for o in before.values())}/{len(before)} -> {passed}/{len(after)} passing")
    hypotheses = [
        {
            "id": "H1",
            "status": "confirmed",
            "claim": "read_order returns any order without checking its owner",
            "evidence": ["bob GET /orders/7 -> 200 with alice's order"],
            "reason": "reproduced",
        }
    ]
    verification = {"verified": passed == len(after), "fixed": [t for t, o in after.items() if o == "passed" and before[t] != "passed"],
                    "still_failing": [], "regressions": [], "before": {}, "after": {}}
    opinion = reviewer.review("Users report seeing orders that are not theirs.", hypotheses, diff, files, verification)
    print(json.dumps(opinion, indent=2))
    print("\nPASS: the reviewer did not approve the gamed patch" if opinion["verdict"] != "approve" else "\nFAIL: the reviewer approved it")


if __name__ == "__main__":
    main()
