"""VLM Tier 3: query VLM for pages where Tesseract failed, before inference."""
from __future__ import annotations

import logging
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

import cv2
import fitz

from core.image import _render_clip
from core.utils import (
    VLM_ENGINE_VERSION,
    VLM_SKIP_ISOLATED,
    VLM_UPSCALE,
    _PageRead,
)
from core.vlm_provider import VLMProvider

log = logging.getLogger(__name__)

# Plausibility guard — same range as Tesseract's _parse() in core/utils.py
_MAX_TOTAL = 10


def _find_candidates(
    reads: list[_PageRead],
    skip_isolated: bool,
) -> list[int]:
    """Find indices of failed pages worth querying.

    Args:
        reads: Page reads from OCR (Tier 1+2).
        skip_isolated: If True, skip single-page failures where both
                       neighbors are successful (inference fills these trivially).

    Returns:
        List of 0-based indices into reads.
    """
    n = len(reads)
    candidates: list[int] = []
    for i in range(n):
        if reads[i].method != "failed":
            continue

        if not skip_isolated:
            candidates.append(i)
            continue

        # Check if this is an isolated single failure between two successes
        is_first_in_run = (i == 0 or reads[i - 1].method != "failed")
        is_last_in_run = (i == n - 1 or reads[i + 1].method != "failed")

        if is_first_in_run and is_last_in_run:
            # Isolated failure — skip, inference handles this trivially
            continue

        # Gap edge: first or last of a multi-page failure run
        if is_first_in_run or is_last_in_run:
            candidates.append(i)

    return candidates


def query_failed_pages(
    reads: list[_PageRead],
    provider: VLMProvider,
    pdf_path: str | Path,
    on_log: Callable[[str, str], None],
    cancel_event: threading.Event | None = None,
    skip_isolated: bool = VLM_SKIP_ISOLATED,
) -> tuple[list[_PageRead], dict]:
    """Query VLM for failed OCR pages and return updated reads.

    Runs as OCR Tier 3: after Tesseract (Tier 1+2), before inference.
    Only queries pages where Tesseract failed. No acceptance gate —
    the inference engine handles conflicts via cross-validation and D-S.

    Args:
        reads: Page reads from Tesseract OCR.
        provider: VLM backend (Ollama or Claude).
        pdf_path: Path to PDF for image rendering.
        on_log: Logging callback.
        cancel_event: Cooperative cancellation.
        skip_isolated: Skip single failures between two successes.

    Returns:
        (reads, vlm_stats) — reads modified in-place where VLM succeeded.
    """
    stats = {
        "provider": provider.name,
        "version": VLM_ENGINE_VERSION,
        "queried": 0,
        "read": 0,
        "failed": 0,
        "errors": 0,
        "latency_sum": 0.0,
    }

    candidates = _find_candidates(reads, skip_isolated)
    if not candidates:
        on_log("VLM Tier 3: no candidates to query", "info")
        return reads, stats

    total_failed = sum(1 for r in reads if r.method == "failed")
    on_log(
        f"VLM Tier 3: {len(candidates)} candidates of {total_failed} failed "
        f"({provider.name}, v{VLM_ENGINE_VERSION})",
        "info",
    )

    doc = fitz.open(str(pdf_path))
    try:
        for idx in candidates:
            if cancel_event is not None and cancel_event.is_set():
                on_log("VLM Tier 3: cancelled", "warn")
                break

            r = reads[idx]
            pdf_page_0idx = r.pdf_page - 1
            if pdf_page_0idx < 0 or pdf_page_0idx >= len(doc):
                continue

            # Render and upscale
            clip = _render_clip(doc[pdf_page_0idx])
            if VLM_UPSCALE != 1.0:
                clip = cv2.resize(
                    clip, None,
                    fx=VLM_UPSCALE, fy=VLM_UPSCALE,
                    interpolation=cv2.INTER_CUBIC,
                )

            # Save to temp file, query VLM
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp_path = tmp.name
            tmp.close()
            try:
                cv2.imwrite(tmp_path, clip)
                vlm_result = provider.query(tmp_path)
            finally:
                try:
                    Path(tmp_path).unlink()
                except OSError:
                    pass

            stats["queried"] += 1
            stats["latency_sum"] += vlm_result.latency_ms

            if vlm_result.error:
                stats["errors"] += 1
                on_log(f"  VLM p{r.pdf_page}: error — {vlm_result.error}", "warn")
                continue

            # Plausibility guard (same as Tesseract: 0 < curr <= total <= 10)
            if vlm_result.parsed is None:
                stats["failed"] += 1
                on_log(f"  VLM p{r.pdf_page}: unparseable", "page_warn")
                continue

            curr, total = vlm_result.parsed
            if not (0 < curr <= total <= _MAX_TOTAL):
                stats["failed"] += 1
                on_log(
                    f"  VLM p{r.pdf_page}: {curr}/{total} out of range",
                    "page_warn",
                )
                continue

            # Accept — mutate read in-place as soft hypothesis
            # method="inferred" so Phase 3 cross-validates against neighbors
            r.curr = curr
            r.total = total
            r.method = "inferred"
            r.confidence = 0.45
            stats["read"] += 1
            on_log(
                f"  VLM p{r.pdf_page}: {curr}/{total} (as inferred@0.45)",
                "page_ok",
            )
    finally:
        doc.close()

    avg_lat = stats["latency_sum"] / stats["queried"] if stats["queried"] > 0 else 0.0
    on_log(
        f"VLM Tier 3: {stats['read']} read, "
        f"{stats['failed']} unparseable, {stats['errors']} errors, "
        f"{avg_lat:.0f}ms avg",
        "ok",
    )

    return reads, stats
