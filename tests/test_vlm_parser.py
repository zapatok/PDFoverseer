"""Tests for VLM response parser."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from vlm.parser import parse


@pytest.mark.parametrize("text, expected", [
    # Direct N/M format
    ("3/10", (3, 10)),
    ("1/2", (1, 2)),
    # Spanish patterns
    ("Página 3 de 10", (3, 10)),
    ("Pagina 1 de 2", (1, 2)),
    ("Pag. 5 de 8", (5, 8)),
    ("Pág 12 de 15", (12, 15)),
    # English patterns
    ("Page 3 of 10", (3, 10)),
    # Variations
    ("3 de 10", (3, 10)),
    ("3 out of 10", (3, 10)),
    # VLM chatty responses
    ("The page number shown is 3/10.", (3, 10)),
    ("I can see Página 2 de 5 in the image.", (2, 5)),
    # Fallback: two integers <= 999
    ("numbers visible: 7 ... 20", (7, 20)),
    # Should NOT match
    ("No text visible", None),
    ("", None),
    # Integers > 999 should not match fallback
    ("15/07/2024", None),
    # But date-like with de should not match (year > 999)
    ("Fecha: 15 de 2024", None),
])
def test_parse(text, expected):
    assert parse(text) == expected


def test_parse_prefers_specific_over_fallback():
    """If both 'Página N de M' and random integers exist, prefer the named pattern."""
    text = "Código: 2024 Página 3 de 10"
    assert parse(text) == (3, 10)
