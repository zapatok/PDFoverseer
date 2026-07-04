"""Factory for trivial filename-glob scanners.

All 20 siglas use this scanner for pase 1 (filename glob). For pase 2, the
implicit-compilation siglas dispatch to AnchorsScanner or PaginationScanner
(see core.scanners.patterns); the rest stay filename-glob only.

Pase-1 confidence is honest (conteo-confiable spec, Tema A1): a cell is HIGH
(green/listo) only when its count is verifiable without OCR — every matched PDF
is a single page (1 page = 1 document) or the sigla is a fixed-page sigla
(pages = documents). A multi-page file of a variable sigla is unverified and
reports LOW (amber/pendiente).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from core.scanners.base import ConfidenceLevel, Scanner, ScanResult, ScanTelemetry
from core.scanners.utils.cell_enumeration import find_duplicate_basenames
from core.scanners.utils.colado_guard import find_foreign_filename_suspects
from core.scanners.utils.filename_glob import (
    GlobCountResult,
    _matches,
    count_pdfs_by_sigla,
    per_empresa_breakdown,
)
from core.scanners.utils.page_count_heuristic import (
    _page_count,
    flag_compilation_suspect,
)
from core.utils import FIXED_PAGE_SIGLAS, FIXED_PAGE_SIGLAS_INFERRED


@dataclass
class SimpleFilenameScanner:
    sigla: str

    def count(
        self,
        folder: Path,
        *,
        override_method: str | None = None,
    ) -> ScanResult:
        start = time.perf_counter()
        glob_result = count_pdfs_by_sigla(folder, sigla=self.sigla)
        breakdown = per_empresa_breakdown(folder)
        flags = list(glob_result.flags)

        # F10: per-file models are keyed by basename, not full path — flag
        # when a folder reuses the same name across subfolders (the second
        # scanned would silently overwrite the first's per_file entry).
        if find_duplicate_basenames(folder):
            flags.append("duplicate_basenames")

        if "folder_missing" in flags:
            # Empty telemetry: no folder → no present files → every persisted
            # suspect is evicted downstream (the evidence lifecycle, §5).
            return self._result(
                glob_result,
                breakdown,
                flags,
                count=0,
                per_file={},
                method="filename_glob",
                confidence=ConfidenceLevel.HIGH,  # 0 is correct for missing
                start=start,
                telemetry=ScanTelemetry(),
            )

        # Single directory traversal, reused for both path resolution and the
        # anti-colados present-file set (avoids a second rglob).
        all_pdfs = list(folder.rglob("*.pdf"))

        # Anti-colados V1 (§3): foreign-named files in this folder → suspects.
        # Detection only; the count derivation below is untouched.
        colado_suspects = find_foreign_filename_suspects([p.name for p in all_pdfs], self.sigla)
        telemetry = ScanTelemetry(
            colado_suspects=colado_suspects,
            present_files=[p.name for p in all_pdfs],
        )

        # Matched basenames may live in empresa subfolders (count_pdfs_by_sigla
        # globs recursively but returns basenames). Resolve each to its on-disk
        # path so _page_count opens the right file; open each matched PDF once.
        # _matches honors count_scope (F14) so this stays in lock-step with
        # count_pdfs_by_sigla's own matching (e.g. chps: folder-scope).
        path_by_name = {p.name: p for p in all_pdfs if _matches(self.sigla, p.name)}
        pages = {
            fn: _page_count(path_by_name[fn])
            for fn in glob_result.matched_filenames
            if fn in path_by_name
        }

        # Fixed-page sigla: pages = documents. Sum pages, report each file's
        # pages in per_file, HIGH confidence (no OCR needed).
        if self.sigla in FIXED_PAGE_SIGLAS:
            if self.sigla in FIXED_PAGE_SIGLAS_INFERRED:
                flags.append("fixed_pages_inferred")
            return self._result(
                glob_result,
                breakdown,
                flags,
                count=sum(pages.values()),
                per_file=dict(pages),
                method="page_count_pure",
                confidence=ConfidenceLevel.HIGH,
                start=start,
                telemetry=telemetry,
            )

        # Variable sigla: 1 file = 1 document. HIGH when no matched file is
        # multi-page — every matched file is trivially one document (1 page =
        # 1 doc), OR there are no matched files at all (count 0 from an empty or
        # unrecognized folder is a certain zero, "cero seguro"; all() over an
        # empty set is True). Any multi-page file is unverified -> LOW (amber).
        # compilation_suspect stays informative but no longer decides confidence.
        no_multipage = all(p == 1 for p in pages.values())
        if flag_compilation_suspect(folder, sigla=self.sigla):
            flags.append("compilation_suspect")
        confidence = ConfidenceLevel.HIGH if no_multipage else ConfidenceLevel.LOW
        return self._result(
            glob_result,
            breakdown,
            flags,
            count=glob_result.count,
            per_file={fn: 1 for fn in glob_result.matched_filenames},
            method="filename_glob",
            confidence=confidence,
            start=start,
            telemetry=telemetry,
        )

    def _result(
        self,
        glob_result: GlobCountResult,
        breakdown: dict[str, int],
        flags: list[str],
        *,
        count: int,
        per_file: dict[str, int],
        method: str,
        confidence: ConfidenceLevel,
        start: float,
        telemetry: ScanTelemetry | None = None,
    ) -> ScanResult:
        """Build a ScanResult from the shared glob/breakdown/flags + variable
        fields. DRY helper (ScanResult is a frozen dataclass, so this lives on
        the scanner, not on the result).
        """
        return ScanResult(
            count=count,
            confidence=confidence,
            method=method,
            breakdown=breakdown if breakdown else None,
            flags=flags,
            errors=[],
            duration_ms=int((time.perf_counter() - start) * 1000),
            files_scanned=glob_result.files_scanned,
            per_file=per_file,
            telemetry=telemetry,
        )


def make_simple_scanner(sigla: str) -> Scanner:
    """Build a SimpleFilenameScanner for the given sigla.

    Args:
        sigla: Canonical sigla string (e.g. ``"art"``).

    Returns:
        A Scanner instance that counts PDFs by filename glob.
    """
    return SimpleFilenameScanner(sigla=sigla)
