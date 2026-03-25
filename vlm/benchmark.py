"""Benchmark runner — evaluate VLM OCR on corpus images."""
from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import cv2

from vlm.client import query, warmup
from vlm.ground_truth import load_ground_truth, load_corpus, OCR_ALL_DIR
from vlm.parser import parse
from vlm.preprocess import apply_preprocess

log = logging.getLogger(__name__)
RESULTS_DIR = Path("vlm/results")

# Defaults matching the first prompt candidate in params.py
DEFAULT_CONFIG = {
    "prompt": "Read the page number pattern 'Pagina N de M' from this image. Reply only with N/M.",
    "temperature": 0.0,
    "top_p": 1.0,
    "seed": 42,
    "preprocess": "none",
    "upscale": 1.0,
    "model": "gemma3:4b",
}


def compute_metrics(results: list[dict]) -> dict:
    """Compute accuracy and latency metrics from benchmark results.

    Each result dict has: parsed, ground_truth, latency_ms.
    """
    if not results:
        return {
            "exact_match": 0.0, "curr_match": 0.0, "parse_rate": 0.0,
            "mean_latency_ms": 0.0, "p95_latency_ms": 0.0,
        }

    n_total = len(results)
    n_parsed = sum(1 for r in results if r["parsed"] is not None)
    with_gt = [r for r in results if r["ground_truth"] is not None]
    n_with_gt = len(with_gt)

    n_exact = sum(1 for r in with_gt if r["parsed"] == r["ground_truth"])
    n_curr = sum(
        1 for r in with_gt
        if r["parsed"] is not None and r["parsed"][0] == r["ground_truth"][0]
    )

    times = [r["latency_ms"] for r in results if r["latency_ms"] > 0]
    mean_lat = statistics.mean(times) if times else 0.0
    p95_lat = (sorted(times)[int(len(times) * 0.95)] if len(times) >= 2
               else (times[0] if times else 0.0))

    return {
        "exact_match": n_exact / n_with_gt if n_with_gt else 0.0,
        "curr_match": n_curr / n_with_gt if n_with_gt else 0.0,
        "parse_rate": n_parsed / n_total if n_total else 0.0,
        "mean_latency_ms": mean_lat,
        "p95_latency_ms": p95_lat,
    }


def run(config: dict | None = None, failures_only: bool = True,
        sample_n: int | None = None) -> dict:
    """Run benchmark with given config.

    Returns dict with config, metrics, and per-image results.
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    gt = load_ground_truth()
    corpus = load_corpus(failures_only=failures_only, sample_n=sample_n)

    log.info("Benchmark: %d images, failures_only=%s, model=%s", len(corpus), failures_only, cfg["model"])
    warmup(model=cfg["model"])

    results = []
    for i, entry in enumerate(corpus):
        img_path = OCR_ALL_DIR / entry.image_path
        img = cv2.imread(str(img_path))
        if img is None:
            results.append({
                "nickname": entry.pdf_nickname, "page": entry.page_num,
                "parsed": None, "ground_truth": gt.get((entry.pdf_nickname, entry.page_num)),
                "latency_ms": 0.0, "raw_text": "", "error": f"imread failed: {img_path}",
            })
            continue

        img = apply_preprocess(img, mode=cfg["preprocess"], upscale=cfg["upscale"])

        # Write preprocessed image to temp file (not in data dir)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            cv2.imwrite(tmp.name, img)
            tmp_file = Path(tmp.name)

        try:
            resp = query(
                str(tmp_file),
                prompt=cfg["prompt"],
                model=cfg["model"],
                temperature=cfg["temperature"],
                top_p=cfg["top_p"],
                seed=cfg["seed"],
            )
        finally:
            tmp_file.unlink(missing_ok=True)

        parsed = parse(resp["raw_text"]) if not resp["error"] else None
        gt_val = gt.get((entry.pdf_nickname, entry.page_num))

        results.append({
            "nickname": entry.pdf_nickname, "page": entry.page_num,
            "parsed": parsed, "ground_truth": gt_val,
            "latency_ms": resp["latency_ms"], "raw_text": resp["raw_text"],
            "error": resp["error"],
        })

        if (i + 1) % 50 == 0 or i == 0:
            pct = (i + 1) / len(corpus) * 100
            log.info("  %d/%d (%.0f%%)", i + 1, len(corpus), pct)

    metrics = compute_metrics(results)
    return {
        "config": cfg,
        "metrics": metrics,
        "n_images": len(corpus),
        "n_with_gt": sum(1 for r in results if r["ground_truth"] is not None),
        "results": results,
        "run_at": datetime.now().isoformat(),
    }


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="VLM OCR Benchmark")
    parser.add_argument("--full", action="store_true", help="Run on all images (not just failures)")
    parser.add_argument("--sample", type=int, default=None, help="Random sample of N images")
    parser.add_argument("--prompt", type=str, default=None)
    parser.add_argument("--temp", type=float, default=None)
    parser.add_argument("--top-p", type=float, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--preprocess", type=str, default=None)
    parser.add_argument("--upscale", type=float, default=None)
    parser.add_argument("--model", type=str, default=None, help="Ollama model name (e.g. gemma3:4b, minicpm-v)")
    args = parser.parse_args()

    cfg = {}
    if args.prompt is not None: cfg["prompt"] = args.prompt
    if args.temp is not None: cfg["temperature"] = args.temp
    if args.top_p is not None: cfg["top_p"] = args.top_p
    if args.seed is not None: cfg["seed"] = args.seed
    if args.preprocess is not None: cfg["preprocess"] = args.preprocess
    if args.upscale is not None: cfg["upscale"] = args.upscale
    if args.model is not None: cfg["model"] = args.model

    result = run(config=cfg, failures_only=not args.full, sample_n=args.sample)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"benchmark_{ts}.json"
    # Strip raw_text from saved results to keep file size down
    save_results = []
    for r in result["results"]:
        sr = {k: v for k, v in r.items() if k != "raw_text"}
        # Convert tuples to lists for JSON
        if sr["parsed"] is not None:
            sr["parsed"] = list(sr["parsed"])
        if sr["ground_truth"] is not None:
            sr["ground_truth"] = list(sr["ground_truth"])
        save_results.append(sr)
    save_data = {**result, "results": save_results}
    out_path.write_text(json.dumps(save_data, indent=2))

    m = result["metrics"]
    print(f"\n{'='*60}")
    print(f"Results: {out_path}")
    print(f"Images: {result['n_images']} | With GT: {result['n_with_gt']}")
    print(f"exact_match:  {m['exact_match']:.1%}")
    print(f"curr_match:   {m['curr_match']:.1%}")
    print(f"parse_rate:   {m['parse_rate']:.1%}")
    print(f"mean_latency: {m['mean_latency_ms']:.0f}ms")
    print(f"p95_latency:  {m['p95_latency_ms']:.0f}ms")


if __name__ == "__main__":
    main()
