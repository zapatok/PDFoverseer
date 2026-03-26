"""
eval/extract_fixtures.py
------------------------
Extract pre-inference OCR reads from real PDFs and save to eval/fixtures/real/<name>.json.

Runs Tesseract (Tier 1 + Tier 2 SR) and EasyOCR GPU (Tier 3) exactly as the
production pipeline does, but stops BEFORE _infer_missing — so the fixtures
capture raw OCR results with method in {"direct", "SR", "easyocr", "failed"}.

Usage:
    source .venv-cuda/Scripts/activate
    python eval/extract_fixtures.py
"""

from __future__ import annotations

import json
import queue
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import fitz  # PyMuPDF

from core.image import _render_clip
from core.ocr import (
    EASYOCR_DPI,
    _init_easyocr,
    _process_page,
    _setup_sr,
)
from core.utils import (
    BATCH_SIZE,
    PARALLEL_WORKERS,
    _PageRead,
    _parse,
)

# ── PDF paths ──────────────────────────────────────────────────────────────────

PDF_PATHS: dict[str, str] = {
    "ART":    r"a:/PROJECTS/PDFoverseer/ART_HLL_674docsapp.pdf",
    "CH_9":   r"a:/PROJECTS/PDFoverseer/CH_9docs.pdf",
    "CH_39":  r"a:/PROJECTS/PDFoverseer/CH_39docs.pdf",
    "CH_51":  r"a:/PROJECTS/PDFoverseer/CH_51docs.pdf",
    "CH_74":  r"a:/PROJECTS/PDFoverseer/CH_74docs.pdf",
    "HLL":    r"a:/PROJECTS/PDFoverseer/HLL_363docs.pdf",
    "INS_31": r"a:/PROJECTS/PDFoverseer/INS_31.pdf.pdf",
}

OUT_DIR = PROJECT_ROOT / "eval" / "fixtures" / "real"


def _log(msg: str, level: str = "info") -> None:
    print(msg.encode("ascii", errors="replace").decode("ascii"), flush=True)


def extract_reads(pdf_path: str, name: str) -> list[_PageRead]:
    """
    Run OCR on all pages of pdf_path (Tesseract + EasyOCR GPU).
    Returns raw _PageRead list — no inference applied.
    """
    meta = fitz.open(pdf_path)
    total_pages = len(meta)
    meta.close()
    _log(f"  {name}: {total_pages} pages")

    reads: list[_PageRead | None] = [None] * total_pages

    # ── GPU consumer (mirrors analyze_pdf) ────────────────────────────────
    import core.ocr as _ocr
    has_gpu = _ocr._easyocr_reader is not None
    gpu_queue: queue.Queue[int | None] = queue.Queue()
    gpu_recovered = [0]

    def _gpu_consumer():
        if not has_gpu:
            while gpu_queue.get() is not None:
                pass
            return
        doc = fitz.open(pdf_path)
        try:
            while True:
                item = gpu_queue.get()
                if item is None:
                    break
                idx = item
                bgr = _render_clip(doc[idx], dpi=EASYOCR_DPI)
                import cv2
                gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
                with _ocr._easyocr_lock:
                    results = _ocr._easyocr_reader.readtext(gray, detail=0, paragraph=True)
                text = " ".join(results) if results else ""
                c, t = _parse(text)
                if c:
                    reads[idx] = _PageRead(idx + 1, c, t, "easyocr", 1.0)
                    gpu_recovered[0] += 1
        finally:
            doc.close()

    gpu_thread = threading.Thread(target=_gpu_consumer, daemon=True, name="gpu-consumer")
    gpu_thread.start()

    # ── Doc pool: one fitz.Document per worker thread ──────────────────────
    _doc_pool: queue.Queue[fitz.Document] = queue.Queue()
    for _ in range(PARALLEL_WORKERS):
        _doc_pool.put(fitz.open(pdf_path))

    def _submit_page(page_idx: int) -> _PageRead:
        doc = _doc_pool.get()
        try:
            return _process_page(doc, page_idx)
        finally:
            _doc_pool.put(doc)

    # ── Producers: parallel Tesseract ─────────────────────────────────────
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as pool:
        for batch_start in range(0, total_pages, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, total_pages)
            future_to_idx = {
                pool.submit(_submit_page, i): i
                for i in range(batch_start, batch_end)
            }
            batch_results: dict[int, _PageRead] = {}
            for future, i in future_to_idx.items():
                try:
                    batch_results[i] = future.result()
                except Exception as e:
                    batch_results[i] = _PageRead(i + 1, None, None, "failed", 0.0)
                    _log(f"    page {i+1}: error — {e}")

            for i in range(batch_start, batch_end):
                r = batch_results[i]
                reads[i] = r
                if r.curr is not None:
                    _log(f"    p{i+1:>4}: {r.curr}/{r.total} [{r.method}]")
                else:
                    _log(f"    p{i+1:>4}: failed -> GPU queue")
                    gpu_queue.put(i)

    # ── Close worker pool ──────────────────────────────────────────────────
    while not _doc_pool.empty():
        _doc_pool.get_nowait().close()

    # ── Stop GPU consumer ──────────────────────────────────────────────────
    gpu_queue.put(None)
    gpu_thread.join()

    if gpu_recovered[0]:
        _log(f"    EasyOCR GPU: {gpu_recovered[0]} pages recovered")

    # Fill any None slots (shouldn't happen, but be defensive)
    for i in range(total_pages):
        if reads[i] is None:
            reads[i] = _PageRead(i + 1, None, None, "failed", 0.0)

    return reads  # type: ignore[return-value]


def serialize_reads(reads: list[_PageRead]) -> list[dict]:
    return [
        {
            "pdf_page":   r.pdf_page,
            "curr":       r.curr,
            "total":      r.total,
            "method":     r.method,
            "confidence": r.confidence,
        }
        for r in reads
    ]


def main() -> None:
    _log("Initializing SR and EasyOCR...")
    _setup_sr(_log)
    _init_easyocr(_log)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for name, pdf_path in PDF_PATHS.items():
        path = Path(pdf_path)
        if not path.exists():
            _log(f"[SKIP] {name}: file not found at {pdf_path}")
            continue

        _log(f"\n=== {name} ===")
        reads = extract_reads(pdf_path, name)

        fixture = {
            "name":   name,
            "source": "real",
            "reads":  serialize_reads(reads),
        }

        out_path = OUT_DIR / f"{name}.json"
        out_path.write_text(json.dumps(fixture, indent=2))
        failed = sum(1 for r in reads if r.method == "failed")
        _log(f"  -> {out_path} ({len(reads)} pages, {failed} failed)")

    _log("\nDone.")


if __name__ == "__main__":
    main()
