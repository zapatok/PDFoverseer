"""Generic OCR scanner driven by patterns.py — replaces the per-sigla
specializations (art, irl, odi, charla). Each sigla's behavior is data-driven.

See: A6 + A7 in the spec.
"""

from __future__ import annotations

import time
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

    def count_ocr(self, folder: Path, *, cancel: CancellationToken) -> ScanResult:
        """Pase 2 — A2 anchors over every multi-page PDF, A7 lock 1-pagers."""
        cancel.check()
        base = self._filename_glob(folder)
        if "folder_missing" in base.flags:
            return base  # A8: nothing to OCR

        pdfs = sorted(folder.rglob("*.pdf"))
        if not pdfs:
            return base

        pattern = PATTERNS.get(self.sigla)
        flavors = pattern.get("cover_flavors", []) if pattern is not None else []
        if not flavors:
            return base
        top_fraction = (
            pattern.get("top_fraction", DEFAULT_TOP_FRACTION)
            if pattern is not None
            else DEFAULT_TOP_FRACTION
        )

        start = time.perf_counter()
        total_count = 0
        per_file: dict[str, int] = {}
        flags = list(base.flags)
        errors: list[str] = []
        near_matches: list[NearMatchEntry] = []
        a7_used = False

        for pdf in pdfs:
            cancel.check()
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
