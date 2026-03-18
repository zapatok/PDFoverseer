# eval/tests/test_inference.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from eval.inference import run_pipeline, PageRead, _detect_period

from eval.params import PRODUCTION_PARAMS as PROD_PARAMS, PARAM_SPACE


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
    Phase 5b is now enabled in PRODUCTION_PARAMS (ph5b_conf_min=0.69).
    Expected result with production params: 31 docs (all corrected to 1/1)."""
    specs = [(i, 1, 1, "direct", 0.90) for i in range(29)]
    specs.append((29, 1, 4, "direct", 0.85))  # OCR misread
    specs.append((30, 2, 4, "direct", 0.85))  # OCR misread
    reads = make_reads(specs)

    # With Phase 5b enabled (production defaults)
    docs_5b = run_pipeline(reads, PROD_PARAMS)
    assert len(docs_5b) == 31, f"With 5b expected 31 docs, got {len(docs_5b)}"
    assert all(d.is_complete for d in docs_5b)

    # Without Phase 5b explicitly disabled
    disabled_params = {**PROD_PARAMS, "ph5b_conf_min": 0.0}
    docs_no_5b = run_pipeline(reads, disabled_params)
    assert len(docs_no_5b) == 30, f"Without 5b expected 30 docs, got {len(docs_no_5b)}"


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


def test_ph5b_enabled_in_production():
    """PRODUCTION_PARAMS has ph5b_conf_min=0.69 (sweep-tuned to enable Phase 5b)."""
    assert PROD_PARAMS["ph5b_conf_min"] == 0.69


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


def test_params_ph5_guard_conf_in_prod():
    """ph5_guard_conf must be in PRODUCTION_PARAMS with sweep-tuned value 0.90."""
    assert "ph5_guard_conf" in PROD_PARAMS
    assert PROD_PARAMS["ph5_guard_conf"] == 0.90


def test_params_ph5b_conf_min_has_040():
    """ph5b_conf_min param space must include 0.40 to cover HLL's ~43% period confidence."""
    assert 0.40 in PARAM_SPACE["ph5b_conf_min"]


def test_params_min_conf_locked():
    """min_conf_for_new_doc must be locked to [0.0] — no sweep needed (binary tradeoff)."""
    assert PARAM_SPACE["min_conf_for_new_doc"] == [0.0]


def test_ph5_guard_baseline_no_change():
    """ph5_guard_conf=0.0 (disabled) produces identical result to PRODUCTION_PARAMS."""
    reads = make_reads([
        (0, 1, 2, "H", 0.95), (1, 2, 2, "H", 0.92),
        (2, 1, 2, "H", 0.91), (3, 2, 2, "H", 0.90),
    ])
    docs_prod  = run_pipeline(reads, PROD_PARAMS)
    docs_guard = run_pipeline(reads, {**PROD_PARAMS, "ph5_guard_conf": 0.0})
    assert len(docs_prod) == len(docs_guard)


def test_ph5_guard_protects_inferred_boundary():
    """With guard enabled, high-conf inferred curr=1 is NOT merged by undercount recovery.

    Setup:
      reads[0]: pdf=0, confirmed 1/3  — doc1 start
      reads[1]: pdf=1, pre-set inferred 3/3 — doc1 "last page" (inconsistent sequence
                with reads[0]; Phase 3 caps its confidence to xval_cap but keeps it
                in doc1.inferred_pages. doc1: declared=3, pages=[0], inferred=[1],
                found_total=2, missing=1.)
      reads[2]: pdf=2, pre-set inferred 1/3 at conf=0.90 — doc2 start.
                Consistent with reads[1] (prev.curr==prev.total → new-doc start valid).
                Phase 3 does NOT cap it. Confidence stays 0.90.

    doc2: declared=3, pages=[], inferred=[2], found_total=1.
    Undercount recovery condition: missing(1) >= found_total(1), declared match.
    Current guard: reads[2].method=="inferred" → has_confirmed_start=False → merge fires.
    New guard (ph5_guard_conf=0.80): reads[2].conf(0.90) >= 0.80 → protected → no merge.
    """
    reads = [
        PageRead(pdf_page=0, curr=1, total=3, method="direct",   confidence=0.95),
        PageRead(pdf_page=1, curr=3, total=3, method="inferred", confidence=0.95),
        PageRead(pdf_page=2, curr=1, total=3, method="inferred", confidence=0.90),
    ]
    docs_no_guard   = run_pipeline(reads, {**PROD_PARAMS, "ph5_guard_conf": 0.0})
    docs_with_guard = run_pipeline(reads, {**PROD_PARAMS, "ph5_guard_conf": 0.80})

    assert len(docs_no_guard)   == 1, "Without guard: over-merge expected (recovery fires)"
    assert len(docs_with_guard) == 2, "With guard: boundary preserved (recovery blocked)"


def test_period2_low_conf_loads():
    """period2_low_conf fixture loads and runs without error."""
    import json
    from pathlib import Path
    data = json.loads(Path("eval/fixtures/synthetic/period2_low_conf.json").read_text())
    reads_raw = [PageRead(**{k: v for k, v in r.items() if not k.startswith("_")})
                 for r in data["reads"]]
    docs = run_pipeline(reads_raw, PROD_PARAMS)
    assert len(docs) >= 1


def test_period2_noisy_splits_loads():
    """period2_noisy_splits fixture loads and runs without error."""
    import json
    from pathlib import Path
    data = json.loads(Path("eval/fixtures/synthetic/period2_noisy_splits.json").read_text())
    reads_raw = [PageRead(**{k: v for k, v in r.items() if not k.startswith("_")})
                 for r in data["reads"]]
    docs = run_pipeline(reads_raw, PROD_PARAMS)
    assert len(docs) >= 1


def test_mixed_1_2_dense_loads():
    """mixed_1_2_dense: 30 docs alternating 1-page and 2-page, all clean reads."""
    import json
    from pathlib import Path
    data = json.loads(Path("eval/fixtures/synthetic/mixed_1_2_dense.json").read_text())
    reads_raw = [PageRead(**{k: v for k, v in r.items() if not k.startswith("_")})
                 for r in data["reads"]]
    docs = run_pipeline(reads_raw, PROD_PARAMS)
    assert len(docs) >= 1


def test_period2_boundary_fp_loads():
    """period2_boundary_fp: 10 x 2-page docs, 3 false-positive curr=1 mid-doc pages."""
    import json
    from pathlib import Path
    data = json.loads(Path("eval/fixtures/synthetic/period2_boundary_fp.json").read_text())
    reads_raw = [PageRead(**{k: v for k, v in r.items() if not k.startswith("_")})
                 for r in data["reads"]]
    docs = run_pipeline(reads_raw, PROD_PARAMS)
    assert len(docs) >= 1
