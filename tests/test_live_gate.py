"""Tests for the live SOP-check gate that attaches warnings to generate_offer output."""

import json


def _fake(monkeypatch, payload):
    from conftest import make_fake_openai
    monkeypatch.setattr("openai.OpenAI", make_fake_openai(json.dumps(payload)))


def test_clean_output_has_no_warnings(appmod, monkeypatch):
    _fake(monkeypatch, {
        "applicable": True, "assessment": "ok", "flags": ["none"],
        "needs_kam_confirmation": False, "source_has_tncs": False,
        "detected_operator_names": [],
        "offers": [{
            "properties": ["Test Prop, Austin"],
            "title": "Big Bonus: Get US$500 GIFT CARD!",
            "body": "Sign a lease at Test Prop and receive a US$500 gift card. Apply now!",
            "terms": ["(1) Subject to availability."], "missing_info": [],
        }],
    })
    out = appmod.generate_offer("United States", "Test Prop, Austin", "raw")
    assert "warnings" in out
    errors = [w for w in out["warnings"] if w["severity"] == "error"]
    assert errors == []


def test_residual_first_person_is_flagged(appmod, monkeypatch):
    # 'our' / 'us' on their own are NOT auto-fixed -> must surface as a warning.
    _fake(monkeypatch, {
        "applicable": True, "assessment": "ok", "flags": ["none"],
        "needs_kam_confirmation": False, "source_has_tncs": True,
        "detected_operator_names": [],
        "offers": [{
            "properties": ["Test Prop, Austin"],
            "title": "Big Bonus: Get US$500 GIFT CARD!",
            "body": "Receive US$500 at Test Prop. Apply now!",
            "terms": ["(1) Bookings are processed at our sole discretion by us."],
            "missing_info": [],
        }],
    })
    out = appmod.generate_offer("United States", "Test Prop, Austin", "raw")
    rules = {w["rule"] for w in out["warnings"]}
    assert "TERMS_FIRST_PERSON" in rules


def test_warnings_never_crash_on_odd_output(appmod, monkeypatch):
    _fake(monkeypatch, {"applicable": True, "offers": []})
    out = appmod.generate_offer("United Kingdom", "P", "raw")
    assert isinstance(out["warnings"], list)


def test_operator_name_inside_property_not_flagged(appmod, monkeypatch):
    # 'UniLodge' is part of the property name -> the kept property mention must
    # NOT trigger a TERMS_OPERATOR error in the live gate.
    _fake(monkeypatch, {
        "applicable": True, "assessment": "ok", "flags": ["none"],
        "needs_kam_confirmation": False, "source_has_tncs": True,
        "detected_operator_names": ["UniLodge"],
        "offers": [{
            "properties": ["UniLodge Melbourne Central"],
            "title": "Big Savings: Get 2 Weeks Rent FREE!",
            "body": "Book at UniLodge Melbourne Central and enjoy 2 weeks rent FREE! Apply now!",
            "terms": ["(1) You must be a new resident at UniLodge Melbourne Central to qualify.",
                      "(2) Property Management reserves the right to amend."],
            "missing_info": [],
        }],
    })
    out = appmod.generate_offer("Australia", "UniLodge Melbourne Central", "raw")
    rules = {w["rule"] for w in out["warnings"]}
    assert "TERMS_OPERATOR" not in rules


def test_leaked_operator_is_removed_and_not_flagged(appmod, monkeypatch):
    # Operator name NOT part of the property -> auto-renamed away by the pipeline,
    # so the final output is clean and carries no TERMS_OPERATOR warning.
    _fake(monkeypatch, {
        "applicable": True, "assessment": "ok", "flags": ["none"],
        "needs_kam_confirmation": False, "source_has_tncs": True,
        "detected_operator_names": ["Maple Living Group"],
        "offers": [{
            "properties": ["Maple Heights Residences, Toronto"],
            "title": "Special Deal: Get CA$750 CASHBACK!",
            "body": "Receive CA$750 at Maple Heights Residences. Apply now!",
            "terms": ["(1) Credited by Maple Living Group after move-in."],
            "missing_info": [],
        }],
    })
    out = appmod.generate_offer("Canada", "Maple Heights Residences, Toronto", "raw")
    joined = " ".join(out["offers"][0]["terms"])
    assert "Maple Living Group" not in joined          # auto-renamed
    assert "Property Management" in joined
    rules = {w["rule"] for w in out["warnings"]}
    assert "TERMS_OPERATOR" not in rules
