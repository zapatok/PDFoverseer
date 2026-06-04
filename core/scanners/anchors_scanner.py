"""Generic OCR scanner driven by patterns.py — replaces the per-sigla
specializations (art, irl, odi, charla). Each sigla's behavior is data-driven.

See: A6 + A7 in the spec.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.scanners.base import (
    ConfidenceLevel,
    NearMatchEntry,
    ScanResult,
    ScanTelemetry,
)
from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.patterns import DEFAULT_TOP_FRACTION, PATTERNS
from core.scanners.simple_factory import SimpleFilenameScanner
from core.scanners.utils.cell_enumeration import enumerate_cell_pdfs
from core.scanners.utils.header_band_anchors import (
    count_covers_by_anchors,
)
from core.scanners.utils.pdf_render import PdfRenderError, get_page_count


@dataclass
class AnchorsScanner:
    """Generic anchor-based scanner. `sigla` indexes into `PATTERNS`."""

    sigla: str

    def count(self, folder: Path, *, override_method: str | None = None) -> ScanResult:
        """Pase 1 — uniform filename_glob."""
        return SimpleFilenameScanner(sigla=self.sigla).count(
            folder, override_method=override_method
        )

    def count_ocr(
        self,
        folder: Path,
        *,
        cancel: CancellationToken,
        on_pdf: Callable[[str], None] | None = None,
        only: str | None = None,
        on_page: Callable[[int, int], None] | None = None,
    ) -> ScanResult:
        """Run pase-2 OCR using header-band anchors (A2) with A7 one-page lock.

        For each PDF in *folder*: single-page files contribute 1 document
        without OCR (A7 lock); multi-page files are scanned by
        ``count_covers_by_anchors`` using the flavors declared in
        ``PATTERNS[sigla]``. Results are summed into a single ``ScanResult``.

        Args:
            folder: Directory containing the PDFs to scan.
            cancel: Token checked before each PDF; raises ``CancelledError``
                if the orchestrator has signalled cancellation.
            on_pdf: Optional callback invoked with each PDF's filename once it
                has been processed (A7, OCR, or handled error). Drives the
                per-PDF progress bar; never called for a PDF aborted by
                cancellation.

        Returns:
            A ``ScanResult`` with:
              - ``count``: total document covers found across all PDFs.
              - ``method``: ``"header_band_anchors"`` (or ``"filename_glob"``
                if no flavors are configured or all files are absent).
              - ``confidence``: ``HIGH`` if no errors, ``LOW`` otherwise.
              - ``flags``: includes ``"a7_one_page_locked"`` when at least one
                single-page PDF was counted trivially.
              - ``per_file``: per-filename document count.
              - ``telemetry``: near-match entries if any were collected.
        """
        cancel.check()
        base = self._filename_glob(folder)
        if "folder_missing" in base.flags:
            return base  # A8: nothing to OCR

        pdfs = enumerate_cell_pdfs(folder)
        if only is not None:
            # Single-file scan (rev-2 #1): scope to just this PDF; per_file/count
            # below cover only it, leaving the rest of the cell untouched.
            pdfs = [p for p in pdfs if p.name == only]
        if not pdfs:
            return base

        pattern = PATTERNS.get(self.sigla)
        flavors = pattern.get("cover_flavors", []) if pattern is not None else []
        if not flavors:
            # No anchor OCR work, but the pre-count already counted these PDFs;
            # emit one progress tick each so the bar's `done` matches `total`.
            if on_pdf is not None:
                for pdf in pdfs:
                    on_pdf(pdf.name)
            return base
        top_fraction = pattern.get("top_fraction", DEFAULT_TOP_FRACTION)  # pattern is non-None here

        start = time.perf_counter()
        total_count = 0
        per_file: dict[str, int] = {}
        flags = list(base.flags)
        errors: list[str] = []
        near_matches: list[NearMatchEntry] = []
        a7_used = False

        for pdf in pdfs:
            cancel.check()  # outside the try: a pre-PDF cancel must not emit on_pdf
            emit = True
            try:
                try:
                    page_count = get_page_count(pdf)
                except PdfRenderError as exc:
                    errors.append(f"page_count_failed:{pdf.name}:{exc}")
                    continue

                if page_count == 1:
                    # A7 — 1 page = 1 doc trivial + locked
                    per_file[pdf.name] = 1
                    total_count += 1
                    a7_used = True
                    continue

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
                    errors.append(f"anchors_failed:{pdf.name}:{exc}")
                    # Fallback to 1 doc per PDF heuristic (conservative)
                    per_file[pdf.name] = 1
                    total_count += 1
                    continue

                per_file[pdf.name] = ocr.count
                total_count += ocr.count
                for nm in ocr.near_matches:
                    near_matches.append(
                        NearMatchEntry(
                            pdf_name=pdf.name,
                            page_index=nm.page_index,
                            flavor_name=nm.flavor_name,
                            matched_anchors=nm.matched_anchors,
                            missing_anchors=nm.missing_anchors,
                        )
                    )
            except CancelledError:
                # Cancelled mid-PDF: this file did not finish — do not tick it.
                emit = False
                raise
            finally:
                # `finally` runs through every `continue` above, so A7/error
                # branches still count as one processed PDF.
                if emit and on_pdf is not None:
                    on_pdf(pdf.name)

        if a7_used:
            flags.append("a7_one_page_locked")

        duration_ms = int((time.perf_counter() - start) * 1000)
        confidence = ConfidenceLevel.HIGH if not errors else ConfidenceLevel.LOW
        return ScanResult(
            count=total_count,
            confidence=confidence,
            method="header_band_anchors",
            breakdown=base.breakdown,
            flags=flags,
            errors=errors,
            duration_ms=duration_ms,
            files_scanned=len(pdfs),
            per_file=per_file,
            telemetry=ScanTelemetry(near_matches=near_matches) if near_matches else None,
        )

    def _filename_glob(self, folder: Path) -> ScanResult:
        return SimpleFilenameScanner(sigla=self.sigla).count(folder)
