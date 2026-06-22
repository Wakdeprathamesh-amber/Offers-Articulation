"""Model-compatibility: the OpenAI call must work whether or not the chosen model
supports a custom temperature (GPT-5 / GPT-5.5 reject temperature != default)."""

import json


def _client_that_rejects_temperature(calls):
    """Fake OpenAI client: raises on a custom temperature, succeeds without it."""
    ok = json.dumps({
        "applicable": True, "assessment": "ok", "flags": ["none"],
        "needs_kam_confirmation": False, "source_has_tncs": False,
        "detected_operator_names": [],
        "offers": [{"properties": ["P"], "title": "Save £500 OFF!", "body": "b. Apply now!",
                    "terms": ["(1) Subject to availability."], "missing_info": []}],
    })

    class _Completions:
        def create(self, **kw):
            calls.append(dict(kw))
            if "temperature" in kw:
                raise Exception(
                    "Error code: 400 - Unsupported value: 'temperature' does not "
                    "support 0.3 with this model. Only the default (1) is supported."
                )
            msg = type("M", (), {"content": ok})
            return type("R", (), {"choices": [type("C", (), {"message": msg})]})

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

        def __init__(self, *a, **k):
            pass

    return _Client


def test_falls_back_when_temperature_unsupported(appmod, monkeypatch):
    calls = []
    monkeypatch.setattr("openai.OpenAI", _client_that_rejects_temperature(calls))
    # reset the session cache so the first call attempts temperature
    monkeypatch.setattr(appmod, "_SEND_TEMPERATURE", True, raising=False)

    out = appmod.generate_offer("United Kingdom", "P", "Get £500 off")
    assert out["applicable"] is True
    # first attempt sent temperature, fallback attempt omitted it
    assert any("temperature" in c for c in calls)
    assert any("temperature" not in c for c in calls)


def test_non_temperature_errors_still_raise(appmod, monkeypatch):
    class _Boom:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    raise RuntimeError("network exploded")

        def __init__(self, *a, **k):
            pass

    monkeypatch.setattr("openai.OpenAI", lambda *a, **k: _Boom())
    monkeypatch.setattr(appmod, "_SEND_TEMPERATURE", True, raising=False)
    try:
        appmod.generate_offer("UK", "P", "offer")
        assert False, "expected the non-temperature error to propagate"
    except RuntimeError as e:
        assert "network exploded" in str(e)
