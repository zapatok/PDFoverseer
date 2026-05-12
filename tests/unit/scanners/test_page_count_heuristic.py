from pathlib import Path

from core.scanners.utils.page_count_heuristic import (
    EXPECTED_PAGES_PER_DOC,
    flag_compilation_suspect,
)

ABRIL = Path("A:/informe mensual/ABRIL")


def test_hpv_odi_individualized_not_suspect():
    """HPV ODI Visitas has 90 individual PDFs of ~2 pages each — no compilation."""
    flagged = flag_compilation_suspect(ABRIL / "HPV" / "3.-ODI Visitas", sigla="odi")
    assert flagged is False


def test_hrb_odi_single_pdf_is_suspect():
    """HRB ODI Visitas has 1 PDF of 34 pages — compilation suspected."""
    flagged = flag_compilation_suspect(ABRIL / "HRB" / "3.-ODI Visitas", sigla="odi")
    assert flagged is True


def test_hlu_odi_single_pdf_is_suspect():
    flagged = flag_compilation_suspect(ABRIL / "HLU" / "3.-ODI Visitas", sigla="odi")
    assert flagged is True


def test_expected_pages_per_doc_table_covers_all_siglas():
    from core.domain import SIGLAS

    for sigla in SIGLAS:
        assert sigla in EXPECTED_PAGES_PER_DOC
