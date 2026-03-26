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
    ("",                    (None, None)),
    ("random garbage text", (None, None)),
    ("P 1 de 2",            (1, 2)),    # short form
    ("Pag 3 de 3",          (3, 3)),    # last page of doc
    ("Pagina 2 de 5",       (2, 5)),    # without accent
    ("PAG 1 DE 10",         (1, 10)),   # all caps
    # tot > 10 accepted up to 20; > 20 rejected
    ("Pag 1 de 11",         (1, 11)),   # accepted
    ("Pag 4 de 20",         (4, 20)),   # boundary: accepted
    ("Pag 1 de 21",         (None, None)),  # exceeds max_total=20
    ("Pag 1 de 100",        (None, None)),  # way over
    ("2 de 4",              (None, None)),  # bare N de M: no P-prefix, not matched
])
def test_parse(text, expected):
    assert _parse(text) == expected
