"""corner_count — count document transitions via Página N de M pagination."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.scanners.utils.corner_count import CornerCountResult, count_paginations
from core.scanners.utils.pdf_render import PdfRenderError

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "scanners_ocr"


@pytest.mark.slow
def test_corner_count_on_real_pdf_runs_and_is_consistent():
    # HRB/odi may or may not have corner pagination; verify invariants only.
    result = count_paginations(FIXTURES / "odi_compilation" / "HRB_odi_compilation.pdf")
    assert isinstance(result, CornerCountResult)
    assert result.method == "corner_count"
    assert result.pages_total > 0
    assert result.count <= result.pages_total
    # Every transition entry must be a (1..M, M) tuple with positive M
    assert all(0 < n <= m and m > 0 for n, m in result.transitions)


def test_corner_count_on_corrupted_raises():
    with pytest.raises(PdfRenderError):
        count_paginations(FIXTURES / "corrupted" / "corrupted.pdf")


def test_corner_count_transitions_logic():
    """Unit-level: given a series of (N, M) tuples, count doc boundaries."""
    from core.scanners.utils.corner_count import _count_transitions

    # Each new document is a 1/M after a previous N/M sequence
    series = [(1, 3), (2, 3), (3, 3), (1, 2), (2, 2)]
    assert _count_transitions(series) == 2  # two docs

    # Single page docs
    assert _count_transitions([(1, 1), (1, 1), (1, 1)]) == 3

    # Empty input
    assert _count_transitions([]) == 0

    # Page numbers with same total — one doc
    assert _count_transitions([(1, 5), (2, 5), (3, 5), (4, 5), (5, 5)]) == 1
