"""Scanner for sigla `art` — Análisis de Riesgo de Tarea.

Decision rule (spec §3.2):
- Folder has N normal PDFs → filename_glob (pase 1 result is already correct).
- Folder has 1 PDF flagged compilation_suspect → corner_count OCR on that PDF.
- corner_count returns 0 or raises → fallback to filename_glob with
  confidence=LOW and flag `ocr_failed`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from core.scanners.base import ConfidenceLevel, ScanResult
from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.simple_factory import SimpleFilenameScanner
from core.scanners.utils.corner_count import count_paginations
from core.scanners.utils.page_count_heuristic import flag_compilation_suspect
from core.scanners.utils.pdf_render import PdfRenderError


@dataclass
class ArtScanner:
    sigla: str = "art"

    def count(
        self,
        folder: Path,
        *,
        override_method: str | None = None,
    ) -> ScanResult:
        """Pase 1 entry point — uses filename_glob like every other scanner."""
        return SimpleFilenameScanner(sigla=self.sigla).count(
            folder, override_method=override_method
        )

    def count_ocr(
        self,
        folder: Path,
        *,
        cancel: CancellationToken,
    ) -> ScanResult:
        cancel.check()
        pdfs = sorted(folder.glob("*.pdf"))
        if not pdfs:
            return self._filename_glob(folder)

        is_compilation = len(pdfs) == 1 and flag_compilation_suspect(folder, sigla=self.sigla)
        if not is_compilation:
            return self._filename_glob(folder)

        cancel.check()
        base = self._filename_glob(folder)  # captures flags for happy-path too
        start = time.perf_counter()
        try:
            ocr = count_paginations(pdfs[0], cancel=cancel)
        except CancelledError:
            raise
        except (PdfRenderError, OSError, RuntimeError) as exc:
            return self._fallback_from_base(base, error=f"corner_count_failed: {exc}")

        if ocr.count <= 0:
            return self._fallback_from_base(base, error="no_matches")

        duration_ms = int((time.perf_counter() - start) * 1000)
        return ScanResult(
            count=ocr.count,
            confidence=ConfidenceLevel.HIGH,
            method="corner_count",
            breakdown=None,
            flags=list(base.flags),  # preserves compilation_suspect + any other
            errors=[],
            duration_ms=duration_ms,
            files_scanned=1,
            per_file={pdfs[0].name: ocr.count},
        )

    def _filename_glob(self, folder: Path) -> ScanResult:
        return SimpleFilenameScanner(sigla=self.sigla).count(folder)

    def _fallback(self, folder: Path, *, error: str) -> ScanResult:
        return self._fallback_from_base(self._filename_glob(folder), error=error)

    def _fallback_from_base(self, base: ScanResult, *, error: str) -> ScanResult:
        return ScanResult(
            count=base.count,
            confidence=ConfidenceLevel.LOW,
            method="filename_glob",
            breakdown=base.breakdown,
            flags=[*base.flags, "ocr_failed"],
            errors=[*base.errors, error],
            duration_ms=base.duration_ms,
            files_scanned=base.files_scanned,
            per_file=base.per_file,
        )
