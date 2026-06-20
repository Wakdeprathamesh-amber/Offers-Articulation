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
    assert "raw offer" in r.get_json()["error"].lower()


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
    monkeypatch.setattr(appmod, "generate_offer", lambda c, p, r: appmod.postprocess(fake))
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
    r = client.post("/generate", json={"raw_offer": "offer"})
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
    r = client.post("/generate", json={"raw_offer": "offer"})
    assert r.status_code == 500
    assert "Generation failed" in r.get_json()["error"]


# ------------------------------------------------------------- POST /extract-pdf
def test_extract_pdf_no_file(client):
    r = client.post("/extract-pdf", data={}, content_type="multipart/form-data")
    assert r.status_code == 400
    assert "No PDF" in r.get_json()["error"]


def test_extract_pdf_wrong_extension(client):
    data = {"pdf": (io.BytesIO(b"hello"), "notes.txt")}
    r = client.post("/extract-pdf", data=data, content_type="multipart/form-data")
    assert r.status_code == 400
    assert ".pdf" in r.get_json()["error"]


def test_extract_pdf_image_based_real_file_warns(client):
    """The real example PDFs are screenshots (no text layer) -> warning."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "UK offer.pdf")
    if not os.path.exists(path):
        pytest.skip("example PDF not present")
    with open(path, "rb") as f:
        data = {"pdf": (io.BytesIO(f.read()), "UK offer.pdf")}
    r = client.post("/extract-pdf", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    body = r.get_json()
    assert body["text"] == ""
    assert "warning" in body
    # our own warning text must not contain an em dash
    assert "—" not in body["warning"]


def test_extract_pdf_extraction_error_returns_400(client, appmod, monkeypatch):
    def boom(_):
        raise ValueError("corrupt pdf")

    monkeypatch.setattr(appmod, "extract_pdf_text", boom)
    data = {"pdf": (io.BytesIO(b"%PDF-1.4 broken"), "x.pdf")}
    r = client.post("/extract-pdf", data=data, content_type="multipart/form-data")
    assert r.status_code == 400
    assert "Could not read PDF" in r.get_json()["error"]


def test_extract_pdf_happy_path_mocked(client, appmod, monkeypatch):
    monkeypatch.setattr(appmod, "extract_pdf_text", lambda _: "Extracted offer text here")
    data = {"pdf": (io.BytesIO(b"%PDF-1.4 whatever"), "real.pdf")}
    r = client.post("/extract-pdf", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    assert r.get_json()["text"] == "Extracted offer text here"
