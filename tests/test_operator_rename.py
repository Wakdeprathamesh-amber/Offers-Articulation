"""Tests for _rename_operator — replaces leaked operator names with
'Property Management' in the two common T&C patterns."""


def test_reserves_the_right_unknown_operator(appmod):
    out = appmod._rename_operator(
        {"offers": [{"terms": ["(4) Maple Living Group reserves the right to amend this offer."]}]}
    )
    assert out["offers"][0]["terms"][0] == "(4) Property Management reserves the right to amend this offer."


def test_reserves_multiword_brand(appmod):
    out = appmod._rename_operator(
        {"offers": [{"terms": ["(1) Cardinal Group Student Living reserves the right to withdraw."]}]}
    )
    assert "Property Management reserves the right" in out["offers"][0]["terms"][0]
    assert "Cardinal" not in out["offers"][0]["terms"][0]


def test_any_other_property(appmod):
    out = appmod._rename_operator(
        {"offers": [{"terms": ["(5) Not available at any other UniLodge property."]}]}
    )
    assert out["offers"][0]["terms"][0] == "(5) Not available at any other Property Management property."


def test_any_other_properties_plural(appmod):
    out = appmod._rename_operator(
        {"offers": [{"terms": ["(5) Excluded at any other Student Roost properties."]}]}
    )
    assert "any other Property Management properties" in out["offers"][0]["terms"][0]


def test_already_property_management_idempotent(appmod):
    term = "(2) Property Management reserves the right to change the offer."
    out = appmod._rename_operator({"offers": [{"terms": [term]}]})
    assert out["offers"][0]["terms"][0] == term


def test_property_name_in_other_clause_untouched(appmod):
    """A term that merely identifies the property must NOT be rewritten."""
    term = "(1) You must be a new eligible resident at UniLodge Melbourne Central to qualify."
    out = appmod._rename_operator({"offers": [{"terms": [term]}]})
    assert out["offers"][0]["terms"][0] == term


def test_body_reserves_also_fixed(appmod):
    out = appmod._rename_operator(
        {"offers": [{"body": "Maple Living Group reserves the right to end this early."}]}
    )
    assert out["offers"][0]["body"].startswith("Property Management reserves the right")


def test_no_false_positive_on_plain_text(appmod):
    term = "(3) The discount is applied after move-in and the first instalment is paid."
    out = appmod._rename_operator({"offers": [{"terms": [term]}]})
    assert out["offers"][0]["terms"][0] == term


def test_runs_inside_full_postprocess(appmod):
    data = {
        "applicable": True,
        "offers": [
            {
                "title": "Special Deal: Get CA$750 CASHBACK!",
                "body": "b",
                "terms": [
                    "(1) Maple Living Group reserves the right to amend this offer.",
                    "(2) Not available at any other Maple Living Group property.",
                ],
            }
        ],
    }
    out = appmod.postprocess(data)
    joined = " ".join(out["offers"][0]["terms"])
    assert "Maple Living Group" not in joined
    assert joined.count("Property Management") == 2


def test_detected_name_blanket_replaced_in_terms(appmod):
    out = appmod._rename_operator(
        {"offers": [{"properties": ["Maple Heights Residences, Toronto"],
                     "terms": ["(1) The cashback is credited by Maple Living Group after move-in."]}]},
        detected_names=["Maple Living Group"],
    )
    t = out["offers"][0]["terms"][0]
    assert "Maple Living Group" not in t
    assert "credited by Property Management after move-in" in t


def test_detected_name_in_body_replaced(appmod):
    out = appmod._rename_operator(
        {"offers": [{"properties": ["Radford Mill, Nottingham"],
                     "body": "As per FSL policy, the discount applies after move-in."}]},
        detected_names=["FSL"],
    )
    assert "FSL" not in out["offers"][0]["body"]
    assert "As per Property Management policy" in out["offers"][0]["body"]


def test_detected_name_overlapping_property_not_blanket_replaced(appmod):
    out = appmod._rename_operator(
        {"offers": [{"properties": ["UniLodge Melbourne Central"],
                     "terms": ["(1) You must be a resident at UniLodge Melbourne Central to qualify.",
                               "(2) UniLodge reserves the right to amend."]}]},
        detected_names=["UniLodge"],
    )
    terms = out["offers"][0]["terms"]
    assert "resident at UniLodge Melbourne Central" in terms[0]   # kept
    assert terms[1] == "(2) Property Management reserves the right to amend."  # regex net


def test_generic_detected_names_ignored(appmod):
    out = appmod._rename_operator(
        {"offers": [{"properties": ["X"], "terms": ["(1) Management will review applications."]}]},
        detected_names=["Management"],
    )
    assert out["offers"][0]["terms"][0] == "(1) Management will review applications."
