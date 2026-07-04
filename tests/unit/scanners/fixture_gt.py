"""Shared ground-truth helpers for the per-sigla scanner smoke tests.

Single source for the boilerplate every ``test_pattern_<sigla>.py`` used to
re-define (fixture paths, ``ground_truth.json`` loading, the Tesseract binary
path) and for the GT access idioms, one per GT shape (see
``tests/fixtures/scanners/README.md``):

- **single-fixture** ``{fixture, pages, covers_expected, notes}`` →
  ``load_gt`` + ``fixture_pdf`` (the path comes FROM the GT, never hardcoded);
- **multi-fixture** ``{fixtures: [{file, covers_expected, ...}, ...]}`` →
  ``fixture_covers``;
- **flavor subdirs** (``chintegral/f_rch/ground_truth.json`` etc.) → pass the
  flavor-relative dir to ``load_gt``/``fixture_dir``.

Fixture PDFs are gitignored local snapshots — tests call
``skip_unless_present`` so a fresh clone stays green (skip, not fail).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytesseract
import pytest

# Mirror core/ocr.py + pagination_count.py convention; idempotent (same value).
pytesseract.pytesseract.tesseract_cmd = os.getenv(
    "TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

FIXTURES_ROOT = Path(__file__).parent.parent.parent / "fixtures" / "scanners"


def fixture_dir(rel: str) -> Path:
    """Directory of a sigla's (or flavor's) fixtures, e.g. ``"exc"`` or ``"dif_pts/f_rch"``."""
    return FIXTURES_ROOT / rel


def load_gt(rel: str) -> dict:
    """Parse ``ground_truth.json`` under ``fixture_dir(rel)``."""
    return json.loads((fixture_dir(rel) / "ground_truth.json").read_text(encoding="utf-8"))


def fixture_pdf(rel: str) -> Path:
    """Single-fixture shape: the PDF path named by ``gt["fixture"]``."""
    return fixture_dir(rel) / load_gt(rel)["fixture"]


def fixture_covers(rel: str, filename: str) -> int:
    """Multi-fixture shape: ``covers_expected`` for ``filename`` in ``gt["fixtures"]``."""
    for entry in load_gt(rel)["fixtures"]:
        if entry["file"] == filename:
            return entry["covers_expected"]
    raise KeyError(f"{filename} not found in {rel}/ground_truth.json fixtures list")


def skip_unless_present(pdf: Path, label: str) -> None:
    """Skip (not fail) when a gitignored fixture PDF is absent on this machine."""
    if not pdf.exists():
        pytest.skip(f"{label} fixture PDF not present (gitignored)")
