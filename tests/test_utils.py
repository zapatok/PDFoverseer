"""
Tests for core.utils._parse() regex and normalization.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from core.utils import _parse


@pytest.mark.parametrize("text,expected", [
    ("Página 1 de 5",       (1, 5)),
    ("Pag 1 de 10",         (1, 10)),
    ("Pag l de 5",          (1, 5)),    # OCR confusion: l → 1
    ("Pag O de 10",         (None, None)),  # O → 0, curr=0 is invalid
    ("Página Z de 3",       (2, 3)),    # Z → 2 via _Z2 substitution
    ("Pag 5 de 3",          (None, None)),  # curr > total
    ("Pag 1 de 100",        (None, None)),  # total > 99
    ("",                    (None, None)),
    ("random garbage text", (None, None)),
    ("P 1 de 2",            (1, 2)),    # short form
    ("Pag 3 de 3",          (3, 3)),    # last page of doc
    ("Pagina 2 de 5",       (2, 5)),    # without accent
    ("PAG 1 DE 10",         (1, 10)),   # all caps
])
def test_parse(text, expected):
    assert _parse(text) == expected
