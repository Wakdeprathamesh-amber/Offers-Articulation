"""Tests for the Flask routes: /, /generate, /extract-pdf. OpenAI is mocked."""

import io
import json
import os

import pytest


# ---------------------------------------------------------------------- GET /
def test_index_loads(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.data.decode()
    assert "amber" in body
    assert "Generate offer content" in body
    assert "ALL_COUNTRIES" in body  # country list present


# ---------------------------------------------------------------- POST /generate
def test_generate_empty_offer_returns_400(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    r = client.post("/generate", json={"raw_offer": "   "})
    assert r.status_code == 400
    assert "offer text" in r.get_json()["error"].lower()


def test_generate_missing_key_returns_400(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = client.post("/generate", json={"raw_offer": "Get £500 off"})
    assert r.status_code == 400
    assert "OPENAI_API_KEY" in r.get_json()["error"]


def test_generate_happy_path(client, appmod, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake = {
        "applicable": True,
        "assessment": "ok",
        "flags": ["none"],
        "needs_kam_confirmation": False,
        "offers": [{"properties": ["P"], "title": "Save £500 OFF!", "body": "b", "terms": [], "missing_info": []}],
    }
    monkeypatch.setattr(appmod, "generate_offer", lambda *a, **k: appmod.postprocess(fake))
    r = client.post("/generate", json={"raw_offer": "£500 off", "country": "United Kingdom", "property_name": "P"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["applicable"] is True
    assert data["offers"][0]["title_status"] == "ok"


def test_generate_handles_exception_as_500(client, appmod, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def boom(*a, **k):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(appmod, "generate_offer", boom)
    r = client.post("/generate", json={"raw_offer": "offer", "country": "United Kingdom"})
    assert r.status_code == 500
    assert "Generation failed" in r.get_json()["error"]


def test_generate_non_json_body(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    # silent parse -> empty dict -> "provide raw offer" validation
    r = client.post("/generate", data="not json", content_type="text/plain")
    assert r.status_code == 400


def test_generate_bad_json_from_model_is_clean_500(client, appmod, monkeypatch):
    """End-to-end: model returns invalid JSON -> route returns a clean 500."""
    from conftest import make_fake_openai

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("openai.OpenAI", make_fake_openai("<<not json>>"))
    r = client.post("/generate", json={"raw_offer": "offer", "country": "United Kingdom"})
    assert r.status_code == 500
    assert "Generation failed" in r.get_json()["error"]


def test_raw_offer_too_long_returns_400(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    r = client.post("/generate", json={"raw_offer": "x" * 20001})
    assert r.status_code == 400
    assert "too long" in r.get_json()["error"].lower()


def test_generate_error_message_is_sanitized(client, appmod, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def boom(*a, **k):
        raise RuntimeError("super secret internal detail")

    monkeypatch.setattr(appmod, "generate_offer", boom)
    r = client.post("/generate", json={"raw_offer": "offer", "country": "United Kingdom"})
    assert r.status_code == 500
    body = r.get_json()["error"]
    assert "secret internal detail" not in body
    assert "Generation failed" in body


def test_max_content_length_configured(appmod):
    assert appmod.app.config.get("MAX_CONTENT_LENGTH") == 8 * 1024 * 1024


# ----------------------------------------------- POST /generate with a file upload
def test_generate_with_file_sends_images_directly(client, appmod, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(appmod, "file_to_images", lambda data, fn: ([b"img-bytes"], "image/png"))
    captured = {}

    def fake_gen(country, property_name, **kw):
        captured.update(country=country, property_name=property_name, **kw)
        return appmod.postprocess({"applicable": True, "offers": [
            {"title": "Big Bonus: Get US$500 GIFT CARD!", "body": "b", "terms": []}]})

    monkeypatch.setattr(appmod, "generate_offer", fake_gen)
    data = {"file": (io.BytesIO(b"%PDF fake"), "offer.pdf"),
            "country": "United States", "property_name": "P"}
    r = client.post("/generate", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    assert captured.get("images") == [b"img-bytes"]
    assert captured.get("image_mime") == "image/png"
    assert captured["country"] == "United States"


def test_generate_with_unsupported_file_returns_400(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    data = {"file": (io.BytesIO(b"x"), "notes.txt"), "country": "United Kingdom"}
    r = client.post("/generate", data=data, content_type="multipart/form-data")
    assert r.status_code == 400
    assert ".pdf" in r.get_json()["error"]


# ------------------------------------------------------------- DB run-logging
def test_generate_attaches_run_id(client, appmod, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake = {"applicable": True, "assessment": "ok", "flags": ["none"],
            "needs_kam_confirmation": False,
            "offers": [{"properties": ["P"], "title": "Save £500 OFF!", "body": "b", "terms": [], "missing_info": []}]}
    monkeypatch.setattr(appmod, "generate_offer", lambda *a, **k: appmod.postprocess(fake))
    monkeypatch.setattr(appmod.store, "log_run", lambda *a, **k: 999)
    r = client.post("/generate", json={"raw_offer": "£500 off", "country": "United Kingdom", "property_name": "P"})
    assert r.status_code == 200
    assert r.get_json()["run_id"] == 999


def test_generate_no_run_id_when_db_disabled(client, appmod, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake = {"applicable": True, "flags": ["none"], "offers": []}
    monkeypatch.setattr(appmod, "generate_offer", lambda *a, **k: appmod.postprocess(fake))
    monkeypatch.setattr(appmod.store, "log_run", lambda *a, **k: None)
    r = client.post("/generate", json={"raw_offer": "x", "country": "UK", "property_name": "P"})
    assert r.status_code == 200
    assert "run_id" not in r.get_json()


def test_feedback_success(client, appmod, monkeypatch):
    called = {}
    monkeypatch.setattr(appmod.store, "save_feedback",
                        lambda run_id, rating, comment: called.update(run_id=run_id, rating=rating, comment=comment) or True)
    r = client.post("/feedback", json={"run_id": 12, "rating": 4, "comment": "good"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert called == {"run_id": 12, "rating": 4, "comment": "good"}


def test_feedback_without_run_id_logs_a_new_row(client, appmod, monkeypatch):
    # No run_id (run wasn't logged) -> create a fresh row from context, then save.
    logged = {}
    monkeypatch.setattr(appmod.store, "save_feedback",
                        lambda run_id, rating, comment: logged.update(saved_id=run_id) or True)
    monkeypatch.setattr(appmod.store, "log_run", lambda *a, **k: "new123")
    r = client.post("/feedback", json={"rating": 4, "comment": "nice",
                                       "context": {"country": "UK", "offers": [{"title": "T", "terms": []}]}})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert logged["saved_id"] == "new123"


def test_feedback_unavailable_when_no_backend(client, appmod, monkeypatch):
    # No run_id and logging disabled -> 503, never crashes.
    monkeypatch.setattr(appmod.store, "save_feedback", lambda *a, **k: False)
    monkeypatch.setattr(appmod.store, "log_run", lambda *a, **k: None)
    r = client.post("/feedback", json={"rating": 4, "comment": "nice", "context": {}})
    assert r.status_code == 503


def test_feedback_rejects_bad_rating(client, appmod, monkeypatch):
    monkeypatch.setattr(appmod.store, "save_feedback", lambda *a, **k: True)
    r = client.post("/feedback", json={"run_id": 1, "rating": 9})
    assert r.status_code == 400


def test_feedback_requires_rating_or_comment(client):
    r = client.post("/feedback", json={"run_id": 1})
    assert r.status_code == 400


def test_generate_without_country_continues_and_flags(client, appmod, monkeypatch):
    # Missing country is a soft gate now: generate anyway and flag it.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake = {"applicable": True, "flags": ["none"],
            "offers": [{"properties": ["P"], "title": "Save £500 OFF!", "body": "b", "terms": []}]}
    monkeypatch.setattr(appmod, "generate_offer",
                        lambda country, prop, **k: {**appmod.postprocess(fake),
                                                    "warnings": appmod._compliance_warnings(appmod.postprocess(fake), country)})
    r = client.post("/generate", json={"raw_offer": "£500 off"})  # no country
    assert r.status_code == 200
    rules = {w["rule"] for w in r.get_json().get("warnings", [])}
    assert "COUNTRY_MISSING" in rules


def test_compliance_flags_missing_country(appmod):
    result = appmod.postprocess({"applicable": True, "offers": [{"title": "T", "body": "b", "terms": []}]})
    warns = appmod._compliance_warnings(result, "")   # no country
    assert "COUNTRY_MISSING" in {w["rule"] for w in warns}
