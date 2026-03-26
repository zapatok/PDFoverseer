# eval/ocr_sweep.py
"""
Two-phase OCR preprocessing sweep.

Phase A: test all valid configs against failed pages (rescue rate).
Phase B: test top-N configs against successful pages (regression check).

Usage:
    cd a:/PROJECTS/PDFoverseer
    python eval/ocr_sweep.py              # fast mode, combined tier1+tier2 baseline
    python eval/ocr_sweep.py --full       # full sweep (all pages × all configs)
    python eval/ocr_sweep.py --tier1      # tier1-only: Tesseract params (24 combos)
    python eval/ocr_sweep.py --mini       # mini: PSM11 × best image config (4 combos)
"""
from __future__ import annotations

import csv
import json
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import pytesseract

from core.utils import _parse
from eval.ocr_params import (
    OCR_PARAM_SPACE, OCR_PRODUCTION_PARAMS,
    OCR_TESS_PARAM_SPACE, OCR_TIER1_PARAMS,
)
from eval.ocr_preprocess import preprocess

_ROOT       = Path(__file__).parent.parent
DATA_DIR    = _ROOT / "data" / "ocr_all"
INDEX_CSV   = DATA_DIR / "all_index.csv"
RESULTS_DIR = Path(__file__).parent / "results"
WORKERS     = 6
PRESCREEN_SAMPLE = 50   # failed pages for fast-mode pre-screening
TOP_K_PRESCREEN  = 50   # configs promoted from pre-screen to full eval


# ── Data types ──────────────────────────────────────────────────────────────

@dataclass
class PageEntry:
    pdf_nickname: str
    page_num:     int
    image_path:   str       # relative to DATA_DIR
    is_success:   bool      # tier1 or tier2 parsed
    expected:     str       # e.g. "1/2" or "" if failed


# ── Data loading ────────────────────────────────────────────────────────────

