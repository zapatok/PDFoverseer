import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.analyzer import Document, _PageRead, _build_documents, classify_doc

def _make_read(page, curr, total, method="direct", confidence=1.0):
    return _PageRead(pdf_page=page, curr=curr, total=total,
                     method=method, confidence=confidence)

def test_classify_doc_direct():
    """Doc with all direct reads → 'direct' tier."""
    reads = [_make_read(1, 1, 2, "direct"), _make_read(2, 2, 2, "direct")]
    docs = _build_documents(reads, lambda m, l: None, lambda p, k, d: None)
    rmap = {r.pdf_page: r for r in reads}
    assert len(docs) == 1
    assert docs[0].is_complete
    assert classify_doc(docs[0], rmap) == "direct"

def test_classify_doc_inferred_hi():
    """Doc complete with inferred pages, all conf >= 0.75 → 'inferred_hi'."""
    reads = [_make_read(1, 1, 2, "direct"), _make_read(2, 2, 2, "inferred", 0.80)]
    docs = _build_documents(reads, lambda m, l: None, lambda p, k, d: None)
    rmap = {r.pdf_page: r for r in reads}
    assert len(docs) == 1
    assert classify_doc(docs[0], rmap) == "inferred_hi"

def test_classify_doc_inferred_lo():
    """Doc complete with inferred pages, min conf < 0.75 → 'inferred_lo'."""
    reads = [_make_read(1, 1, 2, "direct"), _make_read(2, 2, 2, "inferred", 0.50)]
    docs = _build_documents(reads, lambda m, l: None, lambda p, k, d: None)
    rmap = {r.pdf_page: r for r in reads}
    assert len(docs) == 1
    assert classify_doc(docs[0], rmap) == "inferred_lo"

def test_classify_doc_incomplete():
    """Doc missing pages → 'incomplete'."""
    d = Document(index=1, start_pdf_page=1, declared_total=3,
                 pages=[1, 2], inferred_pages=[])
    assert classify_doc(d, {}) == "incomplete"

def test_classify_doc_boundary_0_75():
    """Exactly 0.75 confidence → 'inferred_hi' (threshold is >=)."""
    reads = [_make_read(1, 1, 2, "direct"), _make_read(2, 2, 2, "inferred", 0.75)]
    docs = _build_documents(reads, lambda m, l: None, lambda p, k, d: None)
    rmap = {r.pdf_page: r for r in reads}
    assert classify_doc(docs[0], rmap) == "inferred_hi"
