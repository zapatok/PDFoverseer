"""
End-to-end smoke test: word -> pattern -> match.
Simulates the real use case: OCR'd text contains a corrupted word,
and we need to detect it using the generated pattern.
"""

import re
import regex as re_fuzzy

from ocr_matcher.pattern import generate_charclass_pattern, generate_fuzzy_pattern
from ocr_matcher.distance import is_likely_ocr_of

# Lines with single-char OCR errors — caught by both charclass AND fuzzy k=1
OCR_LINES_SINGLE_ERROR = [
    "Paqina 3 de 5",      # g->q substitution
    "P@gina 1 de 10",     # noise after P (one inserted char)
    "Pag1na 4 de 6",      # i->1 substitution
    "Pagina 7 de 7",      # exact (no errors)
]

# Lines with abbreviations — charclass handles these; fuzzy k=1 does NOT
# (abbreviation = 3+ deletions, beyond k=1 budget)
OCR_LINES_ABBREV = [
    "pag. 2 de 8",        # abbreviation + lowercase
]

NOT_PAGINA_LINES = [
    "Contrato de trabajo",
    "Firma del supervisor",
    "Fecha: 2026-03-15",
    "Total: 12345",
]


def test_charclass_catches_single_error_lines():
    pat = re.compile(generate_charclass_pattern("Pagina"), re.IGNORECASE)
    for line in OCR_LINES_SINGLE_ERROR:
        assert pat.search(line), f"Expected match in: {line!r}"


def test_charclass_catches_abbreviations():
    pat = re.compile(generate_charclass_pattern("Pagina"), re.IGNORECASE)
    for line in OCR_LINES_ABBREV:
        assert pat.search(line), f"Expected abbreviation match in: {line!r}"


def test_charclass_no_false_positives():
    pat = re.compile(generate_charclass_pattern("Pagina"), re.IGNORECASE)
    for line in NOT_PAGINA_LINES:
        assert not pat.search(line), f"Unexpected match in: {line!r}"


def test_fuzzy_catches_single_error_lines():
    # fuzzy k=1 covers single-char errors; abbreviations require k>=3 (not tested here)
    pat = re_fuzzy.compile(generate_fuzzy_pattern("Pagina", k=1), re_fuzzy.IGNORECASE)
    for line in OCR_LINES_SINGLE_ERROR:
        assert pat.search(line), f"Fuzzy expected match in: {line!r}"


def test_distance_scorer_ranks_variants_correctly():
    assert is_likely_ocr_of("paqina", "pagina") is True
    assert is_likely_ocr_of("contrato", "pagina") is False
