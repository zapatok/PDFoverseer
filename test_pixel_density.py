import numpy as np
import pytest
from pixel_density import (
    # scalar
    dark_ratio,
    find_matches,
    auto_threshold,
    ref_band,
    find_matches_in_band,
    page_breaks,
    # grid
    dark_ratio_grid,
    median_vector,
    l2_distance,
    find_matches_vector,
    auto_threshold_vector,
    ref_band_vector,
    find_matches_vector_in_band,
    page_breaks_vector,
    cluster_pages_vector,
    hybrid_mode_vector,
)


# ─── Scalar — original ────────────────────────────────────────────────────────

def test_dark_ratio_all_black():
    img = np.zeros((10, 10), dtype=np.uint8)
    assert dark_ratio(img) == 1.0

def test_dark_ratio_all_white():
    img = np.full((10, 10), 255, dtype=np.uint8)
    assert dark_ratio(img) == 0.0

def test_dark_ratio_half():
    img = np.zeros((10, 10), dtype=np.uint8)
    img[:5, :] = 200
    assert dark_ratio(img) == pytest.approx(0.5)

def test_find_matches_basic():
    ratios = [0.10, 0.30, 0.32, 0.50, 0.29]
    matches = find_matches(ratios, ref_idx=1, threshold=0.05)
    assert set(matches) == {1, 2, 4}

def test_find_matches_always_includes_ref():
    ratios = [0.10, 0.50, 0.90]
    matches = find_matches(ratios, ref_idx=1, threshold=0.01)
    assert 1 in matches

def test_find_matches_boundary():
    ratios = [0.20, 0.30, 0.38]
    matches = find_matches(ratios, ref_idx=1, threshold=0.08)
    assert 2 in matches

def test_auto_threshold_period_based():
    rng = np.random.default_rng(42)
    ratios = rng.uniform(0.01, 0.10, 100).tolist()
    ref_indices = [0, 4, 8]
    ref_value = 0.05
    t, period, expected = auto_threshold(ratios, ref_value, ref_indices)
    assert period == 4.0
    assert expected == 25
    assert t > 0
    matches = [r for r in ratios if abs(r - ref_value) <= t]
    assert 20 <= len(matches) <= 30

def test_auto_threshold_single_ref():
    ratios = [0.01, 0.02, 0.05, 0.05, 0.06, 0.03, 0.04, 0.05]
    t, period, expected = auto_threshold(ratios, 0.05, [2])
    assert period == 4.0
    assert expected == 2
    assert t > 0

def test_auto_threshold_returns_positive():
    ratios = [0.01, 0.02, 0.05, 0.05, 0.06]
    t, _, _ = auto_threshold(ratios, 0.05, [0, 2, 4])
    assert t > 0


# ─── Scalar — ref_band ────────────────────────────────────────────────────────

def test_ref_band_symmetric():
    ratios = [0.0] * 10
    ratios[0] = 0.10
    ratios[1] = 0.20
    ratios[2] = 0.20
    ref_value, lower, upper = ref_band(ratios, [0, 1, 2])
    assert ref_value == pytest.approx((0.10 + 0.20 + 0.20) / 3)
    assert lower == pytest.approx((0.10 + ref_value) / 2)
    assert upper == pytest.approx((ref_value + 0.20) / 2)

def test_ref_band_single_ref_degenerate():
    ratios = [0.05, 0.90, 0.20]
    ref_value, lower, upper = ref_band(ratios, [0])
    assert ref_value == pytest.approx(0.05)
    assert lower == pytest.approx(0.05)
    assert upper == pytest.approx(0.05)

def test_ref_band_lower_le_ref_le_upper():
    ratios = [0.05, 0.08, 0.06, 0.50, 0.90]
    ref_value, lower, upper = ref_band(ratios, [0, 1, 2])
    assert lower <= ref_value <= upper

def test_ref_band_tight_when_refs_similar():
    ratios = [0.100, 0.101, 0.102] + [0.9] * 7
    rv, lo, hi = ref_band(ratios, [0, 1, 2])
    assert (hi - lo) < 0.005

