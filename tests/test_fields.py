"""Tests for the new structured fields, lease defaults, offer-code stripping,
currency-keep, and country/currency mismatch flags."""

import pytest


# ---- lease defaults (min->1, max->72w/24m, unit->weeks) --------------------
@pytest.mark.parametrize("offer,exp", [
    ({}, ("1", "72", "weeks")),                                   # nothing given
    ({"lease_min": "51"}, ("51", "72", "weeks")),                # only min
    ({"lease_max": "44", "lease_unit": "weeks"}, ("1", "44", "weeks")),
    ({"lease_unit": "months"}, ("1", "24", "months")),           # months cap
    ({"lease_min": "6", "lease_max": "12", "lease_unit": "months"}, ("6", "12", "months")),
    ({"lease_min": "51 weeks", "lease_unit": "weeks"}, ("51", "72", "weeks")),  # digits extracted
])
def test_lease_defaults(appmod, offer, exp):
    assert appmod._lease_fields(offer) == exp


def test_normalize_populates_new_fields(appmod):
    out = appmod._normalize({
        "detected_country": " United Kingdom ",
        "offers": [{"title": "T", "offer_code": "DISC250",
                    "offer_start_date": "15 June 2026", "offer_end_date": "31 July 2026",
                    "lease_min": "51", "lease_unit": "weeks"}],
    })
    o = out["offers"][0]
    assert o["offer_code"] == "DISC250"
    assert o["offer_start_date"] == "15 June 2026" and o["offer_end_date"] == "31 July 2026"
    assert o["lease_min"] == "51" and o["lease_max"] == "72" and o["lease_unit"] == "weeks"
    assert out["detected_country"] == "United Kingdom"


def test_normalize_defaults_when_absent(appmod):
    o = appmod._normalize({"offers": [{"title": "T"}]})["offers"][0]
    assert o["offer_code"] == "" and o["offer_start_date"] == "" and o["offer_end_date"] == ""
    assert o["lease_min"] == "1" and o["lease_max"] == "72" and o["lease_unit"] == "weeks"


# ---- offer code stripped from copy, kept as field --------------------------
def test_strip_offer_code_removes_exact_code(appmod):
    out = appmod._strip_offer_code({"offers": [{
        "offer_code": "MAPLE750",
        "title": "Get CA$750 CASHBACK with MAPLE750!",
        "body": "Use code MAPLE750 at checkout.",
        "terms": ["(1) Enter MAPLE750 to claim."]}]})
    o = out["offers"][0]
    assert "MAPLE750" not in o["title"]
    assert "MAPLE750" not in o["body"]
    assert "MAPLE750" not in " ".join(o["terms"])


def test_strip_offer_code_generic_pattern(appmod):
    out = appmod._strip_offer_code({"offers": [{"offer_code": "",
        "title": "", "body": "Book now and use code DISC250 today.", "terms": []}]})
    assert "DISC250" not in out["offers"][0]["body"]


def test_strip_offer_code_keeps_plain_words(appmod):
    # "code of conduct" has no digit -> must NOT be stripped
    term = "(1) Residents must follow the code of conduct at all times."
    out = appmod._strip_offer_code({"offers": [{"offer_code": "", "title": "", "body": "", "terms": [term]}]})
    assert out["offers"][0]["terms"][0] == term


# ---- currency is kept, mismatch is flagged (not changed) -------------------
def test_currency_kept_not_changed(appmod):
    out = appmod.postprocess(
        {"offers": [{"title": "Save US$500 OFF!", "body": "Enjoy US$500 today. Apply now!", "terms": []}]},
        country="United Kingdom",
    )
    assert "US$" in out["offers"][0]["title"]  # NOT converted to £


def test_currency_mismatch_flagged(appmod, monkeypatch):
    import json as _json
    from conftest import make_fake_openai
    monkeypatch.setattr("openai.OpenAI", make_fake_openai(_json.dumps({
        "applicable": True, "flags": ["none"], "detected_country": "United States",
        "offers": [{"properties": ["P"], "title": "Big Bonus: Get US$500 GIFT CARD!",
                    "body": "Receive US$500 at this property. Apply now!", "terms": ["(1) Subject to availability."]}],
    })))
    out = appmod.generate_offer("United Kingdom", "P", "raw")
    rules = {w["rule"] for w in out["warnings"]}
    assert "TITLE_CURRENCY" in rules or "BODY_CURRENCY" in rules   # flagged
    assert "COUNTRY_MISMATCH" in rules                             # US vs UK flagged
