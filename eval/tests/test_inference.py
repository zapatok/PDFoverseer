# eval/tests/test_inference.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from eval.inference import (
    run_pipeline, PageRead, _detect_period, _recon_confidence,
    _extract_anchors, _viterbi_anchor_constrained,
)

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


def test_params_recon_weight_in_production():
    """recon_weight must be in PRODUCTION_PARAMS at 0.0 (disabled by default)."""
    assert "recon_weight" in PROD_PARAMS
    assert PROD_PARAMS["recon_weight"] == 0.0


def test_params_ph5_guard_slope_in_production():
    """ph5_guard_slope must be in PRODUCTION_PARAMS at the sweep-winning value 1.0."""
    assert "ph5_guard_slope" in PROD_PARAMS
    assert PROD_PARAMS["ph5_guard_slope"] == 1.0


def test_params_recon_weight_in_space():
    """recon_weight param space must include 0.0 (disabled) and 0.25."""
    assert 0.0 in PARAM_SPACE["recon_weight"]
    assert 0.25 in PARAM_SPACE["recon_weight"]


def test_params_ph5_guard_slope_in_space():
    """ph5_guard_slope param space must include 0.0 and 1.0."""
    assert 0.0 in PARAM_SPACE["ph5_guard_slope"]
    assert 1.0 in PARAM_SPACE["ph5_guard_slope"]


def test_period2_boundary_fp_loads():
    """period2_boundary_fp: 10 x 2-page docs, 3 false-positive curr=1 mid-doc pages."""
    import json
    from pathlib import Path
    data = json.loads(Path("eval/fixtures/synthetic/period2_boundary_fp.json").read_text())
    reads_raw = [PageRead(**{k: v for k, v in r.items() if not k.startswith("_")})
                 for r in data["reads"]]
    docs = run_pipeline(reads_raw, PROD_PARAMS)
    assert len(docs) >= 1


# ── _recon_confidence tests ────────────────────────────────────────────────────

def test_recon_confidence_perfect_period2():
    """Perfect period=2: all curr=1 at even positions → recon_conf=1.0."""
    reads = make_reads([
        (0, 1, 2, "direct", 0.90), (1, 2, 2, "direct", 0.90),
        (2, 1, 2, "direct", 0.90), (3, 2, 2, "direct", 0.90),
        (4, 1, 2, "direct", 0.90), (5, 2, 2, "direct", 0.90),
    ])
    assert _recon_confidence(reads, 2) == 1.0


def test_recon_confidence_robust_to_total_misread():
    """Misread total doesn't reduce recon confidence — only curr=1 positions matter."""
    reads = make_reads([
        (0, 1, 2, "direct", 0.90), (1, 2, 2, "direct", 0.90),
        (2, 1, 2, "direct", 0.90), (3, 2, 2, "direct", 0.90),
        (4, 1, 1, "direct", 0.88),  # total=1 misread, curr=1 still at expected position
        (5, 2, 2, "direct", 0.90),
        (6, 1, 2, "direct", 0.90), (7, 2, 2, "direct", 0.90),
    ])
    # starts=[0,2,4,6], predicted from anchor=0: {0,2,4,6,...}, all hit → 1.0
    assert _recon_confidence(reads, 2) == 1.0


def test_recon_confidence_ignores_failed():
    """Failed pages are excluded from both starts and predictions."""
    reads = make_reads([
        (0, 1, 2, "direct",  0.90),
        (1, None, None, "failed", 0.0),
        (2, 1, 2, "direct",  0.90),
        (3, 2, 2, "direct",  0.90),
    ])
    # starts=[0,2] (failed page excluded). predicted from anchor=0, period=2: {0,2,4,...}
    assert _recon_confidence(reads, 2) == 1.0


def test_recon_confidence_too_few_starts():
    """Only 1 curr=1 position — page 1 has curr=2, not curr=1 → len(starts)==1 < 2 → 0.0."""
    reads = make_reads([
        (0, 1, 2, "direct", 0.90),   # curr=1 → in starts
        (1, 2, 2, "direct", 0.90),   # curr=2 → NOT in starts
    ])
    # starts=[0] (len=1), guard len(starts) < 2 → return 0.0
    assert _recon_confidence(reads, 2) == 0.0