def test_ref_band_wide_when_refs_spread():
    ratios = [0.10, 0.50, 0.90] + [0.0] * 7
    rv, lo, hi = ref_band(ratios, [0, 1, 2])
    assert (hi - lo) > 0.3

def test_find_matches_in_band_basic():
    ratios = [0.05, 0.15, 0.25, 0.35, 0.45]
    matches = find_matches_in_band(ratios, lower=0.10, upper=0.30)
    assert set(matches) == {1, 2}

def test_find_matches_in_band_inclusive():
    ratios = [0.10, 0.20, 0.30]
    matches = find_matches_in_band(ratios, lower=0.10, upper=0.30)
    assert set(matches) == {0, 1, 2}

def test_find_matches_in_band_empty():
    ratios = [0.01, 0.02, 0.03]
    matches = find_matches_in_band(ratios, lower=0.50, upper=0.60)
    assert matches == []


# ─── Scalar — page_breaks (Option 4) ──────────────────────────────────────────

def test_page_breaks_always_includes_zero():
    matches = page_breaks([0.1], min_drop=0.5)
    assert matches == [0]

def test_page_breaks_detects_drops():
    ratios = [0.5, 0.4, 0.1, 0.8, 0.2]
    matches = page_breaks(ratios, min_drop=0.2)
    assert matches == [0, 2, 4]

def test_page_breaks_ignores_increases():
    ratios = [0.1, 0.9]
    matches = page_breaks(ratios, min_drop=0.1)
    assert matches == [0]


# ─── Grid — original ──────────────────────────────────────────────────────────

def test_dark_ratio_grid_shape():
    img = np.zeros((40, 40), dtype=np.uint8)
    v = dark_ratio_grid(img, 4)
    assert v.shape == (16,)

def test_dark_ratio_grid_all_black():
    img = np.zeros((40, 40), dtype=np.uint8)
    v = dark_ratio_grid(img, 4)
    np.testing.assert_array_almost_equal(v, np.ones(16))

def test_dark_ratio_grid_all_white():
    img = np.full((40, 40), 255, dtype=np.uint8)
    v = dark_ratio_grid(img, 4)
    np.testing.assert_array_almost_equal(v, np.zeros(16))

def test_dark_ratio_grid_top_half_dark():
    img = np.full((40, 40), 255, dtype=np.uint8)
    img[:20, :] = 0
    v = dark_ratio_grid(img, 4)
    assert np.all(v[:8] > 0.9)
    assert np.all(v[8:] < 0.1)

def test_dark_ratio_grid_shape_3x3():
    img = np.zeros((60, 60), dtype=np.uint8)
    v = dark_ratio_grid(img, 3)
    assert v.shape == (9,)

def test_median_vector_basic():
    vecs = [
        np.array([0.1, 0.5, 0.9]),
        np.array([0.2, 0.4, 0.8]),
        np.array([0.3, 0.6, 0.7]),
    ]
    med = median_vector(vecs)
    np.testing.assert_array_almost_equal(med, [0.2, 0.5, 0.8])

def test_l2_distance_zero():
    v = np.array([0.1, 0.2, 0.3])
    assert l2_distance(v, v) == pytest.approx(0.0)

def test_l2_distance_known():
    v   = np.array([3.0, 0.0])
    ref = np.array([0.0, 4.0])
    assert l2_distance(v, ref) == pytest.approx(5.0)

def test_find_matches_vector_always_includes_ref():
    ref = np.array([0.3, 0.3, 0.3, 0.3])
    vectors = [ref.copy(), np.ones(4), np.zeros(4)]
    matches = find_matches_vector(vectors, ref, threshold=0.001)
    assert 0 in matches
    assert 1 not in matches

def test_find_matches_vector_basic():
    ref = np.array([0.5, 0.5])
    close = np.array([0.52, 0.48])
    far   = np.array([0.9, 0.1])
    vectors = [ref.copy(), close, far]
    matches = find_matches_vector(vectors, ref, threshold=0.05)
    assert 0 in matches
    assert 1 in matches
    assert 2 not in matches

