"""OPTIONAL live quality tests against the real OpenAI API.

These are SKIPPED by default (they cost money and need network). Enable with:

    RUN_LIVE_TESTS=1 pytest tests/test_live_examples.py -v

They assert structural quality invariants on the four real scenarios, not exact
wording (which is non-deterministic).
"""

import json
import os

import pytest

LIVE = os.environ.get("RUN_LIVE_TESTS") == "1" and os.environ.get("OPENAI_API_KEY")

pytestmark = pytest.mark.skipif(not LIVE, reason="set RUN_LIVE_TESTS=1 and OPENAI_API_KEY to run live tests")


def _no_dashes(obj):
    blob = json.dumps(obj)
    return "—" not in blob and "–" not in blob


def _gen(appmod, country, prop, raw):
    return appmod.generate_offer(country, prop, raw)


def test_uk_500_discount_applicable(appmod):
    out = _gen(
        appmod,
        "United Kingdom",
        "Radford Mill, Nottingham",
        "Book now and receive a £500 discount! 51-week tenancy, 2026-2027 academic year, "
        "all room types. T&Cs say valid for international agents.",
    )
    assert out["applicable"] is True
    assert _no_dashes(out)
    o = out["offers"][0]
    assert o["title_status"] in ("ok", "over_target")
    assert "£" in o["title"] or "£" in o["body"]
    assert len(o["terms"]) >= 5  # generic fallback or provided


def test_us_multi_offer_varied_hooks(appmod):
    raw = (
        "1. Six11, Ann Arbor: New low rates on 4 & 5 bedroom floor plans + receive a $500 gift card!\n"
        "2. Junction 49, Charlotte: Receive a $400 gift card on select floor plans.\n"
        "3. Rambler Athens, Athens: Get a $500 gift card! The next 10 people to sign a lease."
    )
    out = _gen(appmod, "United States", "Six11; Junction 49; Rambler Athens", raw)
    assert out["applicable"] is True
    assert _no_dashes(out)
    assert len(out["offers"]) >= 2
    titles = [o["title"] for o in out["offers"]]
    # hooks should vary (not all identical openings)
    assert len(set(t.split(":")[0] for t in titles)) > 1
    assert all("US$" in o["title"] or "US$" in o["body"] for o in out["offers"])


def test_aus_with_tncs_removes_agent_clause(appmod):
    raw = (
        "UniLodge Melbourne Central is offering Up to 2 Weeks Rent Free on Studio Standard, "
        "Studio Premium or Studio Long, first 20 bookings 15 June to 31 July 2026.\n"
        "T&Cs:\n"
        "1. New eligible residents at UniLodge Melbourne Central only.\n"
        "2. Lease must commence between 15/06/2026 and 10/08/2026.\n"
        "3. The offer is available via the agent booking portal by education agents, booking agents, or referral agents.\n"
        "4. UniLodge reserves the right to withdraw the offer.\n"
        "Contact partnerships@unilodge.com.au."
    )
    out = _gen(appmod, "Australia", "UniLodge Melbourne Central", raw)
    assert _no_dashes(out)
    blob = json.dumps(out).lower()
    assert "agent booking portal" not in blob
    assert "unilodge.com.au" not in blob
    # operator name swapped in reserves-rights line
    assert "property management" in blob


def test_direct_booking_only_flagged(appmod):
    out = _gen(
        appmod,
        "United States",
        "Some Property",
        "Book directly with us and get a chance to win a $1000 gift card!",
    )
    # lucky draw + direct booking -> not applicable
    assert out["applicable"] is False or out["needs_kam_confirmation"] is True