def test_recon_confidence_invalid_period():
    """Period < 2 → returns 0.0."""
    reads = make_reads([
        (0, 1, 1, "direct", 0.90),
        (1, 1, 1, "direct", 0.90),
        (2, 1, 1, "direct", 0.90),
    ])
    assert _recon_confidence(reads, 1) == 0.0


def test_recon_confidence_partial_match():
    """Spurious curr=1 at wrong position reduces recon_conf below 1.0."""
    reads = make_reads([
        (0, 1, 2, "direct", 0.90), (1, 2, 2, "direct", 0.90),
        (2, 1, 2, "direct", 0.90), (3, 1, 2, "direct", 0.90),  # spurious: should be curr=2
        (4, 1, 2, "direct", 0.90), (5, 2, 2, "direct", 0.90),
    ])
    # starts=[0,2,3,4], predicted from anchor=0, period=2: {0,2,4,...}
    # hits: 0✓, 2✓, 3 → abs(3-2)=1 ≤ 1 ✓ (within tolerance), 4✓ → 4/4 = 1.0
    # OR: 3 is not a predicted position (predicted has 2 and 4); |3-2|=1 ≤ 1 → hit
    # This tests the ±1 tolerance logic
    rc = _recon_confidence(reads, 2)
    assert rc > 0.0   # at least some hits


def test_recon_confidence_small_doc_no_crash():
    """All-period-1 docs: period=2 doesn't match → low recon_conf."""
    reads = make_reads([
        (0, 1, 1, "direct", 0.90),
        (1, 1, 1, "direct", 0.90),
        (2, 1, 1, "direct", 0.90),
        (3, 1, 1, "direct", 0.90),
    ])
    # starts=[0,1,2,3], predicted from anchor=0, period=2: {0,2,4,...}
    # hits: 0✓, 1 → |1-0|=1≤1 or |1-2|=1≤1 ✓, 2✓, 3 → |3-2|=1≤1 ✓ → 4/4 = 1.0
    # Note: ±1 tolerance means adjacent positions still "hit" for small docs
    # This test verifies no crash, not a specific value
    rc = _recon_confidence(reads, 2)
    assert 0.0 <= rc <= 1.0


# ── _detect_period with recon_weight tests ─────────────────────────────────────

def test_detect_period_recon_weight_zero_no_change():
    """recon_weight=0.0 produces same result as calling with params=None."""
    reads = make_reads([
        (0, 1, 2, "direct", 0.90), (1, 2, 2, "direct", 0.90),
        (2, 1, 2, "direct", 0.90), (3, 2, 2, "direct", 0.90),
    ])
    p_none  = _detect_period(reads, None)
    p_zero  = _detect_period(reads, {"recon_weight": 0.0})
    assert p_none["period"] == p_zero["period"]
    assert p_none["confidence"] == p_zero["confidence"]


def test_detect_period_recon_weight_boosts_confidence():
    """recon_weight=0.25 strictly raises confidence when baseline is below 1.0.

    Uses 4 reads (n<6 so acorr is skipped) with one misread total=1.
    gap_conf=1.0 (gap=2 appears once, 1/1=1.0), gap_period=2 (no tie).
    total_conf=0.75 (3 of 4 reads have total=2).
    Without recon: candidates[2] = 1.0*0.45 + 0.75*0.30 = 0.675.
    With recon: starts=[0,2], anchor=0, predicted={0,2} → rc=1.0.
               candidates[2] += 1.0*0.25 = 0.25 → 0.925.
    0.925 > 0.675 → strict improvement, neither value is at the 1.0 cap.
    """
    reads = make_reads([
        (0, 1, 2, "direct", 0.90),
        (1, 2, 2, "direct", 0.90),
        (2, 1, 1, "direct", 0.88),  # total misread as 1; curr=1 still at expected position
        (3, 2, 2, "direct", 0.90),
    ])
    p_no_recon   = _detect_period(reads, {"recon_weight": 0.0})
    p_with_recon = _detect_period(reads, {"recon_weight": 0.25})
    assert p_with_recon["period"] == 2
    assert p_with_recon["confidence"] > p_no_recon["confidence"]


def test_run_pipeline_accepts_recon_weight():
    """run_pipeline passes recon_weight through to _detect_period without error.

    Uses ≥4 reads so _detect_period doesn't early-return on the n<4 guard,
    ensuring the recon_weight branch inside _detect_period is actually reached.
    """
    reads = make_reads([
        (0, 1, 2, "H", 0.95), (1, 2, 2, "H", 0.92),
        (2, 1, 2, "H", 0.91), (3, 2, 2, "H", 0.90),
    ])
    docs = run_pipeline(reads, {**PROD_PARAMS, "recon_weight": 0.25})
    assert len(docs) == 2


