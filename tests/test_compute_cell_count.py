"""Pure function compute_cell_count(cell) — FASE 4 §6.2 precedence."""

from api.state import compute_cell_count


def test_user_override_wins():
    cell = {
        "user_override": 99,
        "per_file": {"a.pdf": 5},
        "per_file_overrides": {"a.pdf": 3},
        "ocr_count": 10,
        "filename_count": 2,
    }
    assert compute_cell_count(cell) == 99


def test_per_file_overrides_compose_with_per_file():
    cell = {
        "user_override": None,
        "per_file": {"a.pdf": 5, "b.pdf": 3},
        "per_file_overrides": {"a.pdf": 7},
        "ocr_count": 99,
    }
    assert compute_cell_count(cell) == 10  # 7 (override) + 3 (per_file)


def test_per_file_only_no_overrides():
    cell = {
        "user_override": None,
        "per_file": {"a.pdf": 24, "b.pdf": 1},
        "per_file_overrides": {},
        "ocr_count": 99,
    }
    assert compute_cell_count(cell) == 25


def test_per_file_overrides_can_add_files_not_in_per_file():
    cell = {
        "user_override": None,
        "per_file": {"a.pdf": 5},
        "per_file_overrides": {"b.pdf": 3},
    }
    assert compute_cell_count(cell) == 8


def test_falls_back_to_ocr_count():
    cell = {
        "user_override": None,
        "per_file": None,
        "per_file_overrides": None,
        "ocr_count": 24,
        "filename_count": 5,
    }
    assert compute_cell_count(cell) == 24


def test_falls_back_to_filename_count_when_no_ocr():
    cell = {
        "user_override": None,
        "per_file": None,
        "per_file_overrides": None,
        "ocr_count": None,
        "filename_count": 5,
    }
    assert compute_cell_count(cell) == 5


def test_returns_zero_when_nothing():
    cell = {"user_override": None, "ocr_count": None, "filename_count": None}
    assert compute_cell_count(cell) == 0
