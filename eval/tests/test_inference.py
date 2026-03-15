# eval/tests/test_inference.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from eval.inference import run_pipeline, PageRead

PROD_PARAMS = {
    "fwd_conf": 0.95, "new_doc_base": 0.60, "new_doc_hom_mul": 0.30,
    "back_conf": 0.90, "xval_cap": 0.50,
    "fallback_base": 0.40, "fallback_hom_base": 0.30, "fallback_hom_mul": 0.20,
    "ds_boost_max": 0.25,
    "window": 5, "hom_threshold": 0.85,
}


def make_reads(specs):
    return [PageRead(pdf_page=p, curr=c, total=t, method=m, confidence=cf)
            for p, c, t, m, cf in specs]


def test_simple_two_doc():
    """Two 2-page docs, no inference needed."""
    reads = make_reads([
        (0, 1, 2, "H", 0.95), (1, 2, 2, "H", 0.92),
        (2, 1, 2, "H", 0.91), (3, 2, 2, "H", 0.90),
    ])
    docs = run_pipeline(reads, PROD_PARAMS)
    assert len(docs) == 2
    assert all(d.is_complete for d in docs)


def test_infer_missing_middle():
    """Page 1 is failed; should be inferred from neighbors."""
    reads = make_reads([
        (0, 1, 3, "H", 0.95),
        (1, None, None, "failed", 0.0),
        (2, 3, 3, "H", 0.90),
    ])
    docs = run_pipeline(reads, PROD_PARAMS)
    assert len(docs) == 1
    assert docs[0].declared_total == 3
    assert docs[0].found_total == 3


def test_metrics_complete_count():
    """Sanity: complete_count via is_complete."""
    reads = make_reads([
        (0, 1, 2, "H", 0.95), (1, 2, 2, "H", 0.92),   # complete
        (2, 1, 3, "H", 0.90),                            # incomplete (only 1 of 3)
    ])
    docs = run_pipeline(reads, PROD_PARAMS)
    complete = sum(1 for d in docs if d.is_complete)
    assert complete == 1


def test_inferred_count():
    """inferred_count = pages assigned by inference, counted once."""
    reads = make_reads([
        (0, 1, 2, "H", 0.95),
        (1, None, None, "failed", 0.0),
    ])
    docs = run_pipeline(reads, PROD_PARAMS)
    inferred = sum(len(d.inferred_pages) for d in docs)
    assert inferred == 1