def load_pages() -> tuple[list[PageEntry], list[PageEntry]]:
    """Load page index, return (failed_pages, success_pages).
    Success = tier1 OR tier2 parsed (combined baseline)."""
    failed, success = [], []
    with open(INDEX_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t1 = (row.get("tier1_parsed") or "").strip()
            t2 = (row.get("tier2_parsed") or "").strip()
            is_ok = bool(t1 or t2)
            entry = PageEntry(
                pdf_nickname=row["pdf_nickname"],
                page_num=int(row["page_num"]),
                image_path=row["image_path"],
                is_success=is_ok,
                expected=t1 or t2,
            )
            (success if is_ok else failed).append(entry)
    return failed, success


def load_pages_tier1() -> tuple[list[PageEntry], list[PageEntry]]:
    """Load page index using tier1_parsed as the sole success criterion.
    Pages rescued only by tier2 are counted as failed — they become
    additional rescue candidates for the tier1 Tesseract param sweep."""
    failed, success = [], []
    with open(INDEX_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t1 = (row.get("tier1_parsed") or "").strip()
            is_ok = bool(t1)
            entry = PageEntry(
                pdf_nickname=row["pdf_nickname"],
                page_num=int(row["page_num"]),
                image_path=row["image_path"],
                is_success=is_ok,
                expected=t1,
            )
            (success if is_ok else failed).append(entry)
    return failed, success


# ── Config enumeration ──────────────────────────────────────────────────────

def enumerate_configs() -> list[dict]:
    """Generate all valid parameter combinations, deduplicating tess_threshold
    when skip_binarization=False (external Otsu ignores tess_threshold)."""
    keys = list(OCR_PARAM_SPACE.keys())
    vals = [OCR_PARAM_SPACE[k] for k in keys]
    configs = []
    seen = set()
    for combo in product(*vals):
        cfg = dict(zip(keys, combo))
        # Normalize: tess_threshold irrelevant when not skipping binarization
        if not cfg["skip_binarization"]:
            cfg["tess_threshold"] = 0
        # Normalize: unsharp_strength irrelevant when sigma == 0
        if cfg["unsharp_sigma"] == 0.0:
            cfg["unsharp_strength"] = 0.0
        key = tuple(sorted(cfg.items()))
        if key not in seen:
            seen.add(key)
            configs.append(cfg)
    return configs


def enumerate_tier1_configs() -> list[dict]:
    """Generate configs for the tier1 Tesseract param sweep.
    Fixes image params at production values and sweeps only OCR_TESS_PARAM_SPACE
    (psm × oem × preserve_interword_spaces = 24 combos).
    No prescreen needed — 24 configs runs full in ~20 min."""
    keys = list(OCR_TESS_PARAM_SPACE.keys())
    vals = [OCR_TESS_PARAM_SPACE[k] for k in keys]
    configs = []
    for combo in product(*vals):
        cfg = {**OCR_PRODUCTION_PARAMS, **dict(zip(keys, combo))}
        configs.append(cfg)
    return configs


# ── Single-page OCR ─────────────────────────────────────────────────────────

def _ocr_page(image_path: str, params: dict) -> tuple[int | None, int | None]:
    """Load image, preprocess, run Tesseract, parse."""
    full_path = str(DATA_DIR / image_path)
    bgr = cv2.imread(full_path)
    if bgr is None:
        return None, None
    img, tess_cfg = preprocess(bgr, params)
    try:
        text = pytesseract.image_to_string(img, lang="eng", config=tess_cfg)
    except Exception:
        return None, None
    return _parse(text)


# ── Scoring ─────────────────────────────────────────────────────────────────

def score_on_pages(params: dict, pages: list[PageEntry]) -> dict:
    """Score a config against a list of pages. Returns counts dict."""
    rescued = regressed = maintained = still_failed = 0
    rescued_pages = []

    for page in pages:
        curr, total = _ocr_page(page.image_path, params)
        parsed = curr is not None

        if page.is_success and parsed:
            maintained += 1
        elif page.is_success and not parsed:
            regressed += 1
        elif not page.is_success and parsed:
            rescued += 1
            rescued_pages.append(f"{page.pdf_nickname}/p{page.page_num:03d}")
        else:
            still_failed += 1

    n_fail = rescued + still_failed
    n_ok = maintained + regressed
    return {
        "rescued":         rescued,
        "regressed":       regressed,
        "maintained":      maintained,
        "still_failed":    still_failed,
        "rescue_rate":     round(rescued / max(1, n_fail), 4),
        "regression_rate": round(regressed / max(1, n_ok), 4),
        "net_gain":        rescued - regressed * 3,
        "rescued_pages":   rescued_pages,
    }


# ── Worker function (for multiprocessing) ──────────────────────────────────

def _score_config_worker(args: tuple) -> tuple[int, dict]:
    """Worker: (config_index, params, pages) -> (config_index, scores)."""
    idx, params, pages = args
    scores = score_on_pages(params, pages)
    return idx, scores


# ── Sweep runner ────────────────────────────────────────────────────────────

def run_sweep() -> dict:
    failed, success = load_pages()
    configs = enumerate_configs()
    print(f"Loaded {len(failed)} failed + {len(success)} success pages")
    print(f"Generated {len(configs)} unique configs")

    # Baseline
    print("\nScoring baseline (production params)...")
    baseline = score_on_pages(OCR_PRODUCTION_PARAMS, failed)
    print(f"  Baseline: rescued={baseline['rescued']}, "
          f"still_failed={baseline['still_failed']}")

    # Phase A: all configs against failed pages
    print(f"\nPhase A: scoring {len(configs)} configs on {len(failed)} failed pages...")
    results_a: list[tuple[dict, dict]] = []
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(_score_config_worker, (i, cfg, failed)): i
            for i, cfg in enumerate(configs)
        }
        done = 0
        for future in as_completed(futures):
            idx, scores = future.result()
            results_a.append((configs[idx], scores))
            done += 1
            if done % 50 == 0 or done == len(configs):
                elapsed = time.time() - t0
                rate = done / elapsed
                eta = (len(configs) - done) / rate if rate > 0 else 0
                print(f"  Phase A: {done}/{len(configs)} "
                      f"({elapsed:.0f}s, ~{eta:.0f}s remaining)", end="\r")

    print(f"\n  Phase A done in {time.time() - t0:.0f}s")

    # Rank by rescue count
    results_a.sort(key=lambda x: (-x[1]["rescued"], x[1]["still_failed"]))
    top10 = results_a[:10]

    print("\n  Top-10 Phase A results:")
    for i, (cfg, sc) in enumerate(top10, 1):
        diff = {k: v for k, v in cfg.items() if v != OCR_PRODUCTION_PARAMS.get(k)}
        print(f"    #{i}: rescued={sc['rescued']} | diff={diff}")

    # Phase B: regression check on top-10 against success sample
    rng = random.Random(42)
    sample_size = min(200, len(success))
    success_sample = rng.sample(success, sample_size)

    print(f"\nPhase B: regression check on {sample_size} success pages...")
    results_b = []
    for i, (cfg, sc_a) in enumerate(top10, 1):
        sc_b = score_on_pages(cfg, success_sample)
        combined = {
            "params": cfg,
            "phase_a": {k: v for k, v in sc_a.items() if k != "rescued_pages"},
            "phase_b": {k: v for k, v in sc_b.items() if k != "rescued_pages"},
            "net_gain": sc_a["rescued"] - sc_b["regressed"] * 3,
            "rescued_pages": sc_a["rescued_pages"],
        }
        results_b.append(combined)
        print(f"  Config #{i}: rescued={sc_a['rescued']}, "
              f"regressed={sc_b['regressed']}/{sample_size}, "
              f"net_gain={combined['net_gain']}")

    # Final ranking by net_gain
    results_b.sort(key=lambda x: -x["net_gain"])

    # Baseline regression check
    baseline_b = score_on_pages(OCR_PRODUCTION_PARAMS, success_sample)

    return {
        "run_at": datetime.now().isoformat(),
        "total_failed_pages": len(failed),
        "total_success_pages": len(success),
        "success_sample_size": sample_size,
        "configs_tested": len(configs),
        "baseline_failed": {k: v for k, v in baseline.items() if k != "rescued_pages"},
        "baseline_success": {k: v for k, v in baseline_b.items() if k != "rescued_pages"},
        "top_configs": results_b,
    }


def run_fast_sweep() -> dict:
    """Pre-screen on sample, then full eval on top configs only."""
    failed, success = load_pages()
    configs = enumerate_configs()
    print(f"Loaded {len(failed)} failed + {len(success)} success pages")
    print(f"Generated {len(configs)} unique configs")

    # Baseline
    print("\nScoring baseline (production params)...")
    baseline = score_on_pages(OCR_PRODUCTION_PARAMS, failed)
    print(f"  Baseline: rescued={baseline['rescued']}, "
          f"still_failed={baseline['still_failed']}")

    # Pre-screen: all configs against a small sample of failed pages
    rng = random.Random(42)
    sample_size = min(PRESCREEN_SAMPLE, len(failed))
    failed_sample = rng.sample(failed, sample_size)

    print(f"\nPre-screen: {len(configs)} configs × {sample_size} failed pages "
          f"({len(configs) * sample_size:,} OCR calls)...")
    results_pre: list[tuple[dict, dict]] = []
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(_score_config_worker, (i, cfg, failed_sample)): i
            for i, cfg in enumerate(configs)
        }
        done = 0
        for future in as_completed(futures):
            idx, scores = future.result()
            results_pre.append((configs[idx], scores))
            done += 1
            if done % 50 == 0 or done == len(configs):
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                eta = (len(configs) - done) / rate if rate > 0 else 0
                print(f"  Pre-screen: {done}/{len(configs)} "
                      f"({elapsed:.0f}s, ~{eta:.0f}s remaining)", end="\r")

    print(f"\n  Pre-screen done in {time.time() - t0:.0f}s")

    # Rank and take top-K
    results_pre.sort(key=lambda x: (-x[1]["rescued"], x[1]["still_failed"]))
    top_k = results_pre[:TOP_K_PRESCREEN]

    print(f"\n  Top-{TOP_K_PRESCREEN} pre-screen (rescued on {sample_size} pages):")
    for i, (cfg, sc) in enumerate(top_k[:10], 1):
        diff = {k: v for k, v in cfg.items() if v != OCR_PRODUCTION_PARAMS.get(k)}
        print(f"    #{i}: rescued={sc['rescued']}/{sample_size} | diff={diff}")
    if len(top_k) > 10:
        print(f"    ... and {len(top_k) - 10} more")

    # Phase A: top-K configs against ALL failed pages
    print(f"\nPhase A: {len(top_k)} configs × {len(failed)} failed pages "
          f"({len(top_k) * len(failed):,} OCR calls)...")
    results_a: list[tuple[dict, dict]] = []
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(_score_config_worker, (i, cfg, failed)): i
            for i, (cfg, _) in enumerate(top_k)
        }
        done = 0
        for future in as_completed(futures):
            idx, scores = future.result()
            results_a.append((top_k[idx][0], scores))
            done += 1
            if done % 5 == 0 or done == len(top_k):
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                eta = (len(top_k) - done) / rate if rate > 0 else 0
                print(f"  Phase A: {done}/{len(top_k)} "
                      f"({elapsed:.0f}s, ~{eta:.0f}s remaining)", end="\r")

    print(f"\n  Phase A done in {time.time() - t0:.0f}s")

    # Rank by rescue count
    results_a.sort(key=lambda x: (-x[1]["rescued"], x[1]["still_failed"]))
    top10 = results_a[:10]

    print("\n  Top-10 Phase A results:")
    for i, (cfg, sc) in enumerate(top10, 1):
        diff = {k: v for k, v in cfg.items() if v != OCR_PRODUCTION_PARAMS.get(k)}
        print(f"    #{i}: rescued={sc['rescued']}/{len(failed)} | diff={diff}")

    # Phase B: regression check on top-10 against success sample
    success_sample_size = min(200, len(success))
    success_sample = rng.sample(success, success_sample_size)

    print(f"\nPhase B: regression check on {success_sample_size} success pages...")
    results_b = []
    for i, (cfg, sc_a) in enumerate(top10, 1):
        sc_b = score_on_pages(cfg, success_sample)
        combined = {
            "params": cfg,
            "phase_a": {k: v for k, v in sc_a.items() if k != "rescued_pages"},
            "phase_b": {k: v for k, v in sc_b.items() if k != "rescued_pages"},
            "net_gain": sc_a["rescued"] - sc_b["regressed"] * 3,
            "rescued_pages": sc_a["rescued_pages"],
        }
        results_b.append(combined)
        print(f"  Config #{i}: rescued={sc_a['rescued']}, "
              f"regressed={sc_b['regressed']}/{success_sample_size}, "
              f"net_gain={combined['net_gain']}")

    # Final ranking by net_gain
    results_b.sort(key=lambda x: -x["net_gain"])

    # Baseline regression check
    baseline_b = score_on_pages(OCR_PRODUCTION_PARAMS, success_sample)

    return {
        "run_at": datetime.now().isoformat(),
        "mode": "fast",
        "prescreen_sample": sample_size,
        "top_k_promoted": len(top_k),
        "total_failed_pages": len(failed),
        "total_success_pages": len(success),
        "success_sample_size": success_sample_size,
        "configs_tested": len(configs),
        "baseline_failed": {k: v for k, v in baseline.items() if k != "rescued_pages"},
        "baseline_success": {k: v for k, v in baseline_b.items() if k != "rescued_pages"},
        "top_configs": results_b,
    }


