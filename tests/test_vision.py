"""Tests for the vision/OCR extraction path (image PDFs + image uploads).
The actual OpenAI vision call and PDF rasterisation are mocked — no network."""

import io


def test_image_pdf_uses_vision_when_text_empty(client, appmod, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(appmod, "extract_pdf_text", lambda _: "")          # no text layer
    monkeypatch.setattr(appmod, "_pdf_to_images", lambda b, **k: [b"fakepng"])
    monkeypatch.setattr(appmod, "extract_with_vision", lambda imgs, **k: "OFFER TEXT FROM IMAGE")
    data = {"pdf": (io.BytesIO(b"%PDF-1.4 scan"), "scan.pdf")}
    r = client.post("/extract-pdf", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    body = r.get_json()
    assert body["text"] == "OFFER TEXT FROM IMAGE"
    assert body.get("source") == "vision"


def test_png_image_uses_vision(client, appmod, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(appmod, "extract_with_vision", lambda imgs, **k: "TEXT FROM PNG")
    data = {"pdf": (io.BytesIO(b"\x89PNG fake"), "offer.png")}
    r = client.post("/extract-pdf", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    assert r.get_json()["text"] == "TEXT FROM PNG"


def test_text_pdf_does_not_call_vision(client, appmod, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(appmod, "extract_pdf_text", lambda _: "Real text layer")

    def boom(*a, **k):
        raise AssertionError("vision must not be called when the PDF has text")

    monkeypatch.setattr(appmod, "extract_with_vision", boom)
    data = {"pdf": (io.BytesIO(b"%PDF-1.4 text"), "doc.pdf")}
    r = client.post("/extract-pdf", data=data, content_type="multipart/form-data")
    assert r.get_json()["text"] == "Real text layer"


def test_image_pdf_no_key_warns_instead_of_vision(client, appmod, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(appmod, "extract_pdf_text", lambda _: "")
    data = {"pdf": (io.BytesIO(b"%PDF-1.4 scan"), "scan.pdf")}
    r = client.post("/extract-pdf", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    body = r.get_json()
    assert body["text"] == ""
    assert "warning" in body
    assert "—" not in body["warning"]


def test_unsupported_extension_rejected(client):
    data = {"pdf": (io.BytesIO(b"hi"), "notes.txt")}
    r = client.post("/extract-pdf", data=data, content_type="multipart/form-data")
    assert r.status_code == 400


def test_vision_returns_empty_warns(client, appmod, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(appmod, "extract_with_vision", lambda imgs, **k: "")
    data = {"pdf": (io.BytesIO(b"\x89PNG fake"), "offer.jpg")}
    r = client.post("/extract-pdf", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    assert r.get_json()["text"] == ""
    assert "warning" in r.get_json()