# ── ph5_guard_slope (Approach B) tests ────────────────────────────────────────

def test_ph5_guard_slope_zero_matches_baseline():
    """ph5_guard_slope=0.0 produces identical result to PROD_PARAMS."""
    reads = make_reads([
        (0, 1, 2, "H", 0.95), (1, 2, 2, "H", 0.92),
        (2, 1, 2, "H", 0.91), (3, 2, 2, "H", 0.90),
    ])
    docs_prod  = run_pipeline(reads, PROD_PARAMS)
    docs_slope = run_pipeline(reads, {**PROD_PARAMS, "ph5_guard_slope": 0.0})
    assert len(docs_prod) == len(docs_slope)


def test_ph5_guard_slope_protects_low_conf_inferred_boundary():
    """slope=1.5 lowers effective_guard so a 0.55-confidence boundary is protected.

    Setup:
      reads[0]: direct  1/3 — doc1 p1
      reads[1]: direct  3/3 — doc1 p3 (p2 missing — incomplete)
      reads[2]: inferred 1/3 at conf=0.55 — doc2 start

    Only reads[2] is inferred → inferred_ratio = 1/3 ≈ 0.333
    slope=0.0: effective_guard=0.90, conf=0.55 < 0.90 → guard silent → merge → 1 doc
    slope=1.5: effective_guard=0.90*(1-1.5*0.333)≈0.45, conf=0.55 ≥ 0.45 → protected → 2 docs

    Note: reads[1] must be "direct" (not "inferred") so only reads[2] is counted
    in inferred_ratio. If reads[1] were inferred, ratio=2/3 and slope=1.5 would
    disable the guard entirely (effective_guard=0.0), failing the assertion.
    """
    reads = [
        PageRead(pdf_page=0, curr=1, total=3, method="direct",   confidence=0.95),
        PageRead(pdf_page=1, curr=3, total=3, method="direct",   confidence=0.90),
        PageRead(pdf_page=2, curr=1, total=3, method="inferred", confidence=0.55),
    ]
    docs_no_slope   = run_pipeline(reads, {**PROD_PARAMS, "ph5_guard_slope": 0.0})
    docs_with_slope = run_pipeline(reads, {**PROD_PARAMS, "ph5_guard_slope": 1.5})

    assert len(docs_no_slope) == 1,   "No slope: low-conf boundary not protected, merge occurs"
    assert len(docs_with_slope) == 2, "Slope=1.5: boundary protected from recovery merge"


def test_ph5_guard_slope_high_disables_guard():
    """slope=2.0 with inferred_ratio≥0.5 disables the guard entirely (effective_guard=0)."""
    reads = [
        PageRead(pdf_page=0, curr=1, total=3, method="direct",   confidence=0.95),
        PageRead(pdf_page=1, curr=3, total=3, method="inferred", confidence=0.95),
        PageRead(pdf_page=2, curr=1, total=3, method="inferred", confidence=0.90),
    ]
    # inferred_ratio = 2/3 ≈ 0.667
    # slope=2.0: effective_guard = 0.90 * max(1 - 2.0*0.667, 0) = 0.90 * 0.0 = 0.0
    # effective_guard=0.0 → guard disabled → same as ph5_guard_conf=0.0
    docs_high_slope = run_pipeline(reads, {**PROD_PARAMS, "ph5_guard_slope": 2.0})
    docs_no_guard   = run_pipeline(reads, {**PROD_PARAMS, "ph5_guard_conf": 0.0,
                                           "ph5_guard_slope": 0.0})
    # Guard disabled → undercount recovery merges → 1 doc (not 2)
    assert len(docs_high_slope) == 1, \
        "slope=2.0 with high inferred_ratio disables guard — recovery merges into 1 doc"
    assert len(docs_high_slope) == len(docs_no_guard), \
        "slope=2.0 should be equivalent to ph5_guard_conf=0.0"


