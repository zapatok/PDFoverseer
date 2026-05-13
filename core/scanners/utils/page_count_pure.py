"""Trivial scanner util: assume 1 PDF page == 1 document.

Used by charla_scanner when the carpeta has a single compilation PDF.
Multi-PDF charla folders fall back to filename_glob — they don't sum
page counts (that would count pages, not documents).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.scanners.utils.pdf_render import get_page_count


@dataclass(frozen=True)
class PageCountPureResult:
    count: int
    pages_total: int
    method: str = "page_count_pure"


def count_documents_in_pdf(pdf_path: Path) -> PageCountPureResult:
    """Open *pdf_path*, return count = page_count. Raises PdfRenderError on
    invalid/missing PDF."""
    n = get_page_count(pdf_path)
    return PageCountPureResult(count=n, pages_total=n)
