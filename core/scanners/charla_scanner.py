"""Scanner for sigla `charla` — Charla de Seguridad.

Decision rule (spec §3.2): compilation PDFs for charla are 1 page = 1 charla.
`page_count_pure` is a PyMuPDF metadata read, not OCR, so it's effectively
free (~5ms). Fallback to filename_glob only if the PDF can't be opened.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from core.scanners.base import ConfidenceLevel, ScanResult
from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.simple_factory import SimpleFilenameScanner
from core.scanners.utils.page_count_heuristic import flag_compilation_suspect
from core.scanners.utils.page_count_pure import count_documents_in_pdf
from core.scanners.utils.pdf_render import PdfRenderError


@dataclass
class CharlaScanner:
    sigla: str = "charla"

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
        base = self._filename_glob(folder)  # capture flags for happy path
        start = time.perf_counter()
        try:
            ocr = count_documents_in_pdf(pdfs[0])  # returns PageCountPureResult
        except CancelledError:
            raise  # consistent with Art/Header scanners
        except (PdfRenderError, OSError, RuntimeError) as exc:
            return self._fallback_from_base(base, error=f"page_count_pure_failed: {exc}")

        if ocr.count <= 0:
            return self._fallback_from_base(base, error="zero_pages")

        duration_ms = int((time.perf_counter() - start) * 1000)
        return ScanResult(
            count=ocr.count,
            confidence=ConfidenceLevel.HIGH,
            method="page_count_pure",
            breakdown=None,
            flags=list(base.flags),  # preserves compilation_suspect
            errors=[],
            duration_ms=duration_ms,
            files_scanned=1,
        )

    def _filename_glob(self, folder: Path) -> ScanResult:
        return SimpleFilenameScanner(sigla=self.sigla).count(folder)

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
        )
