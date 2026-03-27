"""
Tests for core.vlm_resolver — candidate selection, validation, mock provider.
No real VLM calls — uses mock provider.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from core.utils import InferenceIssue, _PageRead
from core.vlm_provider import VLMResult
from core.vlm_resolver import _should_accept


def _make_read(page, curr, total, method="direct", confidence=1.0):
    return _PageRead(pdf_page=page, curr=curr, total=total,
                     method=method, confidence=confidence)


def _failed(page):
    return _PageRead(pdf_page=page, curr=None, total=None,
                     method="failed", confidence=0.0)


# ── _should_accept tests ─────────────────────────────────────────────────────

def test_reject_unparseable():
    """Reject VLM result with no parsed value."""
    reads = [_make_read(1, 1, 3), _failed(2), _make_read(3, 3, 3)]
    result = VLMResult("garbage", None, 0.0, 100.0, None)
    assert _should_accept(result, 1, reads, {}) is False


def test_reject_contradicts_period():
    """Reject when VLM total contradicts strong period."""
    reads = [_make_read(1, 1, 3), _failed(2), _make_read(3, 3, 3)]
    period_info = {"period": 3, "confidence": 0.8, "expected_total": 3}
    result = VLMResult("2/5", (2, 5), 0.85, 100.0, None)
    assert _should_accept(result, 1, reads, period_info) is False


def test_accept_matches_period():
    """Accept when VLM read matches period total."""
    reads = [_make_read(1, 1, 3), _failed(2), _make_read(3, 3, 3)]
    period_info = {"period": 3, "confidence": 0.8, "expected_total": 3}
    result = VLMResult("2/3", (2, 3), 0.85, 100.0, None)
    assert _should_accept(result, 1, reads, period_info) is True


def test_accept_sequential_with_prev():
    """Accept when VLM read is sequential with previous page."""
    reads = [_make_read(1, 1, 4), _make_read(2, 2, 4), _failed(3), _make_read(4, 4, 4)]
    result = VLMResult("3/4", (3, 4), 0.85, 100.0, None)
    assert _should_accept(result, 2, reads, {}) is True


def test_accept_new_doc_after_complete():
    """Accept curr=1 when previous page is last of its document."""
    reads = [_make_read(1, 1, 2), _make_read(2, 2, 2), _failed(3)]
    result = VLMResult("1/3", (1, 3), 0.85, 100.0, None)
    assert _should_accept(result, 2, reads, {}) is True


def test_reject_contradicts_neighbor():
    """Reject when VLM curr=1 but previous is mid-document."""
    reads = [_make_read(1, 1, 4), _make_read(2, 2, 4), _failed(3)]
    result = VLMResult("1/4", (1, 4), 0.85, 100.0, None)
    assert _should_accept(result, 2, reads, {}) is False


def test_accept_confirms_existing():
    """Accept when VLM confirms existing low-confidence read."""
    reads = [
        _make_read(1, 1, 3),
        _PageRead(pdf_page=2, curr=2, total=3, method="inferred", confidence=0.40),
        _make_read(3, 3, 3),
    ]
    result = VLMResult("2/3", (2, 3), 0.85, 100.0, None)
    assert _should_accept(result, 1, reads, {}) is True


def test_reject_low_vlm_confidence():
    """Reject when VLM parser confidence is below minimum."""
    reads = [_make_read(1, 1, 3), _failed(2), _make_read(3, 3, 3)]
    result = VLMResult("numbers 2 3", (2, 3), 0.40, 100.0, None)
    assert _should_accept(result, 1, reads, {}) is False


def test_accept_no_period_gap_fill():
    """Accept gap fill when no period info and sequential."""
    reads = [_make_read(1, 1, 4), _failed(2), _make_read(3, 3, 4)]
    result = VLMResult("2/4", (2, 4), 0.85, 100.0, None)
    assert _should_accept(result, 1, reads, {}) is True


import threading  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

import numpy as np  # noqa: E402

from core.vlm_resolver import ISSUE_PRIORITY, resolve  # noqa: E402


class MockProvider:
    """Mock VLM provider that returns preset results per call index."""
    name = "mock"

    def __init__(self, results: dict[int, VLMResult] | None = None):
        self._results = results or {}
        self._default = VLMResult("", None, 0.0, 100.0, None)
        self.call_count = 0

    def query(self, image_path: str) -> VLMResult:
        idx = self.call_count
        self.call_count += 1
        return self._results.get(idx, self._default)


def test_resolve_no_issues():
    """resolve() with empty issues returns unchanged reads."""
    reads = [_make_read(1, 1, 3), _make_read(2, 2, 3), _make_read(3, 3, 3)]
    provider = MockProvider()
    logs = []

    with patch("core.vlm_resolver.fitz"):
        result, stats = resolve(
            reads, [], 3, provider, "test.pdf", {},
            on_log=lambda m, l: logs.append(m),
        )

    assert stats["total"] == 0
    assert stats["accepted"] == 0


def test_resolve_accepts_valid_read():
    """resolve() accepts a VLM read that passes validation."""
    reads = [
        _make_read(1, 1, 3),
        _failed(2),
        _make_read(3, 3, 3),
    ]
    issues = [InferenceIssue(pdf_page=2, issue_type="gap", confidence=0.0, context="test")]
    provider = MockProvider({0: VLMResult("2/3", (2, 3), 0.85, 100.0, None)})
    logs = []

    mock_doc = MagicMock()
    mock_page = MagicMock()
    mock_doc.__getitem__ = MagicMock(return_value=mock_page)
    mock_doc.__len__ = MagicMock(return_value=3)
    mock_clip = np.zeros((50, 100, 3), dtype=np.uint8)

    with patch("core.vlm_resolver.fitz.open", return_value=mock_doc), \
         patch("core.vlm_resolver._render_clip", return_value=mock_clip):
        result, stats = resolve(
            reads, issues, 3, provider, "test.pdf", {},
            on_log=lambda m, l: logs.append(m),
        )

    assert stats["accepted"] == 1
    assert reads[1].curr == 2
    assert reads[1].total == 3
    assert reads[1].method == "vlm_mock"


def test_resolve_rejects_contradicting_read():
    """resolve() rejects a VLM read that contradicts neighbors."""
    reads = [
        _make_read(1, 1, 4),
        _make_read(2, 2, 4),
        _failed(3),
    ]
    issues = [InferenceIssue(pdf_page=3, issue_type="gap", confidence=0.0, context="test")]
    provider = MockProvider({0: VLMResult("1/4", (1, 4), 0.85, 100.0, None)})
    logs = []

    mock_doc = MagicMock()
    mock_page = MagicMock()
    mock_doc.__getitem__ = MagicMock(return_value=mock_page)
    mock_doc.__len__ = MagicMock(return_value=3)
    mock_clip = np.zeros((50, 100, 3), dtype=np.uint8)

    with patch("core.vlm_resolver.fitz.open", return_value=mock_doc), \
         patch("core.vlm_resolver._render_clip", return_value=mock_clip):
        result, stats = resolve(
            reads, issues, 3, provider, "test.pdf", {},
            on_log=lambda m, l: logs.append(m),
        )

    assert stats["rejected"] == 1
    assert reads[2].method == "failed"


def test_resolve_respects_cancel_event():
    """resolve() stops when cancel_event is set."""
    reads = [_failed(1), _failed(2), _failed(3)]
    issues = [
        InferenceIssue(pdf_page=i, issue_type="gap", confidence=0.0, context="test")
        for i in [1, 2, 3]
    ]
    provider = MockProvider()
    cancel = threading.Event()
    cancel.set()

    mock_doc = MagicMock()
    mock_doc.__len__ = MagicMock(return_value=3)

    with patch("core.vlm_resolver.fitz.open", return_value=mock_doc):
        _, stats = resolve(
            reads, issues, 3, provider, "test.pdf", {},
            on_log=lambda m, l: None,
            cancel_event=cancel,
        )

    assert stats["total"] == 0


def test_resolve_priority_ordering():
    """resolve() processes boundary_inferred before gap."""
    reads = [
        _failed(1),
        _PageRead(pdf_page=2, curr=1, total=3, method="inferred", confidence=0.50),
        _failed(3),
    ]
    issues = [
        InferenceIssue(pdf_page=3, issue_type="gap", confidence=0.0, context="test"),
        InferenceIssue(pdf_page=2, issue_type="boundary_inferred", confidence=0.50, context="test"),
    ]
    log_messages = []

    class TrackingProvider:
        name = "mock"
        def query(self, path):
            return VLMResult("", None, 0.0, 100.0, None)

    mock_doc = MagicMock()
    mock_page = MagicMock()
    mock_doc.__getitem__ = MagicMock(return_value=mock_page)
    mock_doc.__len__ = MagicMock(return_value=3)
    mock_clip = np.zeros((50, 100, 3), dtype=np.uint8)

    with patch("core.vlm_resolver.fitz.open", return_value=mock_doc), \
         patch("core.vlm_resolver._render_clip", return_value=mock_clip):
        resolve(
            reads, issues, 3, TrackingProvider(), "test.pdf", {},
            on_log=lambda m, l: log_messages.append(m),
        )

    # Extract the order pages were processed from VLM log messages
    page_order = [
        int(msg.split("VLM p")[1].split(":")[0])
        for msg in log_messages
        if "VLM p" in msg and msg.startswith("  VLM p")
    ]
    # boundary_inferred (pdf_page=2) should be processed before gap (pdf_page=3)
    assert len(page_order) == 2
    assert page_order[0] == 2  # boundary_inferred first
    assert page_order[1] == 3  # gap second
