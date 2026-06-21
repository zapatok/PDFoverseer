import pytest

from eval.pagination_count.engine import (
    PageRead,
    dominant_total,
    extract_code,
    parse_pagination,
    recover_sequence,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Pagina 1 de 4", (1, 4)),
        ("Página 2 de 4", (2, 4)),
        ("r SpA Fecha: 31/12/2025| Página 2 de 4 L", (2, 4)),  # real OCR noise
        ("Pagina 1de1", (1, 1)),  # missing space
        ("Pagina l de 4", (1, 4)),  # l->1 digit-normalize
        ("Pagina 1", (1, None)),  # curr-only (no total)
        ("F-CRS-ART-01 Rev 02", (None, None)),  # no pagination
        ("", (None, None)),
        ("Pagina 12 de 20", (12, 20)),  # full regex wins over curr-only
    ],
)
def test_parse_pagination(raw, expected):
    assert parse_pagination(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Código: F-CRS-ART-01 Rev 02", "F-CRS-ART-01"),
        ("F-CRS-ODI-01 INFORMACION", "F-CRS-ODI-01"),
        ("F-LCH-CRS-36 EN CALIENTE", "F-LCH-CRS-36"),
        ("no code here", None),
    ],
)
def test_extract_code(raw, expected):
    assert extract_code(raw) == expected


def _currs(reads):
    return [r.curr for r in reads]


def _status(reads):
    return [r.status for r in reads]


def test_dominant_total_mode_ignores_outliers():
    parsed = [
        (1, 4, "A"),
        (2, 4, "A"),
        (3, 4, "A"),
        (4, 4, "A"),
        (1, 4, "A"),
        (2, 3, "A"),
    ]  # one bad total=3
    assert dominant_total(parsed) == 4


def test_dominant_total_none_when_no_totals():
    assert dominant_total([(None, None, None), (1, None, "A")]) is None


def test_recover_no_gaps():
    parsed = [(1, 4, "A"), (2, 4, "A"), (3, 4, "A"), (4, 4, "A")]
    out = recover_sequence(parsed)
    assert _currs(out) == [1, 2, 3, 4]
    assert _status(out) == ["direct"] * 4


def test_recover_run_of_gaps_forward_fill():
    # ART rhythm with 2 unreadable corners mid-run
    parsed = [(1, 4, "A"), (None, None, None), (None, None, None), (4, 4, "A"), (1, 4, "A")]
    out = recover_sequence(parsed)
    assert _currs(out) == [1, 2, 3, 4, 1]
    assert _status(out) == ["direct", "recovered", "recovered", "direct", "direct"]


def test_recovered_page_carries_dominant_total():
    parsed = [(1, 4, "A"), (None, None, None), (3, 4, "A"), (4, 4, "A")]
    out = recover_sequence(parsed)
    assert out[1].status == "recovered" and out[1].curr == 2 and out[1].total == 4


def test_recover_leading_gap_uses_right_neighbor():
    parsed = [(None, None, None), (2, 4, "A"), (3, 4, "A"), (4, 4, "A")]
    out = recover_sequence(parsed)
    assert _currs(out)[0] == 1


def test_recover_orphan_is_failed():
    parsed = [(None, None, None)]  # no dominant total, no neighbor
    out = recover_sequence(parsed)
    assert out[0].status == "failed" and out[0].curr is None
