"""Pagination-first document counter (eval prototype). See spec §6.

Pure functions (parse_pagination / extract_code / dominant_total / recover_sequence /
count_starts) have zero OCR/PDF dependency and are unit-tested directly.
count_documents_by_pagination is the thin OCR orchestrator (integration-tested with
synthetic PDFs).
"""

from __future__ import annotations

import io
import math
import os as _os
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import fitz
import pytesseract
from PIL import Image

from core.scanners.cancellation import CancellationToken

# Tesseract binary path — mirror core/ocr.py convention
pytesseract.pytesseract.tesseract_cmd = _os.getenv(
    "TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

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


# ---------------------------------------------------------------------------
# RCH de-dup approach prototypes (Track D / D2, spec §3). Three comparable,
# pure functions — no OCR/PDF dependency — benchmarked in
# docs/research/2026-07-12-rch-pagination-decision.md against the samples
# characterized in docs/research/2026-07-12-rch-corner-survey.md (Fase 0).
# All operate on the same ``parsed: list[(curr, total, code)]`` shape that
# ``dominant_total``/``recover_sequence`` already consume.
# ---------------------------------------------------------------------------

_ParsedPage = tuple[int | None, int | None, str | None]


def detect_repeated_pattern(parsed: list[_ParsedPage]) -> bool:
    """True iff two ADJACENT pages both read ``curr == 1`` with the same total.

    This is the literal signature of the pinned RCH template bug ("the
    continuation page also reads Página 1 de N"). Fase 0
    (``docs/research/2026-07-12-rch-corner-survey.md``) found ZERO confirmed
    occurrences of this signature across 136 pages of 3 real homogeneous
    charla samples — the trigger is a safety net for a case that, while not
    reproduced in the measured samples, remains possible (Daniel's originally
    reported sample, or a template revision not covered by the 7 samples in
    ``data/samples/``).
    """
    for i in range(len(parsed) - 1):
        c1, t1, _ = parsed[i]
        c2, t2, _ = parsed[i + 1]
        if c1 == 1 and c2 == 1 and t1 is not None and t1 == t2:
            return True
    return False


def count_by_arithmetic_dedup(parsed: list[_ParsedPage]) -> int | None:
    """Approach 1 (spec §3, candidate 1): ``ceil(pages / dominant_total)``.

    Only fires when EVERY page in the file reads ``curr == 1`` (the file-wide
    "every page thinks it's a cover" signature) — spec: "Solo viable si Fase 0
    muestra que el patrón repetido es uniforme". Fase 0 found the opposite (the
    7 real samples alternate curr correctly; this all-curr==1 condition never
    held on any of them) — kept here as a documented, evidence-rejected
    candidate for the benchmark comparison. Returns ``None`` when the trigger
    condition doesn't hold (caller falls back to plain counting).
    """
    if not parsed:
        return None
    if not all(c == 1 for c, _, _ in parsed):
        return None
    dom = dominant_total(parsed)
    if not dom or dom <= 1:
        return None
    return math.ceil(len(parsed) / dom)


def count_by_region_discriminator(parsed: list[_ParsedPage], anchor_hits: list[bool]) -> int:
    """Approach 2 (spec §3, candidate 2): confirm each ``curr == 1`` candidate
    against a second, cheaper region read.

    ``anchor_hits[i]`` is ``True`` iff page *i* matched >= 2
    ``CRS_RCH_ANCHORS`` in the discriminator region — the region itself is a
    Fase-0 correction: the spec's originally proposed "amplified" corner region
    measured a 0% hit rate on real cover pages (docs/research/2026-07-12-rch-corner-survey.md,
    Result 2); ``top_left_half`` is the region that actually contains the
    cover-only fields (52-64% hit rate, 0% false positives on continuations in
    Fase 0). Undercount-safe by construction: an unconfirmed ``curr==1``
    candidate silently does not count (never inflates).

    Raises:
        ValueError: ``anchor_hits`` is not the same length as ``parsed``.
    """
    if len(anchor_hits) != len(parsed):
        raise ValueError("anchor_hits must be the same length as parsed (1 bool per page)")
    return sum(1 for (c, _, _), hit in zip(parsed, anchor_hits, strict=True) if c == 1 and hit)


def count_by_hybrid_fallback(
    parsed: list[_ParsedPage], *, anchors_fallback_count: int | None
) -> int:
    """Approach 3 (spec §3, candidate 3): plain pagination, UNLESS
    ``detect_repeated_pattern`` fires — then the WHOLE file's count comes from
    ``anchors_fallback_count`` (the already-proven anchors engine) instead.

    Fase 0's best-supported candidate: zero count risk on any confirmed bug
    occurrence (delegates to the engine already known correct for RCH), full
    pagination speed on the 100% of measured real samples where the bug never
    fired. The "plain" branch reuses ``recover_sequence`` + ``count_starts`` —
    the same baseline the production engine already applies.

    Args:
        parsed: Per-page ``(curr, total, code)`` reads from the pagination corner.
        anchors_fallback_count: The anchors-engine document count for this same
            file — required (raises) only when the repeated pattern actually
            fires; a caller that never expects the pattern on its inputs may
            pass ``None``.

    Raises:
        ValueError: the repeated pattern fired but no fallback count was given.
    """
    if detect_repeated_pattern(parsed):
        if anchors_fallback_count is None:
            raise ValueError("detect_repeated_pattern fired but anchors_fallback_count is None")
        return anchors_fallback_count
    reads = recover_sequence(parsed)
    return count_starts(reads, None)


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
    return pytesseract.image_to_string(img, config="--psm 6 --oem 1", lang="spa+eng").strip()


def count_documents_by_pagination(
    pdf_path: Path,
    *,
    cancel: CancellationToken,
    cover_code: str | None = None,
    on_page: Callable[[int, int], None] | None = None,
) -> PaginationCountResult:
    """Count documents in a compilation by their "Página N de M" pagination."""
    cancel.check()
    parsed: list[tuple[int | None, int | None, str | None]] = []
    codes: Counter[str] = Counter()
    with fitz.open(pdf_path) as doc:  # single open (A2)
        n = doc.page_count
        for pi in range(n):
            cancel.check()
            raw = _corner_text(doc[pi])
            curr, total = parse_pagination(raw)
            code = extract_code(raw)
            if code:
                codes[code] += 1
            parsed.append((curr, total, code))
            if on_page is not None:
                on_page(pi + 1, n)
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
    )
