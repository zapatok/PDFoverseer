from ocr_matcher.distance import ocr_distance, is_likely_ocr_of


def test_identical_strings_zero_distance():
    assert ocr_distance("pagina", "pagina") == 0.0


def test_common_ocr_error_low_distance():
    assert ocr_distance("pagina", "paqina") < 0.2


def test_unrelated_string_high_distance():
    assert ocr_distance("pagina", "contrato") > 1.0


def test_is_likely_ocr_true():
    assert is_likely_ocr_of("paqina", "pagina", threshold=0.5)


def test_is_likely_ocr_false():
    assert not is_likely_ocr_of("contrato", "pagina", threshold=0.5)


def test_single_insertion_cost():
    # "paginaa" has one extra char — insertion cost is 1.0 (default)
    d = ocr_distance("pagina", "paginaa")
    assert 0.5 < d < 1.5


def test_case_insensitive_option():
    assert ocr_distance("Pagina", "pagina", ignore_case=True) == 0.0
