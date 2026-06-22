"""Scanner for the paginated siglas — counts documents by their per-document
"Página N de M" pagination instead of header anchors (``scan_strategy="pagination"``).

The shared ``count_ocr`` harness lives in :class:`OcrScannerBase`; this module
keeps only the pagination-specific per-PDF work (``_count_one_pdf``). The
counting engine is ``core/scanners/utils/pagination_count`` — it OCRs only the
top-right corner of each page, recovers gaps in the pagination sequence with a
lightweight forward-fill, and counts document boundaries (``curr == 1``). A7
applies (1-page PDFs contribute 1 document without OCR). A count that needed
heavy gap-recovery or produced any unresolved failed read downgrades the cell to
LOW confidence so the operator reviews it.

The per-PDF I/O (``get_page_count`` + ``count_documents_by_pagination``) is
deliberately kept in this module so the unit tests' monkeypatches (which target
``core.scanners.pagination_scanner.*``) take effect.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.ocr_scanner_base import OcrScannerBase, _PdfOutcome
from core.scanners.patterns import PATTERNS
from core.scanners.utils.pagination_count import (
    RECOVERY_LOW_CONF_RATIO,
    count_documents_by_pagination,
)
from core.scanners.utils.pdf_render import PdfRenderError, get_page_count


@dataclass
class PaginationScanner(OcrScannerBase):
    """Counts documents in compilations via the pagination engine.

    ``method`` is ``"pagination"`` (or ``"filename_glob"`` when the folder is
    missing/empty). Confidence is ``HIGH`` only if every multi-page PDF was
    counted from a trustworthy read; any failed read, heavy recovery, or
    cover_code-with-recovery downgrades the cell to ``LOW`` and adds the
    ``pagination_low_confidence`` flag.
    """

    METHOD = "pagination"
    LOW_CONF_FLAG = "pagination_low_confidence"

    def _count_one_pdf(
        self,
        pdf: Path,
        *,
        cancel: CancellationToken,
        on_page: Callable[[int, int], None] | None,
    ) -> _PdfOutcome:
        """Count one PDF via the pagination engine (A7 1-page lock + engine fallback)."""
        try:
            pages = get_page_count(pdf)
        except PdfRenderError as exc:
            # count=None → unreadable: ticked but not merged (Error/pendiente).
            return _PdfOutcome(
                None, "filename_glob", [], False, False, f"page_count_failed:{pdf.name}:{exc}"
            )

        if pages == 1:
            # A7 — 1 page = 1 document, locked, no OCR; method filename_glob → R1.
            return _PdfOutcome(1, "filename_glob", [], False, True, None)

        # Optional cover_code for this sigla (used by IRL-style siglas).
        cover_code: str | None = PATTERNS[self.sigla].get("cover_code")  # type: ignore[assignment]
        try:
            pag = count_documents_by_pagination(
                pdf, cancel=cancel, cover_code=cover_code, on_page=on_page
            )
        except CancelledError:
            raise
        except (PdfRenderError, OSError, RuntimeError) as exc:
            # Conservative fallback: count the compilation as 1 document, low-trust.
            return _PdfOutcome(
                1, "pagination", [], True, False, f"pagination_failed:{pdf.name}:{exc}"
            )

        # A degenerate count of 0 for a multi-page PDF is never right — fall back to 1.
        pdf_count = pag.count if pag.count > 0 else 1
        # Low-trust per-PDF rule: any failed read, heavy recovery, or cover_code
        # with recovered reads (possible missed cover) → LOW.
        low_trust = (
            pag.failed_reads > 0
            or pag.recovered_reads / max(1, pag.pages_total) > RECOVERY_LOW_CONF_RATIO
            or pag.cover_code_recovery
        )
        return _PdfOutcome(pdf_count, "pagination", [], bool(low_trust), False, None)
