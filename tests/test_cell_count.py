from core.cell_count import compute_cell_count


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
