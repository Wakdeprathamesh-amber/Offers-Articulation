"""Tests for _annotate — title length status (60 target / 72 hard cap)."""

import pytest


@pytest.mark.parametrize(
    "length,status",
    [
        (10, "ok"),
        (60, "ok"),        # exactly at target -> ok
        (61, "over_target"),
        (72, "over_target"),   # exactly at hard cap -> still over target, not over cap
        (73, "over_hard_cap"),
        (100, "over_hard_cap"),
    ],
)
def test_title_length_statuses(appmod, length, status):
    data = {"offers": [{"title": "A" * length}]}
    out = appmod._annotate(data)
    assert out["offers"][0]["title_length"] == length
    assert out["offers"][0]["title_status"] == status


def test_missing_title_is_zero_ok(appmod):
    out = appmod._annotate({"offers": [{}]})
    assert out["offers"][0]["title_length"] == 0
    assert out["offers"][0]["title_status"] == "ok"


def test_none_title_is_zero_ok(appmod):
    out = appmod._annotate({"offers": [{"title": None}]})
    assert out["offers"][0]["title_length"] == 0


def test_multiple_offers_each_annotated(appmod):
    out = appmod._annotate({"offers": [{"title": "short"}, {"title": "B" * 80}]})
    assert out["offers"][0]["title_status"] == "ok"
    assert out["offers"][1]["title_status"] == "over_hard_cap"


def test_unicode_currency_counts_correctly(appmod):
    # '£' is a single character; ensure no byte-vs-char miscount.
    title = "Save £500 OFF Today!"
    out = appmod._annotate({"offers": [{"title": title}]})
    assert out["offers"][0]["title_length"] == len(title)
