from pathlib import Path

import pytest

from core.scanners.utils.filename_glob import (
    count_pdfs_by_sigla,
    extract_sigla,
    per_empresa_breakdown,
)

# Real fixtures from ABRIL HPV
ABRIL_ROOT = Path("A:/informe mensual/ABRIL")


# Regression tests for extract_sigla — these reproduce 17 of 54 cells the
# audit found to be miscounting. Two distinct defects in the original regex:
#
# (1) `[a-z_]+?` non-greedy with `_` in the class made the engine stop at the
#     first underscore. Multi-word siglas like `dif_pts` or `herramientas_elec`
#     would be returned as `dif` / `herramientas`, missing every PDF.
#
# (2) `\\.` was double-escaped (literal backslash + any char), so filenames
#     ending right after the sigla — `2026-05-06_odi.pdf` — never matched.
@pytest.mark.parametrize(
    "filename,expected",
    [
        # Bug (1): multi-word siglas should be extracted whole
        ("2026-04-21_dif_pts.pdf", "dif_pts"),
        ("2026-04-07_dif_pts_a.pdf", "dif_pts"),
        ("2026-05-08_herramientas_elec_chequeos.pdf", "herramientas_elec"),
        ("2026-05-08_herramientas_elec.pdf", "herramientas_elec"),
        # Bug (2): trailing-extension after sigla should match
        ("2026-05-06_odi.pdf", "odi"),
        ("2026-04-15_chintegral.pdf", "chintegral"),
        # Already-working baselines — must keep matching
        ("2026-04-15_art_crs_descripcion.pdf", "art"),
        ("2026-04-21_andamios_titan.pdf", "andamios"),
        ("2026-04-09_irl.pdf", "irl"),
        # Negative cases — must return None
        ("not_a_canonical_filename.pdf", None),
        ("2026-04-15_unknownsigla_extra.pdf", None),
        ("README.md", None),
    ],
)
def test_extract_sigla(filename, expected):
    assert extract_sigla(filename) == expected


def test_count_art_in_hpv():
    folder = ABRIL_ROOT / "HPV" / "7.-ART"
    result = count_pdfs_by_sigla(folder, sigla="art")
    # HPV ART has ~767 PDFs across 13 empresa subfolders as of 2026-05-11 audit
    # We don't pin to 767 exactly (corpus may evolve); just bound it
    assert 700 <= result.count <= 900
    assert result.method == "filename_glob"


def test_count_zero_when_folder_empty(tmp_path):
    empty = tmp_path / "1.-Reunion Prevencion 0"
    empty.mkdir()
    result = count_pdfs_by_sigla(empty, sigla="reunion")
    assert result.count == 0


def test_count_zero_when_folder_missing(tmp_path):
    missing = tmp_path / "doesnotexist"
    result = count_pdfs_by_sigla(missing, sigla="reunion")
    assert result.count == 0
    assert "folder_missing" in result.flags


def test_per_empresa_breakdown_for_hpv_art():
    folder = ABRIL_ROOT / "HPV" / "7.-ART"
    breakdown = per_empresa_breakdown(folder)
    # 13 empresa subfolders exist (AGUASAN, ALUMINIO 2000, ARAYA, FLEISHMANN, HU,
    # JAPA, JJC, KOHLER, MMG, RACO, REALI, STI, TITAN).
    # CRS files live flat in the parent, not in a subfolder.
    assert len(breakdown) >= 5
    assert any("JJC" in name.upper() or "TITAN" in name.upper() for name in breakdown)
