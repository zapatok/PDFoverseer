"""Pagination-first document counter (eval prototype). See spec §6.

Pure functions (parse_pagination / extract_code / dominant_total / recover_sequence /
count_starts) have zero OCR/PDF dependency and are unit-tested directly.
count_documents_by_pagination is the thin OCR orchestrator (integration-tested with
synthetic PDFs).
"""

from __future__ import annotations

import io
import os as _os
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

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
        return int(m.group(1)), int(m.group(2))
    m = _PAG_CURR.search(norm) or _PAG_CURR.search(norm.translate(_DIGIT))
    if m:
        return int(m.group(1)), None
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
    status: str  # "direct" | "recovered" | "failed"


def dominant_total(parsed: list[tuple[int | None, int | None, str | None]]) -> int | None:
    """The most frequent read total (the pagination period), or None if no totals read."""
    totals = [t for _, t, _ in parsed if t]
    return Counter(totals).most_common(1)[0][0] if totals else None


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
