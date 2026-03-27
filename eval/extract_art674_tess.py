#!/usr/bin/env python
"""
eval/extract_art674_tess.py
---------------------------
Extract Tesseract reads from data/samples/ART_670.pdf.
Saves raw OCR reads (NO inference) to eval/fixtures/real/ART_674_tess.json.

Does NOT overwrite ART_674.json (VLM fixture).

Usage:
    source .venv-cuda/Scripts/activate   # Windows: .\\.venv-cuda\\Scripts\\activate
    python eval/extract_art674_tess.py
"""
from __future__ import annotations

import json
import queue
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import fitz  # noqa: E402

from core.ocr import _process_page, _setup_sr  # noqa: E402
from core.utils import BATCH_SIZE, PARALLEL_WORKERS, _PageRead  # noqa: E402

PDF_PATH = PROJECT_ROOT / "data" / "samples" / "ART_670.pdf"
OUT_PATH = PROJECT_ROOT / "eval" / "fixtures" / "real" / "ART_674_tess.json"
FIXTURE_NAME = "ART_674_tess"


def _log(msg: str, level: str = "info") -> None:
    print(msg.encode("ascii", errors="replace").decode("ascii"), flush=True)


def main() -> None:
    if not PDF_PATH.exists():
        _log(f"ERROR: PDF not found at {PDF_PATH}")
        sys.exit(1)
    if OUT_PATH.exists():
        _log(f"WARNING: {OUT_PATH.name} already exists — will overwrite")

    _log("Initializing SR model...")
    _setup_sr(_log)

    meta = fitz.open(str(PDF_PATH))
    total_pages = len(meta)
    meta.close()
    _log(f"PDF: {PDF_PATH.name}, {total_pages} pages")

    reads: list[_PageRead | None] = [None] * total_pages

    doc_pool: queue.Queue[fitz.Document] = queue.Queue()
    for _ in range(PARALLEL_WORKERS):
        doc_pool.put(fitz.open(str(PDF_PATH)))

    def _submit(page_idx: int) -> _PageRead:
        doc = doc_pool.get()
        try:
            return _process_page(doc, page_idx)
        except Exception as e:
            _log(f"  p{page_idx+1}: error — {e}")
            return _PageRead(page_idx + 1, None, None, "failed", 0.0)
        finally:
            doc_pool.put(doc)

    _log(f"Scanning {total_pages} pages with {PARALLEL_WORKERS} workers...")
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as pool:
        for batch_start in range(0, total_pages, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, total_pages)
            futures = {pool.submit(_submit, i): i for i in range(batch_start, batch_end)}
            for fut in futures:
                i = futures[fut]
                reads[i] = fut.result()
            # Progress every 10 batches
            if (batch_start // BATCH_SIZE) % 10 == 0:
                done = batch_end
                failed = sum(1 for r in reads[:done] if r is not None and r.method == "failed")
                _log(f"  [{done}/{total_pages}] {failed} failed so far")

    while not doc_pool.empty():
        doc_pool.get_nowait().close()

    # Fill any None slots (defensive)
    for i in range(total_pages):
        if reads[i] is None:
            reads[i] = _PageRead(i + 1, None, None, "failed", 0.0)

    failed_total = sum(1 for r in reads if r.method == "failed")  # type: ignore[union-attr]
    direct_total = sum(1 for r in reads if r.method == "direct")  # type: ignore[union-attr]
    sr_total = sum(1 for r in reads if r.method == "super_resolution")  # type: ignore[union-attr]
    _log(f"\nResults: {total_pages} pages | direct={direct_total} SR={sr_total} failed={failed_total}")

    fixture = {
        "name":   FIXTURE_NAME,
        "source": "real",
        "reads": [
            {
                "pdf_page":   r.pdf_page,
                "curr":       r.curr,
                "total":      r.total,
                "method":     r.method,
                "confidence": r.confidence,
            }
            for r in reads  # type: ignore[union-attr]
        ],
    }
    OUT_PATH.write_text(json.dumps(fixture, indent=2))
    _log(f"Saved -> {OUT_PATH}")


if __name__ == "__main__":
    main()
