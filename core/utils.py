"""Shared configuration, types, and utilities for the OCR pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ============================================================================
# Configuration Constants
# ============================================================================

DPI = 150
CROP_X_START = 0.70  # rightmost 30%
CROP_Y_END = 0.22  # top 22%
TESS_CONFIG = "--psm 6 --oem 1"
PARALLEL_WORKERS = 6  # concurrent Tesseract subprocesses
BATCH_SIZE = 12  # pages per batch (pause/cancel granularity)

# OCR auto-retry (FASE 5) — el orquestador reintenta un scan de celda fallido
# en silencio antes de reportar el error.
OCR_RETRY_COUNT = 2  # reintentos tras el intento inicial (3 intentos totales)
OCR_RETRY_BACKOFF_S = 0.5  # pausa entre intentos

# Compilation-suspect heuristic (audit #4). Two signals flag a folder as a
# likely compilation: a single PDF much longer than one document, OR several
# medium PDFs whose average length is well above one document (a compilation
# spread across files, which the per-PDF factor alone misses -- e.g.
# HRB/andamios check_list_*.pdf of 6-9pp).
COMPILATION_PAGE_FACTOR = 3  # a PDF is suspect if pages > expected x this
COMPILATION_RATIO_FACTOR = 2  # a folder is suspect if avg pages/PDF > expected x this

# Siglas whose every document is a fixed number of pages -> count = total pages.
# For these, pase 1 counts documents by summing page counts (no OCR needed) and
# reports HIGH confidence. Source: corpus audit 2026-05-11 + OCR per-sigla spec
# §9/§11/§13/§15/§16 + calibration Fase A/B. All divisor 1 (1 page = 1 document).
FIXED_PAGE_SIGLAS: dict[str, int] = {
    "bodega": 1,  # documented + Fase A confirmed
    "ext": 1,  # documented + Fase A confirmed (canonical LCH-18/37)
    "caliente": 1,  # inferred (Fase B: 20 pages -> 20 covers)
    "herramientas_elec": 1,  # inferred (Fase B: 38 covers / 40 pages)
    "exc": 1,  # inferred (Fase A: 2 covers / 2 pages, small sample)
}
# Subset whose page-per-doc is inferred (less evidence) -> UI "verificar" hint.
FIXED_PAGE_SIGLAS_INFERRED: frozenset[str] = frozenset({"caliente", "herramientas_elec", "exc"})

MIN_CONF_FOR_NEW_DOC = 0.55  # sweep2 (2026-03-24, 40 fixtures incl. degraded)
ANOMALY_DROPOUT = 0.0
PHASE4_FALLBACK_CONF = 0.15  # re-enabled: recovers pages the gap solver missed
CLASH_BOUNDARY_PEN = 1.5  # sweep2
PH5B_CONF_MIN = 0.50  # sweep2
PH5B_RATIO_MIN = 0.90  # lowered from 0.95: zero regressions on 40 fixtures, fixes INS_31 (3 misreads in 31-page all-1-page PDF)
INFERENCE_ENGINE_VERSION = "s2t-helena"
PAGE_PATTERN_VERSION = (
    "v1-baseline"  # restored baseline: P-prefix only, tot<=10, Unicode quotes intact
)
SCANNER_PATTERNS_VERSION = (
    # v2: pase-1 honest confidence + page-count for FIXED_PAGE_SIGLAS
    "v2-conteo-confiable"
)

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
    index: int
    start_pdf_page: int
    declared_total: int
    pages: list[int] = field(default_factory=list)
    inferred_pages: list[int] = field(default_factory=list)
    sequence_ok: bool = True

    @property
    def found_total(self) -> int:
        return len(self.pages) + len(self.inferred_pages)

    @property
    def is_complete(self) -> bool:
        return self.sequence_ok and self.found_total == self.declared_total


@dataclass
class _PageRead:
    """Internal per-page OCR result used for inference."""

    pdf_page: int
    curr: int | None
    total: int | None
    method: str
    confidence: float
    # Set by Phase 1b; not stored in sessions (has default):
    _ph1_orphan_candidate: bool = field(default=False, repr=False, compare=False)
