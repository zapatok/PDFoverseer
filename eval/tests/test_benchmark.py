import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from eval.ocr_benchmark import extract_paddle_text, load_fixture, score_page


def test_load_fixture_returns_dict():
    """Fixture loads into {pdf_page: (curr, total, method)} dict."""
    gt = load_fixture("eval/fixtures/real/ART_674.json")
    assert isinstance(gt, dict)
    assert len(gt) == 2683  # 2683 VLM-verified reads (Opus visual inspection)
    assert gt[1] == (1, 4, "vlm_opus")


def test_load_fixture_all_vlm_opus():
    """All ART_674 entries use method='vlm_opus' (Opus visual inspection)."""
    gt = load_fixture("eval/fixtures/real/ART_674.json")
    non_vlm = [p for p, (_, _, m) in gt.items() if m != "vlm_opus"]
    assert non_vlm == []


def test_extract_paddle_text_empty():
    """Empty/None PaddleOCR result returns empty string."""
    assert extract_paddle_text(None) == ""
    assert extract_paddle_text([]) == ""
    assert extract_paddle_text([[]]) == ""


def test_extract_paddle_text_single_line():
    """Extracts text from standard PaddleOCR nested result."""
    result = [[
        ([0, 0, 1, 1], ("Página 1 de 4", 0.95))
    ]]
    assert "Página 1 de 4" in extract_paddle_text(result)


def test_extract_paddle_text_multiple_lines():
    """Joins multiple text regions with space."""
    result = [[
        ([0, 0, 1, 1], ("Pag", 0.9)),
        ([1, 0, 2, 1], ("1 de 4", 0.9)),
    ]]
    text = extract_paddle_text(result)
    assert "Pag" in text
    assert "1 de 4" in text


def test_score_page_hit():
    assert score_page(1, 4, 1, 4) == "hit"


def test_score_page_miss():
    assert score_page(2, 4, 1, 4) == "miss"
    assert score_page(1, 3, 1, 4) == "miss"


def test_score_page_none():
    assert score_page(None, None, 1, 4) == "none"


def test_extract_paddle_text_none_inner():
    """PaddleOCR returns [None] for completely blank images — must not crash."""
    assert extract_paddle_text([None]) == ""