def test_auto_threshold_vector_period_from_refs():
    rng = np.random.default_rng(0)
    ref_vector = np.full(4, 0.05)
    vectors = []
    for i in range(100):
        if i % 4 == 0:
            vectors.append(ref_vector + rng.uniform(-0.01, 0.01, 4))
        else:
            vectors.append(rng.uniform(0.3, 0.9, 4))
    ref_indices = [0, 4, 8]
    t, period, expected = auto_threshold_vector(vectors, ref_vector, ref_indices)
    assert period == 4.0
    assert expected == 25
    assert t > 0

def test_auto_threshold_vector_single_ref():
    ref_vector = np.array([0.1, 0.1])
    vectors = [ref_vector + 0.01 * i for i in range(8)]
    t, period, expected = auto_threshold_vector(vectors, ref_vector, [0])
    assert period == 4.0
    assert expected == 2
    assert t > 0


# ─── Grid — ref_band_vector ───────────────────────────────────────────────────

def test_ref_band_vector_lower_le_upper():
    ref_vector = np.array([0.5, 0.5, 0.5, 0.5])
    vectors = [
        ref_vector + np.array([0.01, -0.01,  0.02, -0.02]),
        ref_vector + np.array([0.05,  0.05,  0.05,  0.05]),
        ref_vector + np.array([0.10, -0.10,  0.00,  0.00]),
    ] + [np.zeros(4)] * 7
    lower, upper = ref_band_vector(vectors, ref_vector, [0, 1, 2])
    assert lower <= upper

def test_ref_band_vector_single_ref_degenerate():
    ref_vector = np.array([0.3, 0.3])
    vectors = [ref_vector.copy(), np.array([0.9, 0.1])]
    lower, upper = ref_band_vector(vectors, ref_vector, [0])
    assert lower == pytest.approx(0.0)
    assert upper == pytest.approx(0.0)

def test_ref_band_vector_known_values():
    ref_vector = np.zeros(1)
    vectors = [
        np.array([0.0]),
        np.array([0.2]),
        np.array([0.4]),
    ]
    lower, upper = ref_band_vector(vectors, ref_vector, [0, 1, 2])
    assert lower == pytest.approx(0.1)
    assert upper == pytest.approx(0.3)

def test_find_matches_vector_in_band_basic():
    ref = np.zeros(1)
    vectors = [np.array([x]) for x in [0.05, 0.20, 0.50, 0.80]]
    matches = find_matches_vector_in_band(vectors, ref, lower=0.10, upper=0.30)
    assert set(matches) == {1}

def test_find_matches_vector_in_band_inclusive():
    ref = np.zeros(1)
    vectors = [np.array([0.10]), np.array([0.20]), np.array([0.30])]
    matches = find_matches_vector_in_band(vectors, ref, lower=0.10, upper=0.30)
    assert set(matches) == {0, 1, 2}


# ─── Grid — page_breaks_vector (Option 4) ─────────────────────────────────────

def test_page_breaks_vector_always_includes_zero():
    matches = page_breaks_vector([np.ones(4)], min_l2_jump=0.5)
    assert matches == [0]

def test_page_breaks_vector_detects_jumps():
    p1 = np.zeros(2)
    p2 = np.array([0.1, 0.0]) # jump = 0.1
    p3 = np.array([0.1, 0.5]) # jump = 0.5 ***
    p4 = np.array([0.2, 0.5]) # jump = 0.1
    p5 = np.array([0.9, 0.9]) # jump = ~0.8 ***
    
    vectors = [p1, p2, p3, p4, p5]
    matches = page_breaks_vector(vectors, min_l2_jump=0.4)
    assert matches == [0, 2, 4]


# ─── Grid — cluster_pages_vector (Option 3) ──────────────────────────────────

