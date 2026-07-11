"""Multi-flavor anchor-based cover detection (A2 + A4 + A5 + A14).

OCRea la banda superior de cada página, cuenta páginas que matcheen
≥ min_match anchors de algún flavor declarado en patterns.py. Devuelve
también near-matches (páginas con min_match - 1 anchors) como señal para
mantenimiento (A14).

Sub-utilities:
- `_normalize_text`: lowercase + strip accents + collapse whitespace/separators.
- `_match_flavor`: returns matched_anchors + matched_anti_anchors for a flavor.
- `count_covers_by_anchors`: main entry point — iterates pages.
"""

from __future__ import annotations

import re
import threading
import unicodedata
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
import pytesseract
from PIL import Image

from core.image import _deskew, clean_for_ocr
from core.scanners.patterns import (
    DEFAULT_ANTI_MIN_MATCH,
    DEFAULT_MIN_MATCH,
    DEFAULT_TOP_FRACTION,
    Flavor,
)
from core.scanners.utils.pdf_render import get_page_count, render_page_region
from core.utils import OCR_PAGE_THREADS

if TYPE_CHECKING:
    from core.scanners.cancellation import CancellationToken


_SEPARATORS_RX = re.compile(r"[/\-_]+")
_WHITESPACE_RX = re.compile(r"\s+")


def _normalize_text(text: str) -> str:
    """Lowercase, strip accents, collapse separators (/-_) → space, collapse spaces."""
    # Strip combining marks (accents) using NFKD decomposition
    nfkd = unicodedata.normalize("NFKD", text)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    lower = no_accents.lower()
    no_seps = _SEPARATORS_RX.sub(" ", lower)
    collapsed = _WHITESPACE_RX.sub(" ", no_seps)
    return collapsed.strip()


@dataclass(frozen=True)
class FlavorMatchResult:
    """Per-page match outcome for a single flavor."""

    matched_anchors: list[str]
    matched_anti_anchors: list[str]
    passes: bool  # True iff matched_anchors >= min_match AND anti_anchored is False
    anti_anchored: bool  # True iff matched_anti_anchors >= anti_min_match
    near_match: bool  # A14: matched == min_match - 1 AND not anti_anchored
    missing_anchors: list[str]  # anchors NOT matched (normalized form)


def _match_flavor(normalized_text: str, flavor: Flavor) -> FlavorMatchResult:
    """Count how many anchors / anti-anchors of a flavor match the page text."""
    matched_anchors: list[str] = []
    missing_anchors: list[str] = []
    for anchor in flavor["anchors"]:
        normalized = _normalize_text(anchor)
        if not normalized:
            continue
        if normalized in normalized_text:
            matched_anchors.append(normalized)
        else:
            missing_anchors.append(normalized)

    matched_anti: list[str] = []
    for anti in flavor.get("anti_anchors", []):
        normalized = _normalize_text(anti)
        if normalized and normalized in normalized_text:
            matched_anti.append(normalized)

    min_match = flavor.get("min_match", DEFAULT_MIN_MATCH)
    anti_min = flavor.get("anti_min_match", DEFAULT_ANTI_MIN_MATCH)
    anti_anchored = len(matched_anti) >= anti_min
    passes = len(matched_anchors) >= min_match and not anti_anchored
    near_match = (
        (not passes)
        and (not anti_anchored)
        and min_match > 1
        and (len(matched_anchors) == min_match - 1)
    )
    return FlavorMatchResult(
        matched_anchors=matched_anchors,
        matched_anti_anchors=matched_anti,
        passes=passes,
        anti_anchored=anti_anchored,
        near_match=near_match,
        missing_anchors=missing_anchors,
    )


@dataclass(frozen=True)
class NearMatch:
    """A14: page that matched min_match - 1 anchors → candidate for new variant.

    Note: ``pdf_name`` is intentionally absent here; the calling scanner adds it
    when building a ``NearMatchEntry`` (see ``core.scanners.base``).
    """

    page_index: int
    flavor_name: str
    matched_anchors: list[str]
    missing_anchors: list[str]


@dataclass(frozen=True)
class AnchorCountResult:
    """Aggregated result of the anchor-based cover scan for a single PDF."""

    count: int  # total cover pages across all flavors
    pages_total: int
    matches_per_flavor: dict[str, int] = field(default_factory=dict)
    near_matches: list[NearMatch] = field(default_factory=list)
    method: str = "header_band_anchors"


def _match_page(
    normalized_text: str, flavors: list[Flavor], page_idx: int
) -> tuple[str | None, NearMatch | None]:
    """Match one page's OCR text against the flavors.

    Returns ``(owning_flavor_name, near_match)``: the first flavor that passes
    owns the page (its name, no near-match). If none passes, the first near-match
    (``min_match - 1`` anchors) is returned for telemetry.
    """
    page_near: NearMatch | None = None
    for flavor in flavors:
        res = _match_flavor(normalized_text, flavor)
        if res.passes:
            return flavor["name"], None
        if res.near_match and page_near is None:
            page_near = NearMatch(
                page_index=page_idx,
                flavor_name=flavor["name"],
                matched_anchors=res.matched_anchors,
                missing_anchors=res.missing_anchors,
            )
    return None, page_near