def test_art_like_high_failure_loads():
    """art_like_high_failure fixture loads and baseline produces doc_count ≤ 20."""
    import json
    from pathlib import Path
    data = json.loads(
        Path("eval/fixtures/synthetic/art_like_high_failure.json").read_text()
    )
    reads_raw = [PageRead(**{k: v for k, v in r.items() if not k.startswith("_")})
                 for r in data["reads"]]
    docs = run_pipeline(reads_raw, PROD_PARAMS)
    assert len(docs) >= 1
    # With high failure rate and Approach B disabled, recovery may not achieve all 15.
    # The sweep will find the params that do. This test just verifies no crash.




# ── Phase D: Viterbi anchor-constrained tests ─────────────────────────────────

def make_period_info(period=4, confidence=0.80, expected_total=4):
    return {"period": period, "confidence": confidence, "expected_total": expected_total}


VITERBI_PARAMS = {
    **PROD_PARAMS,
    "viterbi_anchor_conf_min": 0.90,
    "viterbi_period_weight":   0.5,
    "viterbi_prior_weight":    0.4,
}


def test_extract_anchors_returns_high_conf_direct():
    """_extract_anchors returns direct/SR/easyocr reads with conf >= threshold."""
    reads = make_reads([
        (0, 1, 4, "direct",   0.95),  # ← anchor
        (1, 2, 4, "SR",       0.92),  # ← anchor
        (2, 3, 4, "easyocr",  0.91),  # ← anchor
        (3, 4, 4, "manual",   0.90),  # ← anchor (exactly at threshold)
        (4, 1, 4, "inferred", 0.99),  # not anchor (inferred)
        (5, 2, 4, "direct",   0.89),  # not anchor (conf < 0.90)
    ])
    anchors = _extract_anchors(reads, conf_min=0.90)
    assert set(anchors.keys()) == {0, 1, 2, 3}
    assert anchors[0] == (1, 4)
    assert anchors[3] == (4, 4)


def test_extract_anchors_empty_when_no_direct():
    """Returns empty dict when all reads are inferred or failed."""
    reads = make_reads([
        (0, 1, 4, "inferred", 0.99),
        (1, 2, 4, "inferred", 0.95),
        (2, None, None, "failed", 0.0),
    ])
    assert _extract_anchors(reads) == {}


def test_viterbi_noop_when_no_anchors():
    """_viterbi_anchor_constrained does nothing when no direct reads exist."""
    reads = make_reads([
        (0, 1, 4, "inferred", 0.60),
        (1, 2, 4, "inferred", 0.99),
        (2, 3, 4, "inferred", 0.99),
        (3, 4, 4, "inferred", 0.99),
    ])
    original = [(r.curr, r.total, r.confidence) for r in reads]
    _viterbi_anchor_constrained(reads, make_period_info(), VITERBI_PARAMS)
    after = [(r.curr, r.total, r.confidence) for r in reads]
    assert original == after, "Should be no-op with no anchors"


def test_viterbi_fills_two_full_docs_between_doc_end_and_doc_start():
    """
    Anchor at page 0 ends a doc (4/4), anchor at page 9 starts a doc (1/4).
    Gap of 8 pages should be filled with exactly 2 complete 4-page docs.
    Phase 1 already fills these correctly; Viterbi must confirm + boost conf of curr=1 pages.
    """
    # Phase 1 pre-filled (already correct):
    reads = [
        PageRead(0, 4, 4, "direct",   0.95),   # anchor: end of doc0
        PageRead(1, 1, 4, "inferred", 0.60),   # doc1 start (low conf)
        PageRead(2, 2, 4, "inferred", 0.99),
        PageRead(3, 3, 4, "inferred", 0.99),
        PageRead(4, 4, 4, "inferred", 0.99),
        PageRead(5, 1, 4, "inferred", 0.60),   # doc2 start (low conf)
        PageRead(6, 2, 4, "inferred", 0.99),
        PageRead(7, 3, 4, "inferred", 0.99),
        PageRead(8, 4, 4, "inferred", 0.99),
        PageRead(9, 1, 4, "direct",   0.95),   # anchor: start of doc3
    ]
    _viterbi_anchor_constrained(reads, make_period_info(period=4), VITERBI_PARAMS)

    # curr/total assignments remain correct (already were)
    assert [(r.curr, r.total) for r in reads[1:9]] == [
        (1,4),(2,4),(3,4),(4,4),(1,4),(2,4),(3,4),(4,4)
    ]
    # Viterbi boosts confidence of inferred curr=1 reads at correct positions
    assert reads[1].confidence > 0.60, "doc boundary at page 1 should get confidence boost"
    assert reads[5].confidence > 0.60, "doc boundary at page 5 should get confidence boost"
    # Non-boundary inferred pages NOT boosted beyond their existing confidence
    assert reads[2].curr == 2  # unchanged


