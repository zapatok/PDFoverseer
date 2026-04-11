"""Tests for the DiT-based cover detection scorers."""

from __future__ import annotations

import numpy as np

from eval.pixel_density.scorer_dit import (
    score_dit_find_peaks,
    score_dit_percentile,
)


def test_score_dit_find_peaks_returns_sorted_indices_with_page_0():
    """Any scorer output must include page 0 and be sorted ascending."""
    rng = np.random.default_rng(0)
    embeddings = rng.standard_normal((10, 768)).astype(np.float32)
    covers = score_dit_find_peaks(embeddings, prominence=0.1, distance=1)
    assert 0 in covers
    assert covers == sorted(covers)


def test_score_dit_percentile_returns_sorted_indices_with_page_0():
    rng = np.random.default_rng(0)
    embeddings = rng.standard_normal((10, 768)).astype(np.float32)
    covers = score_dit_percentile(embeddings, percentile=75.0)
    assert 0 in covers
    assert covers == sorted(covers)


def test_score_dit_synthetic_singleton_covers_in_uniform_content():
    """A distinctive 'cover' page flanked by uniform content should be a peak.

    With bilateral-min cosine, a page only becomes a peak when it differs from
    BOTH neighbors. This mirrors the production assumption: a real cover page
    differs from the previous document's last page AND from its own body
    content, so min(left, right) is large at covers and small everywhere else.
    """
    rng = np.random.default_rng(42)
    content = rng.standard_normal(768).astype(np.float32)
    cover_a = rng.standard_normal(768).astype(np.float32)
    cover_b = rng.standard_normal(768).astype(np.float32)
    embeddings = np.vstack(
        [
            cover_a[None, :],  # 0  - cover (always force-included)
            np.tile(content, (4, 1)),  # 1-4 - content
            cover_b[None, :],  # 5  - cover (distinct from both neighbors)
            np.tile(content, (4, 1)),  # 6-9 - content
        ]
    )
    covers = score_dit_find_peaks(embeddings, prominence=0.1, distance=1)
    assert 0 in covers
    assert 5 in covers
    # Should not over-detect inside the uniform content runs.
    assert len(covers) <= 3
