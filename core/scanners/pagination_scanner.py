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

**RCH cover de-dup (Track D / D2, Task 8):** the pagination engine flags
``repeated_pattern_detected`` when a file's corner OCR shows the exact RCH
template-bug signature (two adjacent pages both reading ``curr == 1`` with the
same total). For siglas that opt in via ``PATTERNS[sigla]["rch_fallback"]``
(today: only ``charla`` — the migration gate its two RCH siblings,
chintegral/dif_pts, did NOT pass; see
``docs/research/2026-07-12-rch-pagination-decision.md``), that one PDF's count
is re-derived via the anchors engine instead of trusted from pagination —
zero count risk on the rare bug occurrence, full pagination speed on every
other file. Siglas WITHOUT the flag never engage this path, even if the
signal fires — a deliberate per-sigla opt-in so already-migrated siglas
(art, odi, irl, …) can't silently change behavior from a mechanism their own
gate never evaluated.

The per-PDF I/O (``get_page_count`` + ``count_documents_by_pagination`` +
``count_covers_by_anchors``) is deliberately kept in this module so the unit
tests' monkeypatches (which target ``core.scanners.pagination_scanner.*``)
take effect.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.ocr_scanner_base import OcrScannerBase, _PdfOutcome
from core.scanners.patterns import DEFAULT_TOP_FRACTION, PATTERNS
from core.scanners.utils.header_band_anchors import count_covers_by_anchors
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

        pattern = PATTERNS[self.sigla]
        if pag.repeated_pattern_detected and pattern.get("rch_fallback"):
            return self._rch_anchors_fallback(pdf, pattern, cancel=cancel)

        # A degenerate count of 0 for a multi-page PDF is never right — fall back to 1.
        pdf_count = pag.count if pag.count > 0 else 1
        # Low-trust per-PDF rule: any failed read, heavy recovery, cover_code with
        # recovered reads (possible missed cover), or — without cover_code — any
        # recovered document-start (F7: a recovered curr==1 can fabricate a start in
        # a mixed-length compilation; with cover_code set, a recovered curr==1 is
        # never counted anyway — count_starts requires a code match — so
        # cover_code_recovery alone covers that edge) → LOW.
        low_trust = (
            pag.failed_reads > 0
            or pag.recovered_reads / max(1, pag.pages_total) > RECOVERY_LOW_CONF_RATIO
            or pag.cover_code_recovery
            or (cover_code is None and pag.recovered_start_count > 0)
        )
        return _PdfOutcome(pdf_count, "pagination", [], bool(low_trust), False, None)

    def _rch_anchors_fallback(
        self, pdf: Path, pattern: dict, *, cancel: CancellationToken
    ) -> _PdfOutcome:
        """Re-derive one PDF's count via the anchors engine (RCH de-dup, Task 8).

        Reuses this sigla's own ``cover_flavors``/``top_fraction`` (retained on
        the ``patterns.py`` entry per the one-line-reversibility convention) and
        the F8 "0 covers on a multi-page PDF is never right" low-trust rule,
        identical to ``AnchorsScanner``'s own. ``on_page`` is intentionally NOT
        forwarded here: the pagination read already drove the progress counter
        for this PDF once — replaying it through a second, independent engine
        would make the progress bar jump backward mid-file. This is the rare
        path (the migration gate's benchmark measured 2/7 real samples;
        ``docs/research/2026-07-12-rch-pagination-decision.md`` §Velocidad).
        """
        flavors = pattern.get("cover_flavors", [])
        top_fraction = pattern.get("top_fraction", DEFAULT_TOP_FRACTION)
        try:
            anchors = count_covers_by_anchors(
                pdf, flavors=flavors, top_fraction=top_fraction, cancel=cancel, on_page=None
            )
        except CancelledError:
            raise
        except (PdfRenderError, OSError, RuntimeError) as exc:
            # low_trust=True here vs AnchorsScanner's False on its own failure
            # path: inconsequential — the error string below already forces
            # ScanResult.confidence=LOW either way (ocr_scanner_base's
            # `not errors` check); this flag is just more explicit.
            return _PdfOutcome(
                1, "pagination", [], True, False, f"rch_fallback_failed:{pdf.name}:{exc}"
            )
        nms = [
            {
                "pdf_name": pdf.name,
                "page_index": nm.page_index,
                "flavor_name": nm.flavor_name,
                "matched_anchors": list(nm.matched_anchors),
                "missing_anchors": list(nm.missing_anchors),
            }
            for nm in anchors.near_matches
        ]
        # F8, reused verbatim from AnchorsScanner: 0 covers on a multi-page PDF
        # is never right at face value.
        low_trust = anchors.count == 0
        return _PdfOutcome(anchors.count, "header_band_anchors", nms, low_trust, False, None)
