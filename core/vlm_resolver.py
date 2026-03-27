"""VLM Resolver: post-inference selective VLM correction of problematic pages."""
from __future__ import annotations

import logging
import tempfile
import threading
from pathlib import Path

import cv2
import fitz

from core.utils import (
    _PageRead,
    InferenceIssue,
    VLM_UPSCALE,
    VLM_MIN_ACCEPT_CONF,
    VLM_ENGINE_VERSION,
)
from core.vlm_provider import VLMProvider, VLMResult
from core.image import _render_clip

log = logging.getLogger(__name__)

# Priority order: lower = higher priority (more impact per VLM call)
ISSUE_PRIORITY = {
    "boundary_inferred": 0,
    "contradiction":     1,
    "low_confidence":    2,
    "gap":               3,
}


def _should_accept(
    vlm_result: VLMResult,
    page_idx: int,
    reads: list[_PageRead],
    period_info: dict,
) -> bool:
    """Accept VLM read only if coherent with surrounding context.

    This is what prevents the VLM paradox — rejecting reads that would
    cause document merges or contradict strong evidence.
    """
    # 1. Reject if unparseable
    if vlm_result.parsed is None:
        return False

    # 2. Reject if VLM parser confidence is below minimum
    if vlm_result.confidence < VLM_MIN_ACCEPT_CONF:
        return False

    curr, total = vlm_result.parsed

    # 3. Reject if total contradicts strong period
    if period_info.get("confidence", 0) > 0.5:
        expected_total = period_info.get("expected_total")
        if expected_total is not None and total != expected_total:
            return False

    # 4. Check neighbor consistency
    prev = reads[page_idx - 1] if page_idx > 0 else None
    nxt = reads[page_idx + 1] if page_idx < len(reads) - 1 else None

    # 4a. If VLM says curr=1, check if previous page is end-of-document
    if curr == 1 and prev is not None:
        if prev.curr is not None and prev.total is not None:
            if prev.curr != prev.total:
                # Previous is mid-document — claiming new doc start is suspicious
                return False

    # 4b. Check sequential coherence with prev
    if prev is not None and prev.curr is not None and prev.total is not None:
        prev_sequential = (prev.total == total and prev.curr == curr - 1)
        prev_boundary = (prev.curr == prev.total and curr == 1)
        if not prev_sequential and not prev_boundary:
            # Not sequential and not a new doc — check next neighbor
            if nxt is not None and nxt.curr is not None and nxt.total is not None:
                nxt_sequential = (nxt.total == total and nxt.curr == curr + 1)
                nxt_boundary = (curr == total and nxt.curr == 1)
                if not nxt_sequential and not nxt_boundary:
                    return False
            elif reads[page_idx].curr is not None and reads[page_idx].curr == curr:
                pass  # Confirms existing read
            else:
                return False

    # 5. Accept if confirms existing low-confidence read
    existing = reads[page_idx]
    if existing.curr == curr and existing.total == total:
        return True

    # 6. Accept — passed all checks
    return True


def resolve(
    reads: list[_PageRead],
    issues: list[InferenceIssue],
    total_pages: int,
    provider: VLMProvider,
    pdf_path: str | Path,
    period_info: dict,
    on_log: callable,
    cancel_event: threading.Event | None = None,
) -> tuple[list[_PageRead], dict]:
    """Selectively query VLM for problematic pages and return corrected reads.

    Args:
        reads: Page reads from inference pass 1.
        issues: Problems identified by inference engine.
        total_pages: Total pages in PDF.
        provider: VLM backend (Ollama or Claude).
        pdf_path: Path to PDF — renders image strips on demand.
        period_info: Period detection results from pass 1.
        on_log: Logging callback.
        cancel_event: Cooperative cancellation.

    Returns:
        (corrected_reads, vlm_stats) — reads modified in-place and returned.
    """
    stats = {
        "provider": provider.name,
        "version": VLM_ENGINE_VERSION,
        "total": 0,
        "accepted": 0,
        "rejected": 0,
        "errors": 0,
        "latency_sum": 0.0,
        "by_type": {},
    }

    if not issues:
        on_log("VLM resolver: no issues to resolve", "info")
        return reads, stats

    # Build page index for quick lookup
    page_to_idx = {r.pdf_page: i for i, r in enumerate(reads)}

    # Sort candidates by priority
    candidates = sorted(issues, key=lambda iss: ISSUE_PRIORITY.get(iss.issue_type, 99))

    # Deduplicate by pdf_page (keep highest priority)
    seen_pages: set[int] = set()
    unique_candidates: list[InferenceIssue] = []
    for c in candidates:
        if c.pdf_page not in seen_pages:
            seen_pages.add(c.pdf_page)
            unique_candidates.append(c)

    on_log(
        f"VLM resolver: {len(unique_candidates)} candidates "
        f"({provider.name}, v{VLM_ENGINE_VERSION})",
        "info",
    )

    # Open PDF once for all candidates
    doc = fitz.open(str(pdf_path))
    try:
        for issue in unique_candidates:
            if cancel_event is not None and cancel_event.is_set():
                on_log("VLM resolver: cancelled", "warn")
                break

            page_idx = page_to_idx.get(issue.pdf_page)
            if page_idx is None:
                continue

            pdf_page_0idx = issue.pdf_page - 1  # fitz uses 0-indexed
            if pdf_page_0idx < 0 or pdf_page_0idx >= len(doc):
                continue

            # Render image strip
            clip = _render_clip(doc[pdf_page_0idx])

            # Upscale
            if VLM_UPSCALE != 1.0:
                clip = cv2.resize(
                    clip, None,
                    fx=VLM_UPSCALE, fy=VLM_UPSCALE,
                    interpolation=cv2.INTER_CUBIC,
                )

            # Save to temp file
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

            stats["total"] += 1
            stats["latency_sum"] += vlm_result.latency_ms

            # Track per-type stats
            t = issue.issue_type
            if t not in stats["by_type"]:
                stats["by_type"][t] = {"attempted": 0, "accepted": 0}
            stats["by_type"][t]["attempted"] += 1

            if vlm_result.error:
                stats["errors"] += 1
                on_log(
                    f"  VLM p{issue.pdf_page}: error — {vlm_result.error}",
                    "warn",
                )
                continue

            if _should_accept(vlm_result, page_idx, reads, period_info):
                r = reads[page_idx]
                r.curr = vlm_result.parsed[0]
                r.total = vlm_result.parsed[1]
                r.method = f"vlm_{provider.name}"
                r.confidence = vlm_result.confidence

                stats["accepted"] += 1
                stats["by_type"][t]["accepted"] += 1
                on_log(
                    f"  VLM p{issue.pdf_page}: {r.curr}/{r.total} "
                    f"[{issue.issue_type}] accepted",
                    "page_ok",
                )
            else:
                stats["rejected"] += 1
                reason = "unparseable" if vlm_result.parsed is None else "context_mismatch"
                on_log(
                    f"  VLM p{issue.pdf_page}: "
                    f"{'???' if vlm_result.parsed is None else f'{vlm_result.parsed[0]}/{vlm_result.parsed[1]}'} "
                    f"[{issue.issue_type}] rejected ({reason})",
                    "page_warn",
                )
    finally:
        doc.close()

    avg_lat = stats["latency_sum"] / stats["total"] if stats["total"] > 0 else 0.0
    on_log(
        f"VLM resolver: {stats['accepted']} accepted, "
        f"{stats['rejected']} rejected, {stats['errors']} errors, "
        f"{avg_lat:.0f}ms avg",
        "ok",
    )

    return reads, stats
