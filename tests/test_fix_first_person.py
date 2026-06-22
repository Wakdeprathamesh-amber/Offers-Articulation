"""Tests for _fix_first_person — conservative first-person -> Property Management swaps."""

import pytest


@pytest.mark.parametrize("before,after_contains", [
    ("(1) We reserve the right to amend.", "Property Management reserves the right to amend"),
    ("(1) we reserve the right to cancel.", "Property Management reserves the right to cancel"),
    ("(1) We will credit the cashback after move-in.", "Property Management will credit"),
    ("(1) We may withdraw this offer.", "Property Management may withdraw"),
    ("(1) Subject to our terms and conditions.", "Property Management's terms and conditions"),
])
def test_common_first_person_swapped(appmod, before, after_contains):
    out = appmod._fix_first_person({"offers": [{"body": "", "terms": [before]}]})
    assert after_contains in out["offers"][0]["terms"][0]


def test_no_lingering_we_in_handled_patterns(appmod):
    out = appmod._fix_first_person({"offers": [{"body": "We will apply the discount.", "terms": []}]})
    assert "We will" not in out["offers"][0]["body"]
    assert "Property Management will apply" in out["offers"][0]["body"]


def test_idempotent(appmod):
    once = appmod._fix_first_person(
        {"offers": [{"body": "", "terms": ["(1) We reserve the right to amend."]}]}
    )
    twice = appmod._fix_first_person({"offers": [dict(once["offers"][0])]})
    assert once["offers"][0]["terms"] == twice["offers"][0]["terms"]


def test_plain_text_untouched(appmod):
    term = "(1) The discount is applied after the first instalment is paid."
    out = appmod._fix_first_person({"offers": [{"body": "", "terms": [term]}]})
    assert out["offers"][0]["terms"][0] == term