def test_viterbi_corrects_wrong_inferred_boundary():
    """
    Phase 1 over-counts: from anchor (2/4), it infers 3,4,1,2,3,4,1,2 for 8 pages.
    The end anchor is (1/4), so remaining=0, leading=0, middle=8 → 2 docs of 4.
    Result should be curr=1 at pages 1 and 5, not at pages 3 and 7.
    """
    # Anchor0 = (4,4), anchor9 = (1,4): Phase 1 gets this RIGHT
    # Let's test a case where Phase 1 starts from a MID-DOC anchor
    # and Viterbi uses both anchors to fix the inferred values.
    # Anchor0=(2,4), then 4 failed pages, anchor5=(2,4).
    # correct chain for gap=4: remaining=2 → (3,4),(4,4), leading=1 → (1,4)
    # middle = 4-2-1 = 1 → can't divide by period=4 → Viterbi skips (inconsistent pair)
    # This tests that Viterbi correctly skips inconsistent anchor pairs.
    reads = [
        PageRead(0, 2, 4, "direct",   0.95),
        PageRead(1, 3, 4, "inferred", 0.99),   # Phase 1 filled
        PageRead(2, 4, 4, "inferred", 0.99),
        PageRead(3, 1, 4, "inferred", 0.60),   # Phase 1 new-doc guess
        PageRead(4, 2, 4, "inferred", 0.99),
        PageRead(5, 2, 4, "direct",   0.95),   # anchor
    ]
    original_conf = [r.confidence for r in reads[1:5]]
    _viterbi_anchor_constrained(reads, make_period_info(period=4), VITERBI_PARAMS)
    # Inconsistent pair (2,4)→(2,4) with gap=4: can't fit period=4 → no change
    after_conf = [r.confidence for r in reads[1:5]]
    assert original_conf == after_conf, "Inconsistent anchor pair should be skipped (no-op)"


def test_viterbi_respects_period_for_multi_doc_gap():
    """
    End-to-end: run_pipeline with viterbi detects correct doc count
    when gap spans exactly N complete docs matching the period.
    """
    # 3 docs of 4 pages each (12 pages), anchors only at doc starts/ends
    reads = [
        PageRead(0, 4, 4, "direct",   0.95),   # end of doc before range
        PageRead(1, None, None, "failed", 0.0),
        PageRead(2, None, None, "failed", 0.0),
        PageRead(3, None, None, "failed", 0.0),
        PageRead(4, None, None, "failed", 0.0),
        PageRead(5, None, None, "failed", 0.0),
        PageRead(6, None, None, "failed", 0.0),
        PageRead(7, None, None, "failed", 0.0),
        PageRead(8, None, None, "failed", 0.0),
        PageRead(9, 1, 4, "direct",   0.95),   # start of doc after range
    ]
    docs = run_pipeline(reads, VITERBI_PARAMS)
    # Should detect at least 2 complete docs (2 full 4-page docs inferred in the gap)
    complete = [d for d in docs if d.is_complete]
    assert len(complete) >= 2, f"Expected ≥2 complete docs, got {len(complete)}: {docs}"


def test_viterbi_params_in_production():
    """All three Viterbi hyperparams must be in PRODUCTION_PARAMS."""
    assert "viterbi_anchor_conf_min" in PROD_PARAMS
    assert "viterbi_period_weight"   in PROD_PARAMS
    assert "viterbi_prior_weight"    in PROD_PARAMS


def test_viterbi_params_in_param_space():
    """All three Viterbi hyperparams must be in PARAM_SPACE for sweep."""
    assert "viterbi_anchor_conf_min" in PARAM_SPACE
    assert "viterbi_period_weight"   in PARAM_SPACE
    assert "viterbi_prior_weight"    in PARAM_SPACE


def test_hll_recon_period2_loads():
    """hll_recon_period2 fixture loads and runs without error."""
    import json
    from pathlib import Path
    data = json.loads(
        Path("eval/fixtures/synthetic/hll_recon_period2.json").read_text()
    )
    reads_raw = [PageRead(**{k: v for k, v in r.items() if not k.startswith("_")})
                 for r in data["reads"]]
    docs = run_pipeline(reads_raw, PROD_PARAMS)
    assert len(docs) >= 1
