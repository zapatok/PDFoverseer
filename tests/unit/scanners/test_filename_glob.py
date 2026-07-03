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


# F6/F14a — per-sigla filename token aliases (Fase 5). The live corpus grew
# real files that never carry a sigla's own literal token: revdocmaq's real
# files use "revision"+"documentacion" instead of "revdocmaq", and one ABRIL
# chps file is spelled "cphs" (the real Comité Paritario acronym) instead of
# the canonical (transposed) "chps".
@pytest.mark.parametrize(
    "filename,expected",
    [
        ("REVISION_DOCUMENTACION_MAQUINARIA_AGUASAN.pdf", "revdocmaq"),
        ("2026-06-01_revision_documentacion_titan.pdf", "revdocmaq"),
        ("2026-04-30_cphs_acta_reunion.pdf", "chps"),  # real ABRIL file (F14 alias half)
        ("maquinaria_inspeccion_04.pdf", "maquinaria"),  # no regression
        ("2026-04_chps_acta_reunion.pdf", "chps"),  # earliest-match still holds
    ],
)
def test_extract_sigla_aliases(filename, expected):
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


def test_count_pdfs_by_sigla_folder_scope_chps(tmp_path):
    """F14 — chps counts by folder membership: its real files (crs.pdf,
    titan.pdf, the "cphs"-spelled file) carry no reliable chps token, so
    every PDF in the resolved category folder belongs, with no unmatched-file
    flag (the folder itself is the classifier)."""
    (tmp_path / "crs.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "titan.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "2026-04-30_cphs_acta_reunion.pdf").write_bytes(b"%PDF\n%%EOF")

    result = count_pdfs_by_sigla(tmp_path, sigla="chps")

    assert result.count == 3
    assert set(result.matched_filenames) == {
        "crs.pdf",
        "titan.pdf",
        "2026-04-30_cphs_acta_reunion.pdf",
    }
    assert "some_files_unrecognized" not in result.flags
    assert "no_matching_sigla_in_folder" not in result.flags


def test_count_pdfs_by_sigla_token_scope_unchanged(tmp_path):
    """F14 — a token-scoped sigla (charla) is unaffected: unrecognized files
    in the same folder are still excluded and still flagged."""
    (tmp_path / "2026-04-15_charla_supervisor.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "unrelated.pdf").write_bytes(b"%PDF\n%%EOF")

    result = count_pdfs_by_sigla(tmp_path, sigla="charla")

    assert result.count == 1
    assert result.matched_filenames == ["2026-04-15_charla_supervisor.pdf"]
    assert "some_files_unrecognized" in result.flags


def test_per_empresa_breakdown_for_hpv_art():
    folder = ABRIL_ROOT / "HPV" / "7.-ART"
    breakdown = per_empresa_breakdown(folder)
    # 13 empresa subfolders exist (AGUASAN, ALUMINIO 2000, ARAYA, FLEISHMANN, HU,
    # JAPA, JJC, KOHLER, MMG, RACO, REALI, STI, TITAN).
    # CRS files live flat in the parent, not in a subfolder.
    assert len(breakdown) >= 5
    assert any("JJC" in name.upper() or "TITAN" in name.upper() for name in breakdown)