# Best image config from ocr_sweep_20260324_204154.json (net_gain=+23, rescued=149/697)
_BEST_IMAGE_PARAMS = {
    **OCR_TIER1_PARAMS,
    "skip_binarization": True,
    "unsharp_sigma":     1.0,
    "unsharp_strength":  0.3,
}

_MINI_CONFIGS = [
    ("baseline",       dict(OCR_TIER1_PARAMS)),
    ("psm11",          {**OCR_TIER1_PARAMS,   "psm": 11}),
    ("best_img+psm6",  dict(_BEST_IMAGE_PARAMS)),
    ("best_img+psm11", {**_BEST_IMAGE_PARAMS, "psm": 11}),
]


def run_mini_sweep() -> dict:
    """Cross PSM 11 with the best image config from the previous image sweep.
    4 combos × 1967 tier1-failed pages (~3 min)."""
    failed, success = load_pages_tier1()
    print(f"[mini] {len(_MINI_CONFIGS)} combos × {len(failed)} tier1-failed pages "
          f"= {len(_MINI_CONFIGS) * len(failed):,} OCR calls")

    # Phase A: parallel with max_workers=4 (matches config count, avoids idle-worker deadlock)
    print("\nPhase A: scoring configs on failed pages...")
    t0 = time.time()
    phase_a: dict[int, dict] = {}
    with ProcessPoolExecutor(max_workers=len(_MINI_CONFIGS)) as pool:
        futures = {
            pool.submit(_score_config_worker, (i, cfg, failed)): i
            for i, (_, cfg) in enumerate(_MINI_CONFIGS)
        }
        for future in as_completed(futures):
            idx, scores = future.result()
            phase_a[idx] = scores
            label = _MINI_CONFIGS[idx][0]
            print(f"  done: {label} rescued={scores['rescued']}/{len(failed)}")
    print(f"  Phase A done in {time.time() - t0:.0f}s")

    # Phase B: regression on success sample (sequential — only 4 configs)
    rng = random.Random(42)
    success_sample_size = min(200, len(success))
    success_sample = rng.sample(success, success_sample_size)
    print(f"\nPhase B: regression on {success_sample_size} tier1-success pages...")

    results = []
    for i, (label, cfg) in enumerate(_MINI_CONFIGS):
        sc_a = phase_a[i]
        sc_b = score_on_pages(cfg, success_sample)
        net = sc_a["rescued"] - sc_b["regressed"] * 3
        combined = {
            "label":         label,
            "params":        cfg,
            "phase_a":       {k: v for k, v in sc_a.items() if k != "rescued_pages"},
            "phase_b":       {k: v for k, v in sc_b.items() if k != "rescued_pages"},
            "net_gain":      net,
            "rescued_pages": sc_a["rescued_pages"],
        }
        results.append(combined)
        print(f"  {label}: rescued={sc_a['rescued']}, "
              f"regressed={sc_b['regressed']}/{success_sample_size}, net_gain={net}")

    results.sort(key=lambda x: -x["net_gain"])
    baseline_entry = next(r for r in results if r["label"] == "baseline")

    return {
        "run_at":              datetime.now().isoformat(),
        "mode":                "mini",
        "total_failed_pages":  len(failed),
        "total_success_pages": len(success),
        "success_sample_size": success_sample_size,
        "configs_tested":      len(_MINI_CONFIGS),
        "baseline_failed":     baseline_entry["phase_a"],
        "baseline_success":    baseline_entry["phase_b"],
        "top_configs":         results,
    }


