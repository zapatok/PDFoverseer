# eval/tests/test_sweep_scoring.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from eval.sweep import score_config
from eval.inference import PageRead, run_pipeline
from eval.params import PRODUCTION_PARAMS


def _real_fx(name, n_pages, curr=1, total=1):
    """Build a minimal real fixture with n_pages identical reads."""
    return {
        "name": name,
        "source": "real",
        "reads": [
            PageRead(pdf_page=i + 1, curr=curr, total=total,
                     method="direct", confidence=1.0)
            for i in range(n_pages)
        ],
    }


def _syn_fx(name, n_pages, curr=1, total=1):
    """Build a minimal synthetic fixture."""
    return {
        "name": name,
        "source": "synthetic",
        "reads": [
            PageRead(pdf_page=i + 1, curr=curr, total=total,
                     method="direct", confidence=1.0)
            for i in range(n_pages)
        ],
    }


def test_real_exact_scores_5():
    """Real fixture with exact doc count earns +5."""
    gt = {"r_ok": {"doc_count": 1, "complete_count": 1, "inferred_count": 0}}
    result = score_config(PRODUCTION_PARAMS, [_real_fx("r_ok", 1)], gt, set())
    assert result["composite_score"] == 5


def test_synthetic_exact_scores_5():
    """Synthetic fixture exact match earns +3 doc + +2 complete = 5."""
    gt = {"s_ok": {"doc_count": 1, "complete_count": 1, "inferred_count": 0}}
    result = score_config(PRODUCTION_PARAMS, [_syn_fx("s_ok", 1)], gt, set())
    assert result["composite_score"] == 5


def test_real_delta_penalizes_3_per_doc():
    """Real fixture off by 2 docs → penalty = 2 × 3 = -6."""
    # 3 pages each 1/1 → 3 docs; GT says 1 → delta = 2
    gt = {"r_bad": {"doc_count": 1, "complete_count": 1, "inferred_count": 0}}
    result = score_config(PRODUCTION_PARAMS, [_real_fx("r_bad", 3)], gt, set())
    assert result["composite_score"] == -6


def test_synthetic_delta_penalizes_1_per_doc():
    """Synthetic fixture off by 2 docs → penalty = 2 × 1 = -2."""
    gt = {"s_bad": {"doc_count": 1, "complete_count": 1, "inferred_count": 0}}
    result = score_config(PRODUCTION_PARAMS, [_syn_fx("s_bad", 3)], gt, set())
    # doc_delta=2: -2; complete_exact: 0 (doc count wrong); inf_delta: 0
    assert result["composite_score"] == -2


def test_real_wrong_complete_count_not_penalized():
    """Real fixture: wrong complete_count in GT does not affect score."""
    gt = {"r_comp": {"doc_count": 1, "complete_count": 999, "inferred_count": 0}}
    result = score_config(PRODUCTION_PARAMS, [_real_fx("r_comp", 1)], gt, set())
    # Only doc_exact +5 — complete_count irrelevant for real fixtures
    assert result["composite_score"] == 5


def test_regression_penalizes_5():
    """Fixture that was passing but now fails → -5 regression."""
    gt = {"r_reg": {"doc_count": 1, "complete_count": 1, "inferred_count": 0}}
    fx = [_real_fx("r_reg", 3)]  # 3 docs, GT=1 → fails
    result = score_config(PRODUCTION_PARAMS, fx, gt, baseline_passes={"r_reg"})
    # delta penalty + regression: -6 - 5 = -11
    assert result["composite_score"] == -11
