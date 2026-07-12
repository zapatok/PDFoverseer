"""Pagination-first document counter (production engine; prototyped in eval/pagination_count/). See spec §6.

Pure functions (parse_pagination / extract_code / dominant_total / recover_sequence /
count_starts) have zero OCR/PDF dependency and are unit-tested directly.
count_documents_by_pagination is the thin OCR orchestrator (integration-tested with
synthetic PDFs).
"""

from __future__ import annotations

import io
import re
import threading
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import fitz
from PIL import Image

from core.scanners.cancellation import CancellationToken
from core.scanners.utils.ocr_backend import ocr_image
from core.utils import OCR_PAGE_THREADS

# digit-normalize common OCR confusions, then match
_DIGIT = str.maketrans(
    {"O": "0", "o": "0", "l": "1", "I": "1", "|": "1", "Z": "2", "S": "5", "B": "8"}
)
_PAG_FULL = re.compile(r"(?:p[aá4@]?gina|pag)\s*([0-9]{1,3})\s*de\s*([0-9]{1,3})", re.IGNORECASE)
_PAG_CURR = re.compile(r"(?:p[aá4@]?gina|pag)\.?\s*([0-9]{1,3})\b", re.IGNORECASE)
_CODE = re.compile(r"\bF[-\s]?[A-Z]{2,4}[-\s][A-Z0-9\-]{2,12}", re.IGNORECASE)

# Confidence: a count that needed lots of gap-recovery is guesswork (eval-tuned).
RECOVERY_LOW_CONF_RATIO = 0.30

# Corner crop (relative x0,y0,x1,y1). Text is top-right in both orientations.
_CORNER_PORTRAIT = (0.50, 0.0, 1.0, 0.15)
_CORNER_LANDSCAPE = (0.62, 0.0, 1.0, 0.12)
_OCR_DPI = 216


def parse_pagination(raw: str) -> tuple[int | None, int | None]:
    """Parse "Página C de M" (or "Página C" without total) from OCR text.

    Full regex (C de M) takes precedence; the curr-only fallback applies only
    when the full regex does not match (spec §6 precedence).
    """
    norm = raw.replace("\n", " ")
    m = _PAG_FULL.search(norm) or _PAG_FULL.search(norm.translate(_DIGIT))
    if m:
        curr, total = int(m.group(1)), int(m.group(2))
        # plausibility: a real "C de M" has 0 < C <= M. Reject OCR noise like
        # "5 de 4" as a no-read so it can't poison sequence recovery as a bad anchor.
        return (curr, total) if 0 < curr <= total else (None, None)
    m = _PAG_CURR.search(norm) or _PAG_CURR.search(norm.translate(_DIGIT))
    if m:
        curr = int(m.group(1))
        return (curr, None) if curr > 0 else (None, None)
    return None, None


def extract_code(raw: str) -> str | None:
    """Extract a form code like F-CRS-ART-01 from OCR text (uppercased, '-'-joined)."""
    m = _CODE.search(raw.replace("\n", " "))
    if not m:
        return None
    return m.group(0).upper().replace(" ", "-")


@dataclass(frozen=True)
class PageRead:
    curr: int | None
    total: int | None
    code: str | None
    status: Literal["direct", "recovered", "failed"]


def dominant_total(parsed: list[tuple[int | None, int | None, str | None]]) -> int | None:
    """The most frequent read total (the pagination period), or None if no totals read.

    Deterministic tie-break: among equally-frequent totals, the smaller wins (a
    shorter assumed period under-merges rather than over-merges — safer for a
    counts-then-review system, and stable across runs/Python versions).
    """
    totals = [t for _, t, _ in parsed if t]
    if not totals:
        return None
    counts = Counter(totals)
    top = max(counts.values())
    return min(t for t, c in counts.items() if c == top)


def recover_sequence(
    parsed: list[tuple[int | None, int | None, str | None]],
    dom: int | None = None,
) -> list[PageRead]:
    """Fill no-read pages by completing the pagination cycle from neighbors.

    Lite recovery (spec D3): NOT autocorrelation/Dempster-Shafer. ``dom`` is the
    dominant (mode) total; gaps fill forward from the (possibly already-recovered)
    left neighbor, else from the original right neighbor. A gap with no usable
    sequence context stays ``failed``. Recovered pages carry ``total = dom`` and
    ``code = None`` (their corner wasn't read).

    Boundary note (lite-recovery limitation, by design): in a run of consecutive
    gaps at the very START of the document (index 0..k with no readable left
    neighbor), only the rightmost gap of that prefix is recovered via the right
    neighbor; the earlier ones stay ``failed``. This can only UNDERCOUNT (a missed
    start), never invent a spurious ``curr==1`` — the safe direction. Interior gap
    runs fill completely left-to-right. ``failed`` reads drive LOW confidence so
    the operator reviews.
    """
    if dom is None:
        dom = dominant_total(parsed)
    out: list[PageRead] = [
        PageRead(c, t, code, "direct" if c is not None else "failed") for c, t, code in parsed
    ]
    for i, pr in enumerate(out):
        if pr.curr is not None:
            continue
        rec: int | None = None
        if dom:
            left = out[i - 1].curr if i > 0 else None
            if left is not None:
                rec = left % dom + 1
            elif i + 1 < len(parsed) and parsed[i + 1][0] is not None:
                rec = (parsed[i + 1][0] - 2) % dom + 1
        if rec is not None:
            out[i] = PageRead(rec, dom, None, "recovered")
    return out


