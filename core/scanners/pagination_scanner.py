"""Scanner driven by 'Página N de M' pagination — pase 2 for siglas with
heterogeneous templates but reliable Spanish pagination (cat 8 insgral,
cat 14 altura).

Reuses `core/scanners/utils/corner_count.count_paginations` — the minimal
engine that OCR's the upper-right corner and counts document transitions.
This is deliberately MUCH simpler than the full V4 pipeline
(`core/pipeline.py`): no parallel workers, no GPU SR, no Dempster-Shafer
inference. V4 stays intact as legacy code; if a future failure mode
demands its capabilities, we can promote a sigla to V4 via a new strategy.

A7 still applies: 1-page PDFs contribute count=1 without OCR.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from core.scanners.base import ConfidenceLevel, ScanResult
from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.simple_factory import SimpleFilenameScanner
from core.scanners.utils.corner_count import count_paginations
from core.scanners.utils.pdf_render import PdfRenderError, get_page_count


@dataclass
class PaginationScanner:
    """Counts documents in compilations via 'Página N de M' transitions."""

    sigla: str

    def count(self, folder: Path, *, override_method: str | None = None) -> ScanResult:
        return SimpleFilenameScanner(sigla=self.sigla).count(
            folder, override_method=override_method
        )

    def count_ocr(self, folder: Path, *, cancel: CancellationToken) -> ScanResult:
        """Run pase-2 OCR using 'Página N de M' pagination transitions (A7 lock).

        For each PDF in *folder*: single-page files contribute 1 document
        without OCR (A7 lock); multi-page files are scanned by
        ``count_paginations`` which detects document boundaries via Spanish
        pagination stamps in the upper-right corner.

        Args:
            folder: Directory containing the PDFs to scan.
            cancel: Token checked before each PDF; raises ``CancelledError``
                if the orchestrator has signalled cancellation.

        Returns:
            A ``ScanResult`` with:
              - ``count``: total documents found across all PDFs.
              - ``method``: ``"pagination"`` (or ``"filename_glob"`` when the
                folder is missing or empty).
              - ``confidence``: ``HIGH`` if no errors, ``LOW`` otherwise.
              - ``flags``: includes ``"a7_one_page_locked"`` when at least one
                single-page PDF was counted trivially.
              - ``per_file``: per-filename document count.
        """
        cancel.check()
        base = SimpleFilenameScanner(sigla=self.sigla).count(folder)
        if "folder_missing" in base.flags:
            return base  # A8

        pdfs = sorted(folder.rglob("*.pdf"))
        if not pdfs:
            return base

        start = time.perf_counter()
        total = 0
        per_file: dict[str, int] = {}
        errors: list[str] = []
        flags = list(base.flags)
        a7_used = False

        for pdf in pdfs:
            cancel.check()
            try:
                pages = get_page_count(pdf)
            except PdfRenderError as exc:
                errors.append(f"page_count_failed:{pdf.name}:{exc}")
                continue
            if pages == 1:
                # A7
                per_file[pdf.name] = 1
                total += 1
                a7_used = True
                continue
            try:
                result = count_paginations(pdf, cancel=cancel)
            except CancelledError:
                raise
            except (PdfRenderError, OSError, RuntimeError) as exc:
                errors.append(f"pagination_failed:{pdf.name}:{exc}")
                # Conservative fallback: count as 1 doc
                per_file[pdf.name] = 1
                total += 1
                continue
            per_file[pdf.name] = result.count
            total += result.count

        if a7_used:
            flags.append("a7_one_page_locked")

        duration_ms = int((time.perf_counter() - start) * 1000)
        confidence = ConfidenceLevel.HIGH if not errors else ConfidenceLevel.LOW
        return ScanResult(
            count=total,
            confidence=confidence,
            method="pagination",
            breakdown=base.breakdown,
            flags=flags,
            errors=errors,
            duration_ms=duration_ms,
            files_scanned=len(pdfs),
            per_file=per_file,
        )