def count_covers_by_anchors(
    pdf_path: Path,
    *,
    flavors: list[Flavor],
    top_fraction: float = DEFAULT_TOP_FRACTION,
    dpi: int = 200,
    cancel: CancellationToken | None = None,
    on_page: Callable[[int, int], None] | None = None,
    ocr_threads: int | None = None,
) -> AnchorCountResult:
    """OCR the top band of each page; count pages that match any flavor (A4).

    A page contributes exactly +1 to the total even if multiple flavors pass
    (the first passing flavor "owns" the page in `matches_per_flavor`). This
    avoids double-counting when anchor lists overlap.

    Near-matches (A14): a page that matches min_match - 1 anchors of some
    flavor (without anti-anchors firing) is recorded as a candidate for a
    new template variant — surfaced to the operator via telemetry, not
    counted toward `count`.

    Args:
        pdf_path: source PDF.
        flavors: list of Flavor dicts from patterns.py.
        top_fraction: fraction of page height OCR'd from the top (default 0.25).
        dpi: OCR rendering resolution.
        cancel: optional CancellationToken (cooperative cancellation).
        on_page: 0-based monotonic completed-pages counter ``(done - 1, total)``,
            emitted under a lock as pages finish — the same contract as the
            pagination engine (``pagination_count.count_documents_by_pagination``).
        ocr_threads: per-page OCR parallelism (default
            ``core.utils.OCR_PAGE_THREADS``); ``1`` forces the sequential path.
            Per-page results land in page-indexed slots and aggregate in page
            order, so count/telemetry are deterministic in both modes.

    Returns:
        AnchorCountResult with the total cover count + per-flavor breakdown
        + near-match telemetry.

    Raises:
        PdfRenderError: if a page fails to render. Propagates to the caller —
            this layer does not do partial scans. The scanner that wraps this
            (AnchorsScanner) catches it at the PDF level and falls back.
    """
    pages_total = get_page_count(pdf_path)
    bbox = (0.0, 0.0, 1.0, max(0.05, min(1.0, top_fraction)))
    threads = OCR_PAGE_THREADS if ocr_threads is None else ocr_threads

    owned_by_page: list[str | None] = [None] * pages_total
    near_by_page: list[NearMatch | None] = [None] * pages_total
    done = 0
    progress_lock = threading.Lock()

    def _scan_page(page_idx: int) -> None:
        nonlocal done
        if cancel is not None:
            cancel.check()
        # render_page_region opens the PDF per call — measured 0.7–20 ms even on
        # a 516 MB file (lazy xref), so the per-page open is kept: it makes each
        # page task self-contained (fitz Documents are not thread-safe) and
        # preserves the path-based test seam.
        pil: Image.Image = render_page_region(pdf_path, page_idx, bbox=bbox, dpi=dpi)

        # E6 — two-pass OCR. Pass 1: raw band (clean scans read fine, no
        # preprocessing artifacts). Pass 2: only if pass 1 found no cover, retry
        # with the V4 cascade (deskew + color removal + inpaint + grayscale +
        # unsharp) — lifts degraded scans (andamios/ART) while never re-reading a
        # cover the raw pass already found, so clean cells never regress.
        raw = pytesseract.image_to_string(pil, config="--psm 6 --oem 1", lang="spa+eng")
        owned, page_near = _match_page(_normalize_text(raw), flavors, page_idx)
        if owned is None:
            bgr = cv2.cvtColor(np.asarray(pil.convert("RGB")), cv2.COLOR_RGB2BGR)
            gray = clean_for_ocr(_deskew(bgr))
            prep = pytesseract.image_to_string(gray, config="--psm 6 --oem 1", lang="spa+eng")
            owned, page_near = _match_page(_normalize_text(prep), flavors, page_idx)

        owned_by_page[page_idx] = owned
        near_by_page[page_idx] = page_near
        with progress_lock:
            done += 1
            if on_page is not None:
                on_page(done - 1, pages_total)

    if threads <= 1 or pages_total <= 1:
        for page_idx in range(pages_total):
            _scan_page(page_idx)
    else:
        with ThreadPoolExecutor(max_workers=min(threads, pages_total)) as ex:
            futures = [ex.submit(_scan_page, pi) for pi in range(pages_total)]
            try:
                for fut in as_completed(futures):
                    fut.result()
            except BaseException:
                for fut in futures:
                    fut.cancel()
                raise

    matches_per_flavor: dict[str, int] = {f["name"]: 0 for f in flavors}
    near_matches: list[NearMatch] = []
    cover_pages = 0
    for page_idx in range(pages_total):
        owned = owned_by_page[page_idx]
        if owned is not None:
            matches_per_flavor[owned] += 1
            cover_pages += 1
        elif near_by_page[page_idx] is not None:
            near_matches.append(near_by_page[page_idx])

    return AnchorCountResult(
        count=cover_pages,
        pages_total=pages_total,
        matches_per_flavor=matches_per_flavor,
        near_matches=near_matches,
    )
