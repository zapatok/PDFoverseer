"""Smoke test for the insgral pagination pattern (Task 5.3).

Runs the real pagination engine against a fixture PDF. When the fixture is absent
(gitignored), the test is skipped — not failed — so CI stays green.

Fixture: a real 10-page HRB insgral compilation — 10 standalone
'CHEQUEO SISTEMA LAVADO DE RUEDAS' forms, each 'Página 1 de 1'. The pagination
engine counts 10 documents (all read directly). See ground_truth.json.
"""

from __future__ import annotations

from core.scanners.base import ConfidenceLevel
from core.scanners.cancellation import CancellationToken
from core.scanners.pagination_scanner import PaginationScanner
from tests.unit.scanners.fixture_gt import (
    fixture_dir,
    fixture_pdf,
    load_gt,
    skip_unless_present,
)

_SIGLA = "insgral"


def test_insgral_count_ocr_smoke():
    """PaginationScanner counts every document in the real insgral compilation.

    The fixture is one PDF bundling 10 standalone 1-page forms; the pagination
    engine must recover all 10. Method must be 'pagination'.
    """
    skip_unless_present(fixture_pdf(_SIGLA), "Insgral")

    gt = load_gt(_SIGLA)
    scanner = PaginationScanner(sigla=_SIGLA)
    result = scanner.count_ocr(fixture_dir(_SIGLA), cancel=CancellationToken())

    assert result.method == "pagination", f"Expected method 'pagination', got {result.method!r}"
    assert result.count == gt["covers_expected"], (
        f"Insgral count mismatch: got {result.count}, expected "
        f"{gt['covers_expected']}. per_file={result.per_file!r} "
        f"flags={result.flags!r} errors={result.errors!r}"
    )


def test_insgral_count_ocr_per_file_and_confidence():
    """The compilation yields a per_file entry and a HIGH-confidence result.

    Every page of this fixture reads directly, so the pagination engine produces
    a trustworthy count — the cell must not be flagged pagination_low_confidence.
    """
    skip_unless_present(fixture_pdf(_SIGLA), "Insgral")

    gt = load_gt(_SIGLA)
    scanner = PaginationScanner(sigla=_SIGLA)
    result = scanner.count_ocr(fixture_dir(_SIGLA), cancel=CancellationToken())

    assert result.per_file[gt["fixture"]] == gt["covers_expected"]
    assert result.confidence == ConfidenceLevel.HIGH
    assert "pagination_low_confidence" not in result.flags