def test_cluster_pages_vector_separates_majority_minority():
    # 8 "interior" pages (majority)
    interior = [np.ones(2) + np.random.uniform(-0.1, 0.1, 2) for _ in range(8)]
    # 2 "cover" pages (minority)
    covers = [np.zeros(2) + np.random.uniform(-0.1, 0.1, 2) for _ in range(2)]
    
    vectors = interior + covers  # indices 8, 9 are covers
    matches, _, _ = cluster_pages_vector(vectors)
    assert set(matches) == {8, 9}


# ─── Grid — hybrid_mode_vector (Option 4 + 3) ────────────────────────────────

def test_hybrid_mode_vector_filters_then_clusters():
    # p0: cover 1
    # p1..10: interior (no jumps > 0.2)
    # p11: cover 2 (jump!)
    # p12..20: interior (no jumps > 0.2)
    
    p0 = np.zeros(2)
    p1 = np.ones(2)
    interior_1 = [p1 + np.array([0.0, i*0.01]) for i in range(10)]
    
    p11 = np.zeros(2)
    p12 = np.ones(2)
    interior_2 = [p12 + np.array([0.0, i*0.01]) for i in range(9)]
    
    vectors = [p0] + interior_1 + [p11] + interior_2
    # Jumps > 0.2 happen at index 1 (0 -> 1) and index 11 (10 -> 11) and index 12 (11 -> 12).
    # So candidates = [0, 1, 11, 12]
    # Clustering subset: p0 (zero), p1 (ones), p11 (zero), p12 (ones).
    # Cover cluster (minority or equal? equal here, but we force 0 to be included)
    # Actually wait: 2 zeros, 2 ones. Kmeans will pick one. But let's make it unambiguous minority:
    
    # making 3 interiors and 1 cover as candidates to test minority sorting:
    # 0: cover (candidate by default)
    # 1: interior (candidate due to jump from 0)
    # 2: interior (small jump, not candidate)
    # 3: interior (small jump, not candidate)
    # 4: interior (small jump, not candidate)
    
    vectors = [
        np.zeros(2),             # 0: cover [0, 0]
        np.ones(2) * 2,          # 1: interior [2, 2] (jump=2.8)
        np.ones(2) * 2 + [0.1, 0], # 2: interior
        np.ones(2) * 2 + [0.2, 0], # 3: interior
        # jump to [4, 4]
        np.ones(2) * 4,          # 4: interior [4, 4] (jump > 2)
        np.ones(2) * 4,          # 5: interior
        np.ones(2) * 6,          # 6: interior [6, 6] (jump > 2)
    ]
    # Candidates >= 1.0:
    # 0 = [0, 0]
    # 1 = [2, 2]
    # 4 = [4, 4]
    # 6 = [6, 6]
    # The centroid of (1, 4, 6) is [4, 4]. Distance to 0 is ~5.6.
    # K-means should easily group 1, 4, 6 vs 0 (if random seed behaves).
    # To make it absolutely unambiguous, let's just use identical points!
    
    vectors = [
        np.zeros(2),
        np.ones(2),
        np.ones(2) + [0.01, 0],
        np.ones(2),
        np.ones(2),
        np.ones(2) + [2.0, 2.0], # jump here to create another candidate [3, 3]
        np.ones(2) + [2.0, 2.0]
    ]
    # candidates > 0.5:
    # idx 0: [0, 0]
    # idx 1: [1, 1]
    # idx 5: [3, 3]
    # With the new hybrid logic, we cluster JUMPS, not absolute coordinates.
    # We want exactly one big jump.
    # p0: 0, p1: 0 (jump 0)
    # p2: 0, p3: 0 (jump 0)
    # p4: 0, p5: 10 (jump 10) -> index 5 should be the match!
    # p6: 10, p7: 10 (jump 0)
    vectors = [
        np.zeros(2), # 0
        np.zeros(2), # 1
        np.zeros(2), # 2
        np.zeros(2), # 3
        np.zeros(2), # 4
        
        np.array([10., 10.]), # 5 (jump = 14.14)
        np.array([10., 10.]), # 6
        np.array([10., 10.]), # 7
    ]
    # matches will include 0 (forced) and 5.
    matches, th, max_low = hybrid_mode_vector(vectors)
    assert matches == [0, 5]
