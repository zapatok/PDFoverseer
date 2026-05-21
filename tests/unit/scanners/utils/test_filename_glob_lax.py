"""A10 — lax filename matching."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.scanners.utils.filename_glob import (
    count_pdfs_by_sigla,
    extract_sigla,
)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("2026-04-15_reunion_supervisor.pdf", "reunion"),
        ("2026-04_reunion.pdf", "reunion"),  # HLL mega, no day
        ("REUNION_OLD.PDF", "reunion"),  # case-insensitive
        ("2026-04_herramientas_elec.pdf", "herramientas_elec"),
        ("2026-04-15_dif_pts_aguasan.pdf", "dif_pts"),  # multi-word sigla
        ("2026-04_chps_acta_reunion.pdf", "chps"),  # 'reunion' is substring; chps wins
    ],
)
def test_extract_sigla_lax(filename: str, expected: str):
    assert extract_sigla(filename) == expected


@pytest.mark.parametrize(
    "filename",
    [
        "notice.pdf",
        "random_document.pdf",
        "informe.pdf",
    ],
)
def test_extract_sigla_no_match(filename: str):
    assert extract_sigla(filename) is None


def test_count_pdfs_recursive_via_pattern(tmp_path: Path):
    """HPV-style subcarpetas: rglob captures HLL mega files within a folder."""
    (tmp_path / "AGUASAN").mkdir()
    (tmp_path / "AGUASAN" / "2026-04-15_andamios_chequeo_aguasan.pdf").write_bytes(b"%PDF-1.4\n")
    (tmp_path / "2026-04_andamios.pdf").write_bytes(b"%PDF-1.4\n")  # HLL mega
    (tmp_path / "unrelated.pdf").write_bytes(b"%PDF-1.4\n")

    result = count_pdfs_by_sigla(tmp_path, sigla="andamios")
    assert result.count == 2
    assert result.files_scanned == 3
    assert "some_files_unrecognized" in result.flags


def test_count_pdfs_folder_missing_returns_zero_with_flag(tmp_path: Path):
    """A8 — carpeta inexistente devuelve count=0 con flag, sin error."""
    missing = tmp_path / "DOES_NOT_EXIST"
    result = count_pdfs_by_sigla(missing, sigla="andamios")
    assert result.count == 0
    assert result.files_scanned == 0
    assert "folder_missing" in result.flags
