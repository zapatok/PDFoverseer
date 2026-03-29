"""
Tests for core.vlm_resolver — VLM Tier 3: gap-edge targeting, plausibility guard, mock provider.
No real VLM calls — uses mock provider.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import threading  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from core.utils import _PageRead  # noqa: E402
from core.vlm_provider import VLMResult  # noqa: E402
from core.vlm_resolver import _find_candidates, query_failed_pages  # noqa: E402


def _make_read(page, curr, total, method="direct", confidence=1.0):
    return _PageRead(pdf_page=page, curr=curr, total=total,
                     method=method, confidence=confidence)


def _failed(page):
    return _PageRead(pdf_page=page, curr=None, total=None,
                     method="failed", confidence=0.0)


# ── _find_candidates tests ────────────────────────────────────────────────────

def test_find_candidates_skip_isolated():
    """Isolated single failures between two successes are skipped."""
    reads = [_make_read(1, 1, 4), _failed(2), _make_read(3, 3, 4)]
    candidates = _find_candidates(reads, skip_isolated=True)
    assert candidates == []


def test_find_candidates_include_isolated_when_disabled():
    """Isolated failures included when skip_isolated=False."""
    reads = [_make_read(1, 1, 4), _failed(2), _make_read(3, 3, 4)]
    candidates = _find_candidates(reads, skip_isolated=False)
    assert candidates == [1]


def test_find_candidates_gap_edges():
    """Multi-page gap: first and last pages are selected."""
    reads = [
        _make_read(1, 1, 4),
        _failed(2),          # first in run
        _failed(3),
        _failed(4),          # last in run
        _make_read(5, 1, 4),
    ]
    candidates = _find_candidates(reads, skip_isolated=True)
    assert candidates == [1, 3]  # indices of pages 2 and 4


def test_find_candidates_two_page_gap():
    """Two-page gap: both pages are edges (first AND last)."""
    reads = [
        _make_read(1, 1, 4),
        _failed(2),          # first and last of run
        _failed(3),          # first and last of run
        _make_read(4, 4, 4),
    ]
    candidates = _find_candidates(reads, skip_isolated=True)
    assert candidates == [1, 2]


def test_find_candidates_all_failed():
    """All pages failed — first and last are edges."""
    reads = [_failed(1), _failed(2), _failed(3), _failed(4)]
    candidates = _find_candidates(reads, skip_isolated=True)
    assert candidates == [0, 3]


def test_find_candidates_no_failures():
    """No failures — empty result."""
    reads = [_make_read(1, 1, 3), _make_read(2, 2, 3), _make_read(3, 3, 3)]
    candidates = _find_candidates(reads, skip_isolated=True)
    assert candidates == []


def test_find_candidates_mixed_pattern():
    """Mix of isolated and multi-page gaps."""
    reads = [
        _make_read(1, 1, 4),
        _failed(2),           # isolated → skip
        _make_read(3, 3, 4),
        _failed(4),           # first in run
        _failed(5),
        _failed(6),           # last in run
        _make_read(7, 3, 4),
        _failed(8),           # isolated → skip
        _make_read(9, 1, 4),
    ]
    candidates = _find_candidates(reads, skip_isolated=True)
    assert candidates == [3, 5]  # indices of pages 4 and 6


# ── query_failed_pages tests ─────────────────────────────────────────────────

class MockProvider:
    """Mock VLM provider returning preset results per call index."""
    name = "mock"

    def __init__(self, results: dict[int, VLMResult] | None = None):
        self._results = results or {}
        self._default = VLMResult("", None, 0.0, 100.0, None)
        self.call_count = 0

    def query(self, image_path: str) -> VLMResult:
        idx = self.call_count
        self.call_count += 1
        return self._results.get(idx, self._default)


def _mock_fitz_and_clip():
    """Return patch context managers for fitz and _render_clip."""
    mock_doc = MagicMock()
    mock_doc.__getitem__ = MagicMock(return_value=MagicMock())
    mock_doc.__len__ = MagicMock(return_value=100)
    mock_clip = np.zeros((50, 100, 3), dtype=np.uint8)
    return (
        patch("core.vlm_resolver.fitz.open", return_value=mock_doc),
        patch("core.vlm_resolver._render_clip", return_value=mock_clip),
    )


def test_query_reads_successful_vlm():
    """Successful VLM read mutates the failed page."""
    reads = [
        _make_read(1, 1, 4),
        _failed(2),           # gap edge (first)
        _failed(3),           # gap edge (last)
        _make_read(4, 4, 4),
    ]
    provider = MockProvider({
        0: VLMResult("2/4", (2, 4), 0.85, 200.0, None),
        1: VLMResult("3/4", (3, 4), 0.85, 200.0, None),
    })

    p1, p2 = _mock_fitz_and_clip()
    with p1, p2:
        _, stats = query_failed_pages(
            reads, provider, "test.pdf",
            on_log=lambda m, l: None, skip_isolated=True,
        )

    assert stats["read"] == 2
    assert reads[1].curr == 2
    assert reads[1].total == 4
    assert reads[1].method == "inferred"
    assert reads[1].confidence == 0.45
    assert reads[2].curr == 3
    assert reads[2].method == "inferred"


def test_query_rejects_out_of_range():
    """VLM read with total > 10 is rejected by plausibility guard."""
    reads = [
        _make_read(1, 1, 4),
        _failed(2),
        _failed(3),
        _make_read(4, 4, 4),
    ]
    provider = MockProvider({
        0: VLMResult("2/15", (2, 15), 0.85, 200.0, None),
        1: VLMResult("3/4", (3, 4), 0.85, 200.0, None),
    })

    p1, p2 = _mock_fitz_and_clip()
    with p1, p2:
        _, stats = query_failed_pages(
            reads, provider, "test.pdf",
            on_log=lambda m, l: None, skip_isolated=True,
        )

    assert stats["read"] == 1
    assert stats["failed"] == 1
    assert reads[1].method == "failed"  # still failed (out of range)
    assert reads[2].method == "inferred"  # accepted as soft hypothesis


def test_query_handles_unparseable():
    """Unparseable VLM response leaves page as failed."""
    reads = [
        _make_read(1, 1, 4),
        _failed(2),
        _failed(3),
        _make_read(4, 4, 4),
    ]
    provider = MockProvider({
        0: VLMResult("no numbers here", None, 0.0, 200.0, None),
        1: VLMResult("3/4", (3, 4), 0.85, 200.0, None),
    })

    p1, p2 = _mock_fitz_and_clip()
    with p1, p2:
        _, stats = query_failed_pages(
            reads, provider, "test.pdf",
            on_log=lambda m, l: None, skip_isolated=True,
        )

    assert stats["failed"] == 1
    assert reads[1].method == "failed"


def test_query_handles_errors():
    """VLM errors are counted and page stays failed."""
    reads = [
        _make_read(1, 1, 4),
        _failed(2),
        _failed(3),
        _make_read(4, 4, 4),
    ]
    provider = MockProvider({
        0: VLMResult("", None, 0.0, 0.0, "timeout"),
        1: VLMResult("3/4", (3, 4), 0.85, 200.0, None),
    })

    p1, p2 = _mock_fitz_and_clip()
    with p1, p2:
        _, stats = query_failed_pages(
            reads, provider, "test.pdf",
            on_log=lambda m, l: None, skip_isolated=True,
        )

    assert stats["errors"] == 1
    assert stats["read"] == 1


def test_query_respects_cancel():
    """query_failed_pages stops when cancel_event is set."""
    reads = [_failed(1), _failed(2), _failed(3)]
    provider = MockProvider()
    cancel = threading.Event()
    cancel.set()

    mock_doc = MagicMock()
    mock_doc.__len__ = MagicMock(return_value=3)

    with patch("core.vlm_resolver.fitz.open", return_value=mock_doc):
        _, stats = query_failed_pages(
            reads, provider, "test.pdf",
            on_log=lambda m, l: None,
            cancel_event=cancel, skip_isolated=False,
        )

    assert stats["queried"] == 0


def test_query_no_candidates():
    """No failed pages → no queries, stats show zeros."""
    reads = [_make_read(1, 1, 3), _make_read(2, 2, 3), _make_read(3, 3, 3)]
    provider = MockProvider()

    _, stats = query_failed_pages(
        reads, provider, "test.pdf",
        on_log=lambda m, l: None,
    )

    assert stats["queried"] == 0
    assert stats["read"] == 0
