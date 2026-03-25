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
