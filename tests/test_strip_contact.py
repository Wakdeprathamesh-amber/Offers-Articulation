"""Tests for _strip_contact_info — removes emails/URLs/phones from body+terms."""


def test_email_removed_from_body(appmod):
    out = appmod._strip_contact_info(
        {"offers": [{"body": "Save now! Email leasing@pmg.com to apply.", "terms": []}]}
    )
    assert "leasing@pmg.com" not in out["offers"][0]["body"]


def test_url_removed_from_body(appmod):
    out = appmod._strip_contact_info(
        {"offers": [{"body": "Visit https://pmg.com/offer for details.", "terms": []}]}
    )
    assert "http" not in out["offers"][0]["body"]


def test_phone_removed_from_terms(appmod):
    out = appmod._strip_contact_info(
        {"offers": [{"body": "", "terms": ["(1) Call +61 3 9000 0000 for help.", "(2) Keeper term here."]}]}
    )
    joined = " ".join(out["offers"][0]["terms"])
    assert "9000 0000" not in joined
    assert "Keeper term" in joined


def test_contact_only_term_dropped_and_renumbered(appmod):
    out = appmod._strip_contact_info(
        {"offers": [{"body": "", "terms": [
            "(1) A real condition applies.",
            "(2) Contact bookings@pmg.com for queries.",
            "(3) Another real condition.",
        ]}]}
    )
    terms = out["offers"][0]["terms"]
    assert terms == ["(1) A real condition applies.", "(2) Another real condition."]


def test_term_with_embedded_email_kept_but_scrubbed(appmod):
    out = appmod._strip_contact_info(
        {"offers": [{"body": "", "terms": [
            "(1) The discount is applied after move-in; queries to leasing@pmg.com are welcome."
        ]}]}
    )
    t = out["offers"][0]["terms"][0]
    assert "leasing@pmg.com" not in t
    assert "discount is applied after move-in" in t


def test_no_contact_is_idempotent(appmod):
    once = appmod._strip_contact_info(
        {"offers": [{"body": "Plain body, no contacts.", "terms": ["(1) Plain term."]}]}
    )
    assert once["offers"][0]["body"] == "Plain body, no contacts."
    assert once["offers"][0]["terms"] == ["(1) Plain term."]


def test_date_range_not_treated_as_phone(appmod):
    out = appmod._strip_contact_info(
        {"offers": [{"body": "Valid 15/06/2026 to 10/08/2026.", "terms": []}]}
    )
    assert "15/06/2026" in out["offers"][0]["body"]


def test_dangling_contact_clause_trimmed(appmod):
    out = appmod._strip_contact_info(
        {"offers": [{"body": "", "terms": [
            "(1) The cashback is credited after move-in; queries to leasing@pmg.com."
        ]}]}
    )
    t = out["offers"][0]["terms"][0]
    assert "queries" not in t.lower()
    assert "credited after move-in" in t


def test_legit_call_word_without_contact_token_kept(appmod):
    # No email/phone token -> trailing cleanup must NOT fire and strip 'call'.
    term = "(1) You may need to call."
    out = appmod._strip_contact_info({"offers": [{"body": "", "terms": [term]}]})
    assert out["offers"][0]["terms"][0] == term
