"""Scanner for the open-universe siglas — insgral (cat 8) and altura (cat 14).

These siglas have heterogeneous templates with no stable anchor set, so they
are counted by their per-document "Página N de M" pagination instead
(``scan_strategy="pagination"``).

The counting engine is the **pagination engine**
(``core/scanners/utils/pagination_count.count_documents_by_pagination``), which
OCRs only the top-right corner of each page, recovers gaps in the pagination
sequence with a lightweight forward-fill algorithm, and counts document
boundaries (``curr == 1`` transitions). A7 still applies: 1-page PDFs
contribute 1 document without OCR. A count that needed heavy gap-recovery or
produced any unresolved failed reads downgrades the cell to LOW confidence so
the operator reviews it.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.scanners.base import ConfidenceLevel, ScanResult
from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.patterns import PATTERNS
from core.scanners.simple_factory import SimpleFilenameScanner
from core.scanners.utils.cell_enumeration import enumerate_cell_pdfs
from core.scanners.utils.pagination_count import (
    RECOVERY_LOW_CONF_RATIO,
    count_documents_by_pagination,
)
from core.scanners.utils.pdf_render import PdfRenderError, get_page_count


@dataclass
class PaginationScanner:
    """Counts documents in compilations via the pagination engine."""

    sigla: str

    def count(self, folder: Path, *, override_method: str | None = None) -> ScanResult:
        return SimpleFilenameScanner(sigla=self.sigla).count(
            folder, override_method=override_method
        )

    def count_ocr(
        self,
        folder: Path,
        *,
        cancel: CancellationToken,
        on_pdf: Callable[[str, int | None, str, list[dict]], None] | None = None,
        only: str | None = None,
        skip: set[str] | None = None,
        on_page: Callable[[int, int], None] | None = None,
    ) -> ScanResult:
        """Run pase-2 OCR by counting "Página N de M" documents via the pagination engine.

        For each PDF in *folder*: single-page files contribute 1 document
        without OCR (A7 lock); multi-page files are analyzed by the pagination
        engine, which counts document boundaries from the top-right corner
        pagination stamps.

        Args:
            folder: Directory containing the PDFs to scan.
            cancel: Token checked before each PDF; raises ``CancelledError``
                if the orchestrator has signalled cancellation.
            on_pdf: Optional callback invoked once per processed PDF as
                ``on_pdf(filename, count, method, near_matches)`` (Incr. 1A):
                ``count`` = docs found (``None`` if unreadable), ``method`` =
                ``"filename_glob"`` for A7/1-page (chip R1) else
                ``"pagination"``, ``near_matches`` = always ``[]`` (pagination
                engine has no near-matches). Drives the per-PDF progress bar
                AND the incremental merge; never called for a PDF aborted by
                cancellation.
            only: scope the scan to a single filename (per-file re-scan).
            skip: filenames to NOT scan — already reliable (R1/manual/prior OCR).
            on_page: Optional callback invoked per page as ``on_page(done, total)``
                by the pagination engine while processing each multi-page PDF.

        Returns:
            A ``ScanResult`` with:
              - ``count``: total documents found across all PDFs.
              - ``method``: ``"pagination"`` (or ``"filename_glob"`` when the
                folder is missing or empty).
              - ``confidence``: ``HIGH`` only if every multi-page PDF was
                counted from a trustworthy (mostly-direct) read; ``LOW``
                if any PDF errored, had too many recovered reads, or had
                failed reads.
              - ``flags``: includes ``"a7_one_page_locked"`` when at least
                one single-page PDF was counted trivially, and
                ``"pagination_low_confidence"`` when at least one PDF's count
                is guesswork.
              - ``per_file``: per-filename document count.
        """
        cancel.check()
        base = SimpleFilenameScanner(sigla=self.sigla).count(folder)
        if "folder_missing" in base.flags:
            return base  # A8

        pdfs = enumerate_cell_pdfs(folder)
        if only is not None:
            pdfs = [p for p in pdfs if p.name == only]
        if skip:
            # Incr. 1A fusionar-y-saltar: omite los archivos ya confiables.
            pdfs = [p for p in pdfs if p.name not in skip]
        if not pdfs:
            return base

        # Look up optional cover_code for this sigla (used by IRL-style siglas).
        cover_code: str | None = PATTERNS[self.sigla].get("cover_code")  # type: ignore[assignment]

        start = time.perf_counter()
        total = 0
        per_file: dict[str, int] = {}
        errors: list[str] = []
        flags = list(base.flags)
        a7_used = False
        low_confidence_files: list[str] = []

        for pdf in pdfs:
            cancel.check()  # outside the try: a pre-PDF cancel must not emit on_pdf
            emit = True
            # Capturados por PDF para el callback enriquecido (Incr. 1A): count=None
            # → ilegible (la ruta no fusiona). method filename_glob (A7) → chip R1.
            file_count: int | None = None
            file_method = "filename_glob"
            try:
                try:
                    pages = get_page_count(pdf)
                except PdfRenderError as exc:
                    errors.append(f"page_count_failed:{pdf.name}:{exc}")
                    continue  # file_count stays None → no merge (Error/pendiente)
                if pages == 1:
                    # A7 — 1 page = 1 document, locked, no OCR; method R1.
                    per_file[pdf.name] = 1
                    total += 1
                    a7_used = True
                    file_count, file_method = 1, "filename_glob"
                    continue
                try:
                    pag = count_documents_by_pagination(
                        pdf, cancel=cancel, cover_code=cover_code, on_page=on_page
                    )
                except CancelledError:
                    raise
                except (PdfRenderError, OSError, RuntimeError) as exc:
                    errors.append(f"pagination_failed:{pdf.name}:{exc}")
                    # Conservative fallback: count the compilation as 1 document.
                    per_file[pdf.name] = 1
                    total += 1
                    low_confidence_files.append(pdf.name)
                    file_count, file_method = 1, "pagination"
                    continue
                # A degenerate count of 0 for a multi-page PDF is never right —
                # fall back to 1 and flag it.
                pdf_count = pag.count if pag.count > 0 else 1
                per_file[pdf.name] = pdf_count
                total += pdf_count
                file_count, file_method = pdf_count, "pagination"
                # Low-trust per-PDF rule: any failed read, heavy recovery, or
                # cover_code with recovered reads (possible missed cover) → LOW.
                low_trust = (
                    pag.failed_reads > 0
                    or pag.recovered_reads / max(1, pag.pages_total) > RECOVERY_LOW_CONF_RATIO
                    or pag.cover_code_recovery
                )
                if low_trust:
                    low_confidence_files.append(pdf.name)
            except CancelledError:
                # Cancelled mid-PDF: this file did not finish — do not tick it.
                emit = False
                raise
            finally:
                # `finally` runs through every `continue` above, so A7/error
                # branches still count as one processed PDF. Pagination engine
                # has no near-matches.
                if emit and on_pdf is not None:
                    on_pdf(pdf.name, file_count, file_method, [])

        if a7_used:
            flags.append("a7_one_page_locked")
        if low_confidence_files:
            flags.append("pagination_low_confidence")

        duration_ms = int((time.perf_counter() - start) * 1000)
        confidence = (
            ConfidenceLevel.HIGH if not errors and not low_confidence_files else ConfidenceLevel.LOW
        )
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
