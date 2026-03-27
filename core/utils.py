"""Shared configuration, types, and utilities for the OCR pipeline."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ============================================================================
# Configuration Constants
# ============================================================================

DPI              = 150
CROP_X_START     = 0.70   # rightmost 30%
CROP_Y_END       = 0.22   # top 22%
TESS_CONFIG      = "--psm 6 --oem 1"
PARALLEL_WORKERS = 6      # concurrent Tesseract subprocesses
BATCH_SIZE       = 12     # pages per batch (pause/cancel granularity)

MIN_CONF_FOR_NEW_DOC = 0.55   # sweep2 (2026-03-24, 40 fixtures incl. degraded)
ANOMALY_DROPOUT      = 0.0
PHASE4_FALLBACK_CONF = 0.15  # re-enabled: recovers pages the gap solver missed
CLASH_BOUNDARY_PEN   = 1.5   # sweep2
PH5B_CONF_MIN        = 0.50  # sweep2
PH5B_RATIO_MIN       = 0.90  # lowered from 0.95: zero regressions on 40 fixtures, fixes INS_31 (3 misreads in 31-page all-1-page PDF)
MIN_BOUNDARY_GAP     = 2     # suppress one of two curr=1 reads closer than this; only when period >= 2*gap (guards against 1-page docs)
INFERENCE_ENGINE_VERSION = "s2t-helena"
PAGE_PATTERN_VERSION     = "v1-baseline"  # restored baseline: P-prefix only, tot<=10, Unicode quotes intact

# ============================================================================
# Page Number Patterns & Normalization
# ============================================================================

# Page number pattern — robust to OCR confusion (O↔0, I↔1, Z↔2, etc)
_PAGE_PATTERNS = [
    re.compile(
        r"P.{0,6}\s*([0-9OoIilL|zZtT\'\‘\’\`\´]{1,3})\s*\.?\s*d[ea]\s*([0-9OoIilL|zZtT\'\‘\’\`\´]{1,3})",
        re.IGNORECASE,
    ),
]
_Z2 = re.compile(r"(?<!\d)Z(?!\d)")

# OCR digit normalization: handle Tesseract confusion
_OCR_DIGIT = str.maketrans("OoIilLzZ|tT'‘’`´", "0011112201111111")


def _to_int(s: str) -> int:
    """Convert OCR-confused digits to int. E.g., 'O' → '0', 'l' → '1'."""
    return int(s.translate(_OCR_DIGIT))


def _parse(text: str) -> tuple[int | None, int | None]:
    t = _Z2.sub("2", text)

    for pat in _PAGE_PATTERNS:
        m = pat.search(t)
        if m:
            c, tot = _to_int(m.group(1)), _to_int(m.group(2))
            if 0 < c <= tot <= 10:
                return c, tot

    return None, None


# ============================================================================
# Data Types
# ============================================================================

@dataclass
class Document:
    index:          int
    start_pdf_page: int
    declared_total: int
    pages:          list[int] = field(default_factory=list)
    inferred_pages: list[int] = field(default_factory=list)
    sequence_ok:    bool      = True

    @property
    def found_total(self) -> int:
        return len(self.pages) + len(self.inferred_pages)

    @property
    def is_complete(self) -> bool:
        return self.sequence_ok and self.found_total == self.declared_total


@dataclass
class _PageRead:
    """Internal per-page OCR result used for inference."""
    pdf_page:   int
    curr:       int | None
    total:      int | None
    method:     str
    confidence: float
    # Set by Phase 1b; not stored in sessions (has default):
    _ph1_orphan_candidate: bool = field(default=False, repr=False, compare=False)
