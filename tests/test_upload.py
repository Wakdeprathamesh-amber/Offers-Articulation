"""Tests for file -> images conversion used by the direct multimodal generation."""

import os


def test_image_passthrough(appmod):
    imgs, mime = appmod.file_to_images(b"\x89PNG-fake", "screenshot.png")
    assert imgs == [b"\x89PNG-fake"]
    assert mime == "image/png"


def test_jpg_mime(appmod):
    _, mime = appmod.file_to_images(b"jpegbytes", "offer.JPG")
    assert mime == "image/jpeg"


def test_pdf_rasterised_to_images(appmod):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "US Offer.pdf")
    if not os.path.exists(path):
        import pytest
        pytest.skip("example PDF not present")
    with open(path, "rb") as f:
        imgs, mime = appmod.file_to_images(f.read(), "US Offer.pdf")
    assert len(imgs) >= 1
    assert imgs[0][:8] == b"\x89PNG\r\n\x1a\n"   # PNG magic
    assert mime == "image/png"


def test_image_content_builds_data_uris(appmod):
    parts = appmod._image_content([b"abc"], "image/png")
    assert parts[0]["type"] == "image_url"
    assert parts[0]["image_url"]["url"].startswith("data:image/png;base64,")
