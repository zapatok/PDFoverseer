import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from eval.graph_inference import build_state_space, PageRead, Document, compute_log_emission
import math


def test_state_space_max_total_3():
    """max_total=3 → states: (1,1),(1,2),(2,2),(1,3),(2,3),(3,3) + NULL."""
    states, idx = build_state_space(max_total=3)
    # 1+2+3 = 6 real states + NULL
    assert len(states) == 7
    assert states[0] is None  # NULL state at index 0
    assert (1, 1) in states
    assert (3, 3) in states
    assert idx[(1, 1)] >= 1
    assert idx[None] == 0


def test_state_space_max_total_30():
    """max_total=30 → 30*31/2 = 465 real states + NULL = 466."""
    states, idx = build_state_space(max_total=30)
    assert len(states) == 466


def test_emit_exact_match_high_conf():
    """Exact OCR match with high confidence → highest log probability."""
    params = {
        "emit_match": 0.90, "emit_conf_scale": 1.0,
        "emit_partial": 0.10, "emit_null": 0.3, "max_total": 5,
    }
    read = PageRead(0, curr=2, total=3, method="direct", confidence=0.95)
    # State (2,3) should get highest emission
    log_p_match = compute_log_emission(read, (2, 3), params)
    log_p_partial = compute_log_emission(read, (1, 3), params)  # same total, diff curr
    log_p_diff = compute_log_emission(read, (2, 5), params)     # different total
    assert log_p_match > log_p_partial
    assert log_p_partial > log_p_diff


def test_emit_null_observation():
    """Failed read → uniform-ish emission (no information)."""
    params = {
        "emit_match": 0.90, "emit_conf_scale": 1.0,
        "emit_partial": 0.10, "emit_null": 0.3, "max_total": 5,
    }
    read = PageRead(0, curr=None, total=None, method="failed", confidence=0.0)
    log_p_a = compute_log_emission(read, (1, 3), params)
    log_p_b = compute_log_emission(read, (2, 5), params)
    # Both should be equal (uniform for null reads)
    assert abs(log_p_a - log_p_b) < 1e-9


def test_emit_null_state():
    """NULL hidden state with any observation."""
    params = {
        "emit_match": 0.90, "emit_conf_scale": 1.0,
        "emit_partial": 0.10, "emit_null": 0.3, "max_total": 5,
    }
    read = PageRead(0, curr=2, total=3, method="direct", confidence=0.95)
    log_p = compute_log_emission(read, None, params)
    assert math.isfinite(log_p)
