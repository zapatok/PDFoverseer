import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from eval.graph_inference import build_state_space, PageRead, Document, compute_log_emission, compute_log_transition
import math
import json
import time


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


from eval.graph_inference import viterbi_decode, extract_documents


def test_viterbi_clean_two_docs():
    """Two clean 2-page docs → Viterbi should decode perfectly."""
    reads = [
        PageRead(0, 1, 2, "direct", 0.95),
        PageRead(1, 2, 2, "direct", 0.92),
        PageRead(2, 1, 2, "direct", 0.91),
        PageRead(3, 2, 2, "direct", 0.90),
    ]
    params = {
        "trans_continue": 0.85, "trans_new_doc": 0.10, "trans_skip": 0.03,
        "emit_match": 0.90, "emit_conf_scale": 1.0, "emit_partial": 0.10,
        "emit_null": 0.3, "max_total": 5, "boundary_bonus": 2.0,
        "period_prior": 0.0,
    }
    path = viterbi_decode(reads, params)
    assert len(path) == 4
    assert path[0] == (1, 2)
    assert path[1] == (2, 2)
    assert path[2] == (1, 2)
    assert path[3] == (2, 2)


def test_viterbi_missing_middle():
    """3-page doc with failed middle read → should infer (2, 3)."""
    reads = [
        PageRead(0, 1, 3, "direct", 0.95),
        PageRead(1, None, None, "failed", 0.0),
        PageRead(2, 3, 3, "direct", 0.90),
    ]
    params = {
        "trans_continue": 0.85, "trans_new_doc": 0.10, "trans_skip": 0.03,
        "emit_match": 0.90, "emit_conf_scale": 1.0, "emit_partial": 0.10,
        "emit_null": 0.3, "max_total": 5, "boundary_bonus": 2.0,
        "period_prior": 0.0,
    }
    path = viterbi_decode(reads, params)
    assert path[0] == (1, 3)
    assert path[1] == (2, 3)  # inferred from context
    assert path[2] == (3, 3)


def test_extract_two_complete_docs():
    """Two 2-page docs from Viterbi path."""
    reads = [
        PageRead(0, 1, 2, "direct", 0.95),
        PageRead(1, 2, 2, "direct", 0.92),
        PageRead(2, 1, 2, "direct", 0.91),
        PageRead(3, 2, 2, "direct", 0.90),
    ]
    path = [(1, 2), (2, 2), (1, 2), (2, 2)]
    docs = extract_documents(reads, path)
    assert len(docs) == 2
    assert docs[0].declared_total == 2
    assert docs[0].is_complete
    assert docs[1].start_pdf_page == 2


def test_extract_with_inferred_page():
    """3-page doc where middle page was failed → inferred."""
    reads = [
        PageRead(0, 1, 3, "direct", 0.95),
        PageRead(1, None, None, "failed", 0.0),
        PageRead(2, 3, 3, "direct", 0.90),
    ]
    path = [(1, 3), (2, 3), (3, 3)]
    docs = extract_documents(reads, path)
    assert len(docs) == 1
    assert docs[0].declared_total == 3
    assert len(docs[0].pages) == 2        # pages 0 and 2 had OCR
    assert len(docs[0].inferred_pages) == 1  # page 1 was inferred
    assert docs[0].is_complete


def test_extract_with_skip():
    """Doc with a skip: (1,3) → (3,3) — page 2 missing from observations."""
    reads = [
        PageRead(0, 1, 3, "direct", 0.95),
        PageRead(1, 3, 3, "direct", 0.90),
    ]
    path = [(1, 3), (3, 3)]
    docs = extract_documents(reads, path)
    assert len(docs) == 1
    assert docs[0].declared_total == 3
    assert not docs[0].sequence_ok  # gap in sequence


# Task 6: run_pipeline integration + end-to-end tests

from eval.graph_inference import run_pipeline

BASIC_PARAMS = {
    "trans_continue": 0.85, "trans_new_doc": 0.10, "trans_skip": 0.03,
    "emit_match": 0.90, "emit_conf_scale": 1.0, "emit_partial": 0.10,
    "emit_null": 0.3, "max_total": 10, "boundary_bonus": 2.0,
    "period_prior": 0.0,
}


def test_e2e_simple_two_docs():
    """End-to-end: two clean 2-page docs."""
    reads = [
        PageRead(0, 1, 2, "direct", 0.95), PageRead(1, 2, 2, "direct", 0.92),
        PageRead(2, 1, 2, "direct", 0.91), PageRead(3, 2, 2, "direct", 0.90),
    ]
    docs = run_pipeline(reads, BASIC_PARAMS)
    assert len(docs) == 2
    assert all(d.is_complete for d in docs)


