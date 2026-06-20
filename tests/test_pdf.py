"""Tests for PDF text extraction against the real example files and a
generated text-PDF (when reportlab is available)."""

import glob
import io
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _example_pdfs():
    return glob.glob(os.path.join(ROOT, "*.pdf"))


def test_real_example_pdfs_have_no_text_layer(appmod):
    """The four shared tickets are screenshots; extraction should be empty."""
    pdfs = _example_pdfs()
    if not pdfs:
        pytest.skip("no example PDFs present")
    for path in pdfs:
        with open(path, "rb") as f:
            text = appmod.extract_pdf_text(io.BytesIO(f.read()))
        # image-based -> empty (this is the documented v1 behaviour)
        assert text == "", f"{os.path.basename(path)} unexpectedly had a text layer"


def test_text_pdf_extracts(appmod):
    """Happy path: a real text-based PDF should extract its text."""
    reportlab = pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas  # noqa: E402

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, "Book now and receive a 500 pound discount")
    c.save()
    buf.seek(0)

    text = appmod.extract_pdf_text(buf)
    assert "Book now" in text
    assert "discount" in text


def test_corrupt_pdf_raises(appmod):
    with pytest.raises(Exception):
        appmod.extract_pdf_text(io.BytesIO(b"this is definitely not a pdf"))
