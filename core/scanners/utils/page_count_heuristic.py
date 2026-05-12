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

# Tentative thresholds — calibrate per sigla as needed. Conservative
# defaults; better to flag false positives than miss real compilations.
EXPECTED_PAGES_PER_DOC: dict[str, int] = {
    "reunion": 4,
    "irl": 2,
    "odi": 2,
    "charla": 3,
    "chintegral": 8,
    "dif_pts": 3,
    "art": 4,
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

_TIGHT_FACTOR = 5  # PDF is suspect if pages > expected × factor


def _page_count(pdf_path: Path) -> int:
    try:
        with fitz.open(pdf_path) as doc:
            return doc.page_count
    except (fitz.FileDataError, OSError):
        return 0


def flag_compilation_suspect(folder: Path, *, sigla: str) -> bool:
    """Return True if at least one PDF in folder has page-count
    >> expected for this sigla (likely compilation).

    Args:
        folder: Directory to scan recursively for PDF files.
        sigla: Category key used to look up the expected pages per document.

    Returns:
        True if any PDF exceeds the compilation threshold, False otherwise.
    """
    if not folder.exists():
        return False
    expected = EXPECTED_PAGES_PER_DOC.get(sigla, 5)
    threshold = expected * _TIGHT_FACTOR
    for pdf in folder.rglob("*.pdf"):
        if _page_count(pdf) > threshold:
            return True
    return False
