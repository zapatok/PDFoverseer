"""Template-Method base for the pase-2 OCR scanners.

``AnchorsScanner`` and ``PaginationScanner`` shared ~75% of their ``count_ocr``
scaffolding — the *harness*: folder guard, PDF enumeration, ``only``/``skip``
filtering, the per-PDF loop (cancel + A7 + emit semantics), and ``ScanResult``
assembly. That harness lives here. Each subclass implements only:

- ``_count_one_pdf(pdf)`` — the per-PDF work (page-count read, A7 1-page branch,
  the engine call, per-PDF error fallback), returning a :class:`_PdfOutcome`.
- ``_precheck(...)`` — an optional short-circuit (``AnchorsScanner`` uses it for
  the "no flavors configured" case; default returns ``None``).
- class attrs ``METHOD`` (result-level method name) and ``LOW_CONF_FLAG`` (the
  flag appended when any PDF is low-trust; each subclass sets its own).

**Why the per-PDF I/O stays in the subclass module, not here:** the scanner unit
tests monkeypatch ``get_page_count`` and the engine on the *concrete scanner
module namespace* (e.g. ``core.scanners.anchors_scanner.get_page_count``). Python
binds those names at the calling module, so ``_count_one_pdf`` — and its
``get_page_count``/engine calls — MUST be defined in the subclass module for the
patches to take effect. Keeping it there means the existing scanner suite is the
byte-identity proof of this refactor (zero test migration).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from core.scanners.base import (
    ConfidenceLevel,
    NearMatchEntry,
    ScanResult,
    ScanTelemetry,
)
from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.simple_factory import SimpleFilenameScanner
from core.scanners.utils.cell_enumeration import enumerate_cell_pdfs


@dataclass
class _PdfOutcome:
    """Per-PDF result returned by a subclass ``_count_one_pdf``.

    ``count`` is ``None`` for an unreadable PDF (page-count failed): the file is
    still ticked via ``on_pdf`` (so the progress bar advances) but is NOT merged
    into ``per_file``/``total``. ``a7`` flags the 1-page trivial branch so the
    base appends ``a7_one_page_locked``. ``error_msg`` (when set) is appended to
    ``ScanResult.errors``. ``near_matches`` are serialized dicts (``[]`` for
    pagination); the base rebuilds :class:`NearMatchEntry` telemetry from them.
    """

    count: int | None
    method: str
    near_matches: list[dict]
    low_trust: bool
    a7: bool
    error_msg: str | None


@dataclass
class OcrScannerBase:
    """Shared harness for the anchor + pagination OCR scanners."""

    sigla: str

    #: Result-level ``ScanResult.method`` for a successful OCR scan (subclass override).
    METHOD: ClassVar[str] = ""
    #: Flag appended when any PDF is low-trust (``None`` → no flag; every current
    #: subclass overrides it, e.g. ``anchors_low_confidence``).
    LOW_CONF_FLAG: ClassVar[str | None] = None

    def count(self, folder: Path, *, override_method: str | None = None) -> ScanResult:
        """Pase 1 — uniform filename_glob (delegates to ``SimpleFilenameScanner``)."""
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
        """Run pase-2 OCR over the PDFs in *folder*, delegating per-PDF work.

        The outer harness (folder guard, enumeration, ``only``/``skip`` filtering,
        the per-PDF loop with cancel + emit semantics, and ``ScanResult``
        assembly) is identical for every OCR scanner. Per-PDF counting is
        delegated to :meth:`_count_one_pdf` (subclass), and an optional
        short-circuit to :meth:`_precheck`.

        Args:
            folder: Directory containing the PDFs to scan.
            cancel: Token checked before each PDF; raises ``CancelledError`` on
                cancellation. A PDF aborted mid-scan is never ticked via ``on_pdf``.
            on_pdf: Optional per-PDF callback ``on_pdf(name, count, method,
                near_matches)`` (Incr. 1A) — drives the progress bar AND the
                incremental merge. ``count=None`` → unreadable (not merged).
            only: Scope the scan to a single filename (per-file re-scan).
            skip: Filenames to NOT scan — already reliable (R1/manual/prior OCR).
            on_page: Optional per-page callback forwarded to the engine. Contract
                (U7, unified across both engines): ``on_page(done_0based, total)``
                — a 0-based monotonic completed-pages counter, emitted under a
                lock as pages finish (the engines OCR pages on worker threads;
                the counter sequence is 0..total-1 in both execution modes) —
                matches ``header_band_anchors.count_covers_by_anchors`` and
                ``pagination_count.count_documents_by_pagination``. A caller
                rendering "page N of M" should use ``done_0based + 1``. NOTE:
                the callback may fire from an engine worker thread — keep it
                small and thread-safe.

        Returns:
            A ``ScanResult`` summing the per-PDF counts, with method
            :attr:`METHOD`, ``HIGH`` confidence only when there were no errors and
            no low-trust PDFs, and the ``a7_one_page_locked`` /
            :attr:`LOW_CONF_FLAG` flags as applicable.
        """
        cancel.check()
        base = SimpleFilenameScanner(sigla=self.sigla).count(folder)
        if "folder_missing" in base.flags:
            return base  # A8: nothing to OCR

        pdfs = enumerate_cell_pdfs(folder)
        if only is not None:
            # Single-file scan (rev-2 #1): scope to just this PDF.
            pdfs = [p for p in pdfs if p.name == only]
        if skip:
            # Incr. 1A fusionar-y-saltar: omit files already reliable.
            pdfs = [p for p in pdfs if p.name not in skip]
        if not pdfs:
            return base

        precheck = self._precheck(folder, pdfs, base, on_pdf)
        if precheck is not None:
            return precheck

        start = time.perf_counter()
        total = 0
        per_file: dict[str, int] = {}
        flags = list(base.flags)
        errors: list[str] = []
        near_matches: list[NearMatchEntry] = []
        a7_used = False
        low_confidence_files: list[str] = []

        for pdf in pdfs:
            cancel.check()  # outside the try: a pre-PDF cancel must not emit on_pdf
            emit = True
            # Per-PDF capture for the enriched on_pdf callback (Incr. 1A). count=None
            # → unreadable (route does not merge). method filename_glob (A7) → chip R1.
            file_count: int | None = None
            file_method = "filename_glob"
            file_nms: list[dict] = []
            try:
                outcome = self._count_one_pdf(pdf, cancel=cancel, on_page=on_page)
                if outcome.error_msg:
                    errors.append(outcome.error_msg)
                if outcome.count is not None:
                    per_file[pdf.name] = outcome.count
                    total += outcome.count
                if outcome.a7:
                    a7_used = True
                for nm in outcome.near_matches:
                    near_matches.append(
                        NearMatchEntry(
                            pdf_name=nm["pdf_name"],
                            page_index=nm["page_index"],
                            flavor_name=nm["flavor_name"],
                            matched_anchors=nm["matched_anchors"],
                            missing_anchors=nm["missing_anchors"],
                        )
                    )
                if outcome.low_trust:
                    low_confidence_files.append(pdf.name)
                file_count, file_method, file_nms = (
                    outcome.count,
                    outcome.method,
                    outcome.near_matches,
                )
            except CancelledError:
                # Cancelled mid-PDF: this file did not finish — do not tick it.
                emit = False
                raise
            finally:
                # `finally` runs through the early returns above, so A7/error
                # branches still count as one processed PDF.
                if emit and on_pdf is not None:
                    on_pdf(pdf.name, file_count, file_method, file_nms)

        if a7_used:
            flags.append("a7_one_page_locked")
        if low_confidence_files and self.LOW_CONF_FLAG:
            flags.append(self.LOW_CONF_FLAG)

        duration_ms = int((time.perf_counter() - start) * 1000)
        confidence = (
            ConfidenceLevel.HIGH if not errors and not low_confidence_files else ConfidenceLevel.LOW
        )
        return ScanResult(
            count=total,
            confidence=confidence,
            method=self.METHOD,
            breakdown=base.breakdown,
            flags=flags,
            errors=errors,
            duration_ms=duration_ms,
            files_scanned=len(pdfs),
            per_file=per_file,
            telemetry=ScanTelemetry(near_matches=near_matches) if near_matches else None,
        )

    def _precheck(
        self,
        folder: Path,
        pdfs: list[Path],
        base: ScanResult,
        on_pdf: Callable[[str, int | None, str, list[dict]], None] | None,
    ) -> ScanResult | None:
        """Optional short-circuit before the per-PDF loop. Default: no short-circuit."""
        return None

    def _count_one_pdf(
        self,
        pdf: Path,
        *,
        cancel: CancellationToken,
        on_page: Callable[[int, int], None] | None,
    ) -> _PdfOutcome:
        """Count one PDF. Implemented by each subclass (in the subclass module).

        MUST re-raise ``CancelledError`` (catch only the engine's own
        ``PdfRenderError``/``OSError``/``RuntimeError`` for its fallback) so the
        base loop's cancel handling fires.
        """
        raise NotImplementedError