def test_e2e_infer_missing():
    """End-to-end: infer missing middle page."""
    reads = [
        PageRead(0, 1, 3, "direct", 0.95),
        PageRead(1, None, None, "failed", 0.0),
        PageRead(2, 3, 3, "direct", 0.90),
    ]
    docs = run_pipeline(reads, BASIC_PARAMS)
    assert len(docs) == 1
    assert docs[0].declared_total == 3
    assert docs[0].found_total == 3


def test_e2e_mixed_sizes():
    """End-to-end: mixed 1-page and 3-page docs."""
    reads = [
        PageRead(0, 1, 1, "direct", 0.90),
        PageRead(1, 1, 3, "direct", 0.88),
        PageRead(2, 2, 3, "direct", 0.85),
        PageRead(3, 3, 3, "direct", 0.87),
        PageRead(4, 1, 1, "direct", 0.91),
    ]
    docs = run_pipeline(reads, BASIC_PARAMS)
    assert len(docs) == 3  # 1-page + 3-page + 1-page


def test_e2e_does_not_mutate_input():
    """run_pipeline must not mutate the input reads list."""
    reads = [PageRead(0, 1, 2, "direct", 0.95), PageRead(1, 2, 2, "direct", 0.92)]
    original_conf = reads[0].confidence
    run_pipeline(reads, BASIC_PARAMS)
    assert reads[0].confidence == original_conf


# Task 9: Smoke tests with real + synthetic fixtures


def test_real_fixture_no_crash():
    """Smoke test: graph engine runs on a real fixture without errors."""
    fixture_path = Path("eval/fixtures/real/CH_9.json")
    if not fixture_path.exists():
        import pytest
        pytest.skip("CH_9.json fixture not found")

    data = json.loads(fixture_path.read_text())
    reads = [PageRead(**r) for r in data["reads"]]
    docs = run_pipeline(reads, BASIC_PARAMS)

    assert len(docs) >= 1
    assert all(isinstance(d, Document) for d in docs)
    # Every page should be assigned to exactly one document
    all_pages = set()
    for d in docs:
        for p in d.pages + d.inferred_pages:
            assert p not in all_pages, f"Page {p} assigned to multiple docs"
            all_pages.add(p)


def test_synthetic_fixture_no_crash():
    """Smoke test: graph engine runs on a synthetic fixture."""
    fixture_path = Path("eval/fixtures/synthetic/clean_period2.json")
    if not fixture_path.exists():
        import pytest
        pytest.skip("clean_period2.json fixture not found")

    data = json.loads(fixture_path.read_text())
    reads = [PageRead(**r) for r in data["reads"]]
    docs = run_pipeline(reads, BASIC_PARAMS)
    assert len(docs) >= 1


def test_e2e_single_page():
    """Single-page PDF → one document."""
    reads = [PageRead(0, 1, 1, "direct", 0.90)]
    docs = run_pipeline(reads, BASIC_PARAMS)
    assert len(docs) == 1
    assert docs[0].declared_total == 1


def test_e2e_all_failed():
    """All OCR failed → should still return without error."""
    reads = [
        PageRead(i, None, None, "failed", 0.0)
        for i in range(5)
    ]
    docs = run_pipeline(reads, BASIC_PARAMS)
    # Should not crash; exact doc count depends on model behavior
    assert isinstance(docs, list)


def test_e2e_empty_input():
    """Empty reads → empty docs."""
    docs = run_pipeline([], BASIC_PARAMS)
    assert docs == []


def test_performance_200_pages():
    """Spec constraint: must handle 200 pages in <30s (conservative)."""
    reads = []
    # 40 documents of 5 pages each = 200 pages
    for doc_idx in range(40):
        for page in range(5):
            pdf_page = doc_idx * 5 + page
            # 80% have good reads, 20% failed
            if pdf_page % 5 != 3:
                reads.append(PageRead(pdf_page, page + 1, 5, "direct", 0.85))
            else:
                reads.append(PageRead(pdf_page, None, None, "failed", 0.0))

    params = {**BASIC_PARAMS, "max_total": 20}
    t0 = time.perf_counter()
    docs = run_pipeline(reads, params)
    elapsed = time.perf_counter() - t0

    assert len(docs) >= 1
    assert elapsed < 30.0, f"200-page Viterbi took {elapsed:.1f}s, must be <30s"
