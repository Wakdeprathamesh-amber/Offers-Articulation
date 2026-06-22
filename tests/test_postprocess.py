"""Tests for the full deterministic postprocess() pipeline and generate_offer()
with a mocked OpenAI client. No network calls."""

import json


def test_postprocess_full_pipeline(appmod, sample_model_output):
    out = appmod.postprocess(sample_model_output)
    blob = json.dumps(out)

    # Shape guaranteed
    assert out["applicable"] is True
    assert out["flags"] == ["none"]
    assert isinstance(out["offers"], list) and len(out["offers"]) == 1
    offer = out["offers"][0]

    # properties string was normalised to a list
    assert offer["properties"] == ["UniLodge Melbourne Central"]

    # No dashes anywhere
    assert "—" not in blob and "–" not in blob

    # Agent-channel term removed, legit referral-agreement term kept
    terms_joined = " ".join(offer["terms"]).lower()
    assert "agent booking portal" not in terms_joined
    assert "nomination agreement or a referral agreement" in terms_joined

    # Terms renumbered sequentially
    nums = [t.split(")")[0] + ")" for t in offer["terms"]]
    assert nums == [f"({i+1})" for i in range(len(offer["terms"]))]

    # Title annotated
    assert "title_length" in offer and "title_status" in offer


def test_postprocess_idempotent(appmod, sample_model_output):
    once = appmod.postprocess(sample_model_output)
    twice = appmod.postprocess(json.loads(json.dumps(once)))
    assert once["offers"][0]["terms"] == twice["offers"][0]["terms"]


def test_generate_offer_with_mocked_openai(appmod, monkeypatch):
    from conftest import make_fake_openai

    fake_json = json.dumps(
        {
            "applicable": True,
            "assessment": "Fine — good offer.",
            "flags": ["none"],
            "needs_kam_confirmation": False,
            "offers": [
                {
                    "properties": ["Test Prop"],
                    "title": "Big Bonus: Get US$500 GIFT CARD!",
                    "body": "Sign a lease and get US$500 between June 15–July 31.",
                    "terms": [
                        "(1) Only booking agents qualify.",
                        "(2) Subject to availability.",
                    ],
                    "missing_info": [],
                }
            ],
        }
    )
    monkeypatch.setattr("openai.OpenAI", make_fake_openai(fake_json))

    out = appmod.generate_offer("United States", "Test Prop", "Get $500 gift card")
    blob = json.dumps(out)
    assert out["applicable"] is True
    assert "—" not in blob and "–" not in blob          # dashes cleaned
    # agent term removed -> only the availability term remains
    assert out["offers"][0]["terms"] == ["(1) Subject to availability."]
    assert out["offers"][0]["title_status"] == "ok"


def test_generate_offer_propagates_bad_json(appmod, monkeypatch):
    from conftest import make_fake_openai

    monkeypatch.setattr("openai.OpenAI", make_fake_openai("this is not json"))
    try:
        appmod.generate_offer("UK", "P", "offer")
        assert False, "expected JSONDecodeError"
    except json.JSONDecodeError:
        pass  # the /generate route turns this into a clean 500


def test_pipeline_runs_all_sanitizers(appmod):
    data = {
        "applicable": True,
        "assessment": "ok",
        "flags": ["none"],
        "needs_kam_confirmation": False,
        "detected_operator_names": ["Maple Living Group"],
        "source_has_tncs": True,
        "offers": [{
            "properties": ["Maple Heights Residences, Toronto"],
            "title": "Special Deal: Get US$750 CASHBACK — Today!",   # wrong currency + em dash
            "body": "We will credit US$750 at Maple Heights Residences! Email x@y.com. Apply now!",
            "terms": [
                "1. We reserve the right to amend.",
                "2. Credited by Maple Living Group after move-in.",
                "3. Contact bookings@maple.ca for queries.",
            ],
        }],
    }
    out = appmod.postprocess(data, country="Canada")
    o = out["offers"][0]
    blob = json.dumps(out)
    assert "—" not in blob                       # dash cleaned
    assert "US$" not in o["title"] and "CA$750" in o["title"]   # currency fixed
    assert "We will" not in o["body"]            # first person fixed
    assert "x@y.com" not in o["body"]            # contact stripped
    assert "Maple Living Group" not in " ".join(o["terms"])     # operator renamed
    assert o["terms"] == [
        "(1) Property Management reserves the right to amend.",
        "(2) Credited by Property Management after move-in.",
    ]                                            # contact-only term dropped + renumbered
