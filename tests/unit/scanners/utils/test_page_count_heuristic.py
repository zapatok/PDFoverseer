"""Compilation-suspect heuristic calibration (audit finding #4).

Two signals flag a folder: a single PDF much longer than one document
(per-PDF factor), or several medium PDFs whose average length is well above one
document (aggregate ratio — the moderate compilations the ×factor alone misses).
"""

from core.scanners.utils.page_count_heuristic import flag_compilation_suspect


def test_andamios_moderate_compilation_flagged(tmp_path, monkeypatch):
    # 1 PDF of 9 pages, expected andamios=2. With ×3 (threshold 6) → suspect.
    (tmp_path / "check_list_a.pdf").write_bytes(b"x")
    monkeypatch.setattr("core.scanners.utils.page_count_heuristic._page_count", lambda p: 9)
    assert flag_compilation_suspect(tmp_path, sigla="andamios") is True


def test_regime1_art_not_flagged(tmp_path, monkeypatch):
    # ART of 4 pages, expected art=10 → not suspect (healthy regime 1).
    (tmp_path / "art1.pdf").write_bytes(b"x")
    monkeypatch.setattr("core.scanners.utils.page_count_heuristic._page_count", lambda p: 4)
    assert flag_compilation_suspect(tmp_path, sigla="art") is False


def test_aggregate_ratio_flags_many_medium_pdfs(tmp_path, monkeypatch):
    # 5 PDFs of 5pp each, expected 2 → no single PDF exceeds ×3 (6), but the
    # aggregate ratio (avg 5 > 2×2) marks aggregate suspicion.
    for i in range(5):
        (tmp_path / f"f{i}.pdf").write_bytes(b"x")
    monkeypatch.setattr("core.scanners.utils.page_count_heuristic._page_count", lambda p: 5)
    assert flag_compilation_suspect(tmp_path, sigla="exc") is True


def test_two_medium_pdfs_not_flagged(tmp_path, monkeypatch):
    # Only 2 medium PDFs → below the ≥3 aggregate floor; not flagged (avoids
    # false positives on small healthy folders).
    for i in range(2):
        (tmp_path / f"f{i}.pdf").write_bytes(b"x")
    monkeypatch.setattr("core.scanners.utils.page_count_heuristic._page_count", lambda p: 5)
    assert flag_compilation_suspect(tmp_path, sigla="exc") is False


def test_single_large_pdf_still_flagged(tmp_path, monkeypatch):
    # The original per-PDF signal must still fire for a clearly oversized PDF.
    (tmp_path / "big.pdf").write_bytes(b"x")
    monkeypatch.setattr("core.scanners.utils.page_count_heuristic._page_count", lambda p: 50)
    assert flag_compilation_suspect(tmp_path, sigla="art") is True


def test_empty_folder_not_flagged(tmp_path):
    assert flag_compilation_suspect(tmp_path, sigla="andamios") is False
