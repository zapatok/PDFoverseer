"""Tests for PD V3 post-processing: absolute floor + consecutive suppression."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402


def test_apply_floor_removes_low_scores():
    """Pages below floor are removed, page 0 always kept."""
    from eval.pixel_density.sweep_rescue import _apply_floor

    scores = np.array([5.0, 12.0, 15.0, 8.0, 14.0])
    matches = [0, 1, 2, 3, 4]
    result = _apply_floor(matches, scores, floor=10.0)
    assert result == [0, 1, 2, 4]  # page 3 (score=8) removed, page 0 kept despite score=5


def test_apply_floor_keeps_page_0_always():
    """Page 0 is never removed by floor, even if its score is below."""
    from eval.pixel_density.sweep_rescue import _apply_floor

    scores = np.array([1.0, 20.0, 20.0])
    matches = [0, 1, 2]
    result = _apply_floor(matches, scores, floor=15.0)
    assert 0 in result


def test_apply_floor_zero_is_noop():
    """Floor of 0.0 removes nothing."""
    from eval.pixel_density.sweep_rescue import _apply_floor

    scores = np.array([5.0, 3.0, 8.0])
    matches = [0, 1, 2]
    result = _apply_floor(matches, scores, floor=0.0)
    assert result == [0, 1, 2]


def test_suppress_consecutive_picks_higher_score():
    """When pages N and N+1 are both detected, keep the one with higher score."""
    from eval.pixel_density.sweep_rescue import _suppress_consecutive

    scores = np.array([5.0, 14.0, 15.0, 3.0, 18.0])
    matches = [0, 1, 2, 4]  # pages 1 and 2 are consecutive
    result = _suppress_consecutive(matches, scores)
    assert 2 in result  # page 2 has higher score (15 > 14)
    assert 1 not in result


def test_suppress_consecutive_no_pairs():
    """When no consecutive pairs exist, nothing is removed."""
    from eval.pixel_density.sweep_rescue import _suppress_consecutive

    scores = np.array([5.0, 14.0, 3.0, 15.0, 3.0])
    matches = [0, 1, 3]  # no consecutive detections
    result = _suppress_consecutive(matches, scores)
    assert result == [0, 1, 3]


def test_suppress_consecutive_triple():
    """Three consecutive detections: keep the one with the highest score + page 0."""
    from eval.pixel_density.sweep_rescue import _suppress_consecutive

    scores = np.array([5.0, 14.0, 18.0, 12.0, 3.0])
    matches = [0, 1, 2, 3]  # all four form one consecutive run
    result = _suppress_consecutive(matches, scores)
    assert 0 in result  # page 0 always kept
    assert 2 in result  # highest score in the run
    assert 1 not in result
    assert 3 not in result
    assert len(result) == 2


def test_suppress_consecutive_keeps_page_0_wins():
    """Page 0 is kept when it has the highest score in its run."""
    from eval.pixel_density.sweep_rescue import _suppress_consecutive

    scores = np.array([20.0, 15.0, 3.0])
    matches = [0, 1]
    result = _suppress_consecutive(matches, scores)
    assert 0 in result  # page 0 wins on score AND is always kept
    assert 1 not in result


def test_suppress_consecutive_keeps_page_0_loses():
    """Page 0 is kept even when it loses on score — both survive."""
    from eval.pixel_density.sweep_rescue import _suppress_consecutive

    scores = np.array([10.0, 20.0, 3.0])
    matches = [0, 1]
    result = _suppress_consecutive(matches, scores)
    assert 0 in result  # page 0 always kept (exemption)
    assert 1 in result  # page 1 kept as best in run
    # Note: both survive. This is by design — page 0 is sacred.


def test_scorer_v3_returns_list_of_ints():
    """scorer_v3() returns cover page indices with post-processing applied."""
    from eval.pixel_density.sweep_rescue import scorer_v3

    pages = np.zeros((8, 100, 80), dtype=np.uint8)
    matches = scorer_v3(pages)
    assert isinstance(matches, list)
    assert all(isinstance(i, int) for i in matches)
    assert 0 in matches


def test_scorer_v3_floor_0_consecutive_off_equals_rescue_c():
    """With floor=0 and suppress=False, V3 should equal rescue_c."""
    from eval.pixel_density.sweep_rescue import scorer_rescue_c, scorer_v3

    rng = np.random.RandomState(42)
    pages = rng.randint(0, 256, size=(20, 100, 80), dtype=np.uint8)
    rescue_c = scorer_rescue_c(pages)
    v3_noop = scorer_v3(pages, floor=0.0, suppress_consecutive=False)
    assert rescue_c == v3_noop


@pytest.fixture()
def _needs_samples():
    """Skip if sample PDFs are not available."""
    if not Path("data/samples/QUEVEDO_1.pdf").exists():
        pytest.skip("Sample PDFs not available")


def test_v3_floor_reduces_detections_on_few_doc_pdf(_needs_samples):
    """V3 with floor should detect fewer covers than without floor on a low-doc-ratio PDF.

    QUEVEDO_2 has 2 documents in ~8 pages — the percentile threshold over-detects.
    The floor should filter out spurious detections with low absolute scores.
    """
    from eval.pixel_density.cache import ensure_cache
    from eval.pixel_density.sweep_rescue import scorer_v3

    pages = ensure_cache("data/samples/QUEVEDO_2.pdf", dpi=100)
    # Without floor, suppress off: percentile marks ~25% as covers
    matches_no_floor = scorer_v3(pages, floor=0.0, suppress_consecutive=False)
    # With floor: should detect fewer (only pages with genuinely high bilateral scores)
    # TODO: Replace 10.0 with the actual floor value from sweep_v3 winner.
    matches_with_floor = scorer_v3(pages, floor=10.0, suppress_consecutive=False)
    # The floor version should have equal or fewer detections
    assert len(matches_with_floor) <= len(matches_no_floor), (
        "Floor should not increase detections"
    )


def test_shift_to_cover_shifts_when_similar():
    """When previous page has score within sim ratio, shift detection left."""
    from eval.pixel_density.sweep_rescue import _shift_to_cover

    scores = np.array([3.0, 18.0, 18.1, 5.0, 15.0])
    peaks = [0, 2]
    result = _shift_to_cover(peaks, scores, score_similarity=0.99)
    assert 1 in result
    assert 2 not in result


def test_shift_to_cover_no_shift_when_dissimilar():
    """When previous page score is much lower, no shift."""
    from eval.pixel_density.sweep_rescue import _shift_to_cover

    scores = np.array([3.0, 8.0, 18.0, 5.0])
    peaks = [0, 2]
    result = _shift_to_cover(peaks, scores, score_similarity=0.99)
    assert 2 in result
    assert 1 not in result


def test_shift_to_cover_keeps_page_0():
    """Page 0 is never shifted. Page 1 shifts to 0 and deduplicates."""
    from eval.pixel_density.sweep_rescue import _shift_to_cover

    scores = np.array([18.0, 17.9, 5.0])
    peaks = [0, 1]
    result = _shift_to_cover(peaks, scores, score_similarity=0.99)
    assert 0 in result
    assert 1 not in result
    assert len(result) == 1


def test_shift_to_cover_deduplicates():
    """If shift would create a duplicate, result is deduplicated."""
    from eval.pixel_density.sweep_rescue import _shift_to_cover

    scores = np.array([18.0, 18.0, 18.1, 5.0])
    peaks = [0, 2]
    result = _shift_to_cover(peaks, scores, score_similarity=0.99)
    assert result == [0, 1]


def test_scorer_find_peaks_returns_list_of_ints():
    """scorer_find_peaks() returns cover page indices."""
    from eval.pixel_density.sweep_rescue import scorer_find_peaks

    rng = np.random.RandomState(42)
    pages = rng.randint(0, 256, size=(20, 100, 80), dtype=np.uint8)
    matches = scorer_find_peaks(pages)
    assert isinstance(matches, list)
    assert all(isinstance(i, int) for i in matches)
    assert 0 in matches


def test_scorer_find_peaks_page_0_always_included():
    """Page 0 is always in the result even on flat signal (all pages identical)."""
    from eval.pixel_density.sweep_rescue import scorer_find_peaks

    pages = np.full((10, 100, 80), 128, dtype=np.uint8)
    matches = scorer_find_peaks(pages)
    assert 0 in matches


def test_scorer_find_peaks_no_shift_when_disabled():
    """With shift_covers=False, no displacement correction is applied."""
    from eval.pixel_density.sweep_rescue import scorer_find_peaks

    rng = np.random.RandomState(42)
    pages = rng.randint(0, 256, size=(20, 100, 80), dtype=np.uint8)
    with_shift = scorer_find_peaks(pages, shift_covers=True)
    without_shift = scorer_find_peaks(pages, shift_covers=False)
    assert isinstance(with_shift, list)
    assert isinstance(without_shift, list)
    assert 0 in with_shift
    assert 0 in without_shift
