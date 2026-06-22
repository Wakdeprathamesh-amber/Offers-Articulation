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
