import re
import regex as re_fuzzy

from ocr_matcher.pattern import generate_charclass_pattern, generate_fuzzy_pattern


# --- charclass pattern ---

def test_charclass_matches_exact():
    pat = re.compile(generate_charclass_pattern("pagina"), re.IGNORECASE)
    assert pat.search("pagina")


def test_charclass_matches_ocr_g_q():
    pat = re.compile(generate_charclass_pattern("pagina"), re.IGNORECASE)
    assert pat.search("paqina")


def test_charclass_matches_abbreviation():
    pat = re.compile(generate_charclass_pattern("pagina"), re.IGNORECASE)
    assert pat.search("pag.")


def test_charclass_no_false_positive():
    pat = re.compile(generate_charclass_pattern("firma"), re.IGNORECASE)
    assert not pat.search("contrato")


def test_charclass_word_boundary():
    # "firma" should NOT match inside "confirmar"
    pat = re.compile(generate_charclass_pattern("firma"), re.IGNORECASE)
    assert not pat.search("confirmar")


def test_charclass_matches_accented_input():
    # OCR may preserve the accent in output — á must be in the char class
    pat = re.compile(generate_charclass_pattern("Pagina"), re.IGNORECASE)
    assert pat.search("Página 3 de 8")


# --- fuzzy pattern ---

def test_fuzzy_matches_exact():
    pat = re_fuzzy.compile(generate_fuzzy_pattern("pagina", k=1), re_fuzzy.IGNORECASE)
    assert pat.search("pagina")


def test_fuzzy_matches_one_error():
    pat = re_fuzzy.compile(generate_fuzzy_pattern("pagina", k=1), re_fuzzy.IGNORECASE)
    assert pat.search("paqina")  # g→q


def test_fuzzy_no_match_beyond_k():
    pat = re_fuzzy.compile(generate_fuzzy_pattern("pagina", k=1), re_fuzzy.IGNORECASE)
    assert not pat.search("contrato")
