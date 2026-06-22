"""Tests for prompts.py — the SOP-encoded prompt builder and constants."""

import pytest


def test_generic_tnc_has_seven_items(prompts):
    assert len(prompts.GENERIC_TNC) == 7
    assert all(isinstance(t, str) and t for t in prompts.GENERIC_TNC)


def test_power_words_present(prompts):
    for w in ["FREE", "DISCOUNT", "CASHBACK", "SAVE", "GIFT CARD"]:
        assert w in prompts.POWER_WORDS


def test_system_prompt_contains_core_rules(prompts):
    sp = prompts.SYSTEM_PROMPT
    assert "NEVER use em dashes" in sp
    assert "OFFER TITLE" in sp
    assert "OFFER BODY" in sp
    assert "TERMS & CONDITIONS" in sp
    assert "Property Management" in sp
    # generic T&Cs block is embedded
    assert prompts.GENERIC_TNC[0] in sp
    # output contract documented
    assert '"applicable"' in sp and '"offers"' in sp


def test_few_shot_has_all_four_examples(prompts):
    fs = prompts.FEW_SHOT_EXAMPLES
    for marker in ["EXAMPLE 1", "EXAMPLE 2", "EXAMPLE 3", "EXAMPLE 4"]:
        assert marker in fs


@pytest.mark.parametrize(
    "country,symbol",
    [
        ("United Kingdom", "£"),
        ("UK", "£"),
        ("United States", "US$"),
        ("USA", "US$"),
        ("Australia", "AU$"),
        ("Canada", "CA$"),
        ("Singapore", "S$"),
    ],
)
def test_build_user_prompt_injects_known_currency(prompts, country, symbol):
    p = prompts.build_user_prompt(country, "Some Property", "Get a deal")
    assert f"use currency symbol: {symbol}" in p


def test_build_user_prompt_unknown_country(prompts):
    p = prompts.build_user_prompt("Brazil", "Prop", "offer")
    assert "use the correct local currency symbol" in p
    assert "Brazil" in p


def test_build_user_prompt_empty_country(prompts):
    p = prompts.build_user_prompt("", "Prop", "offer")
    assert "Country: not specified" in p


def test_build_user_prompt_includes_inputs_and_fewshot(prompts):
    p = prompts.build_user_prompt("Australia", "UniLodge Melbourne Central", "RAWOFFERXYZ")
    assert "UniLodge Melbourne Central" in p
    assert "RAWOFFERXYZ" in p
    assert "EXAMPLE 1" in p  # few-shot is embedded in the user prompt
    assert "No em dashes" in p


def test_build_user_prompt_handles_none_property(prompts):
    p = prompts.build_user_prompt("Australia", None, "offer")
    assert "not specified" in p


def test_example3_rewrites_provided_tncs_not_generic(prompts):
    fs = prompts.FEW_SHOT_EXAMPLES
    # Example 3 (Radford Mill) had T&Cs in a screenshot -> must show rewritten terms,
    # NOT instruct "use the 7 generic T&Cs".
    start = fs.index("EXAMPLE 3")
    end = fs.index("EXAMPLE 4")
    block = fs[start:end]
    assert "use the 7 GENERIC T&Cs" not in block
    assert "51 week tenancy" in block or "51-week" in block
    assert "Property Management reserves the right" in block


def test_output_contract_has_new_fields(prompts):
    sp = prompts.SYSTEM_PROMPT
    assert '"detected_operator_names"' in sp
    assert '"source_has_tncs"' in sp