def count_recovered_starts(reads: list[PageRead]) -> int:
    """Count *recovered* document starts (curr == 1 among status=='recovered').

    F7: a recovered curr==1 is a possible fabricated start — in a mixed-length
    compilation, recovery can land on curr==1 when the left neighbor happens to
    complete a dominant cycle inside a *longer* document (over-count risk). This
    is a raw, cover_code-agnostic count (unlike ``count_starts``): the scanner
    decides how to weigh it against a configured ``cover_code`` (Task 11's
    ``cover_code_recovery`` already covers the missed-cover edge for that case).
    """
    return sum(1 for r in reads if r.curr == 1 and r.status == "recovered")


def count_starts(reads: list[PageRead], cover_code: str | None) -> int:
    """Count document starts (curr == 1).

    With ``cover_code`` set, count only starts whose page code contains it (IRL:
    ignore appendix page-1s). KNOWN LIMITATION: a *recovered* curr==1 page has
    ``code=None`` and is therefore NOT counted under cover_code (a cover whose
    corner OCR failed would be missed). The scanner offsets this by forcing LOW
    confidence when cover_code is set and any recovered read exists (Task 11), so
    the operator reviews. In practice IRL covers are the cleanest page of a packet
    and read directly; the eval (Task 9) confirms the real impact.
    """
    if cover_code:
        cc = cover_code.upper()
        return sum(1 for r in reads if r.curr == 1 and r.code and cc in r.code.upper())
    return sum(1 for r in reads if r.curr == 1)


def detect_repeated_pattern(
    parsed: list[tuple[int | None, int | None, str | None]],
) -> bool:
    """True iff two ADJACENT pages both read ``curr == 1`` with the same total.

    This is the exact signature of the RCH template bug (``patterns.py``
    :data:`CRS_RCH_ANCHORS` docstring, D2 spec §3): "the continuation page
    also reads Página 1 de N" instead of incrementing. Track D / D2's Fase 0
    survey (``docs/research/2026-07-12-rch-corner-survey.md``) found ZERO
    confirmed occurrences of this signature across 136 real charla pages — the
    trigger is a safety net for a case that, while not reproduced in the
    measured samples, remains possible (a template revision or scan not
    covered by ``data/samples/``). ``PaginationScanner`` acts on this only for
    siglas that opt in via ``PATTERNS[sigla]["rch_fallback"]``.
    """
    for i in range(len(parsed) - 1):
        c1, t1, _ = parsed[i]
        c2, t2, _ = parsed[i + 1]
        if c1 == 1 and c2 == 1 and t1 is not None and t1 == t2:
            return True
    return False


@dataclass(frozen=True)
class PaginationCountResult:
    count: int
    pages_total: int
    direct_reads: int
    recovered_reads: int
    failed_reads: int
    dominant_total: int | None
    codes: dict[str, int]
    cover_code_recovery: bool  # cover_code set AND >=1 recovered read → caller forces LOW
    recovered_start_count: int  # recovered curr==1 reads (F7) — fabricated-start risk signal
    repeated_pattern_detected: bool  # RCH bug signature (D2) — caller may re-route to anchors


def _corner_text(page: fitz.Page) -> str:
    r = page.rect
    bbox = _CORNER_LANDSCAPE if r.width > r.height else _CORNER_PORTRAIT
    clip = fitz.Rect(
        r.x0 + bbox[0] * r.width,
        r.y0 + bbox[1] * r.height,
        r.x0 + bbox[2] * r.width,
        r.y0 + bbox[3] * r.height,
    )
    pix = page.get_pixmap(
        matrix=fitz.Matrix(_OCR_DPI / 72.0, _OCR_DPI / 72.0), clip=clip, alpha=False
    )
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
    return ocr_image(img, config="--psm 6 --oem 1", lang="spa+eng").strip()


