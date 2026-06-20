"""Shared pytest fixtures and path setup for the offer-automation test suite."""

import os
import sys

import pytest

# Make the project root importable (app.py / prompts.py live one level up).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as app_module  # noqa: E402
import prompts as prompts_module  # noqa: E402


@pytest.fixture
def appmod():
    """The imported app module (for calling helper functions directly)."""
    return app_module


@pytest.fixture
def prompts():
    return prompts_module


@pytest.fixture
def client():
    """Flask test client."""
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


@pytest.fixture
def sample_model_output():
    """A realistic raw model output (pre-postprocess) used across tests.

    Deliberately contains: an em dash, an en dash, an agent-channel term,
    a string `flags`, and a missing `missing_info` to exercise normalisation
    and cleaning together.
    """
    return {
        "applicable": True,
        "assessment": "Valid offer — applicable to agents.",
        "flags": "none",
        "needs_kam_confirmation": False,
        "offers": [
            {
                "properties": "UniLodge Melbourne Central",
                "title": "Big Savings: Get Up to 2 Weeks Rent FREE on Select Units!",
                "body": "Book now and enjoy 2 weeks rent FREE between June 15–July 31, 2026 — limited spots!",
                "terms": [
                    "(1) Valid for new eligible residents at UniLodge Melbourne Central.",
                    "(2) The offer is available via the agent booking portal by education agents, booking agents, or referral agents.",
                    "(3) This offer excludes bookings referred through a nomination agreement or a referral agreement.",
                    "(4) UniLodge reserves the right to withdraw the offer.",
                ],
            }
        ],
    }


def make_fake_openai(content: str):
    """Return a fake OpenAI client class that yields `content` as the response.

    Usage in a test:
        monkeypatch.setattr("openai.OpenAI", make_fake_openai(json_str))
    """

    class _Msg:
        def __init__(self, c):
            self.content = c

    class _Choice:
        def __init__(self, c):
            self.message = _Msg(c)

    class _Resp:
        def __init__(self, c):
            self.choices = [_Choice(c)]

    class _Completions:
        def create(self, **kwargs):
            # Validate the call shape the app relies on.
            assert kwargs.get("model")
            assert kwargs.get("response_format") == {"type": "json_object"}
            assert isinstance(kwargs.get("messages"), list)
            return _Resp(content)

    class _Chat:
        completions = _Completions()

    class _FakeClient:
        chat = _Chat()

    def _factory(*args, **kwargs):
        return _FakeClient()

    return _factory
