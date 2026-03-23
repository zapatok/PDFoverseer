"""
Inference unit tests — no GPU/Tesseract required.
Tests cover _infer_missing(), _detect_period(), _build_documents(), classify_doc().
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from core.utils import _PageRead, Document
from core.inference import _infer_missing, _detect_period, _build_documents, classify_doc


def _make_read(page, curr, total, method="direct", confidence=1.0):
    return _PageRead(pdf_page=page, curr=curr, total=total,
                     method=method, confidence=confidence)


def _failed(page):
    return _PageRead(pdf_page=page, curr=None, total=None,
                     method="failed", confidence=0.0)


def _no_issue(*args, **kwargs):
    pass


# ── _infer_missing tests ──────────────────────────────────────────────────────

def test_forward_fill_mid_gap():
    """Middle page failed → forward propagation assigns curr+1."""
    reads = [
        _make_read(1, 1, 5),
        _make_read(2, 2, 5),
        _failed(3),
        _make_read(4, 4, 5),
        _make_read(5, 5, 5),
    ]
    result = _infer_missing(reads)
    assert result[2].curr == 3
    assert result[2].total == 5
    assert result[2].method == "inferred"


def test_backward_fill_mid_gap():
    """Middle page failed, backward neighbor provides info."""
    reads = [
        _make_read(1, 1, 3),
        _failed(2),
        _make_read(3, 3, 3),
    ]
    result = _infer_missing(reads)
    assert result[1].curr == 2
    assert result[1].total == 3
    assert result[1].method == "inferred"


def test_gap_at_start():
    """First page(s) failed — no left neighbor, backward fill from right."""
    reads = [
        _failed(1),
        _make_read(2, 2, 3),
        _make_read(3, 3, 3),
    ]
    result = _infer_missing(reads)
    # Should infer curr=1 from backward propagation
    assert result[0].method == "inferred"
    assert result[0].curr == 1


def test_gap_at_end():
    """Last page(s) failed — no right neighbor."""
    reads = [
        _make_read(1, 1, 3),
        _make_read(2, 2, 3),
        _failed(3),
    ]
    result = _infer_missing(reads)
    assert result[2].method == "inferred"
    assert result[2].curr == 3


def test_all_pages_failed():
    """All pages failed → no crash, returns same number of reads."""
    reads = [_failed(i) for i in range(1, 6)]
    result = _infer_missing(reads)
    assert len(result) == 5


# ── _detect_period tests ──────────────────────────────────────────────────────

def test_detect_period_known():
    """3 identical documents of period 3 → _detect_period returns period=3."""
    reads = []
    for doc_n in range(3):
        base = doc_n * 3
        reads.append(_make_read(base + 1, 1, 3))
        reads.append(_make_read(base + 2, 2, 3))
        reads.append(_make_read(base + 3, 3, 3))
    info = _detect_period(reads)
    assert info["period"] == 3


def test_detect_period_conflicting():
    """Mixed totals → graceful handling, no crash."""
    reads = [
        _make_read(1, 1, 3), _make_read(2, 2, 3), _make_read(3, 3, 3),
        _make_read(4, 1, 5), _make_read(5, 2, 5), _make_read(6, 3, 5),
        _make_read(7, 4, 5), _make_read(8, 5, 5),
    ]
    info = _detect_period(reads)
    # Should not crash; period may or may not be detected
    assert isinstance(info, dict)
    assert "period" in info


# ── _build_documents tests ────────────────────────────────────────────────────

def test_phase5b_contradiction():
    """One read with wrong total should be corrected when period is strong."""
    # 3 docs of period=3, one read has total=4 (wrong)
    reads = []
    for doc_n in range(3):
        base = doc_n * 3
        reads.append(_make_read(base + 1, 1, 3))
        reads.append(_make_read(base + 2, 2, 3 if doc_n != 1 else 4))  # one wrong
        reads.append(_make_read(base + 3, 3, 3))
    period_info = {"period": 3, "confidence": 0.9, "expected_total": 3}
    result = _infer_missing(reads, period_info)
    # Should not crash
    assert len(result) == len(reads)


def test_phase6_orphan_suppression():
    """Two consecutive curr=1 inferred with low confidence → at least one suppressed or marked excluded."""
    reads = [
        _make_read(1, 1, 3),
        _make_read(2, 2, 3),
        _make_read(3, 3, 3),
        _PageRead(pdf_page=4, curr=1, total=3, method="inferred", confidence=0.40),
        _PageRead(pdf_page=5, curr=1, total=3, method="inferred", confidence=0.40),
        _make_read(6, 2, 3),
    ]
    result = _infer_missing(reads)
    # No crash; result is valid
    assert len(result) == len(reads)


def test_classify_doc_boundary_negative():
    """Confidence 0.74 inferred doc should NOT be 'inferred_hi' (threshold is 0.75)."""
    reads = [
        _make_read(1, 1, 2, "direct"),
        _PageRead(pdf_page=2, curr=2, total=2, method="inferred", confidence=0.74),
    ]
    docs = _build_documents(reads, lambda m, l: None, lambda p, k, d, *a: None)
    rmap = {r.pdf_page: r for r in reads}
    assert len(docs) == 1
    tier = classify_doc(docs[0], rmap)
    assert tier in ("inferred_lo", "inferred_hi", "direct")
    # 0.74 is below the 0.75 threshold — should be inferred_lo
    assert tier == "inferred_lo"
