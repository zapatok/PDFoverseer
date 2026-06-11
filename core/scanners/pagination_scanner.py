"""Scanner for the open-universe siglas — insgral (cat 8) and altura (cat 14).

These siglas have heterogeneous templates with no stable anchor set, so they
are counted by their per-document "Página N de M" pagination instead
(``scan_strategy="pagination"``).

The counting engine is the **full V4 pipeline** (``core/pipeline.py``), reached
through ``core/scanners/utils/v4_count.count_documents_v4``. V4 OCRs every
page, detects the pagination period by autocorrelation and recovers
OCR-failed pages with Dempster-Shafer inference. This replaced the original
lightweight ``corner_count`` helper, which undercounted on the real corpus
(13/18 documents where V4 recovered 18/18 — decided 2026-05-21).

A7 still applies: 1-page PDFs contribute 1 document without OCR. A V4 result
built mostly from inferred (guessed) reads downgrades the cell to LOW
confidence so the operator reviews it.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.scanners.base import ConfidenceLevel, ScanResult
from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.simple_factory import SimpleFilenameScanner
from core.scanners.utils.cell_enumeration import enumerate_cell_pdfs
from core.scanners.utils.pdf_render import PdfRenderError, get_page_count
from core.scanners.utils.v4_count import V4CountResult, count_documents_v4


def _v4_result_is_trustworthy(v4: V4CountResult) -> bool:
    """A V4 count is trustworthy when most pages were read directly.

    A count built mostly from Dempster-Shafer ``inferred`` reads (or with any
    unresolved ``failed`` read, or no documents at all) is guesswork — the
    cell is downgraded to LOW confidence for operator review.
    """
    if v4.count == 0 or v4.failed_reads > 0:
        return False
    return v4.direct_reads >= v4.inferred_reads


@dataclass
class PaginationScanner:
    """Counts documents in compilations via the V4 pagination pipeline."""

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
        """Run pase-2 OCR by counting "Página N de M" documents via V4.

        For each PDF in *folder*: single-page files contribute 1 document
        without OCR (A7 lock); multi-page files are analyzed by the V4
        pipeline, which counts document boundaries from the pagination
        stamps.

        Args:
            folder: Directory containing the PDFs to scan.
            cancel: Token checked before each PDF; raises ``CancelledError``
                if the orchestrator has signalled cancellation.
            on_pdf: Optional callback invoked once per processed PDF as
                ``on_pdf(filename, count, method, near_matches)`` (Incr. 1A):
                ``count`` = docs found (``None`` if unreadable), ``method`` =
                ``"filename_glob"`` for A7/1-page (chip R1) else ``"v4"``,
                ``near_matches`` = always ``[]`` (V4 has no near-matches). Drives
                the per-PDF progress bar AND the incremental merge; never called
                for a PDF aborted by cancellation.
            only: scope the scan to a single filename (per-file re-scan).
            skip: filenames to NOT scan — already reliable (R1/manual/prior OCR).

        Returns:
            A ``ScanResult`` with:
              - ``count``: total documents found across all PDFs.
              - ``method``: ``"v4"`` (or ``"filename_glob"`` when the folder
                is missing or empty).
              - ``confidence``: ``HIGH`` only if every multi-page PDF was
                counted from a trustworthy (mostly-direct) V4 read; ``LOW``
                if any PDF errored or produced a guesswork count.
              - ``flags``: includes ``"a7_one_page_locked"`` when at least
                one single-page PDF was counted trivially, and
                ``"v4_low_confidence"`` when at least one PDF's count is
                guesswork.
              - ``per_file``: per-filename document count.
        """
        cancel.check()
        base = SimpleFilenameScanner(sigla=self.sigla).count(folder)
        if "folder_missing" in base.flags:
            return base  # A8

        pdfs = enumerate_cell_pdfs(folder)
        if only is not None:
            # Single-file scan (rev-2 #1). `on_page` is accepted for interface
            # parity but ignored: V4 (pipeline.analyze_pdf) has no per-page hook,
            # so the viewer bar stays indeterminate for insgral/altura.
            pdfs = [p for p in pdfs if p.name == only]
        if skip:
            # Incr. 1A fusionar-y-saltar: omite los archivos ya confiables.
            pdfs = [p for p in pdfs if p.name not in skip]
        if not pdfs:
            return base

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
                    v4 = count_documents_v4(pdf, cancel=cancel)
                except CancelledError:
                    raise
                except (PdfRenderError, OSError, RuntimeError) as exc:
                    errors.append(f"v4_failed:{pdf.name}:{exc}")
                    # Conservative fallback: count the compilation as 1 document.
                    per_file[pdf.name] = 1
                    total += 1
                    low_confidence_files.append(pdf.name)
                    file_count, file_method = 1, "v4"
                    continue
                # A degenerate count of 0 for a multi-page PDF is never right —
                # fall back to 1 and flag it.
                pdf_count = v4.count if v4.count > 0 else 1
                per_file[pdf.name] = pdf_count
                total += pdf_count
                file_count, file_method = pdf_count, "v4"
                if not _v4_result_is_trustworthy(v4):
                    low_confidence_files.append(pdf.name)
            except CancelledError:
                # Cancelled mid-PDF: this file did not finish — do not tick it.
                emit = False
                raise
            finally:
                # `finally` runs through every `continue` above, so A7/error
                # branches still count as one processed PDF. V4 has no near-matches.
                if emit and on_pdf is not None:
                    on_pdf(pdf.name, file_count, file_method, [])

        if a7_used:
            flags.append("a7_one_page_locked")
        if low_confidence_files:
            flags.append("v4_low_confidence")

        duration_ms = int((time.perf_counter() - start) * 1000)
        confidence = (
            ConfidenceLevel.HIGH if not errors and not low_confidence_files else ConfidenceLevel.LOW
        )
        return ScanResult(
            count=total,
            confidence=confidence,
            method="v4",
            breakdown=base.breakdown,
            flags=flags,
            errors=errors,
            duration_ms=duration_ms,
            files_scanned=len(pdfs),
            per_file=per_file,
        )
