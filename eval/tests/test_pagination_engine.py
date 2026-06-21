import pytest

from eval.pagination_count.engine import parse_pagination


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
