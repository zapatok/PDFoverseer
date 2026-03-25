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


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_results(
    engine_results: list[dict],
    ground_truth: dict[int, tuple[int, int, str]],
) -> dict:
    """
    Score engine results against ground truth.

    Returns a dict with per-category counts and per-page details.

    Categories:
      direct: GT exists with method="direct" (Tesseract baseline pages)
      vlm:    GT exists with method in (vlm_claude, vlm_opus) (hard pages)
      no_gt:  No GT — engine output tracked as potential recoveries
    """
    cats = {
        "direct": {"hits": 0, "misses": 0, "nones": 0},
        "vlm":    {"hits": 0, "misses": 0, "nones": 0},
    }
    no_gt_found = []   # (pdf_page, curr, total) — engine found something
    no_gt_none  = 0    # engine found nothing, no GT

    _key = {"hit": "hits", "miss": "misses", "none": "nones"}

    for r in engine_results:
        page = r["pdf_page"]
        curr, total = r["curr"], r["total"]

        if page in ground_truth:
            gt_curr, gt_total, method = ground_truth[page]
            cat = "direct" if method == "direct" else "vlm"
            outcome = score_page(curr, total, gt_curr, gt_total)
            cats[cat][_key[outcome]] += 1
        else:
            if curr is not None:
                no_gt_found.append({"pdf_page": page, "curr": curr, "total": total})
            else:
                no_gt_none += 1

    return {
        "direct": cats["direct"],
        "vlm":    cats["vlm"],
        "no_gt_found": no_gt_found,
        "no_gt_none":  no_gt_none,
    }


def avg_ms(results: list[dict]) -> float:
    """Average ms per page. Skips first result to reduce cold-cache noise."""
    times = [r["ms"] for r in results[1:] if r["ms"] > 0]
    return round(sum(times) / len(times), 1) if times else 0.0


def print_report(
    easy_results: list[dict],
    paddle_results: list[dict],
    easy_score: dict,
    paddle_score: dict,
) -> None:
    """Print benchmark summary to console."""

    def pct(hits, total):
        return f"{hits}/{total} ({round(100*hits/total)}%)" if total else "0/0"

    e_d = easy_score["direct"]
    e_v = easy_score["vlm"]
    p_d = paddle_score["direct"]
    p_v = paddle_score["vlm"]

    e_d_total = e_d["hits"] + e_d["misses"] + e_d["nones"]
    e_v_total = e_v["hits"] + e_v["misses"] + e_v["nones"]
    p_d_total = p_d["hits"] + p_d["misses"] + p_d["nones"]
    p_v_total = p_v["hits"] + p_v["misses"] + p_v["nones"]

    print("\n" + "="*70)
    print("ART_670 OCR Benchmark Results")
    print("="*70)
    print(f"\n{'Category':<25} {'EasyOCR':>20} {'PaddleOCR':>20}")
    print("-"*65)
    print(f"{'direct (n=' + str(e_d_total) + ')':<25} {pct(e_d['hits'], e_d_total):>20} {pct(p_d['hits'], p_d_total):>20}")
    print(f"{'vlm/hard (n=' + str(e_v_total) + ')':<25} {pct(e_v['hits'], e_v_total):>20} {pct(p_v['hits'], p_v_total):>20}")

    e_gt_total = e_d_total + e_v_total
    p_gt_total = p_d_total + p_v_total
    e_gt_hits  = e_d["hits"] + e_v["hits"]
    p_gt_hits  = p_d["hits"] + p_v["hits"]
    print(f"{'ALL GT (n=' + str(e_gt_total) + ')':<25} {pct(e_gt_hits, e_gt_total):>20} {pct(p_gt_hits, p_gt_total):>20}")

    print(f"\n{'Potential recoveries':<25} {len(easy_score['no_gt_found']):>20} {len(paddle_score['no_gt_found']):>20}")
    print(f"{'  (no GT, parsed something)'}")
    print(f"{'Complete failures':<25} {easy_score['no_gt_none']:>20} {paddle_score['no_gt_none']:>20}")
    print(f"{'  (no GT, parse = None)'}")

    print(f"\n{'Timing (ms/page)':<25} {avg_ms(easy_results):>20.1f} {avg_ms(paddle_results):>20.1f}")
    print("="*70)

    # Show sample recoveries (first 10 from PaddleOCR)
    paddle_recoveries = paddle_score["no_gt_found"]
    if paddle_recoveries:
        print(f"\nPaddleOCR potential recoveries (first 10 of {len(paddle_recoveries)}):")
        for r in paddle_recoveries[:10]:
            print(f"  p{r['pdf_page']:04d}: {r['curr']}/{r['total']}")

    easy_recoveries = easy_score["no_gt_found"]
    if easy_recoveries:
        print(f"\nEasyOCR potential recoveries (first 10 of {len(easy_recoveries)}):")
        for r in easy_recoveries[:10]:
            print(f"  p{r['pdf_page']:04d}: {r['curr']}/{r['total']}")


def save_json(
    easy_results: list[dict],
    paddle_results: list[dict],
    easy_score: dict,
    paddle_score: dict,
    path: Path,
) -> None:
    """Save full per-page results and summary to JSON."""
    # Build a page-indexed dict for easy lookup
    easy_by_page   = {r["pdf_page"]: r for r in easy_results}
    paddle_by_page = {r["pdf_page"]: r for r in paddle_results}

    pages = []
    for page in range(1, TOTAL_PAGES + 1):
        e = easy_by_page.get(page, {})
        p = paddle_by_page.get(page, {})
        pages.append({
            "pdf_page":  page,
            "easyocr":   {"curr": e.get("curr"), "total": e.get("total"), "ms": e.get("ms")},
            "paddleocr": {"curr": p.get("curr"), "total": p.get("total"), "ms": p.get("ms")},
        })

    output = {
        "fixture":   "eval/fixtures/real/ART_670.json",
        "images_dir": str(IMAGES_DIR),
        "summary": {
            "easyocr":   {
                "direct":  easy_score["direct"],
                "vlm":     easy_score["vlm"],
                "no_gt_found_count": len(easy_score["no_gt_found"]),
                "no_gt_none_count":  easy_score["no_gt_none"],
                "avg_ms":  avg_ms(easy_results),
            },
            "paddleocr": {
                "direct":  paddle_score["direct"],
                "vlm":     paddle_score["vlm"],
                "no_gt_found_count": len(paddle_score["no_gt_found"]),
                "no_gt_none_count":  paddle_score["no_gt_none"],
                "avg_ms":  avg_ms(paddle_results),
            },
        },
        "pages": pages,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ground_truth = load_fixture(FIXTURE_PATH)
    print(f"Fixture loaded: {len(ground_truth)} GT pages")

    print("\nLoading images...", flush=True)
    images = load_images()
    print(f"Loaded {len(images)} images", flush=True)

    print("\n--- EasyOCR pass ---")
    easy_results = run_easyocr(images)

    print("\n--- PaddleOCR pass ---")
    paddle_results = run_paddleocr(images)

    print("\n--- Scoring ---")
    easy_score   = score_results(easy_results, ground_truth)
    paddle_score = score_results(paddle_results, ground_truth)

    print_report(easy_results, paddle_results, easy_score, paddle_score)
    save_json(easy_results, paddle_results, easy_score, paddle_score, OUTPUT_PATH)


if __name__ == "__main__":
    main()
