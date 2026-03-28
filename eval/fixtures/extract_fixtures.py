"""
eval/fixtures/extract_fixtures.py
---------------------------------
Extract pre-inference OCR reads from real PDFs and save to eval/fixtures/real/<name>.json.

Runs Tesseract (Tier 1 direct + Tier 2 SR-GPU bicubic) exactly as the production
pipeline does, but stops BEFORE _infer_missing — so the fixtures capture raw OCR
results with method in {"direct", "super_resolution", "failed"}.

Usage:
    source .venv-cuda/Scripts/activate
    python eval/fixtures/extract_fixtures.py
"""

from __future__ import annotations

import json
import queue
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import fitz  # PyMuPDF  # noqa: E402

from core.ocr import _process_page, _setup_sr  # noqa: E402
from core.utils import BATCH_SIZE, PARALLEL_WORKERS, _PageRead  # noqa: E402

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

OUT_DIR = Path(__file__).parent / "real"


def _log(msg: str, level: str = "info") -> None:
    print(msg.encode("ascii", errors="replace").decode("ascii"), flush=True)


def extract_reads(pdf_path: str, name: str) -> list[_PageRead]:
    """Run Tesseract OCR on all pages of pdf_path (Tier 1 + Tier 2 SR).

    Returns raw _PageRead list — no inference applied.

    Args:
        pdf_path: Path to the PDF file.
        name: Fixture name for logging.

    Returns:
        List of _PageRead with method in {"direct", "super_resolution", "failed"}.
    """
    meta = fitz.open(pdf_path)
    total_pages = len(meta)
    meta.close()
    _log(f"  {name}: {total_pages} pages")

    reads: list[_PageRead | None] = [None] * total_pages

    # ── Doc pool: one fitz.Document per worker thread ──────────────────────
    _doc_pool: queue.Queue[fitz.Document] = queue.Queue()
    for _ in range(PARALLEL_WORKERS):
        _doc_pool.put(fitz.open(pdf_path))

    def _submit_page(page_idx: int) -> _PageRead:
        doc = _doc_pool.get()
        try:
            return _process_page(doc, page_idx)
        except Exception as e:
            _log(f"    page {page_idx+1}: error — {e}")
            return _PageRead(page_idx + 1, None, None, "failed", 0.0)
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
            for future, i in future_to_idx.items():
                reads[i] = future.result()

            # Progress every 10 batches
            if (batch_start // BATCH_SIZE) % 10 == 0:
                done = batch_end
                failed = sum(1 for r in reads[:done] if r is not None and r.method == "failed")
                _log(f"  [{done}/{total_pages}] {failed} failed so far")

    # ── Close worker pool ──────────────────────────────────────────────────
    while not _doc_pool.empty():
        _doc_pool.get_nowait().close()

    # Fill any None slots (defensive)
    for i in range(total_pages):
        if reads[i] is None:
            reads[i] = _PageRead(i + 1, None, None, "failed", 0.0)

    return reads  # type: ignore[return-value]


def serialize_reads(reads: list[_PageRead]) -> list[dict]:
    """Serialize _PageRead list to JSON-friendly dicts."""
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
    _log("Initializing SR model...")
    _setup_sr(_log)

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
