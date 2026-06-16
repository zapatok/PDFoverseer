import fitz
from api.routes.sessions import compute_settled


def _make_pdf(path, n_pages):
    doc = fitz.open()
    for _ in range(n_pages):
        doc.new_page()
    doc.save(str(path))
    doc.close()


def test_all_r1_single_page_is_settled(tmp_path):
    _make_pdf(tmp_path / "a.pdf", 1)
    _make_pdf(tmp_path / "b.pdf", 1)
    cell = {
        "per_file": {"a.pdf": 1, "b.pdf": 1},
        "per_file_method": {"a.pdf": "filename_glob", "b.pdf": "filename_glob"},
        "per_file_overrides": {},
        "method": "filename_glob",
    }
    assert compute_settled(cell, tmp_path) is True


def test_a_pending_multipage_is_not_settled(tmp_path):
    _make_pdf(tmp_path / "a.pdf", 1)
    _make_pdf(tmp_path / "big.pdf", 8)  # filename_glob multipage → Pendiente
    cell = {
        "per_file": {"a.pdf": 1, "big.pdf": 1},
        "per_file_method": {"a.pdf": "filename_glob", "big.pdf": "filename_glob"},
        "per_file_overrides": {},
        "method": "filename_glob",
    }
    assert compute_settled(cell, tmp_path) is False


def test_ocr_file_is_not_settled(tmp_path):
    _make_pdf(tmp_path / "a.pdf", 5)
    cell = {
        "per_file": {"a.pdf": 2},
        "per_file_method": {"a.pdf": "v4"},
        "per_file_overrides": {},
        "method": "v4",
    }
    assert compute_settled(cell, tmp_path) is False


def test_ratio_n_is_settled(tmp_path):
    _make_pdf(tmp_path / "big.pdf", 8)
    cell = {
        "per_file": {"big.pdf": 4},
        "per_file_method": {"big.pdf": "ratio_n"},
        "per_file_overrides": {},
        "method": "filename_glob",
    }
    assert compute_settled(cell, tmp_path) is True


def test_pending_overridden_per_file_is_settled(tmp_path):
    _make_pdf(tmp_path / "big.pdf", 8)
    cell = {
        "per_file": {"big.pdf": 1},
        "per_file_method": {"big.pdf": "filename_glob"},
        "per_file_overrides": {"big.pdf": 3},
        "method": "filename_glob",
    }
    assert compute_settled(cell, tmp_path) is True  # Manual via per-file override


def test_empty_folder_is_not_settled(tmp_path):
    cell = {
        "per_file": {},
        "per_file_method": {},
        "per_file_overrides": {},
        "method": "filename_glob",
    }
    assert compute_settled(cell, tmp_path) is False
