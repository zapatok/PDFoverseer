"""Generic OCR scanner driven by patterns.py — replaces the per-sigla
specializations (art, irl, odi, charla). Each sigla's behavior is data-driven.

The shared ``count_ocr`` harness lives in :class:`OcrScannerBase`; this module
keeps only the anchor-specific per-PDF work (``_count_one_pdf``) and the
"no flavors configured" short-circuit (``_precheck``). The per-PDF I/O
(``get_page_count`` + ``count_covers_by_anchors``) is deliberately kept in this
module so the unit tests' monkeypatches (which target
``core.scanners.anchors_scanner.*``) take effect.

See: A6 + A7 in the spec.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.scanners.base import ScanResult
from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.ocr_scanner_base import OcrScannerBase, _PdfOutcome
from core.scanners.patterns import DEFAULT_TOP_FRACTION, PATTERNS
from core.scanners.utils.header_band_anchors import count_covers_by_anchors
from core.scanners.utils.pdf_render import PdfRenderError, get_page_count


@dataclass
class AnchorsScanner(OcrScannerBase):
    """Generic anchor-based scanner. ``sigla`` indexes into ``PATTERNS``.

    Pase-2 OCR uses header-band anchors (A2) with the A7 one-page lock:
    single-page files contribute 1 document without OCR; multi-page files are
    scanned by ``count_covers_by_anchors`` using the flavors declared in
    ``PATTERNS[sigla]``. ``method`` is ``"header_band_anchors"`` (or
    ``"filename_glob"`` when no flavors are configured / the folder is missing).
    """

    METHOD = "header_band_anchors"
    LOW_CONF_FLAG = None

    def _precheck(
        self,
        folder: Path,
        pdfs: list[Path],
        base: ScanResult,
        on_pdf: Callable[[str, int | None, str, list[dict]], None] | None,
    ) -> ScanResult | None:
        """No-flavors short-circuit: tick progress only, never merge (clobber-guard)."""
        pattern = PATTERNS.get(self.sigla)
        flavors = pattern.get("cover_flavors", []) if pattern is not None else []
        if not flavors:
            # No anchor OCR work, but the pre-count already counted these PDFs;
            # emit one progress tick each so the bar's `done` matches `total`.
            # method="filename_glob" → la ruta lo trata como solo-progreso (no
            # fusiona), así no pisa el conteo de pase 1.
            if on_pdf is not None:
                base_pf = base.per_file or {}
                for pdf in pdfs:
                    on_pdf(pdf.name, base_pf.get(pdf.name, 0), "filename_glob", [])
            return base
        return None

    def _count_one_pdf(
        self,
        pdf: Path,
        *,
        cancel: CancellationToken,
        on_page: Callable[[int, int], None] | None,
    ) -> _PdfOutcome:
        """Count one PDF via header-band anchors (A7 1-page lock + engine fallback)."""
        try:
            page_count = get_page_count(pdf)
        except PdfRenderError as exc:
            # count=None → unreadable: ticked but not merged (Error/pendiente).
            return _PdfOutcome(
                None, "filename_glob", [], False, False, f"page_count_failed:{pdf.name}:{exc}"
            )

        if page_count == 1:
            # A7 — 1 page = 1 doc trivial + locked; method filename_glob → R1.
            return _PdfOutcome(1, "filename_glob", [], False, True, None)

        pattern = PATTERNS.get(self.sigla)
        flavors = pattern.get("cover_flavors", []) if pattern is not None else []
        top_fraction = (
            pattern.get("top_fraction", DEFAULT_TOP_FRACTION)
            if pattern is not None
            else DEFAULT_TOP_FRACTION
        )
        try:
            ocr = count_covers_by_anchors(
                pdf,
                flavors=flavors,
                top_fraction=top_fraction,
                cancel=cancel,
                on_page=on_page,
            )
        except CancelledError:
            raise
        except (PdfRenderError, OSError, RuntimeError) as exc:
            # Fallback to 1 doc per PDF heuristic (conservative); not low-trust.
            return _PdfOutcome(
                1, "header_band_anchors", [], False, False, f"anchors_failed:{pdf.name}:{exc}"
            )

        # Serialize near-matches to dicts to cross the IPC queue + for
        # apply_per_file_ocr_result (expects list[dict]); the base rebuilds
        # NearMatchEntry telemetry from these keys.
        nms = [
            {
                "pdf_name": pdf.name,
                "page_index": nm.page_index,
                "flavor_name": nm.flavor_name,
                "matched_anchors": list(nm.matched_anchors),
                "missing_anchors": list(nm.missing_anchors),
            }
            for nm in ocr.near_matches
        ]
        return _PdfOutcome(ocr.count, "header_band_anchors", nms, False, False, None)
