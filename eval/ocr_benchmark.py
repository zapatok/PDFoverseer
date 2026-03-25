"""
OCR Benchmark: EasyOCR vs PaddleOCR on ART_670 pre-captured images.

Loads 2719 images from data/ocr_all/ART_670/, runs each engine sequentially,
scores against 796 VLM-verified ground truth entries.

Usage:
    source .venv-cuda/Scripts/activate
    python eval/ocr_benchmark.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

# Add project root so eval/ocr_benchmark.py can import core.utils
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.utils import _parse

# ── Paths ─────────────────────────────────────────────────────────────────────

FIXTURE_PATH = Path("eval/fixtures/real/ART_670.json")
IMAGES_DIR   = Path("data/ocr_all/ART_670")
OUTPUT_PATH  = Path("data/benchmark_results.json")
TOTAL_PAGES  = 2719


# ── Helper functions ──────────────────────────────────────────────────────────

def load_fixture(path: str | Path) -> dict[int, tuple[int, int, str]]:
    """
    Load a fixture JSON file.

    Returns:
        {pdf_page: (curr, total, method)} for each entry in the fixture.
    """
    with open(path) as f:
        data = json.load(f)
    return {
        r["pdf_page"]: (r["curr"], r["total"], r["method"])
        for r in data["reads"]
    }


def extract_paddle_text(result) -> str:
    """
    Flatten PaddleOCR nested result into a single string.

    PaddleOCR returns: [[  [bbox, (text, conf)], ... ]]
    The outer list is per-image (always 1 image here), the inner list is
    per-detected-region.
    """
    if not result:
        return ""
    # result is a list with one element per image
    lines = result[0] if result else []
    if not lines:
        return ""
    parts = []
    for item in lines:
        if item and len(item) >= 2:
            text_conf = item[1]
            if text_conf and len(text_conf) >= 1:
                parts.append(str(text_conf[0]))
    return " ".join(parts)


def score_page(
    curr: Optional[int],
    total: Optional[int],
    gt_curr: int,
    gt_total: int,
) -> str:
    """
    Compare OCR result against ground truth.

    Returns:
        "hit"  — both curr and total match ground truth
        "miss" — result was parsed but does not match ground truth
        "none" — OCR returned no parseable result
    """
    if curr is None:
        return "none"
    if curr == gt_curr and total == gt_total:
        return "hit"
    return "miss"


def load_images() -> list[tuple[int, np.ndarray]]:
    """
    Load all 2719 ART_670 page images.

    Returns:
        List of (pdf_page, bgr_image) sorted by page number.
        Images are loaded as BGR (cv2 default).
    """
    images = []
    for i in range(1, TOTAL_PAGES + 1):
        path = IMAGES_DIR / f"p{i:03d}.png"
        img = cv2.imread(str(path))
        if img is None:
            print(f"  WARNING: missing image {path}", flush=True)
            continue
        images.append((i, img))
    return images


# ── Engine: EasyOCR ───────────────────────────────────────────────────────────

def run_easyocr(
    images: list[tuple[int, np.ndarray]],
) -> list[dict]:
    """
    Run EasyOCR on all images sequentially.

    Uses grayscale input to match production pipeline behavior
    (core/pipeline.py converts BGR to gray before calling readtext).

    Warm-up: runs first image before timing begins.
    Timing: covers readtext() call only, not _parse().

    Returns:
        List of {pdf_page, curr, total, ms} dicts.
        curr/total are None if _parse() found nothing.
    """
    import easyocr
    import torch

    print("EasyOCR: initializing...", flush=True)
    reader = easyocr.Reader(["es", "en"], gpu=True, verbose=False)
    print("EasyOCR: ready", flush=True)

    # Warm-up (excluded from timing)
    _, bgr0 = images[0]
    gray0 = cv2.cvtColor(bgr0, cv2.COLOR_BGR2GRAY)
    reader.readtext(gray0, detail=0, paragraph=True)
    print("EasyOCR: warm-up done, starting timed run...", flush=True)

    results = []
    for i, (pdf_page, bgr) in enumerate(images):
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        t0 = time.perf_counter()
        texts = reader.readtext(gray, detail=0, paragraph=True)
        ms = (time.perf_counter() - t0) * 1000

        text = " ".join(texts)
        curr, total = _parse(text)
        results.append({"pdf_page": pdf_page, "curr": curr, "total": total, "ms": round(ms, 1)})

        if (i + 1) % 200 == 0:
            print(f"  EasyOCR: {i + 1}/{len(images)} pages", flush=True)

    del reader
    torch.cuda.empty_cache()
    print("EasyOCR: done, GPU memory released", flush=True)
    return results


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Loading images...", flush=True)
    images = load_images()
    print(f"Loaded {len(images)} images", flush=True)

    print("\n--- EasyOCR pass ---")
    easy_results = run_easyocr(images)

    # Minimal progress report
    easy_found = sum(1 for r in easy_results if r["curr"] is not None)
    print(f"EasyOCR: parsed {easy_found}/{len(images)} pages")

    # Placeholder for PaddleOCR and scoring (added in Chunk 3 and 4)
    print("\n[Chunk 2 complete — PaddleOCR and scoring pending]")


if __name__ == "__main__":
    main()
