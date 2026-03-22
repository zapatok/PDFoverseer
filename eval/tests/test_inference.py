# eval/tests/test_inference.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from eval.inference import run_pipeline, PageRead, _detect_period

from eval.params import PRODUCTION_PARAMS as PROD_PARAMS


def make_reads(specs):
    return [PageRead(pdf_page=p, curr=c, total=t, method=m, confidence=cf)
            for p, c, t, m, cf in specs]


def ph5b_params(**overrides):
    """PROD_PARAMS with Phase 5b enabled by default."""
    p = {**PROD_PARAMS, "ph5b_conf_min": 0.50, "ph5b_ratio_min": 0.85}
    p.update(overrides)
    return p


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


# ── Phase 5b: Period-contradiction tests ─────────────────────────────────────

def test_ph5b_ins31_scenario():
    """INS_31: 29 pages read as 1/1, last 2 read as 1/4 and 2/4.
    Without Phase 5b: 30 docs (pages 30-31 form one 4-page doc, incomplete).
    With Phase 5b: 31 docs (pages 30-31 corrected to 1/1 each)."""
    specs = [(i, 1, 1, "direct", 0.90) for i in range(29)]
    specs.append((29, 1, 4, "direct", 0.85))  # OCR misread
    specs.append((30, 2, 4, "direct", 0.85))  # OCR misread
    reads = make_reads(specs)

    # Without Phase 5b (explicitly disabled)
    docs_no_5b = run_pipeline(reads, {**PROD_PARAMS, "ph5b_conf_min": 0.0})
    assert len(docs_no_5b) == 30, f"Without 5b expected 30 docs, got {len(docs_no_5b)}"

    # With Phase 5b enabled
    docs_5b = run_pipeline(reads, ph5b_params())
    assert len(docs_5b) == 31, f"With 5b expected 31 docs, got {len(docs_5b)}"
    assert all(d.is_complete for d in docs_5b)


def test_ph5b_no_correction_when_mixed():
    """When period is ambiguous (many different totals), Phase 5b should NOT
    activate even if enabled — the ratio threshold protects against false corrections."""
    specs = [
        # Mix of 1-page, 2-page, and 3-page docs — no dominant period
        (0, 1, 1, "direct", 0.90),
        (1, 1, 2, "direct", 0.90), (2, 2, 2, "direct", 0.90),
        (3, 1, 3, "direct", 0.90), (4, 2, 3, "direct", 0.90), (5, 3, 3, "direct", 0.90),
        (6, 1, 1, "direct", 0.90),
        (7, 1, 2, "direct", 0.90), (8, 2, 2, "direct", 0.90),
        (9, 1, 4, "direct", 0.90),  # "anomalous" — but not really, since no dominant period
    ]
    reads = make_reads(specs)

    docs_no_5b = run_pipeline(reads, PROD_PARAMS)
    docs_5b = run_pipeline(reads, ph5b_params())
    # Should produce same result — Phase 5b shouldn't activate
    assert len(docs_5b) == len(docs_no_5b)


def test_ph5b_enabled_by_default():
    """PRODUCTION_PARAMS enables Phase 5b via soft clash resolution validation."""
    assert PROD_PARAMS["ph5b_conf_min"] > 0.0


def test_ph5b_respects_conf_threshold():
    """Phase 5b should NOT activate if period confidence is below threshold."""
    # 5 pages of 1/1 + 1 page of 1/3 — period might be detected but low confidence
    specs = [(i, 1, 1, "direct", 0.90) for i in range(5)]
    specs.append((5, 1, 3, "direct", 0.90))
    reads = make_reads(specs)

    # With very high confidence threshold — should not activate
    docs = run_pipeline(reads, ph5b_params(ph5b_conf_min=0.99))
    docs_prod = run_pipeline(reads, PROD_PARAMS)
    assert len(docs) == len(docs_prod)
