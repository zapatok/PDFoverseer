"""DiT (Document Image Transformer) embedding extraction with disk cache.

Loads microsoft/dit-base (42M document images pretrained, 768-d CLS output)
and produces one embedding per rendered page. Mirrors the pattern of
cache.py for the pixel-array cache.

Cache layout: data/pixel_density/dit_cache/<stem>_dit_base.npz
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

import numpy as np

from eval.pixel_density.cache import ensure_cache

logger = logging.getLogger(__name__)

DEFAULT_DIT_CACHE_DIR = Path("data/pixel_density/dit_cache")
MODEL_NAME = "microsoft/dit-base"
EMBED_DIM = 768
BATCH_SIZE = 16

# Lazy module-level singletons for the model + processor.
_model = None
_processor = None
_device = None


def _load_model():
    """Lazy-load DiT-base onto CUDA (or CPU fallback) exactly once."""
    global _model, _processor, _device
    if _model is not None:
        return _model, _processor, _device

    import torch
    from transformers import AutoImageProcessor, AutoModel

    _device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("Loading %s on %s...", MODEL_NAME, _device)
    _processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
    _model = AutoModel.from_pretrained(MODEL_NAME).to(_device).eval()
    return _model, _processor, _device


def _cache_path(pdf_path: str, cache_dir: Path) -> Path:
    stem = Path(pdf_path).stem
    return cache_dir / f"{stem}_dit_base.npz"


def _embed_pages(pages: np.ndarray) -> np.ndarray:
    """Run DiT over all pages in batches. Returns (n_pages, 768) float32.

    Args:
        pages: Grayscale uint8 array, shape (n, H, W).
    """
    import torch
    from PIL import Image

    model, processor, device = _load_model()
    n = pages.shape[0]
    out = np.empty((n, EMBED_DIM), dtype=np.float32)

    with torch.no_grad():
        for start in range(0, n, BATCH_SIZE):
            end = min(start + BATCH_SIZE, n)
            # Grayscale -> RGB (repeat channel, DiT expects 3-channel input)
            batch_imgs = [Image.fromarray(pages[i]).convert("RGB") for i in range(start, end)]
            inputs = processor(images=batch_imgs, return_tensors="pt").to(device)
            outputs = model(**inputs)
            # CLS token = first position of last_hidden_state
            cls = outputs.last_hidden_state[:, 0, :].cpu().numpy().astype(np.float32)
            out[start:end] = cls
    return out


def ensure_dit_embeddings(
    pdf_path: str,
    cache_dir: Path | None = None,
) -> np.ndarray:
    """Return cached DiT embeddings for a PDF, computing on first call.

    Args:
        pdf_path: Path to PDF file.
        cache_dir: Override cache directory (default: data/pixel_density/dit_cache/).

    Returns:
        Array of shape (n_pages, 768), dtype float32.
    """
    if cache_dir is None:
        cache_dir = DEFAULT_DIT_CACHE_DIR

    path = _cache_path(pdf_path, cache_dir)
    if path.exists():
        try:
            data = np.load(str(path))
            arr = data["embeddings"]
            logger.info("DiT cache hit: %s (%d pages)", path.name, arr.shape[0])
            return arr
        except Exception:
            logger.warning("DiT cache load failed for %s, recomputing", path.name)

    pages = ensure_cache(pdf_path)  # uses existing pixel cache
    logger.info("Embedding %s with %s...", Path(pdf_path).name, MODEL_NAME)
    t0 = time.perf_counter()
    embeddings = _embed_pages(pages)
    elapsed = time.perf_counter() - t0
    logger.info(
        "Embedded %d pages in %.1fs (%.1f ms/page)",
        embeddings.shape[0],
        elapsed,
        1000 * elapsed / max(embeddings.shape[0], 1),
    )

    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp.npz")
    np.savez_compressed(str(tmp_path), embeddings=embeddings)
    shutil.move(str(tmp_path), str(path))
    logger.info("Cached to %s (%.1f MB)", path.name, path.stat().st_size / 1e6)

    return embeddings
