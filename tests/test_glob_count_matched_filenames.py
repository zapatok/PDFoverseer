"""GlobCountResult.matched_filenames exposes the matching files."""

from pathlib import Path

import pytest

from core.scanners.utils.filename_glob import count_pdfs_by_sigla


def test_matched_filenames_contains_only_sigla_matches(tmp_path: Path):
    # 2 ART files + 1 IRL file
    (tmp_path / "2026-04-01_art_demo_empresa.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "2026-04-02_art_otro_empresa.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "2026-04-03_irl_x_empresa.pdf").write_bytes(b"%PDF\n%%EOF")

    result = count_pdfs_by_sigla(tmp_path, sigla="art")

    assert result.count == 2
    assert sorted(result.matched_filenames) == [
        "2026-04-01_art_demo_empresa.pdf",
        "2026-04-02_art_otro_empresa.pdf",
    ]


def test_matched_filenames_empty_when_no_match(tmp_path: Path):
    (tmp_path / "2026-04-03_irl_x_empresa.pdf").write_bytes(b"%PDF\n%%EOF")
    result = count_pdfs_by_sigla(tmp_path, sigla="art")
    assert result.matched_filenames == []


def test_matched_filenames_empty_when_folder_missing(tmp_path: Path):
    missing = tmp_path / "no_such_folder"
    result = count_pdfs_by_sigla(missing, sigla="art")
    assert result.matched_filenames == []
    assert "folder_missing" in result.flags
