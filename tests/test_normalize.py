"""Tests for _normalize — guarantees a stable output contract for the UI."""


def test_missing_keys_get_defaults(appmod):
    out = appmod._normalize({})
    assert out["applicable"] is False
    assert out["assessment"] == ""
    assert out["needs_kam_confirmation"] is False
    assert out["flags"] == ["none"]
    assert out["offers"] == []


def test_non_dict_input(appmod):
    out = appmod._normalize("garbage")
    assert out["offers"] == []
    assert out["applicable"] is False


def test_flags_string_becomes_list(appmod):
    out = appmod._normalize({"flags": "lucky_draw"})
    assert out["flags"] == ["lucky_draw"]


def test_flags_missing_defaults_to_none(appmod):
    out = appmod._normalize({"flags": []})
    assert out["flags"] == ["none"]


def test_offers_none_becomes_empty(appmod):
    out = appmod._normalize({"offers": None})
    assert out["offers"] == []


def test_non_dict_offer_skipped(appmod):
    out = appmod._normalize({"offers": ["not a dict", {"title": "Real"}]})
    assert len(out["offers"]) == 1
    assert out["offers"][0]["title"] == "Real"


def test_offer_shape_filled(appmod):
    out = appmod._normalize({"offers": [{"title": "T"}]})
    o = out["offers"][0]
    assert o["properties"] == []
    assert o["body"] == ""
    assert o["terms"] == []
    assert o["missing_info"] == []


def test_properties_string_becomes_list(appmod):
    out = appmod._normalize({"offers": [{"properties": "One Prop"}]})
    assert out["offers"][0]["properties"] == ["One Prop"]


def test_terms_string_becomes_list(appmod):
    out = appmod._normalize({"offers": [{"terms": "(1) only one"}]})
    assert out["offers"][0]["terms"] == ["(1) only one"]


def test_terms_non_list_non_str_becomes_empty(appmod):
    out = appmod._normalize({"offers": [{"terms": 5}]})
    assert out["offers"][0]["terms"] == []


def test_missing_info_string_becomes_list(appmod):
    out = appmod._normalize({"offers": [{"missing_info": "no date"}]})
    assert out["offers"][0]["missing_info"] == ["no date"]


def test_non_string_title_body_coerced(appmod):
    out = appmod._normalize({"offers": [{"title": 123, "body": None}]})
    assert out["offers"][0]["title"] == ""
    assert out["offers"][0]["body"] == ""


def test_applicable_truthy_coerced_to_bool(appmod):
    out = appmod._normalize({"applicable": "yes"})
    assert out["applicable"] is True
