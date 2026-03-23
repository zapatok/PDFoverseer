import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from eval.graph_inference import build_state_space, PageRead, Document, compute_log_emission, compute_log_transition
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


def test_trans_continue_highest():
    """(1,3) → (2,3) should have highest probability (continue doc)."""
    params = {
        "trans_continue": 0.85, "trans_new_doc": 0.10, "trans_skip": 0.03,
        "max_total": 5, "boundary_bonus": 2.0, "period_prior": 0.0,
    }
    states, idx = build_state_space(5)
    modal_total = None
    log_cont = compute_log_transition((1, 3), (2, 3), params, modal_total)
    log_new = compute_log_transition((1, 3), (1, 2), params, modal_total)
    assert log_cont > log_new


def test_trans_complete_doc_bonus():
    """After complete doc (3,3), transition to (1,t') gets boundary_bonus."""
    params = {
        "trans_continue": 0.85, "trans_new_doc": 0.10, "trans_skip": 0.03,
        "max_total": 5, "boundary_bonus": 3.0, "period_prior": 0.0,
    }
    modal_total = None
    # From (3,3) — document complete → new doc should be boosted
    log_new_after_complete = compute_log_transition((3, 3), (1, 2), params, modal_total)
    # From (1,3) — mid-document → new doc should NOT be boosted
    log_new_mid_doc = compute_log_transition((1, 3), (1, 2), params, modal_total)
    assert log_new_after_complete > log_new_mid_doc


def test_trans_period_prior():
    """When modal_total is known, new docs with that total get boosted."""
    params = {
        "trans_continue": 0.85, "trans_new_doc": 0.10, "trans_skip": 0.03,
        "max_total": 5, "boundary_bonus": 2.0, "period_prior": 0.4,
    }
    modal_total = 3
    log_to_modal = compute_log_transition((2, 2), (1, 3), params, modal_total)
    log_to_other = compute_log_transition((2, 2), (1, 5), params, modal_total)
    assert log_to_modal > log_to_other
