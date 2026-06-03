"""Adapter: count documents in a compilation PDF via the V4 pipeline.

``PaginationScanner`` (``scan_strategy="pagination"``) uses this for the
open-universe siglas — insgral (cat 8) and altura (cat 14) — where templates
are heterogeneous and the only reliable counting signal is the per-document
"Página N de M" pagination stamp.

V4 (``core/pipeline.py``) OCRs every page, detects the pagination period by
autocorrelation, and recovers OCR-failed pages with Dempster-Shafer inference.
It is materially more robust than the lightweight ``corner_count`` helper:
on a clean 18-document altura compilation, ``corner_count`` recovered 13/18
documents while V4 recovered 18/18 (decided 2026-05-21, with evidence — the
plan's original "corner_count is enough" assumption did not survive the real
corpus).

V4 is invoked with no-op progress/log callbacks. The cooperative
``CancellationToken`` is bridged to the ``threading.Event``-like ``.is_set()``
interface that ``analyze_pdf`` expects for its ``cancel_event``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.pipeline import analyze_pdf
from core.scanners.cancellation import CancellationToken, CancelledError


@dataclass(frozen=True)
class V4CountResult:
    """Outcome of a V4-backed document count for a single PDF.

    The per-read-method tallies let the caller judge trust: a count built
    mostly from ``direct`` reads is high-trust; one built entirely from
    ``inferred`` reads is Dempster-Shafer guesswork and should be surfaced
    as low confidence for operator review.
    """

    count: int  # number of documents V4 inferred
    pages_total: int
    direct_reads: int  # pages whose pagination OCR'd directly (high trust)
    inferred_reads: int  # pages recovered by Dempster-Shafer (lower trust)
    failed_reads: int  # pages V4 could not resolve at all


class _CancelEventShim:
    """Adapts a CancellationToken to the ``.is_set()`` interface V4 expects."""

    __slots__ = ("_token",)

    def __init__(self, token: CancellationToken) -> None:
        self._token = token

    def is_set(self) -> bool:
        return self._token.cancelled


def _noop_log(message: str, level: str = "info") -> None:
    """Discard V4 log lines — the scanner reports its own telemetry."""


def count_documents_v4(pdf_path: Path, *, cancel: CancellationToken) -> V4CountResult:
    """Count the documents in *pdf_path* with the V4 pipeline.

    Args:
        pdf_path: PDF compilation to analyze.
        cancel: cooperative cancellation token, bridged to V4's
            ``cancel_event`` so a signalled cancel aborts the V4 run.

    Returns:
        A :class:`V4CountResult` with the document count and the
        per-read-method tallies.

    Raises:
        CancelledError: if cancellation was signalled before or during the run.
        RuntimeError: if V4 returned no pages for a run that was not
            cancelled — treated as a pipeline failure so the caller can fall
            back conservatively.
    """
    cancel.check()
    documents, reads = analyze_pdf(
        str(pdf_path),
        None,  # on_progress — scanner does not surface per-page progress
        _noop_log,  # on_log — required callable
        cancel_event=_CancelEventShim(cancel),
    )
    if cancel.cancelled:
        raise CancelledError()
    if not reads:
        # analyze_pdf returns ([], []) on a PDF read error (and on cancel,
        # already handled above) — surface it as a pipeline failure.
        raise RuntimeError(f"v4_returned_no_reads:{pdf_path.name}")
    direct = sum(1 for r in reads if r.method == "direct")
    inferred = sum(1 for r in reads if r.method == "inferred")
    failed = sum(1 for r in reads if r.method == "failed")
    return V4CountResult(
        count=len(documents),
        pages_total=len(reads),
        direct_reads=direct,
        inferred_reads=inferred,
        failed_reads=failed,
    )
