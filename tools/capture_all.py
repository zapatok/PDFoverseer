"""
capture_all.py — Save OCR image strips for ALL pages
=====================================================
Renders the top-right crop (page number region) for every page in a PDF
and saves it as a PNG, along with OCR text from each tier in a CSV index.

Usage:
    python tools/capture_all.py data/samples/CH_39.pdf
    python tools/capture_all.py data/samples/              # all PDFs in dir
    python tools/capture_all.py data/samples/ --easyocr    # include Tier 3

Output: data/ocr_all/{pdf_nickname}/p001.png ... + data/ocr_all/all_index.csv
"""

import argparse
import csv
import sys
from pathlib import Path

OUTPUT_ROOT = Path("data/ocr_all")
CSV_COLUMNS = [
    "pdf_nickname", "page_num", "tier1_parsed", "tier2_parsed",
    "tier1_text", "tier2_text", "tier3_text", "image_path",
]


def _parsed_str(curr, total) -> str:
    """Format parsed result as 'curr/total' or '' if None."""
    if curr is not None and total is not None:
        return f"{curr}/{total}"
    return ""


def capture_pdf(
    pdf_path: Path | str,
    out_dir: Path | str = OUTPUT_ROOT,
    include_easyocr: bool = False,
) -> list[dict]:
    """
    Render and save the page-number strip for every page in a PDF.

    Returns list of CSV row dicts.
    """
    import cv2
    import fitz

    # Ensure project root is on path for core imports
    project_root = str(Path(__file__).parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    import core.ocr as ocr_mod  # for _easyocr_reader access after init
    from core.image import _deskew, _render_clip
    from core.ocr import (
        EASYOCR_DPI,
        _init_easyocr,
        _setup_sr,
        _tess_ocr,
        _upsample_4x,
    )
    from core.utils import DPI, _parse

    _setup_sr(print)
    if include_easyocr:
        _init_easyocr(print)

    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    nickname = pdf_path.stem

    img_dir = out_dir / nickname
    img_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "all_index.csv"
    write_header = not csv_path.exists()
    csv_file = open(csv_path, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
    if write_header:
        writer.writeheader()

    rows = []

    try:
        doc = fitz.open(str(pdf_path))
        total_pages = len(doc)
        print(f"[capture_all] {nickname}: {total_pages} pages")

        for page_idx in range(total_pages):
            page = doc[page_idx]
            page_num = page_idx + 1

            # Render + deskew
            bgr_raw = _render_clip(page, dpi=DPI)
            bgr = _deskew(bgr_raw)

            # Save image strip
            filename = f"p{page_num:03d}.png"
            cv2.imwrite(str(img_dir / filename), bgr)

            # Tier 1: Tesseract on deskewed crop
            text1 = _tess_ocr(bgr)
            c1, t1 = _parse(text1)

            # Tier 2: 4x SR + Tesseract
            text2 = ""
            c2, t2 = None, None
            if c1 is None:
                bgr_sr = _upsample_4x(bgr)
                text2 = _tess_ocr(bgr_sr)
                c2, t2 = _parse(text2)

            # Tier 3: EasyOCR (optional)
            text3 = ""
            if include_easyocr and c1 is None and c2 is None:
                reader = ocr_mod._easyocr_reader
                if reader is not None:
                    bgr_hires = _render_clip(page, dpi=EASYOCR_DPI)
                    results = reader.readtext(bgr_hires, detail=0)
                    text3 = " ".join(results)

            rel_path = f"{nickname}/{filename}"
            status = "T1" if c1 else ("T2" if c2 else "FAIL")

            row = {
                "pdf_nickname": nickname,
                "page_num": page_num,
                "tier1_parsed": _parsed_str(c1, t1),
                "tier2_parsed": _parsed_str(c2, t2),
                "tier1_text": text1.strip(),
                "tier2_text": text2.strip(),
                "tier3_text": text3.strip(),
                "image_path": rel_path,
            }
            writer.writerow(row)
            rows.append(row)

            print(f"  [{status:4s}] page {page_num:3d}"
                  + (f"  {c1}/{t1}" if c1 else f"  {c2}/{t2}" if c2 else ""))

        doc.close()

    finally:
        csv_file.close()

    ok = sum(1 for r in rows if r["tier1_parsed"] or r["tier2_parsed"])
    print(f"[capture_all] done: {ok} parsed / {total_pages} total")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Save OCR image strips for ALL pages in PDFs."
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
        help="Also run EasyOCR Tier 3 on pages where Tier 1+2 fail.",
    )
    args = parser.parse_args()

    target = Path(args.path)
    out_dir = Path(args.out)

    if target.is_dir():
        pdfs = sorted(target.glob("*.pdf")) + sorted(target.glob("*.PDF"))
        # Deduplicate (case-insensitive filesystems)
        seen = set()
        unique = []
        for p in pdfs:
            key = str(p).lower()
            if key not in seen:
                seen.add(key)
                unique.append(p)
        pdfs = unique
        if not pdfs:
            print(f"No PDF files found in {target}")
            sys.exit(1)
    elif target.is_file() and target.suffix.lower() == ".pdf":
        pdfs = [target]
    else:
        print(f"Error: {target} is not a PDF file or a directory.")
        sys.exit(1)

    print(f"[capture_all] {len(pdfs)} PDFs -> {out_dir}/")
    total_rows = 0
    for pdf in pdfs:
        rows = capture_pdf(pdf, out_dir=out_dir, include_easyocr=args.easyocr)
        total_rows += len(rows)

    print(f"\n[capture_all] Total: {total_rows} pages captured -> {out_dir}/all_index.csv")


if __name__ == "__main__":
    main()
