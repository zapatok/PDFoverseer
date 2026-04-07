"""Tests for scorer_forms: vertical density feature, Otsu 1D, scorer smoke, ART gate."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

# ── feat_vertical_density ─────────────────────────────────────────────────


def test_vertical_density_shape():
    """Returns shape (2,) for any image."""
    from eval.pixel_density.features import feat_vertical_density

    img = np.random.randint(0, 256, (100, 80), dtype=np.uint8)
    result = feat_vertical_density(img, bottom_frac=0.35)
    assert result.shape == (2,)
    assert result.dtype == np.float64


def test_vertical_density_white_page():
    """All-white page has [0, 0] dark ratios."""
    from eval.pixel_density.features import feat_vertical_density

    img = np.full((100, 80), 255, dtype=np.uint8)
    result = feat_vertical_density(img, bottom_frac=0.35)
    assert result[0] == 0.0
    assert result[1] == 0.0


def test_vertical_density_black_page():
    """All-black page has [1, 1] dark ratios (all pixels < 128)."""
    from eval.pixel_density.features import feat_vertical_density

    img = np.zeros((100, 80), dtype=np.uint8)
    result = feat_vertical_density(img, bottom_frac=0.35)
    assert result[0] == pytest.approx(1.0)
    assert result[1] == pytest.approx(1.0)


def test_vertical_density_bottom_heavy():
    """Page with dark bottom, white top has high bot_dark, low top_dark."""
    from eval.pixel_density.features import feat_vertical_density

    img = np.full((100, 80), 255, dtype=np.uint8)
    img[65:, :] = 0  # bottom 35% is black
    result = feat_vertical_density(img, bottom_frac=0.35)
    assert result[0] == 0.0  # top is white
    assert result[1] == pytest.approx(1.0)  # bottom is black


def test_vertical_density_different_bottom_frac():
    """Changing bottom_frac changes the split point."""
    from eval.pixel_density.features import feat_vertical_density

    img = np.full((100, 80), 255, dtype=np.uint8)
    img[50:, :] = 0  # bottom 50% is black

    r25 = feat_vertical_density(img, bottom_frac=0.25)
    r50 = feat_vertical_density(img, bottom_frac=0.50)
    # With bottom_frac=0.50, bot zone covers exactly the black region
    assert r50[1] == pytest.approx(1.0)
    # With bottom_frac=0.25, bot zone is fully black AND top zone has some black
    assert r25[1] == pytest.approx(1.0)
    assert r25[0] > 0.0  # top zone includes some black pixels


def test_vertical_density_not_in_registry():
    """feat_vertical_density must NOT be in the feature registry."""
    from eval.pixel_density.features import _FEATURE_REGISTRY

    assert "vertical_density" not in _FEATURE_REGISTRY


# ── Otsu 1D + bimodality ──────────────────────────────────────────────────


def test_otsu_bimodal_separation():
    """Otsu on clearly bimodal data separates the two groups."""
    from eval.pixel_density.sweep_forms import otsu_threshold_1d

    rng = np.random.default_rng(42)
    low = rng.normal(0.3, 0.02, 200)
    high = rng.normal(0.8, 0.02, 100)
    data = np.concatenate([low, high])
    thresh = otsu_threshold_1d(data)
    assert 0.34 < thresh < 0.7  # threshold falls between groups


def test_otsu_uniform_data():
    """Otsu on uniform data returns some threshold without crashing."""
    from eval.pixel_density.sweep_forms import otsu_threshold_1d

    data = np.linspace(0.0, 1.0, 100)
    thresh = otsu_threshold_1d(data)
    assert 0.0 <= thresh <= 1.0


def test_bimodal_coefficient_bimodal():
    """Bimodal data has BC >= 0.555."""
    from eval.pixel_density.sweep_forms import bimodal_coefficient

    rng = np.random.default_rng(42)
    low = rng.normal(0.3, 0.02, 300)
    high = rng.normal(0.8, 0.02, 300)
    data = np.concatenate([low, high])
    bc = bimodal_coefficient(data)
    assert bc >= 0.555


def test_bimodal_coefficient_unimodal():
    """Unimodal data has BC < 0.555."""
    from eval.pixel_density.sweep_forms import bimodal_coefficient

    rng = np.random.default_rng(42)
    data = rng.normal(0.5, 0.1, 500)
    bc = bimodal_coefficient(data)
    assert bc < 0.555


# ── scorer_forms ──────────────────────────────────────────────────────────


def test_scorer_forms_returns_list():
    """Scorer returns a list of ints."""
    from eval.pixel_density.sweep_forms import scorer_forms

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (10, 100, 80), dtype=np.uint8)
    result = scorer_forms(pages)
    assert isinstance(result, list)
    assert all(isinstance(i, int) for i in result)


def test_scorer_forms_includes_page_0():
    """Page 0 is always in the result."""
    from eval.pixel_density.sweep_forms import scorer_forms

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (10, 100, 80), dtype=np.uint8)
    result = scorer_forms(pages)
    assert 0 in result


def test_scorer_forms_single_page():
    """Single-page PDF returns [0]."""
    from eval.pixel_density.sweep_forms import scorer_forms

    pages = np.full((1, 100, 80), 200, dtype=np.uint8)
    result = scorer_forms(pages)
    assert result == [0]


def test_scorer_forms_sorted_output():
    """Output is sorted ascending."""
    from eval.pixel_density.sweep_forms import scorer_forms

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (20, 100, 80), dtype=np.uint8)
    result = scorer_forms(pages)
    assert result == sorted(result)


def test_scorer_forms_all_signals():
    """All signal types run without error."""
    from eval.pixel_density.sweep_forms import scorer_forms

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (10, 100, 80), dtype=np.uint8)
    for signal in ("bot_top_ratio", "bot_absolute", "bot_full_ratio", "bot_mid_ratio"):
        result = scorer_forms(pages, signal=signal)
        assert 0 in result


def test_scorer_forms_all_threshold_methods():
    """All threshold methods run without error."""
    from eval.pixel_density.sweep_forms import scorer_forms

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (10, 100, 80), dtype=np.uint8)
    for method in ("otsu", "kmeans_k2", "percentile_50"):
        result = scorer_forms(pages, threshold_method=method)
        assert 0 in result


def test_scorer_forms_otsu_bimodality_guard_identical():
    """Otsu on identical pages triggers bimodality guard (early return path)."""
    from eval.pixel_density.sweep_forms import scorer_forms

    page = np.full((100, 80), 200, dtype=np.uint8)
    pages = np.stack([page] * 10)
    result = scorer_forms(pages, threshold_method="otsu")
    assert result == [0]


def test_scorer_forms_otsu_bimodality_guard_unimodal():
    """Otsu on varied but unimodal pages triggers bimodality guard (BC formula path)."""
    from eval.pixel_density.sweep_forms import scorer_forms

    rng = np.random.default_rng(42)
    pages = np.full((20, 100, 80), 200, dtype=np.uint8)
    for i in range(20):
        noise = rng.integers(0, 10 + i * 2, (100, 80), dtype=np.uint8)
        pages[i] = np.clip(pages[i].astype(np.int16) - noise, 0, 255).astype(np.uint8)
    result = scorer_forms(pages, threshold_method="otsu")
    assert 0 in result


# ── scorer_forms_v2 ────────────────────────────────────────────────────────


def test_scorer_forms_v2_returns_list():
    """Returns a list of ints."""
    from eval.pixel_density.sweep_forms import scorer_forms_v2

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (10, 100, 80), dtype=np.uint8)
    result = scorer_forms_v2(pages, ["cc_stats"])
    assert isinstance(result, list)
    assert all(isinstance(i, int) for i in result)


def test_scorer_forms_v2_includes_page_0():
    """Page 0 is always in the result."""
    from eval.pixel_density.sweep_forms import scorer_forms_v2

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (10, 100, 80), dtype=np.uint8)
    result = scorer_forms_v2(pages, ["cc_stats", "edge_density_grid"])
    assert 0 in result


def test_scorer_forms_v2_single_page():
    """Single-page PDF returns [0]."""
    from eval.pixel_density.sweep_forms import scorer_forms_v2

    pages = np.full((1, 100, 80), 200, dtype=np.uint8)
    result = scorer_forms_v2(pages, ["cc_stats"])
    assert result == [0]


def test_scorer_forms_v2_sorted_output():
    """Output is sorted ascending."""
    from eval.pixel_density.sweep_forms import scorer_forms_v2

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (20, 100, 80), dtype=np.uint8)
    result = scorer_forms_v2(pages, ["cc_stats", "edge_density_grid"])
    assert result == sorted(result)


def test_scorer_forms_v2_identical_pages():
    """All-identical pages returns [0] via pre-normalization check."""
    from eval.pixel_density.sweep_forms import scorer_forms_v2

    page = np.full((100, 80), 128, dtype=np.uint8)
    pages = np.stack([page] * 8)
    result = scorer_forms_v2(pages, ["cc_stats", "dark_ratio_grid"])
    assert result == [0]


def test_scorer_forms_v2_vertical_density_group():
    """vertical_density feature group works (special-cased, not in registry)."""
    from eval.pixel_density.sweep_forms import scorer_forms_v2

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (10, 100, 80), dtype=np.uint8)
    result = scorer_forms_v2(pages, ["vertical_density"])
    assert 0 in result
    assert isinstance(result, list)


def test_scorer_forms_v2_all_feature_groups():
    """All 6 feature groups together run without error."""
    from eval.pixel_density.sweep_forms import scorer_forms_v2

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (10, 100, 80), dtype=np.uint8)
    groups = [
        "vertical_density", "projection_stats", "edge_density_grid",
        "cc_stats", "dark_ratio_grid", "lbp_histogram",
    ]
    result = scorer_forms_v2(pages, groups)
    assert 0 in result


# ── sweep_forms_v2 utilities ──────────────────────────────────────────────


def test_load_ch_gt_covers_and_noncov():
    """load_ch_gt returns non-overlapping covers and noncov sets."""
    from eval.pixel_density.sweep_forms_v2 import load_ch_gt

    covers, noncov = load_ch_gt("eval/fixtures/real/CH_39.json")
    assert len(covers) > 0
    assert len(noncov) > 0
    assert covers.isdisjoint(noncov)
    assert 0 in covers  # first page is always a cover


def test_load_ch_gt_zero_indexed():
    """load_ch_gt returns 0-indexed page indices (pdf_page - 1)."""
    from eval.pixel_density.sweep_forms_v2 import load_ch_gt

    covers, noncov = load_ch_gt("eval/fixtures/real/CH_39.json")
    assert all(i >= 0 for i in covers | noncov)


def test_load_ch_gt_excludes_failed():
    """Pages with method=='failed' are excluded from both sets."""
    import json

    from eval.pixel_density.sweep_forms_v2 import load_ch_gt

    with open("eval/fixtures/real/CH_39.json") as f:
        data = json.load(f)

    failed = {r["pdf_page"] - 1 for r in data["reads"] if r["method"] == "failed"}
    covers, noncov = load_ch_gt("eval/fixtures/real/CH_39.json")
    # failed pages must not appear in either set
    assert failed.isdisjoint(covers | noncov)


def test_compute_f1_perfect():
    """Perfect prediction gives F1=1.0."""
    from eval.pixel_density.sweep_forms_v2 import compute_f1

    covers = {0, 2, 4}
    noncov = {1, 3, 5}
    m = compute_f1(list(covers), covers, noncov)
    assert m["f1"] == pytest.approx(1.0)
    assert m["precision"] == pytest.approx(1.0)
    assert m["recall"] == pytest.approx(1.0)


def test_compute_f1_missed_covers():
    """Missing predicted covers reduces recall."""
    from eval.pixel_density.sweep_forms_v2 import compute_f1

    covers = {0, 2, 4}
    noncov = {1, 3, 5}
    m = compute_f1([0], covers, noncov)  # only page 0 predicted (forced)
    assert m["recall"] < 1.0
    assert m["f1"] < 1.0


def test_compute_f1_failed_pages_ignored():
    """Predicting a failed page (not in covers or noncov) does not count as FP."""
    from eval.pixel_density.sweep_forms_v2 import compute_f1

    covers = {0, 2}
    noncov = {1, 3}
    # page 99 is a "failed" page — not in covers or noncov
    m_with = compute_f1([0, 2, 99], covers, noncov)
    m_without = compute_f1([0, 2], covers, noncov)
    # FP count should be the same
    assert m_with["fp"] == m_without["fp"]
    assert m_with["f1"] == pytest.approx(m_without["f1"])


def test_extract_all_features_shape():
    """extract_all_features returns dict with correct per-group shapes."""
    from eval.pixel_density.sweep_forms_v2 import extract_all_features

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (5, 100, 80), dtype=np.uint8)
    feats = extract_all_features(pages, bottom_frac=0.35)

    expected_shapes = {
        "vertical_density": (5, 2),
        "projection_stats": (5, 6),
        "edge_density_grid": (5, 16),
        "cc_stats": (5, 2),
        "dark_ratio_grid": (5, 64),
        "lbp_histogram": (5, 10),
    }
    for group, shape in expected_shapes.items():
        assert group in feats, f"Missing group: {group}"
        assert feats[group].shape == shape, f"{group}: expected {shape}, got {feats[group].shape}"


def test_scorer_forms_v2_precomputed_matches_live():
    """scorer_forms_v2 with precomputed cache gives same result as live extraction."""
    from eval.pixel_density.sweep_forms import scorer_forms_v2
    from eval.pixel_density.sweep_forms_v2 import extract_all_features

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (8, 100, 80), dtype=np.uint8)

    precomp = extract_all_features(pages)
    r_precomp = scorer_forms_v2(pages, ["cc_stats", "edge_density_grid"],
                                _features_precomputed=precomp)
    r_live = scorer_forms_v2(pages, ["cc_stats", "edge_density_grid"])
    assert r_precomp == r_live


# ── ART safety gate ───────────────────────────────────────────────────────


@pytest.mark.slow
def test_art_safety_gate():
    """Importing scorer_forms must not affect scorer_find_peaks ART results.

    This is the hard gate: if this test fails, the new code is broken.
    Runs scorer_find_peaks on all 6 ART PDFs and verifies exact doc counts.
    """
    # Import scorer_forms first to trigger any side effects
    from eval.pixel_density.cache import ensure_cache
    from eval.pixel_density.sweep_forms import scorer_forms  # noqa: F401
    from eval.pixel_density.sweep_rescue import scorer_find_peaks

    art_pdfs = [
        ("ART_674", "data/samples/ART_674.pdf", 674),
        ("ART_CH_13", "data/samples/arts/ART_CH_13.pdf", 13),
        ("ART_CON_13", "data/samples/arts/ART_CON_13.pdf", 13),
        ("ART_EX_13", "data/samples/arts/ART_EX_13.pdf", 13),
        ("ART_GR_8", "data/samples/arts/ART_GR_8.pdf", 8),
        ("ART_ROC_10", "data/samples/arts/ART_ROC_10.pdf", 10),
    ]

    for name, pdf_path, target in art_pdfs:
        pages = ensure_cache(pdf_path, dpi=100)
        matches = scorer_find_peaks(
            pages, prominence=0.5, distance=2,
            shift_covers=True, score_similarity=0.99,
            rescue_threshold=0.40,
        )
        assert len(matches) == target, (
            f"ART GATE FAILED: {name} expected {target}, got {len(matches)}"
        )
