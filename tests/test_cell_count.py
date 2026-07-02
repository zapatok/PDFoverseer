from core.cell_count import compute_cell_count, compute_worker_count


def test_reorg_doc_delta_is_additive():
    assert compute_cell_count({"per_file": {"a.pdf": 3}}) == 3
    assert compute_cell_count({"per_file": {"a.pdf": 3}, "reorg_doc_delta": 2}) == 5
    assert compute_cell_count({"per_file": {"a.pdf": 3}, "reorg_doc_delta": -1}) == 2


def test_reorg_delta_respects_override_as_base():
    assert compute_cell_count({"user_override": 10, "reorg_doc_delta": 2}) == 12


def test_reorg_delta_applies_to_checks():
    cell = {"worker_marks": {"a.pdf": [{"page": 1, "count": 4}]}, "reorg_doc_delta": 1}
    assert compute_cell_count(cell, count_type="checks", present_files={"a.pdf"}) == 5


def test_no_delta_defaults_to_base():
    assert compute_cell_count({"per_file": {"a.pdf": 2}}) == 2
    assert compute_cell_count({}) == 0


def test_negative_effective_count_clamped_to_zero():
    # F5: a reorg delta can never drive the effective count below 0.
    assert compute_cell_count({"filename_count": 2, "reorg_doc_delta": -5}) == 0
    cell = {"worker_marks": {"a.pdf": [{"page": 1, "count": 2}]}, "reorg_doc_delta": -5}
    assert compute_cell_count(cell, count_type="checks", present_files={"a.pdf"}) == 0


def test_negative_effective_worker_count_clamped_to_zero():
    # F5: reorg_worker_delta can never drive the worker total below 0.
    assert compute_worker_count({"worker_marks": {}, "reorg_worker_delta": -3}) == 0
    cell = {"worker_marks": {"a.pdf": [{"page": 1, "count": 2}]}, "reorg_worker_delta": -5}
    assert compute_worker_count(cell, {"a.pdf"}) == 0


def test_worker_count_legacy_orphan_filter_by_per_file():
    # F1 cross-language PIN: IDENTICAL input/expected as the JS test
    # "F1: fallback filtra huérfanas por per_file" in
    # frontend/src/lib/worker-count.test.js. present_files=None (legacy) filters
    # marks by per_file keys → gone.pdf orphan excluded → 0 (NOT 9). This is the
    # exact fallback DetailPanel uses before the backend worker_count lands.
    cell = {
        "worker_marks": {"gone.pdf": [{"page": 1, "count": 9}]},
        "per_file": {"real.pdf": 1},
    }
    assert compute_worker_count(cell, None) == 0
