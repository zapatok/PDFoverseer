from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pytest


def test_ensure_cache_returns_3d_array(tmp_path):
    """Smoke test with a tiny 2-page synthetic PDF."""
    import fitz

    from eval.pixel_density.cache import ensure_cache

    # Create minimal PDF
    doc = fitz.open()
    for _ in range(2):
        page = doc.new_page(width=100, height=100)
        page.insert_text((10, 50), "Test")
    pdf_path = tmp_path / "test.pdf"
    doc.save(str(pdf_path))
    doc.close()

    arr = ensure_cache(str(pdf_path), dpi=72, cache_dir=tmp_path / "cache")
    assert arr.ndim == 3
    assert arr.shape[0] == 2  # 2 pages
    assert arr.dtype == np.uint8


def test_ensure_cache_loads_from_disk(tmp_path):
    """Second call loads from cache, not re-rendering."""
    import fitz

    from eval.pixel_density.cache import ensure_cache

    doc = fitz.open()
    doc.new_page(width=50, height=50)
    pdf_path = tmp_path / "test.pdf"
    doc.save(str(pdf_path))
    doc.close()

    cache_dir = tmp_path / "cache"
    arr1 = ensure_cache(str(pdf_path), dpi=72, cache_dir=cache_dir)
    arr2 = ensure_cache(str(pdf_path), dpi=72, cache_dir=cache_dir)
    np.testing.assert_array_equal(arr1, arr2)


def test_ensure_cache_different_dpi_separate_files(tmp_path):
    """Different DPI values produce separate cache files."""
    import fitz

    from eval.pixel_density.cache import ensure_cache

    doc = fitz.open()
    doc.new_page(width=50, height=50)
    pdf_path = tmp_path / "test.pdf"
    doc.save(str(pdf_path))
    doc.close()

    cache_dir = tmp_path / "cache"
    arr72 = ensure_cache(str(pdf_path), dpi=72, cache_dir=cache_dir)
    arr100 = ensure_cache(str(pdf_path), dpi=100, cache_dir=cache_dir)
    # Different DPI -> different resolution -> different shapes
    assert arr72.shape != arr100.shape