def run_tier1_sweep() -> dict:
    """Tier1 Tesseract param sweep.
    24 configs (psm × oem × preserve_interword_spaces) × 1967 tier1-failed pages.
    No prescreen — small enough to run full in ~20 min."""
    failed, success = load_pages_tier1()
    configs = enumerate_tier1_configs()
    print(f"[tier1] {len(configs)} Tesseract configs × {len(failed)} tier1-failed pages "
          f"= {len(configs) * len(failed):,} OCR calls")

    print("\nScoring baseline (production tier1 params)...")
    baseline = score_on_pages(OCR_TIER1_PARAMS, failed)
    print(f"  Baseline: rescued={baseline['rescued']}, "
          f"still_failed={baseline['still_failed']}")

    print(f"\nPhase A: all {len(configs)} configs × {len(failed)} pages...")
    results_a: list[tuple[dict, dict]] = []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(_score_config_worker, (i, cfg, failed)): i
            for i, cfg in enumerate(configs)
        }
        done = 0
        for future in as_completed(futures):
            idx, scores = future.result()
            results_a.append((configs[idx], scores))
            done += 1
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta = (len(configs) - done) / rate if rate > 0 else 0
            print(f"  {done}/{len(configs)} ({elapsed:.0f}s, ~{eta:.0f}s remaining)",
                  end="\r")
    print(f"\n  Phase A done in {time.time() - t0:.0f}s")

    results_a.sort(key=lambda x: (-x[1]["rescued"], x[1]["still_failed"]))
    print("\n  All results (rescued / still_failed | diff from baseline):")
    for i, (cfg, sc) in enumerate(results_a, 1):
        diff = {k: v for k, v in cfg.items() if v != OCR_TIER1_PARAMS.get(k)
                and k in OCR_TESS_PARAM_SPACE}
        print(f"    #{i:>2}: rescued={sc['rescued']:>4}/{len(failed)} "
              f"still_failed={sc['still_failed']:>4} | {diff}")

    # Phase B: regression on tier1-success pages
    rng = random.Random(42)
    success_sample_size = min(200, len(success))
    success_sample = rng.sample(success, success_sample_size)
    top10 = results_a[:10]
    print(f"\nPhase B: regression check on {success_sample_size} tier1-success pages...")
    results_b = []
    for i, (cfg, sc_a) in enumerate(top10, 1):
        sc_b = score_on_pages(cfg, success_sample)
        diff = {k: v for k, v in cfg.items() if v != OCR_TIER1_PARAMS.get(k)
                and k in OCR_TESS_PARAM_SPACE}
        combined = {
            "params": cfg,
            "phase_a": {k: v for k, v in sc_a.items() if k != "rescued_pages"},
            "phase_b": {k: v for k, v in sc_b.items() if k != "rescued_pages"},
            "net_gain": sc_a["rescued"] - sc_b["regressed"] * 3,
            "rescued_pages": sc_a["rescued_pages"],
        }
        results_b.append(combined)
        print(f"  Config #{i} {diff}: rescued={sc_a['rescued']}, "
              f"regressed={sc_b['regressed']}/{success_sample_size}, "
              f"net_gain={combined['net_gain']}")

    results_b.sort(key=lambda x: -x["net_gain"])
    baseline_b = score_on_pages(OCR_TIER1_PARAMS, success_sample)

    return {
        "run_at": datetime.now().isoformat(),
        "mode": "tier1",
        "total_failed_pages": len(failed),
        "total_success_pages": len(success),
        "success_sample_size": success_sample_size,
        "configs_tested": len(configs),
        "baseline_failed": {k: v for k, v in baseline.items() if k != "rescued_pages"},
        "baseline_success": {k: v for k, v in baseline_b.items() if k != "rescued_pages"},
        "top_configs": results_b,
    }


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    full_mode  = "--full"  in sys.argv
    tier1_mode = "--tier1" in sys.argv
    mini_mode  = "--mini"  in sys.argv
    if mini_mode:
        result = run_mini_sweep()
        tag = "ocr_mini_sweep"
    elif tier1_mode:
        result = run_tier1_sweep()
        tag = "ocr_tier1_sweep"
    else:
        result = run_sweep() if full_mode else run_fast_sweep()
        tag = "ocr_sweep"
    out_path = RESULTS_DIR / f"{tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nResults saved to {out_path}")
    if result["top_configs"]:
        top = result["top_configs"][0]
        print(f"Best config: net_gain={top['net_gain']}, "
              f"rescued={top['phase_a']['rescued']}, "
              f"regressed={top['phase_b']['regressed']}")


if __name__ == "__main__":
    main()
