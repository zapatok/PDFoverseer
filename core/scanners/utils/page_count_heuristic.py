"""Heuristic: flag a folder as containing a likely compilation.

We use page-count anomaly: if one PDF in the folder is much longer than
the expected per-document length for that sigla, that PDF is probably a
compilation of multiple documents (not a single document).

The actual COUNTING of internal documents is FASE 2 work via OCR scanners.
This util only produces a boolean flag for the badge.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

from core.utils import COMPILATION_PAGE_FACTOR, COMPILATION_RATIO_FACTOR

# Tentative thresholds — calibrate per sigla as needed. Conservative
# defaults; better to flag false positives than miss real compilations.
EXPECTED_PAGES_PER_DOC: dict[str, int] = {
    "reunion": 4,
    "irl": 2,
    "odi": 2,
    "charla": 3,
    "chintegral": 8,
    "dif_pts": 3,
    "art": 10,  # ART forms run up to ~28pp normally (multi-worker sheets)
    "insgral": 3,
    "bodega": 2,
    "maquinaria": 2,
    "ext": 2,
    "senal": 2,
    "exc": 2,
    "altura": 2,
    "caliente": 2,
    "herramientas_elec": 2,
    "andamios": 2,
    "chps": 4,
}


def _page_count(pdf_path: Path) -> int:
    try:
        with fitz.open(pdf_path) as doc:
            return doc.page_count
    except (fitz.FileDataError, OSError):
        return 0


def flag_compilation_suspect(folder: Path, *, sigla: str) -> bool:
    """Return True if a folder likely contains a compilation (audit #4).

    Two signals:
      1. **Per-PDF:** any single PDF longer than ``expected ×
         COMPILATION_PAGE_FACTOR`` — a compilation packed into one file.
      2. **Aggregate:** at least 3 PDFs whose *average* length exceeds
         ``expected × COMPILATION_RATIO_FACTOR`` — a compilation spread across
         several medium PDFs that no single PDF reveals (e.g. HRB/andamios
         ``check_list_*.pdf`` of 6-9pp).

    Args:
        folder: Directory to scan recursively for PDF files.
        sigla: Category key used to look up the expected pages per document.

    Returns:
        True if either signal fires, False otherwise.
    """
    if not folder.exists():
        return False
    counts = [c for c in (_page_count(p) for p in folder.rglob("*.pdf")) if c > 0]
    if not counts:
        return False
    expected = EXPECTED_PAGES_PER_DOC.get(sigla, 5)
    # Per-PDF signal: one file much longer than a single document.
    if any(c > expected * COMPILATION_PAGE_FACTOR for c in counts):
        return True
    # Aggregate signal: several medium PDFs averaging well above one document.
    avg = sum(counts) / len(counts)
    return len(counts) >= 3 and avg > expected * COMPILATION_RATIO_FACTOR
