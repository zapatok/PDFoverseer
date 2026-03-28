"""
OCR Benchmark: EasyOCR vs PaddleOCR on ART_670.

Renders 2719 pages from data/samples/ART_670.pdf at 300 DPI (matching the
production GPU fallback in core/pipeline.py _gpu_consumer), then runs each
OCR engine and scores against 796 VLM-verified ground truth entries.

Each engine runs in a subprocess to isolate CUDA DLL state (paddle and torch
bundle conflicting versions of cuDNN that cannot coexist in one process).

Usage:
    source .venv-cuda/Scripts/activate
    python eval/ocr_benchmark.py              # full benchmark (spawns subprocesses)
    python eval/ocr_benchmark.py --engine easy    # EasyOCR only (subprocess worker)
    python eval/ocr_benchmark.py --engine paddle  # PaddleOCR only (subprocess worker)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

# Add project root so eval/ocr_benchmark.py can import core.utils / core.image
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.image import _render_clip
from core.utils import _parse

# ── Paths ─────────────────────────────────────────────────────────────────────

FIXTURE_PATH = Path("eval/fixtures/real/ART_674.json")
PDF_PATH     = Path("data/samples/ART_670.pdf")
OUTPUT_PATH  = Path("data/benchmark_results.json")
TOTAL_PAGES  = 2719

# Production GPU fallback renders at this DPI (core/ocr.py EASYOCR_DPI = 300)
RENDER_DPI = 300


# ── Lenient parser for OCR garbling ───────────────────────────────────────────

# Matches "d<digit>" where EasyOCR merged "de " + total into one token (e.g. "d2" = "de 2")
_DE_DIGIT_MERGE_RE = re.compile(r'\b([dD])([1-9]\d{0,2})\b')

def _parse_lenient(text: str) -> tuple[int | None, int | None]:
    """
    Lenient page number parser for OCR benchmark only (not production).

    Handles common EasyOCR character-substitution garbling of 'de':
      'd2'  → 'de 2'   (total digit absorbed into 'de' token)
      'dE'  → 'de'     (capital E substitution)
      'dc'  → 'de'     (c/e confusion)
      'dlo' → 'de'     (multi-char garble)

    Tries standard _parse() first; only applies lenient rules on failure.
    """
    # 1. Standard parse (fast path, no mutation)
    curr, total = _parse(text)
    if curr is not None:
        return curr, total

    # 2. Fix merged "d<digit>" tokens: "d2" → "de 2"
    step2 = _DE_DIGIT_MERGE_RE.sub(r'\1e \2', text)
    if step2 != text:
        curr, total = _parse(step2)
        if curr is not None:
            return curr, total

    # 3. Substitute other isolated garbled 'de' variants (up to 3 chars to handle 'dlo')
    step3 = re.sub(r'\b[dD][eEcClLoO]{1,3}\b', 'de', step2)
    if step3 != step2:
        curr, total = _parse(step3)
        if curr is not None:
            return curr, total

    # 4. Bare numeric pattern — garbled P-word like "Papina"/"Paglna" won't match
    #    the production regex P.{0,2}[gq], so look for \d+ de \d+ anywhere in text.
    m = re.search(r'\b(\d{1,3})\s+de\s+(\d{1,3})\b', step3)
    if m:
        return int(m.group(1)), int(m.group(2))

    return None, None


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
    curr: int | None,
    total: int | None,
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


def render_images(dpi: int = RENDER_DPI) -> list[tuple[int, np.ndarray]]:
    """
    Render all ART_670 pages from the PDF at the given DPI.

    Replicates core/pipeline.py _gpu_consumer(): renders the top-right crop
    of each page via _render_clip(), matching production EasyOCR input exactly.

    Returns:
        List of (pdf_page, bgr_image) sorted by page number (1-based).
    """
    import fitz  # PyMuPDF

    if not PDF_PATH.exists():
        raise FileNotFoundError(
            f"PDF not found: {PDF_PATH}  — ensure data/samples/ART_670.pdf exists"
        )

    images = []
    doc = fitz.open(str(PDF_PATH))
    n = len(doc)
    for i in range(n):
        bgr = _render_clip(doc[i], dpi=dpi)
        images.append((i + 1, bgr))   # 1-based pdf_page
    doc.close()
    return images


# ── Engine: EasyOCR ───────────────────────────────────────────────────────────

def run_easyocr(
    images: list[tuple[int, np.ndarray]],
    diagnose: int = 0,
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
        if diagnose > 0 and i < diagnose:
            print(f"  [diagnose] p{pdf_page:04d} raw={repr(text[:120])}", flush=True)
        curr, total = _parse_lenient(text)
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
    diagnose: int = 0,
) -> list[dict]:
    """
    Run PaddleOCR on all images sequentially.

    Uses BGR input (PaddleOCR accepts numpy BGR arrays directly).
    ocr_version="PP-OCRv4": uses PP-OCRv4_mobile_det + en_PP-OCRv4_mobile_rec.
    PP-OCRv5_server_det (the v5 default) returns empty dt_polys for all images in
    this environment — switching to v4 mobile detection resolves this.

    diagnose: if > 0, print raw OCR text for the first N pages (for debugging).

    Warm-up: runs first image before timing begins.
    Timing: covers predict() call only, not extract_paddle_text() or _parse().

    Returns:
        List of {pdf_page, curr, total, ms} dicts.
        curr/total are None if _parse_lenient() found nothing.
    """
    import os as _os
    import sys as _sys
    import types as _types

    # Stub modelscope BEFORE importing paddleocr.
    # paddleocr → paddlex → modelscope → torch, and torch's bundled cuDNN (torch/lib/)
    # is a different version from paddle's nvidia/cudnn/bin/ cuDNN.  Both need
    # cudnn64_9.dll by name; whichever loads first poisons the other's sub-libraries
    # with WinError 127 (procedure not found).  Stubbing modelscope keeps torch out of
    # this process entirely, so only paddle's CUDA stack loads.
    if "modelscope" not in _sys.modules:
        _sys.modules["modelscope"] = _types.ModuleType("modelscope")

    _site = str((Path(_sys.executable).parent.parent / "Lib" / "site-packages").resolve())
    _dll_dirs = [
        "nvidia/cudnn/bin",
        "nvidia/cublas/bin",
        "nvidia/cuda_runtime/bin",
        "nvidia/cufft/bin",
        "nvidia/curand/bin",
        "nvidia/nvjitlink/bin",
        "nvidia/cusolver/bin",
        "nvidia/cusparse/bin",
        "paddle/libs",
    ]
    for _pkg in _dll_dirs:
        _p = _os.path.join(_site, _pkg.replace("/", _os.sep))
        if _os.path.exists(_p):
            _os.add_dll_directory(_p)

    from paddleocr import PaddleOCR as _PaddleOCR

    print("PaddleOCR: initializing...", flush=True)
    # ocr_version="PP-OCRv4" → PP-OCRv4_mobile_det + en_PP-OCRv4_mobile_rec.
    # PP-OCRv5_server_det (the v5 default) returns empty dt_polys for all test images
    # in this environment; v4 mobile detection works correctly.
    # enable_mkldnn=False avoids ConvertPirAttribute2RuntimeAttribute crash on Windows.
    reader = _PaddleOCR(
        lang="en",
        ocr_version="PP-OCRv4",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False,
    )
    print("PaddleOCR: ready", flush=True)

    # Warm-up (excluded from timing)
    _, bgr0 = images[0]
    list(reader.predict(bgr0))
    print("PaddleOCR: warm-up done, starting timed run...", flush=True)

    results = []
    for i, (pdf_page, bgr) in enumerate(images):
        t0 = time.perf_counter()
        raw = list(reader.predict(bgr))
        ms = (time.perf_counter() - t0) * 1000

        if diagnose > 0 and i < diagnose:
            print(f"  [diagnose-raw] p{pdf_page:04d} type={type(raw)!r} len={len(raw)}", flush=True)
            if raw:
                first = raw[0]
                print(f"  [diagnose-raw]   first type={type(first)!r}", flush=True)
                if hasattr(first, "__dict__"):
                    print(f"  [diagnose-raw]   attrs={list(vars(first).keys())!r}", flush=True)
                elif hasattr(first, "keys"):
                    print(f"  [diagnose-raw]   keys={list(first.keys())!r}", flush=True)
                try:
                    print(f"  [diagnose-raw]   rec_texts={first['rec_texts']!r}", flush=True)
                    print(f"  [diagnose-raw]   dt_polys len={len(first['dt_polys'])}", flush=True)
                except Exception as ex:
                    print(f"  [diagnose-raw]   getitem err: {ex}", flush=True)
                try:
                    print(f"  [diagnose-raw]   repr={repr(first)[:200]}", flush=True)
                except Exception:
                    pass
        text = extract_paddle_text(raw)
        if diagnose > 0 and i < diagnose:
            print(f"  [diagnose] p{pdf_page:04d} text={repr(text[:120])}", flush=True)
        curr, total = _parse_lenient(text)
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
        "fixture":    "eval/fixtures/real/ART_674.json",
        "source_pdf": str(PDF_PATH),
        "render_dpi": RENDER_DPI,
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


# ── Subprocess worker (single-engine mode) ────────────────────────────────────

def run_worker(engine: str, out_path: str, sample: int = 0, diagnose: int = 0) -> None:
    """
    Worker entry point: runs one engine, writes results JSON to out_path.
    Called when --engine flag is present (subprocess isolation).

    sample: if > 0, process only the first N pages (for quick validation).
    diagnose: if > 0, print raw OCR text for the first N pages.
    """
    print(f"Rendering pages from PDF at {RENDER_DPI} DPI...", flush=True)
    images = render_images(dpi=RENDER_DPI)
    if sample > 0:
        images = images[:sample]
        print(f"Sample mode: {len(images)} pages", flush=True)
    else:
        print(f"Loaded {len(images)} images", flush=True)

    if engine == "easy":
        print("\n--- EasyOCR pass ---")
        results = run_easyocr(images, diagnose=diagnose)
    elif engine == "paddle":
        print("\n--- PaddleOCR pass ---")
        results = run_paddleocr(images, diagnose=diagnose)
    else:
        print(f"Unknown engine: {engine}", file=sys.stderr)
        sys.exit(1)

    with open(out_path, "w") as f:
        json.dump(results, f)
    print(f"\nResults written to {out_path}", flush=True)


# ── Main (orchestrator) ───────────────────────────────────────────────────────

def main(sample: int = 0, diagnose: int = 0):
    ground_truth = load_fixture(FIXTURE_PATH)
    print(f"Fixture loaded: {len(ground_truth)} GT pages")

    # Run each engine in a separate subprocess to isolate CUDA DLL state.
    # paddle/paddleocr bundles its own nvidia/* DLL stack; EasyOCR uses torch's
    # bundled cuDNN. Both load cudnn_cnn64_9.dll from different paths and cannot
    # coexist in one process — WinError 127 results if either runs second.
    script = str(Path(__file__).resolve())
    python = sys.executable

    extra_args: list[str] = []
    if sample > 0:
        extra_args += ["--sample", str(sample)]
    if diagnose > 0:
        extra_args += ["--diagnose", str(diagnose)]

    with tempfile.NamedTemporaryFile(suffix="_paddle.json", delete=False) as tf_p:
        paddle_tmp = tf_p.name
    with tempfile.NamedTemporaryFile(suffix="_easy.json", delete=False) as tf_e:
        easy_tmp = tf_e.name

    print("\n--- PaddleOCR pass (subprocess) ---", flush=True)
    proc_paddle = subprocess.run(
        [python, script, "--engine", "paddle", "--out", paddle_tmp] + extra_args,
        check=False,
    )

    print("\n--- EasyOCR pass (subprocess) ---", flush=True)
    proc_easy = subprocess.run(
        [python, script, "--engine", "easy", "--out", easy_tmp] + extra_args,
        check=False,
    )

    # Load results (empty list if subprocess failed)
    paddle_results: list[dict] = []
    easy_results:   list[dict] = []

    if proc_paddle.returncode == 0:
        with open(paddle_tmp) as f:
            paddle_results = json.load(f)
    else:
        print(f"WARNING: PaddleOCR subprocess exited {proc_paddle.returncode} — no paddle results")

    if proc_easy.returncode == 0:
        with open(easy_tmp) as f:
            easy_results = json.load(f)
    else:
        print(f"WARNING: EasyOCR subprocess exited {proc_easy.returncode} — no easy results")

    # Clean up temp files
    for p in (paddle_tmp, easy_tmp):
        try:
            Path(p).unlink()
        except OSError:
            pass

    print("\n--- Scoring ---")
    easy_score   = score_results(easy_results,   ground_truth)
    paddle_score = score_results(paddle_results, ground_truth)

    print_report(easy_results, paddle_results, easy_score, paddle_score)
    save_json(easy_results, paddle_results, easy_score, paddle_score, OUTPUT_PATH)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EasyOCR vs PaddleOCR benchmark")
    parser.add_argument("--engine", choices=["easy", "paddle"],
                        help="Run a single engine (subprocess worker mode)")
    parser.add_argument("--out", help="Output JSON path (required with --engine)")
    parser.add_argument("--sample", type=int, default=0, metavar="N",
                        help="Process only the first N pages (for quick validation)")
    parser.add_argument("--diagnose", type=int, default=0, metavar="N",
                        help="Print raw OCR text for the first N pages")
    args = parser.parse_args()

    if args.engine:
        if not args.out:
            print("--out required when --engine is set", file=sys.stderr)
            sys.exit(1)
        run_worker(args.engine, args.out, sample=args.sample, diagnose=args.diagnose)
    else:
        main(sample=args.sample, diagnose=args.diagnose)
