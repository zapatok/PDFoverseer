"""Find `F-CRS-XXX/NN` form codes in the top-third of each PDF page.

Used by odi_scanner and irl_scanner to count documents in compilations.
The form code pattern is canonical to CRS prevention paperwork:
`F-CRS-ODI/03`, `F-CRS-IRL/45`, etc.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pytesseract
from PIL import Image

from core.scanners.utils.pdf_render import get_page_count, render_page_region


@dataclass(frozen=True)
class HeaderDetectResult:
    count: int
    matches: list[str] = field(default_factory=list)
    pages_with_match: list[int] = field(default_factory=list)
    pages_total: int = 0
    method: str = "header_detect"


_TOP_THIRD_BBOX = (0.0, 0.0, 1.0, 0.35)  # full width, top 35% of page


def _build_pattern(sigla_code: str) -> re.Pattern[str]:
    # Tolerant of OCR noise around dashes/slashes and case
    return re.compile(
        rf"F[\s\-_]*CRS[\s\-_]*{re.escape(sigla_code)}[\s\-_/]+(\d{{1,3}})",
        re.IGNORECASE,
    )


def count_form_codes(
    pdf_path: Path,
    *,
    sigla_code: str,
    dpi: int = 200,
) -> HeaderDetectResult:
    """OCR the top-third of each page; count unique form codes.

    Args:
        pdf_path: Source PDF.
        sigla_code: Uppercase sigla (``"ODI"``, ``"IRL"``, ...). Matches
                    ``F-CRS-<sigla>/<number>``.
        dpi: rendering DPI (default 200 — sufficient for form codes).

    Returns:
        :class:`HeaderDetectResult` with the count of unique codes matched.
    """
    pages_total = get_page_count(pdf_path)
    pattern = _build_pattern(sigla_code)
    matches: set[str] = set()
    pages_with_match: list[int] = []

    for page_idx in range(pages_total):
        img: Image.Image = render_page_region(pdf_path, page_idx, bbox=_TOP_THIRD_BBOX, dpi=dpi)
        text = pytesseract.image_to_string(img, config="--psm 6 --oem 1", lang="spa+eng")
        page_matches = pattern.findall(text)
        if page_matches:
            for m in page_matches:
                matches.add(f"F-CRS-{sigla_code.upper()}/{m}")
            pages_with_match.append(page_idx)

    return HeaderDetectResult(
        count=len(matches),
        matches=sorted(matches),
        pages_with_match=pages_with_match,
        pages_total=pages_total,
    )
