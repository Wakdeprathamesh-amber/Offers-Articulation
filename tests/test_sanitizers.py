"""Tests for the dash-cleaning and agent-term-removal sanitizers."""

import pytest


# ---------------------------------------------------------------- _clean_dashes
def test_en_dash_becomes_hyphen(appmod):
    assert appmod._clean_dashes("2026–2027") == "2026-2027"


def test_en_dash_range_with_spaces(appmod):
    assert appmod._clean_dashes("Levels 2–11") == "Levels 2-11"


def test_em_dash_becomes_comma(appmod):
    assert appmod._clean_dashes("great deal — act now") == "great deal, act now"


def test_horizontal_bar_handled(appmod):
    assert "―" not in appmod._clean_dashes("a ― b")


def test_leading_em_dash_no_leading_comma(appmod):
    assert not appmod._clean_dashes("— hello").startswith(",")


def test_em_dash_after_newline(appmod):
    out = appmod._clean_dashes("line one\n— line two")
    assert "\n," not in out
    assert "—" not in out


def test_double_spaces_collapsed(appmod):
    assert appmod._clean_dashes("a    b") == "a b"


def test_no_dashes_remain_complex(appmod):
    s = "From $549–$590 per week — book between June 15–July 31 — limited!"
    out = appmod._clean_dashes(s)
    assert "—" not in out and "–" not in out and "―" not in out


def test_non_string_passthrough(appmod):
    assert appmod._clean_dashes(None) is None
    assert appmod._clean_dashes(42) == 42


def test_plain_hyphen_untouched(appmod):
    assert appmod._clean_dashes("first-come, first-served") == "first-come, first-served"


# --------------------------------------------------------------- _strip_dashes
def test_strip_dashes_across_fields(appmod):
    data = {
        "assessment": "ok — fine",
        "offers": [
            {"title": "A–B", "body": "x — y", "terms": ["(1) p–q", "(2) r — s"]},
        ],
    }
    out = appmod._strip_dashes(data)
    blob = str(out)
    assert "—" not in blob and "–" not in blob


def test_strip_dashes_handles_none_offers(appmod):
    out = appmod._strip_dashes({"offers": None})
    assert out["offers"] is None  # untouched, no crash


def test_strip_dashes_missing_assessment(appmod):
    out = appmod._strip_dashes({"offers": []})
    assert "assessment" not in out  # not added by strip step


# ----------------------------------------------------------- _clean_agent_terms
AGENT_TERMS = [
    "(1) Available via the agent booking portal.",
    "(2) Only booking agents qualify.",
    "(3) Education agents must use the portal.",
    "(4) Valid for referral agents.",
    "(5) Use your agent code at checkout.",
    "(6) Agent commission is payable.",
    "(7) Referral commission applies.",
    "(8) Bookings are only commissionable via the portal.",
]


@pytest.mark.parametrize("term", AGENT_TERMS)
def test_each_agent_term_removed(appmod, term):
    out = appmod._clean_agent_terms({"offers": [{"terms": [term, "(2) A clean keeper term."]}]})
    kept = out["offers"][0]["terms"]
    assert len(kept) == 1
    assert "keeper" in kept[0]


def test_legit_referral_agreement_kept(appmod):
    """'nomination agreement or a referral agreement' must NOT be removed."""
    term = "(1) This offer excludes bookings referred through a nomination agreement or a referral agreement."
    out = appmod._clean_agent_terms({"offers": [{"terms": [term]}]})
    assert len(out["offers"][0]["terms"]) == 1


def test_renumbering_after_removal(appmod):
    terms = [
        "(1) Keep this one.",
        "(2) Available via the agent booking portal by booking agents.",
        "(3) Keep this too.",
        "(4) Keep three.",
    ]
    out = appmod._clean_agent_terms({"offers": [{"terms": terms}]})
    kept = out["offers"][0]["terms"]
    assert kept == ["(1) Keep this one.", "(2) Keep this too.", "(3) Keep three."]


def test_handles_dot_numbering(appmod):
    out = appmod._clean_agent_terms({"offers": [{"terms": ["1. First term.", "2. Second term."]}]})
    assert out["offers"][0]["terms"] == ["(1) First term.", "(2) Second term."]


def test_term_starting_with_number_not_mangled(appmod):
    out = appmod._clean_agent_terms({"offers": [{"terms": ["(6) 2 weeks rent free for half-year term."]}]})
    assert out["offers"][0]["terms"] == ["(1) 2 weeks rent free for half-year term."]


def test_case_insensitive_removal(appmod):
    out = appmod._clean_agent_terms({"offers": [{"terms": ["(1) BOOKING AGENTS only.", "(2) keep"]}]})
    assert len(out["offers"][0]["terms"]) == 1


def test_terms_not_a_list_skipped(appmod):
    out = appmod._clean_agent_terms({"offers": [{"terms": "not a list"}]})
    assert out["offers"][0]["terms"] == "not a list"  # untouched, no crash


def test_empty_terms(appmod):
    out = appmod._clean_agent_terms({"offers": [{"terms": []}]})
    assert out["offers"][0]["terms"] == []
