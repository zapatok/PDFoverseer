"""
capture_failures.py — OCR Failure Capture Tool
===============================================
Standalone research script. Scans a PDF and saves image strips + metadata
for every page where Tesseract (both tiers) fails to detect the page number.

Usage:
    python tools/capture_failures.py path/to/file.pdf
    python tools/capture_failures.py path/to/dir/   # all PDFs in directory

Output: data/ocr_failures/{pdf_nickname}/*.png + data/ocr_failures/failures_index.csv
"""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

# Heavy imports (cv2, fitz, core.analyzer) are deferred inside capture_pdf()
# so that importing this module for unit-testing pure helpers does not require
# the full GPU/CV stack to be installed and configured.

OUTPUT_ROOT = Path("data/ocr_failures")
CSV_COLUMNS = [
    "pdf_nickname", "page_num", "timestamp",
    "image_path", "tier1_text", "tier2_text", "tier3_text",
]


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _make_image_filename(page_num: int, dt: datetime) -> str:
    """Return filename like 'p037_20260317_143022.png'."""
    return f"p{page_num:03d}_{dt.strftime('%Y%m%d_%H%M%S')}.png"


def _make_image_path(pdf_nickname: str, page_num: int, dt: datetime) -> str:
    """Return CSV-relative path like 'CH_39docs/p037_20260317_143022.png'."""
    return f"{pdf_nickname}/{_make_image_filename(page_num, dt)}"


def _build_csv_row(
    pdf_nickname: str,
    page_num: int,
    timestamp: datetime,
    image_path: str,
    tier1_text: str,
    tier2_text: str,
    tier3_text: str,
) -> dict:
    """Build a CSV row dict with all required columns."""
    return {
        "pdf_nickname": pdf_nickname,
        "page_num":     page_num,
        "timestamp":    timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
        "image_path":   image_path,
        "tier1_text":   tier1_text,
        "tier2_text":   tier2_text,
        "tier3_text":   tier3_text,
    }

def capture_pdf(
    pdf_path: Path | str,
    out_dir: Path | str = OUTPUT_ROOT,
    include_easyocr: bool = False,
) -> list[dict]:
    """
    Scan a PDF and capture every page where both Tesseract tiers fail
    to match the page number pattern.

    Args:
        pdf_path:       Path to the PDF file.
        out_dir:        Root output directory (default: data/ocr_failures/).
        include_easyocr: If True, also run EasyOCR Tier 3 and record its text.

    Returns:
        List of CSV row dicts, one per captured page.
    """
    # Deferred heavy imports — keep module-level imports stdlib-only
    import sys as _sys

    import cv2
    import fitz  # PyMuPDF
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    import core.analyzer as analyzer
    from core.analyzer import (
        DPI,
        EASYOCR_DPI,
        _init_easyocr,
        _parse,
        _render_clip,
        _setup_sr,
        _tess_ocr,
        _upsample_4x,
    )

    # One-time SR init (idempotent — safe to call on every capture_pdf() invocation)
    _setup_sr(print)

    # EasyOCR init (idempotent) — only when caller requests Tier 3 capture
    if include_easyocr:
        _init_easyocr(print)

    pdf_path = Path(pdf_path)
    out_dir  = Path(out_dir)
    nickname = pdf_path.stem

    # Output dirs
    img_dir  = out_dir / nickname
    img_dir.mkdir(parents=True, exist_ok=True)

    # CSV (append mode — multiple PDFs may write to same file)
    csv_path    = out_dir / "failures_index.csv"
    write_header = not csv_path.exists()
    csv_file    = open(csv_path, "a", newline="", encoding="utf-8")
    writer      = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
    if write_header:
        writer.writeheader()

    captured = []

    try:
        doc = fitz.open(str(pdf_path))
        total_pages = len(doc)
        print(f"[capture] {nickname}: {total_pages} pages")

        for page_idx in range(total_pages):
            page    = doc[page_idx]
            page_num = page_idx + 1

            bgr_raw  = _render_clip(page, dpi=DPI)
            gray     = cv2.cvtColor(bgr_raw, cv2.COLOR_BGR2GRAY)

            # Tier 1: Tesseract on raw crop (Otsu applied inside _tess_ocr)
            text1 = _tess_ocr(gray)
            c, _ = _parse(text1)
            if c:
                continue

            # Tier 2: 4x SR upscale + Tesseract
            bgr_sr  = _upsample_4x(bgr_raw)   # expects BGR, not gray
            gray_sr = cv2.cvtColor(bgr_sr, cv2.COLOR_BGR2GRAY)
            text2   = _tess_ocr(gray_sr)
            c, _    = _parse(text2)
            if c:
                continue

            # Both tiers failed — capture this page
            text3 = ""
            if include_easyocr and analyzer._easyocr_reader is not None:
                # Re-render at EASYOCR_DPI for results comparable to production
                bgr_hires = _render_clip(page, dpi=EASYOCR_DPI)
                results   = analyzer._easyocr_reader.readtext(bgr_hires, detail=0)
                text3     = " ".join(results)

            dt       = datetime.now()
            filename = _make_image_filename(page_num, dt)
            rel_path = _make_image_path(nickname, page_num, dt)

            # Save raw BGR strip (what the human eye sees, pre-Otsu)
            cv2.imwrite(str(img_dir / filename), bgr_raw)

            row = _build_csv_row(nickname, page_num, dt, rel_path, text1.strip(), text2.strip(), text3.strip())
            writer.writerow(row)
            captured.append(row)
            print(f"  [FAIL] page {page_num:3d} — saved {rel_path}")

        doc.close()

    finally:
        csv_file.close()

    print(f"[capture] done: {len(captured)} failures / {total_pages} pages")
    return captured

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture OCR failure image strips from PDFs for analysis."
    )
    parser.add_argument(
        "path",
        help="Path to a PDF file, or a directory to scan all PDFs inside it.",
    )
    parser.add_argument(
        "--out", default=str(OUTPUT_ROOT),
        help=f"Output directory (default: {OUTPUT_ROOT})",
    )
    parser.add_argument(
        "--easyocr", action="store_true",
        help="Also run EasyOCR Tier 3 and record its output in the CSV.",
    )
    args = parser.parse_args()

    target = Path(args.path)
    out_dir = Path(args.out)

    if target.is_dir():
        pdfs = sorted(target.glob("*.pdf"))
        if not pdfs:
            print(f"No PDF files found in {target}")
            sys.exit(1)
    elif target.is_file() and target.suffix.lower() == ".pdf":
        pdfs = [target]
    else:
        print(f"Error: {target} is not a PDF file or a directory.")
        sys.exit(1)

    # SR and EasyOCR are initialized inside capture_pdf() — no separate init needed here.

    total_failures = 0
    for pdf in pdfs:
        rows = capture_pdf(pdf, out_dir=out_dir, include_easyocr=args.easyocr)
        total_failures += len(rows)

    print(f"\n[capture] Total: {total_failures} failures captured → {out_dir}/failures_index.csv")


if __name__ == "__main__":
    main()
