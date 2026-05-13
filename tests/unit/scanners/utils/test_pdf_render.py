"""pdf_render utility — PyMuPDF wrappers for rendering and counting."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from core.scanners.utils.pdf_render import (
    PdfRenderError,
    get_page_count,
    render_page_image,
    render_page_region,
)

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "scanners_ocr"
HRB_ODI = FIXTURES / "odi_compilation" / "HRB_odi_compilation.pdf"
CORRUPTED = FIXTURES / "corrupted" / "corrupted.pdf"


def test_get_page_count_on_real_pdf():
    n = get_page_count(HRB_ODI)
    assert n > 1  # compilation has multiple pages


def test_get_page_count_on_corrupted_raises():
    with pytest.raises(PdfRenderError):
        get_page_count(CORRUPTED)


def test_get_page_count_on_missing_file_raises():
    with pytest.raises(PdfRenderError):
        get_page_count(Path("/does/not/exist.pdf"))


def test_render_page_image_returns_pil_image():
    img = render_page_image(HRB_ODI, page_idx=0, dpi=150)
    assert isinstance(img, Image.Image)
    assert img.width > 100
    assert img.height > 100


def test_render_page_image_invalid_page_raises():
    with pytest.raises(PdfRenderError):
        render_page_image(HRB_ODI, page_idx=9999, dpi=150)


def test_render_page_region_clips_to_bbox():
    # Top-right quadrant
    full = render_page_image(HRB_ODI, page_idx=0, dpi=150)
    region = render_page_region(HRB_ODI, page_idx=0, bbox=(0.5, 0.0, 1.0, 0.5), dpi=150)
    assert region.width < full.width
    assert region.height < full.height
    # bbox uses relative coords [0..1]; top-right ≈ quarter of full area
    assert abs(region.width - full.width / 2) < 5
    assert abs(region.height - full.height / 2) < 5


def test_render_page_region_validates_bbox():
    with pytest.raises(ValueError):
        render_page_region(HRB_ODI, page_idx=0, bbox=(0.0, 0.0, 2.0, 1.0), dpi=150)
