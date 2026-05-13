"""header_detect — find F-CRS-XXX/NN form codes on each page via OCR."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.scanners.utils.header_detect import HeaderDetectResult, count_form_codes
from core.scanners.utils.pdf_render import PdfRenderError

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "scanners_ocr"


@pytest.mark.slow
def test_header_detect_on_hrb_odi_compilation():
    result = count_form_codes(
        FIXTURES / "odi_compilation" / "HRB_odi_compilation.pdf", sigla_code="ODI"
    )
    assert isinstance(result, HeaderDetectResult)
    # The HRB ODI compilation should have ~17 forms; allow wide range due to OCR variance
    assert 5 <= result.count <= 50
    assert all(re.match(r"F-CRS-ODI/\d+", m, re.IGNORECASE) for m in result.matches)
    assert len(result.pages_with_match) <= result.pages_total
    assert all(0 <= p < result.pages_total for p in result.pages_with_match)
    assert result.count == len(result.pages_with_match)  # count ↔ pages_with_match consistency


def test_header_detect_on_corrupted_raises():
    with pytest.raises(PdfRenderError):
        count_form_codes(FIXTURES / "corrupted" / "corrupted.pdf", sigla_code="ODI")


def test_header_detect_sigla_code_filters_match():
    # Calling with a sigla that doesn't appear in the doc returns 0
    result = count_form_codes(
        FIXTURES / "odi_compilation" / "HRB_odi_compilation.pdf", sigla_code="NOPE"
    )
    assert result.count == 0
    assert result.matches == []
