"""Live SOP-compliance regression suite.

Runs every scenario in scenarios.py through the REAL model and asserts the
output has ZERO hard SOP violations (per sop_checker). This is the test that
would have caught the operator-name leak and the agent-applicability bug.

SKIPPED by default (costs money, needs network). Enable with:

    RUN_LIVE_TESTS=1 OPENAI_API_KEY=sk-... pytest tests/test_sop_compliance_live.py -v

Run this before every release / prompt change.
"""

import os

import pytest

import app
from scenarios import SCENARIOS
from sop_checker import check_compliance, summarize

LIVE = os.environ.get("RUN_LIVE_TESTS") == "1" and os.environ.get("OPENAI_API_KEY")
pytestmark = pytest.mark.skipif(not LIVE, reason="set RUN_LIVE_TESTS=1 and OPENAI_API_KEY to run live tests")


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
def test_scenario_is_sop_compliant(scenario):
    result = app.generate_offer(scenario["country"], scenario["property_name"], scenario["raw"])
    violations = check_compliance(result, scenario["ctx"])
    s = summarize(violations)
    if not s["ok"]:
        detail = "\n".join(f"  ERROR [{e['rule']}] {e['message']}" for e in s["errors"])
        pytest.fail(f"{scenario['id']} failed SOP compliance:\n{detail}")
