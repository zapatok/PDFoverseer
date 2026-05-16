"""Count document boundaries by detecting "Página N de M" transitions.

Used by art_scanner when ART folders contain a compilation PDF.
Each new document starts at page 1 of a new pagination series.

Reuses regex + digit normalization from core/utils when available, falls
back to a local pattern otherwise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pytesseract
from PIL import Image

from core.scanners.utils.pdf_render import get_page_count, render_page_region

if TYPE_CHECKING:
    from core.scanners.cancellation import CancellationToken  # noqa: F401

# Top-right corner: rightmost 30%, top 22% (matches project CROP defaults)
_CORNER_BBOX = (0.70, 0.0, 1.0, 0.22)

# Spanish pagination: tolerant of OCR noise ("Pag", "Pagina", "Página", optional accent)
_FALLBACK_PATTERN = re.compile(
    r"P[áa]?g(?:ina|\.)?\s*(\d{1,3})\s*(?:de|\/)\s*(\d{1,3})",
    re.IGNORECASE,
)


def _get_patterns() -> list[re.Pattern[str]]:
    """Reuse core/utils._PAGE_PATTERNS if available; else use fallback."""
    try:
        from core import utils as _u

        return list(_u._PAGE_PATTERNS) if hasattr(_u, "_PAGE_PATTERNS") else [_FALLBACK_PATTERN]
    except ImportError:
        return [_FALLBACK_PATTERN]


def _normalize_digits(text: str) -> str:
    """OCR digit normalization (per core/CLAUDE.md OCR Assumptions)."""
    table = str.maketrans(
        {
            "O": "0",
            "I": "1",
            "l": "1",
            "L": "1",
            "i": "1",
            "z": "2",
            "Z": "2",
            "|": "1",
            "t": "1",
            "T": "1",
            "'": "1",
        }
    )
    return text.translate(table)


@dataclass(frozen=True)
class CornerCountResult:
    """Result of corner pagination analysis."""

    count: int
    transitions: list[tuple[int, int]] = field(default_factory=list)
    pages_total: int = 0
    method: str = "corner_count"


def _count_transitions(series: list[tuple[int, int]]) -> int:
    """Given a list of (N, M) per page, count how many distinct documents exist.

    Each new doc starts at page 1; consecutive page 1s with different M values
    indicate distinct compilations.
    """
    if not series:
        return 0
    docs = 0
    prev: tuple[int, int] | None = None
    for n, m in series:
        if prev is None:
            docs = 1
        else:
            # New document if we see a page 1 again
            if n == 1:
                docs += 1
        prev = (n, m)
    return docs


def count_paginations(
    pdf_path: Path,
    *,
    dpi: int = 200,
    cancel: CancellationToken | None = None,
) -> CornerCountResult:
    """OCR the upper-right corner of each page, parse "Página N de M",
    count document transitions."""
    pages_total = get_page_count(pdf_path)
    patterns = _get_patterns()
    series: list[tuple[int, int]] = []

    for page_idx in range(pages_total):
        if cancel is not None:
            cancel.check()
        img: Image.Image = render_page_region(pdf_path, page_idx, bbox=_CORNER_BBOX, dpi=dpi)
        text = pytesseract.image_to_string(img, config="--psm 7 --oem 1", lang="spa+eng")
        text = _normalize_digits(text)
        match = None
        for pattern in patterns:
            m = pattern.search(text)
            if m and len(m.groups()) >= 2:
                match = m
                break
        if match:
            try:
                n, total = int(match.group(1)), int(match.group(2))
                if 0 < n <= total <= 99:
                    series.append((n, total))
            except (ValueError, IndexError):
                continue

    count = _count_transitions(series)
    return CornerCountResult(count=count, transitions=series, pages_total=pages_total)
