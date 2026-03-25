"""Tests for OCR tier cascade (core/ocr.py).

Tier order: T1 (DPI 150) → T2 (SR 4x) → T2b (DPI 300) → EasyOCR (GPU consumer).
"""
import numpy as np
import pytest
from unittest.mock import patch, MagicMock
import fitz

from core.utils import _PageRead


def _make_fake_doc(n_pages=1):
    """Create a mock fitz.Document with n pages."""
    doc = MagicMock(spec=fitz.Document)
    pages = []
    for _ in range(n_pages):
        page = MagicMock(spec=fitz.Page)
        page.rect = fitz.Rect(0, 0, 612, 792)
        pages.append(page)
    doc.__getitem__ = lambda self, idx: pages[idx]
    doc.__len__ = lambda self: len(pages)
    return doc


class TestProcessPageReturnType:
    """_process_page must return (PageRead, bgr_300_or_None)."""

    @patch("core.ocr._tess_ocr", return_value="Página 1 de 4")
    @patch("core.ocr._deskew", side_effect=lambda x: x)
    @patch("core.ocr._render_clip", return_value=np.zeros((50, 150, 3), dtype=np.uint8))
    def test_tier1_success_returns_tuple_with_none(self, mock_render, mock_deskew, mock_tess):
        """When Tier 1 succeeds, return (PageRead, None) — no DPI 300 image needed."""
        from core.ocr import _process_page
        doc = _make_fake_doc()
        result = _process_page(doc, 0)
        assert isinstance(result, tuple) and len(result) == 2
        pr, img = result
        assert isinstance(pr, _PageRead)
        assert pr.method == "direct"
        assert img is None

    @patch("core.ocr._tess_ocr")
    @patch("core.ocr._upsample_4x", return_value=np.zeros((200, 600, 3), dtype=np.uint8))
    @patch("core.ocr._deskew", side_effect=lambda x: x)
    @patch("core.ocr._render_clip", return_value=np.zeros((50, 150, 3), dtype=np.uint8))
    def test_tier2_sr_success_returns_no_image(self, mock_render, mock_deskew, mock_sr, mock_tess):
        """When Tier 1 fails but SR succeeds, return (PageRead, None)."""
        mock_tess.side_effect = ["garbage", "Página 2 de 4"]
        from core.ocr import _process_page
        doc = _make_fake_doc()
        result = _process_page(doc, 0)
        pr, img = result
        assert pr.method == "super_resolution"
        assert pr.curr == 2
        assert img is None

    @patch("core.ocr._tess_ocr")
    @patch("core.ocr._upsample_4x", return_value=np.zeros((200, 600, 3), dtype=np.uint8))
    @patch("core.ocr._deskew", side_effect=lambda x: x)
    @patch("core.ocr._render_clip", return_value=np.zeros((50, 150, 3), dtype=np.uint8))
    def test_tier2b_dpi300_success_returns_image(self, mock_render, mock_deskew, mock_sr, mock_tess):
        """When T1 and SR fail but T2b succeeds, method is 'dpi300' and bgr_300 is returned."""
        # T1 fails, SR fails, T2b succeeds
        mock_tess.side_effect = ["garbage", "garbage", "Página 3 de 4"]
        from core.ocr import _process_page
        doc = _make_fake_doc()
        result = _process_page(doc, 0)
        pr, img = result
        assert pr.method == "dpi300"
        assert pr.curr == 3
        assert pr.total == 4
        # bgr_300 returned so GPU consumer can reuse it
        assert img is not None
        assert isinstance(img, np.ndarray)
        # Verify DPI 300 render happened (2nd render call)
        assert mock_render.call_count == 2
        assert mock_render.call_args_list[1][1].get("dpi") == 300

    @patch("core.ocr._tess_ocr", return_value="garbage no match")
    @patch("core.ocr._upsample_4x", return_value=np.zeros((200, 600, 3), dtype=np.uint8))
    @patch("core.ocr._deskew", side_effect=lambda x: x)
    @patch("core.ocr._render_clip", return_value=np.zeros((50, 150, 3), dtype=np.uint8))
    def test_all_tiers_fail_returns_bgr300(self, mock_render, mock_deskew, mock_sr, mock_tess):
        """When all Tesseract tiers fail, return (failed_PageRead, bgr_300)."""
        from core.ocr import _process_page
        doc = _make_fake_doc()
        result = _process_page(doc, 0)
        pr, img = result
        assert pr.method == "failed"
        assert img is not None
        assert isinstance(img, np.ndarray)
        assert len(img.shape) == 3
