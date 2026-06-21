"""Smoke test for the altura pagination pattern (Task 5.9).

Runs the real pagination engine against a fixture PDF. When the fixture is absent
(gitignored), the test is skipped — not failed — so CI stays green.

Fixture: a real 18-page HPV altura compilation — 18 standalone
'CHEQUEO DE ARNÉS DE SEGURIDAD' forms, each 'Página 1 de 1'. The pagination
engine counts 18 documents (direct reads + gap-recovery). See ground_truth.json.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytesseract
import pytest

pytesseract.pytesseract.tesseract_cmd = os.getenv(
    "TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

from core.scanners.base import ConfidenceLevel  # noqa: E402
from core.scanners.cancellation import CancellationToken  # noqa: E402
from core.scanners.pagination_scanner import PaginationScanner  # noqa: E402

_FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures" / "scanners" / "altura"
_GT = _FIXTURE_DIR / "ground_truth.json"


def _load_gt() -> dict:
    return json.loads(_GT.read_text(encoding="utf-8"))


def _fixture_pdf() -> Path:
    return _FIXTURE_DIR / _load_gt()["fixture"]


def test_altura_count_ocr_smoke():
    """PaginationScanner counts every document in the real altura compilation.

    The fixture bundles 18 standalone 1-page forms; the pagination engine must
    recover all 18, including pages that need gap-fill recovery. Method = 'pagination'.
    """
    if not _fixture_pdf().exists():
        pytest.skip("Altura fixture PDF not present (gitignored)")

    gt = _load_gt()
    scanner = PaginationScanner(sigla="altura")
    result = scanner.count_ocr(_FIXTURE_DIR, cancel=CancellationToken())

    assert result.method == "pagination", f"Expected method 'pagination', got {result.method!r}"
    assert result.count == gt["covers_expected"], (
        f"Altura count mismatch: got {result.count}, expected "
        f"{gt['covers_expected']}. per_file={result.per_file!r} "
        f"flags={result.flags!r} errors={result.errors!r}"
    )


def test_altura_count_ocr_per_file_and_confidence():
    """The compilation yields a per_file entry and a HIGH-confidence result.

    Most pages read directly, so the pagination engine count is trustworthy —
    the cell must not be flagged pagination_low_confidence.
    """
    if not _fixture_pdf().exists():
        pytest.skip("Altura fixture PDF not present (gitignored)")

    gt = _load_gt()
    scanner = PaginationScanner(sigla="altura")
    result = scanner.count_ocr(_FIXTURE_DIR, cancel=CancellationToken())

    assert result.per_file[gt["fixture"]] == gt["covers_expected"]
    assert result.confidence == ConfidenceLevel.HIGH
    assert "pagination_low_confidence" not in result.flags
