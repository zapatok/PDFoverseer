"""
Tests for generate_phrase_pattern — OCR-aware multi-token phrase matching.
"""

import re

from ocr_matcher.phrase import generate_phrase_pattern

# Template under test
PAGINA_TMPL = "Pagina {num} de {num}"


def test_phrase_matches_clean():
    pat = re.compile(generate_phrase_pattern(PAGINA_TMPL), re.IGNORECASE)
    assert pat.search("Pagina 3 de 8")


def test_phrase_extracts_numbers():
    pat = re.compile(generate_phrase_pattern(PAGINA_TMPL), re.IGNORECASE)
    m = pat.search("Pagina 3 de 8")
    assert m is not None
    assert m.group(1) == "3"
    assert m.group(2) == "8"


def test_phrase_ocr_word_variant():
    # g→q substitution in "Pagina"
    pat = re.compile(generate_phrase_pattern(PAGINA_TMPL), re.IGNORECASE)
    assert pat.search("Paqina 3 de 8")


def test_phrase_ocr_digit_l():
    # 1→l confusion
    pat = re.compile(generate_phrase_pattern(PAGINA_TMPL), re.IGNORECASE)
    m = pat.search("Pagina l de 8")
    assert m is not None
    assert m.group(1) == "l"


def test_phrase_ocr_digit_z():
    # 2→z confusion
    pat = re.compile(generate_phrase_pattern(PAGINA_TMPL), re.IGNORECASE)
    m = pat.search("Pagina 1 de z")
    assert m is not None
    assert m.group(2) == "z"


def test_phrase_pegado():
    # No spaces — OCR drops whitespace
    pat = re.compile(generate_phrase_pattern(PAGINA_TMPL), re.IGNORECASE)
    assert pat.search("Pagina3de8")


def test_phrase_word_only():
    # Template with no {num} tokens — pure incidence matching
    pat = re.compile(generate_phrase_pattern("Firma del supervisor"), re.IGNORECASE)
    assert pat.search("Firma del supervisor")
    assert not pat.search("Contrato de trabajo")


def test_phrase_pag_abbreviated():
    # Progressive suffix: "Pag." and "Pag" must connect to the number in phrase context
    pat = re.compile(generate_phrase_pattern(PAGINA_TMPL), re.IGNORECASE)
    assert pat.search("Pag. 3 de 8")
    assert pat.search("Pag 3 de 8")


def test_phrase_no_false_positive():
    # "X de N" alone should NOT match without the word anchor
    pat = re.compile(generate_phrase_pattern(PAGINA_TMPL), re.IGNORECASE)
    assert not pat.search("Total: 3 de 8 elementos")
    assert not pat.search("Contrato de trabajo numero 5")
