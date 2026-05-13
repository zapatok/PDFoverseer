"""Parameterized base for sigla scanners whose primary technique is
`header_detect` (regex F-CRS-<SIGLA_CODE>/NN). Used by OdiScanner and
IrlScanner. Not a public scanner — leading underscore.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from core.scanners.base import ConfidenceLevel, ScanResult
from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.simple_factory import SimpleFilenameScanner
from core.scanners.utils.header_detect import count_form_codes
from core.scanners.utils.page_count_heuristic import flag_compilation_suspect
from core.scanners.utils.pdf_render import PdfRenderError


@dataclass(kw_only=True)
class HeaderDetectScanner:
    """Concrete subclasses set ``sigla`` and ``sigla_code`` (e.g. "ODI", "IRL").

    ``kw_only=True`` keeps subclass inheritance safe: subclasses can override
    field defaults without tripping the "non-default field after default field"
    dataclass rule.
    """

    sigla: str
    sigla_code: str

    def count(
        self,
        folder: Path,
        *,
        override_method: str | None = None,
    ) -> ScanResult:
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
            ocr = count_form_codes(pdfs[0], sigla_code=self.sigla_code)
        except CancelledError:
            raise
        except (PdfRenderError, OSError, RuntimeError) as exc:
            return self._fallback_from_base(base, error=f"header_detect_failed: {exc}")

        if ocr.count <= 0:
            return self._fallback_from_base(base, error="no_matches")

        duration_ms = int((time.perf_counter() - start) * 1000)
        return ScanResult(
            count=ocr.count,
            confidence=ConfidenceLevel.HIGH,
            method="header_detect",
            breakdown=None,
            flags=list(base.flags),  # preserves compilation_suspect + others
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
