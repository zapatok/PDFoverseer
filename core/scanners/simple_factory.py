"""Factory for trivial filename-glob scanners.

In FASE 1 ALL 18 siglas use this factory. In FASE 2, 4 of them
(art, irl, odi, charla) get replaced with specialized scanners.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from core.scanners.base import ConfidenceLevel, Scanner, ScanResult
from core.scanners.utils.filename_glob import (
    count_pdfs_by_sigla,
    per_empresa_breakdown,
)
from core.scanners.utils.page_count_heuristic import flag_compilation_suspect


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

        is_compilation = flag_compilation_suspect(folder, sigla=self.sigla)
        if is_compilation:
            flags.append("compilation_suspect")
            confidence = ConfidenceLevel.LOW
        elif "folder_missing" in flags:
            confidence = ConfidenceLevel.HIGH  # 0 is correct for missing
        else:
            confidence = ConfidenceLevel.HIGH

        duration_ms = int((time.perf_counter() - start) * 1000)
        return ScanResult(
            count=glob_result.count,
            confidence=confidence,
            method="filename_glob",
            breakdown=breakdown if breakdown else None,
            flags=flags,
            errors=[],
            duration_ms=duration_ms,
            files_scanned=glob_result.files_scanned,
            per_file={fn: 1 for fn in glob_result.matched_filenames},
        )


def make_simple_scanner(sigla: str) -> Scanner:
    """Build a SimpleFilenameScanner for the given sigla.

    Args:
        sigla: Canonical sigla string (e.g. ``"art"``).

    Returns:
        A Scanner instance that counts PDFs by filename glob.
    """
    return SimpleFilenameScanner(sigla=sigla)