def _read_pages_sequential(
    pdf_path: Path,
    cancel: CancellationToken,
    on_page: Callable[[int, int], None] | None,
) -> list[tuple[int | None, int | None, str | None]]:
    """Read every corner in page order on the calling thread (single open, A2)."""
    parsed: list[tuple[int | None, int | None, str | None]] = []
    with fitz.open(pdf_path) as doc:
        n = doc.page_count
        for pi in range(n):
            cancel.check()
            raw = _corner_text(doc[pi])
            curr, total = parse_pagination(raw)
            parsed.append((curr, total, extract_code(raw)))
            if on_page is not None:
                on_page(pi, n)
    return parsed


def _read_pages_threaded(
    pdf_path: Path,
    threads: int,
    cancel: CancellationToken,
    on_page: Callable[[int, int], None] | None,
) -> list[tuple[int | None, int | None, str | None]]:
    """Read all corners with a thread pool (pytesseract releases the GIL).

    fitz Documents are not thread-safe, so each worker thread opens its own
    handle (cheap: 0.7–20 ms measured, even on a 516 MB PDF) and keeps it
    thread-local for its whole share of pages. Results land in a page-indexed
    list, so parse/recover/count downstream see the exact same input order as
    the sequential path — the count is deterministic regardless of completion
    order. ``on_page`` reports a monotonic completed-pages counter under a lock
    (0-based, same value sequence as sequential). Cancellation: each page task
    re-checks the token; the first ``CancelledError`` cancels the queued
    futures and propagates (in-flight pages finish, ≤1 page per thread).
    """
    with fitz.open(pdf_path) as doc:
        n = doc.page_count
    if n == 0:
        return []
    parsed: list[tuple[int | None, int | None, str | None]] = [(None, None, None)] * n
    done = 0
    progress_lock = threading.Lock()
    tl = threading.local()
    docs: list[fitz.Document] = []
    docs_lock = threading.Lock()

    def _read_one(pi: int) -> None:
        nonlocal done
        cancel.check()
        d = getattr(tl, "doc", None)
        if d is None:
            d = fitz.open(pdf_path)
            tl.doc = d
            with docs_lock:
                docs.append(d)
        raw = _corner_text(d[pi])
        curr, total = parse_pagination(raw)
        parsed[pi] = (curr, total, extract_code(raw))
        with progress_lock:
            done += 1
            if on_page is not None:
                on_page(done - 1, n)

    try:
        with ThreadPoolExecutor(max_workers=min(threads, n)) as ex:
            futures = [ex.submit(_read_one, pi) for pi in range(n)]
            try:
                for fut in as_completed(futures):
                    fut.result()
            except BaseException:
                for fut in futures:
                    fut.cancel()
                raise
    finally:
        for d in docs:
            d.close()
    return parsed


def count_documents_by_pagination(
    pdf_path: Path,
    *,
    cancel: CancellationToken,
    cover_code: str | None = None,
    on_page: Callable[[int, int], None] | None = None,
    ocr_threads: int | None = None,
) -> PaginationCountResult:
    """Count documents in a compilation by their "Página N de M" pagination.

    ``on_page`` (U7), when given, is called with 0-based ``(pages_done - 1,
    total)`` as each page completes OCR — a monotonic progress counter (the
    same value sequence in both execution modes; under threads the *counter*
    is ordered even though pages complete out of order). Same contract as the
    anchors engine (``header_band_anchors.count_covers_by_anchors``).

    ``ocr_threads`` (default ``core.utils.OCR_PAGE_THREADS``) parallelizes the
    per-page corner OCR; ``1`` forces the sequential path. Counting is
    deterministic in both modes — page reads land in page order before any
    interpretation runs.
    """
    cancel.check()
    threads = OCR_PAGE_THREADS if ocr_threads is None else ocr_threads
    if threads <= 1:
        parsed = _read_pages_sequential(pdf_path, cancel, on_page)
    else:
        parsed = _read_pages_threaded(pdf_path, threads, cancel, on_page)
    codes: Counter[str] = Counter()
    for _, _, code in parsed:  # page order → deterministic Counter order
        if code:
            codes[code] += 1
    dom = dominant_total(parsed)
    reads = recover_sequence(parsed, dom)
    recovered = sum(1 for r in reads if r.status == "recovered")
    return PaginationCountResult(
        count=count_starts(reads, cover_code),
        pages_total=len(reads),
        direct_reads=sum(1 for r in reads if r.status == "direct"),
        recovered_reads=recovered,
        failed_reads=sum(1 for r in reads if r.status == "failed"),
        dominant_total=dom,
        codes=dict(codes),
        cover_code_recovery=bool(cover_code) and recovered > 0,
        recovered_start_count=count_recovered_starts(reads),
        repeated_pattern_detected=detect_repeated_pattern(parsed),
    )
