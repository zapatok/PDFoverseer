"""page_count_pure — count documents in a single PDF as N pages."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.scanners.utils.page_count_pure import count_documents_in_pdf
from core.scanners.utils.pdf_render import PdfRenderError

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "scanners_ocr"


def test_count_equals_page_count():
    result = count_documents_in_pdf(FIXTURES / "odi_compilation" / "HRB_odi_compilation.pdf")
    assert result.count > 1
    assert result.method == "page_count_pure"
    assert result.pages_total == result.count


def test_count_on_corrupted_raises():
    with pytest.raises(PdfRenderError):
        count_documents_in_pdf(FIXTURES / "corrupted" / "corrupted.pdf")
