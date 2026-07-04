"""Smoke test for the altura pagination pattern (Task 5.9).

Runs the real pagination engine against a fixture PDF. When the fixture is absent
(gitignored), the test is skipped — not failed — so CI stays green.

Fixture: a real 18-page HPV altura compilation — 18 standalone
'CHEQUEO DE ARNÉS DE SEGURIDAD' forms, each 'Página 1 de 1'. The pagination
engine counts 18 documents (direct reads + gap-recovery). See ground_truth.json.
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

_SIGLA = "altura"


def test_altura_count_ocr_smoke():
    """PaginationScanner counts every document in the real altura compilation.

    The fixture bundles 18 standalone 1-page forms; the pagination engine must
    recover all 18, including pages that need gap-fill recovery. Method = 'pagination'.
    """
    skip_unless_present(fixture_pdf(_SIGLA), "Altura")

    gt = load_gt(_SIGLA)
    scanner = PaginationScanner(sigla=_SIGLA)
    result = scanner.count_ocr(fixture_dir(_SIGLA), cancel=CancellationToken())

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
    skip_unless_present(fixture_pdf(_SIGLA), "Altura")

    gt = load_gt(_SIGLA)
    scanner = PaginationScanner(sigla=_SIGLA)
    result = scanner.count_ocr(fixture_dir(_SIGLA), cancel=CancellationToken())

    assert result.per_file[gt["fixture"]] == gt["covers_expected"]
    assert result.confidence == ConfidenceLevel.HIGH
    assert "pagination_low_confidence" not in result.flags
