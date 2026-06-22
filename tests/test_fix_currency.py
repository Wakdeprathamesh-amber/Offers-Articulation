"""Tests for _fix_currency — swaps wrong currency symbols for the expected one."""


def test_wrong_symbol_in_title_swapped(appmod):
    out = appmod._fix_currency(
        {"offers": [{"title": "Save US$500 OFF!", "body": ""}]}, "£"
    )
    assert out["offers"][0]["title"] == "Save £500 OFF!"


def test_us_token_not_confused_with_s(appmod):
    # Expected S$ (Singapore); US$ must become S$, not be left as "US$".
    out = appmod._fix_currency(
        {"offers": [{"title": "Get US$500 GIFT CARD!", "body": "Enjoy US$500 today."}]}, "S$"
    )
    assert "US$" not in out["offers"][0]["title"]
    assert out["offers"][0]["title"] == "Get S$500 GIFT CARD!"


def test_correct_symbol_untouched(appmod):
    out = appmod._fix_currency({"offers": [{"title": "Save £500 OFF!", "body": ""}]}, "£")
    assert out["offers"][0]["title"] == "Save £500 OFF!"


def test_unknown_country_is_noop(appmod):
    out = appmod._fix_currency({"offers": [{"title": "Save US$500!", "body": ""}]}, None)
    assert out["offers"][0]["title"] == "Save US$500!"


def test_multiple_symbols_all_normalized(appmod):
    out = appmod._fix_currency({"offers": [{"title": "", "body": "AU$50 or €50 or £50"}]}, "£")
    assert out["offers"][0]["body"] == "£50 or £50 or £50"
