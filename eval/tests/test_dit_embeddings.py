"""Tests for DiT embedding extraction + cache."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from eval.pixel_density.cache import ensure_cache
from eval.pixel_density.dit_embeddings import ensure_dit_embeddings

# Small fixture: 3-page ART PINGON (01).pdf. Real file from the rio_bueno corpus.
# If run on a machine without that file, the test is skipped.
TINY_PDF = Path(
    "A:/informe mensual/MARZO/rio_bueno/7.- ART  Realizadas/ART PINGON 23/ART PINGON (01).pdf"
)


@pytest.mark.skipif(not TINY_PDF.exists(), reason="rio_bueno corpus not present")
def test_ensure_dit_embeddings_shape_and_dtype(tmp_path: Path):
    """Embedding array should be (n_pages, 768) float32."""
    embeddings = ensure_dit_embeddings(str(TINY_PDF), cache_dir=tmp_path)
    pages = ensure_cache(str(TINY_PDF))
    assert embeddings.shape == (pages.shape[0], 768)
    assert embeddings.dtype == np.float32


@pytest.mark.skipif(not TINY_PDF.exists(), reason="rio_bueno corpus not present")
def test_ensure_dit_embeddings_cache_hit_returns_identical_array(tmp_path: Path):
    """Second call should load from cache, not recompute."""
    first = ensure_dit_embeddings(str(TINY_PDF), cache_dir=tmp_path)
    second = ensure_dit_embeddings(str(TINY_PDF), cache_dir=tmp_path)
    np.testing.assert_array_equal(first, second)
