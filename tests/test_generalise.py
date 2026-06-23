"""Tests for _generalise_property — replaces the specific property name with
'the property' so no brand name appears in the offer copy."""


def test_property_name_replaced_in_body(appmod):
    out = appmod._generalise_property(
        {"offers": [{"title": "", "body": "Book a room at Maple Heights Residences and save!", "terms": []}]},
        "Maple Heights Residences, Toronto",
    )
    assert "Maple Heights" not in out["offers"][0]["body"]
    assert "at the property" in out["offers"][0]["body"]


def test_property_core_and_full_replaced(appmod):
    out = appmod._generalise_property(
        {"offers": [{"title": "", "body": "Valid at Maple Heights Residences, Toronto only.",
                     "terms": ["(1) Resident at Maple Heights Residences to qualify."]}]},
        "Maple Heights Residences, Toronto",
    )
    blob = out["offers"][0]["body"] + " " + " ".join(out["offers"][0]["terms"])
    assert "Maple Heights" not in blob


def test_no_double_the(appmod):
    out = appmod._generalise_property(
        {"offers": [{"title": "", "body": "Stay at the Maple Heights Residences today.", "terms": []}]},
        "Maple Heights Residences",
    )
    low = out["offers"][0]["body"].lower()
    assert "the the property" not in low
    assert "the property" in low


def test_empty_property_is_noop(appmod):
    out = appmod._generalise_property({"offers": [{"title": "", "body": "Book at Lark Austin now.", "terms": []}]}, "")
    assert out["offers"][0]["body"] == "Book at Lark Austin now."


def test_runs_inside_postprocess_with_property(appmod):
    data = {
        "applicable": True,
        "offers": [{
            "properties": ["UniLodge Melbourne Central"],
            "title": "Big Savings: Get 2 Weeks Rent FREE!",
            "body": "Book a room at UniLodge Melbourne Central and enjoy 2 weeks rent FREE! Apply now!",
            "terms": ["(1) New eligible resident at UniLodge Melbourne Central to qualify."],
        }],
    }
    out = appmod.postprocess(data, country="Australia", property_name="UniLodge Melbourne Central")
    blob = out["offers"][0]["body"] + " " + " ".join(out["offers"][0]["terms"])
    assert "UniLodge" not in blob
    assert "the property" in blob.lower()
