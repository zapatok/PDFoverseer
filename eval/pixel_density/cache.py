"""Disk cache for rendered PDF page arrays (grayscale uint8).

Rendering ART_674 (2719pp, DPI=100) takes ~100s. This module caches the
rendered arrays to disk so subsequent runs load in ~2-3s.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

import fitz
import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path("data/pixel_density/cache")


def _cache_path(pdf_path: str, dpi: int, cache_dir: Path) -> Path:
    """Compute cache file path: {stem}_{dpi}.npz."""
    stem = Path(pdf_path).stem
    return cache_dir / f"{stem}_{dpi}.npz"


def _render_all(pdf_path: str, dpi: int) -> np.ndarray:
    """Render all pages as grayscale uint8.

    Args:
        pdf_path: Path to PDF file.
        dpi: Rendering DPI.

    Returns:
        Array of shape (n_pages, H, W), dtype uint8.
        All pages padded to max H/W if dimensions vary.
    """
    doc = fitz.open(pdf_path)
    mat = fitz.Matrix(dpi / 72, dpi / 72)

    pages: list[np.ndarray] = []
    for page in doc:
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY, alpha=False)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w)
        pages.append(arr)
    doc.close()

    # Pad to uniform shape (pages can differ by ±1 pixel)
    max_h = max(p.shape[0] for p in pages)
    max_w = max(p.shape[1] for p in pages)
    result = np.full((len(pages), max_h, max_w), 255, dtype=np.uint8)
    for i, p in enumerate(pages):
        result[i, : p.shape[0], : p.shape[1]] = p

    return result


def ensure_cache(
    pdf_path: str,
    dpi: int = 100,
    cache_dir: Path | None = None,
) -> np.ndarray:
    """Return cached rendered page arrays, rendering on first call.

    Args:
        pdf_path: Path to PDF file.
        dpi: Rendering DPI.
        cache_dir: Override cache directory (default: data/pixel_density/cache/).

    Returns:
        Array of shape (n_pages, H, W), dtype uint8.
    """
    if cache_dir is None:
        cache_dir = DEFAULT_CACHE_DIR

    path = _cache_path(pdf_path, dpi, cache_dir)

    # Try loading from cache
    if path.exists():
        try:
            data = np.load(str(path))
            arr = data["pages"]
            logger.info("Cache hit: %s (%d pages)", path.name, arr.shape[0])
            return arr
        except Exception:
            logger.warning("Cache load failed for %s, re-rendering", path.name)

    # Render and save
    logger.info("Rendering %s at DPI=%d...", Path(pdf_path).name, dpi)
    t0 = time.perf_counter()
    arr = _render_all(pdf_path, dpi)
    elapsed = time.perf_counter() - t0
    logger.info("Rendered %d pages in %.1fs", arr.shape[0], elapsed)

    # Atomic write: save to .tmp, replace (Windows-safe)
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp.npz")
    np.savez_compressed(str(tmp_path), pages=arr)
    shutil.move(str(tmp_path), str(path))
    logger.info("Cached to %s (%.1f MB)", path.name, path.stat().st_size / 1e6)

    return arr
