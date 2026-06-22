"""Unit tests for the SOP compliance checker (sop_checker.check_compliance).

These feed deliberately good/bad outputs and assert the linter flags the right
rules. This is what makes the linter trustworthy enough to run over live output.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sop_checker import check_compliance, summarize  # noqa: E402


def _rules(violations):
    return {v["rule"] for v in violations}


GOOD = {
    "applicable": True,
    "assessment": "Applicable offer.",
    "flags": ["none"],
    "needs_kam_confirmation": False,
    "offers": [
        {
            "properties": ["Maple Heights Residences, Toronto"],
            "title": "Special Deal: Get CA$750 CASHBACK Today!",
            "body": "Book a room at Maple Heights Residences and receive CA$750 cashback! "
                    "Available for the 2026-2027 academic year. Apply now to claim this offer!",
            "terms": [
                "(1) The CA$750 cashback will be credited after move-in.",
                "(2) Property Management reserves the right to amend the offer.",
            ],
        }
    ],
}

GOOD_CTX = {
    "country": "Canada",
    "property_names": ["Maple Heights Residences, Toronto"],
    "source_has_tncs": True,
    "operator_names": ["Maple Living Group"],
    "expect_applicable": True,
}


def test_good_output_has_no_errors():
    v = check_compliance(GOOD, GOOD_CTX)
    assert summarize(v)["ok"], [x for x in v if x["severity"] == "error"]


def test_detects_wrong_currency():
    bad = _mutate_title("Special Deal: Get £750 CASHBACK Today!")
    v = check_compliance(bad, GOOD_CTX)
    assert "TITLE_CURRENCY" in _rules(v)


def test_detects_title_over_hard_cap():
    bad = _mutate_title("Special Deal: " + "X" * 80)
    v = check_compliance(bad, GOOD_CTX)
    assert "TITLE_HARD_CAP" in _rules(v)


def test_detects_book_start():
    bad = _mutate_title("Book Now and Get CA$750 CASHBACK!")
    v = check_compliance(bad, GOOD_CTX)
    assert "TITLE_BOOK" in _rules(v)


def test_detects_spelled_number():
    bad = _mutate_title("Special Deal: Get Four Weeks FREE!")
    v = check_compliance(bad, {**GOOD_CTX, "country": "Canada"})
    assert "TITLE_DIGITS" in _rules(v)


def test_detects_title_case_violation():
    bad = _mutate_title("Save CA$200 On Select Studios!")
    v = check_compliance(bad, GOOD_CTX)
    assert "TITLE_CASE" in _rules(v)


def test_detects_missing_powerword():
    bad = _mutate_title("Special Deal: Get CA$750 Cashback Today!")  # 'Cashback' not all caps
    v = check_compliance(bad, GOOD_CTX)
    assert "TITLE_POWERWORD" in _rules(v)


def test_detects_first_person_in_terms():
    bad = _mutate_terms(["(1) We will credit the cashback after move-in."])
    v = check_compliance(bad, GOOD_CTX)
    assert "TERMS_FIRST_PERSON" in _rules(v)


def test_detects_operator_leak():
    bad = _mutate_terms(["(1) Maple Living Group reserves the right to amend."])
    v = check_compliance(bad, GOOD_CTX)
    assert "TERMS_OPERATOR" in _rules(v)


def test_detects_agent_clause():
    bad = _mutate_terms(["(1) Available via the agent booking portal by booking agents."])
    v = check_compliance(bad, GOOD_CTX)
    assert "TERMS_AGENT" in _rules(v)


def test_detects_email_in_terms():
    bad = _mutate_terms(["(1) Contact leasing@maplelivinggroup.ca for queries."])
    v = check_compliance(bad, GOOD_CTX)
    assert "TERMS_CONTACT" in _rules(v)


def test_detects_bullets_in_terms():
    bad = _mutate_terms(["• This offer is subject to availability."])
    v = check_compliance(bad, GOOD_CTX)
    assert "TERMS_BULLETS" in _rules(v)


def test_detects_em_dash():
    bad = _mutate_title("Special Deal: Get CA$750 CASHBACK — Today!")
    v = check_compliance(bad, GOOD_CTX)
    assert "NO_DASHES" in _rules(v)


def test_detects_missing_cta():
    bad = _clone(GOOD)
    bad["offers"][0]["body"] = "Receive CA$750 cashback at Maple Heights Residences for 2026-2027."
    v = check_compliance(bad, GOOD_CTX)
    assert "BODY_CTA" in _rules(v)


def test_detects_email_in_body():
    bad = _clone(GOOD)
    bad["offers"][0]["body"] += " Email leasing@maplelivinggroup.ca to apply now!"
    v = check_compliance(bad, GOOD_CTX)
    assert "BODY_CONTACT" in _rules(v)


def test_detects_applicability_should_be_rejected():
    bad = _clone(GOOD)
    v = check_compliance(bad, {**GOOD_CTX, "expect_applicable": False})
    assert "APPLICABILITY" in _rules(v)


def test_date_ranges_do_not_trigger_phone_false_positive():
    ok = _clone(GOOD)
    ok["offers"][0]["body"] = ("Book at Maple Heights Residences between September 1, 2026 and "
                               "November 30, 2026 for the 2026-2027 year. Apply now!")
    v = check_compliance(ok, GOOD_CTX)
    assert "BODY_CONTACT" not in _rules(v)


# --------------------------------------------------------------- helpers
import copy


def _clone(d):
    return copy.deepcopy(d)


def _mutate_title(title):
    d = _clone(GOOD)
    d["offers"][0]["title"] = title
    return d


def _mutate_terms(terms):
    d = _clone(GOOD)
    d["offers"][0]["terms"] = terms
    return d


def test_up_to_idiom_not_flagged_title_case():
    # "Up to" is the idiom used in the SOP's own canonical example; must not warn.
    ok = _mutate_title("Big Savings: Get Up to 2 Weeks Rent FREE!")
    v = check_compliance(ok, GOOD_CTX)
    assert "TITLE_CASE" not in _rules(v)


def test_genuine_title_case_still_flagged():
    bad = _mutate_title("Save CA$200 On Select Studios!")  # 'On' wrongly capitalised
    v = check_compliance(bad, GOOD_CTX)
    assert "TITLE_CASE" in _rules(v)
