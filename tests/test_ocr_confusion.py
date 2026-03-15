from ocr_matcher.confusion import substitution_cost, build_matrix


def test_identical_chars_cost_zero():
    assert substitution_cost('a', 'a') == 0.0


def test_common_ocr_pair_low_cost():
    assert substitution_cost('g', 'q') < 0.2
    assert substitution_cost('q', 'g') < 0.2  # bidirectional


def test_unrelated_chars_full_cost():
    assert substitution_cost('g', 'z') == 1.0


def test_matrix_shape():
    m = build_matrix()
    assert m.shape == (128, 128)


def test_matrix_diagonal_zero():
    m = build_matrix()
    assert all(m[i, i] == 0.0 for i in range(128))


def test_matrix_is_symmetric_for_known_pair():
    m = build_matrix()
    assert m[ord('g'), ord('q')] == m[ord('q'), ord('g')]
