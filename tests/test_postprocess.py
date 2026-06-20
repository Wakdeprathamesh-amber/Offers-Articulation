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
