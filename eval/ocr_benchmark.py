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
    Flatten PaddleOCR result into a single string.

    PaddleOCR 3.x returns a list of OCRResult objects (one per image).
    Each result has a 'rec_texts' key with a list of recognized strings.

    Falls back to the 2.x nested-list format for compatibility:
    [[  [bbox, (text, conf)], ... ]]
    """
    if not result:
        return ""
    first = result[0]
    # PaddleOCR 3.x: OCRResult dict-like with rec_texts
    if hasattr(first, "__getitem__"):
        try:
            texts = first["rec_texts"]
            if isinstance(texts, list):
                return " ".join(str(t) for t in texts)
        except (KeyError, TypeError):
            pass
    # PaddleOCR 2.x fallback: list of [bbox, (text, conf)]
    lines = first if first else []
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


# ── Engine: PaddleOCR ─────────────────────────────────────────────────────────

def run_paddleocr(
    images: list[tuple[int, np.ndarray]],
) -> list[dict]:
    """
    Run PaddleOCR on all images sequentially.

    Uses BGR input (PaddleOCR accepts numpy BGR arrays directly).
    use_angle_cls=False: skip orientation classifier (not needed for fixed-crop pages).
    lang="en": English model; handles mixed Spanish/English well enough for digit patterns.

    Warm-up: runs first image before timing begins.
    Timing: covers ocr() call only, not extract_paddle_text() or _parse().

    Returns:
        List of {pdf_page, curr, total, ms} dicts.
        curr/total are None if _parse() found nothing.
    """
    from paddleocr import PaddleOCR as _PaddleOCR

    print("PaddleOCR: initializing...", flush=True)
    # PaddleOCR 3.x API: use_angle_cls/use_gpu removed.
    # enable_mkldnn=False avoids ConvertPirAttribute2RuntimeAttribute crash on Windows CPU.
    reader = _PaddleOCR(
        lang="en",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False,
    )
    print("PaddleOCR: ready", flush=True)

    # Warm-up (excluded from timing)
    _, bgr0 = images[0]
    reader.ocr(bgr0)
    print("PaddleOCR: warm-up done, starting timed run...", flush=True)

    results = []
    for i, (pdf_page, bgr) in enumerate(images):
        t0 = time.perf_counter()
        raw = reader.ocr(bgr)
        ms = (time.perf_counter() - t0) * 1000

        text = extract_paddle_text(raw)
        curr, total = _parse(text)
        results.append({"pdf_page": pdf_page, "curr": curr, "total": total, "ms": round(ms, 1)})

        if (i + 1) % 200 == 0:
            print(f"  PaddleOCR: {i + 1}/{len(images)} pages", flush=True)

    del reader
    try:
        import paddle
        paddle.device.cuda.empty_cache()
    except Exception:
        pass
    print("PaddleOCR: done, GPU memory released", flush=True)
    return results


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Loading images...", flush=True)
    images = load_images()
    print(f"Loaded {len(images)} images", flush=True)

    print("\n--- EasyOCR pass ---")
    easy_results = run_easyocr(images)
    easy_found = sum(1 for r in easy_results if r["curr"] is not None)
    print(f"EasyOCR: parsed {easy_found}/{len(images)} pages")

    print("\n--- PaddleOCR pass ---")
    paddle_results = run_paddleocr(images)
    paddle_found = sum(1 for r in paddle_results if r["curr"] is not None)
    print(f"PaddleOCR: parsed {paddle_found}/{len(images)} pages")

    # Placeholder for scoring and output (added in Chunk 4)
    print("\n[Chunk 3 complete — scoring and output pending]")


if __name__ == "__main__":
    main()
