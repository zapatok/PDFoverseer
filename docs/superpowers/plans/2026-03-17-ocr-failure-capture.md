# OCR Failure Capture Tool — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `tools/capture_failures.py`, a standalone script that scans a PDF, finds pages where Tesseract (both tiers) fails to detect the page number pattern, and saves the raw image strip + a CSV row for offline analysis.

**Architecture:** The script inlines the two-tier OCR logic (instead of calling `_process_page`) so it can (a) avoid double-rendering and (b) capture the intermediate Tesseract text strings for the CSV. Output goes to `data/ocr_failures/{pdf_nickname}/` with a shared `failures_index.csv`.

**Tech Stack:** Python 3.10+, PyMuPDF (fitz), OpenCV (cv2), Tesseract via pytesseract, `core/analyzer.py` private helpers, standard library (csv, argparse, pathlib, datetime).

---

## Chunk 1: Helpers + CSV writer

### Task 1: Scaffold `tools/` directory and pure helper functions

**Files:**
- Create: `tools/__init__.py` (empty)
- Create: `tools/capture_failures.py`
- Create: `tests/test_capture_failures.py`

**Context:** The project root already has `tests/test_tray_issues.py` as a model. Tests use `sys.path.insert(0, ...)` to reach the project root. No mocking — use real functions and fixtures.

- [ ] **Step 1: Create `tools/__init__.py`** (empty file, makes `tools/` a package)

- [ ] **Step 2: Write the failing tests for helper functions**

Create `tests/test_capture_failures.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime
from tools.capture_failures import _make_image_filename, _make_image_path, _build_csv_row


def test_make_image_filename_format():
    dt = datetime(2026, 3, 17, 14, 30, 22)
    assert _make_image_filename(37, dt) == "p037_20260317_143022.png"


def test_make_image_filename_pads_page():
    dt = datetime(2026, 3, 17, 0, 0, 0)
    assert _make_image_filename(1, dt) == "p001_20260317_000000.png"


def test_make_image_path():
    dt = datetime(2026, 3, 17, 14, 30, 22)
    result = _make_image_path("CH_39docs", 37, dt)
    assert result == "CH_39docs/p037_20260317_143022.png"


def test_build_csv_row_all_fields():
    row = _build_csv_row(
        pdf_nickname="INS_31docs",
        page_num=1,
        timestamp=datetime(2026, 3, 17, 14, 30, 22),
        image_path="INS_31docs/p001_20260317_143022.png",
        tier1_text="Pbgina 1 de",
        tier2_text="",
        tier3_text="",
    )
    assert row["pdf_nickname"] == "INS_31docs"
    assert row["page_num"] == 1
    assert row["timestamp"] == "2026-03-17T14:30:22"
    assert row["image_path"] == "INS_31docs/p001_20260317_143022.png"
    assert row["tier1_text"] == "Pbgina 1 de"
    assert row["tier2_text"] == ""
    assert row["tier3_text"] == ""


CSV_COLUMNS = [
    "pdf_nickname", "page_num", "timestamp",
    "image_path", "tier1_text", "tier2_text", "tier3_text",
]

def test_build_csv_row_has_all_columns():
    row = _build_csv_row("x", 1, datetime.now(), "x/p001.png", "", "", "")
    assert list(row.keys()) == CSV_COLUMNS
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
source .venv-cuda/Scripts/activate
pytest tests/test_capture_failures.py -v
```

Expected: `ImportError: cannot import name '_make_image_filename' from 'tools.capture_failures'`

- [ ] **Step 4: Implement the helper functions in `tools/capture_failures.py`**

Note: heavy imports (`cv2`, `fitz`, `core.analyzer`) are deferred to inside `capture_pdf()` and `main()` so that importing this module for unit tests does not require the full GPU/CV stack.

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_capture_failures.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/__init__.py tools/capture_failures.py tests/test_capture_failures.py
git commit -m "feat(capture): add helper functions and tests for OCR failure capture tool"
```

---

## Chunk 2: Core capture logic + CLI

### Task 2: Implement `capture_pdf()` and integration test

**Files:**
- Modify: `tools/capture_failures.py` (add `capture_pdf` function)
- Modify: `tests/test_capture_failures.py` (add integration test)

**Context:** The integration test uses `eval/fixtures/real/INS_31docs.pdf`, which is known to have visually clear pages that fail all OCR tiers. It should produce ≥1 capture. The test writes to a `tmp_path` (pytest fixture) so it doesn't pollute `data/ocr_failures/`.

- [ ] **Step 1: Write the failing integration test**

Add to `tests/test_capture_failures.py`:

```python
import pytest
from pathlib import Path
from tools.capture_failures import capture_pdf

FIXTURE_INS31 = Path("eval/fixtures/real/INS_31docs.pdf")

@pytest.mark.skipif(not FIXTURE_INS31.exists(), reason="fixture not found")
def test_capture_pdf_ins31_produces_failures(tmp_path):
    """INS_31docs is a known failure case — must produce at least 1 captured page."""
    failures = capture_pdf(FIXTURE_INS31, out_dir=tmp_path)

    assert len(failures) >= 1, "Expected at least 1 OCR failure in INS_31docs"

    # Every failure must have a saved PNG
    for row in failures:
        img_path = tmp_path / row["image_path"]
        assert img_path.exists(), f"Missing image: {img_path}"
        assert img_path.stat().st_size > 0

    # CSV must exist and have correct headers
    csv_path = tmp_path / "failures_index.csv"
    assert csv_path.exists()
    import csv as _csv
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = _csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == len(failures)
    assert list(rows[0].keys()) == CSV_COLUMNS
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/test_capture_failures.py::test_capture_pdf_ins31_produces_failures -v
```

Expected: `ImportError: cannot import name 'capture_pdf'`

- [ ] **Step 3: Implement `capture_pdf()` in `tools/capture_failures.py`**

Add after the helpers section. Heavy imports live here, not at module level:

```python
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
    import cv2
    import fitz  # PyMuPDF
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    import core.analyzer as analyzer
    from core.analyzer import (
        _render_clip, _tess_ocr, _upsample_4x, _parse,
        _setup_sr, _init_easyocr,
        DPI, EASYOCR_DPI,
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
```

- [ ] **Step 4: Run the integration test**

```bash
pytest tests/test_capture_failures.py::test_capture_pdf_ins31_produces_failures -v -s
```

Expected: PASS. You should see `[FAIL] page   1 — saved INS_31docs/p001_...png` in the output.

- [ ] **Step 5: Run the full test suite to check nothing regressed**

```bash
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/capture_failures.py tests/test_capture_failures.py
git commit -m "feat(capture): implement capture_pdf core logic with integration test"
```

---

### Task 3: CLI entry point + directory support

**Files:**
- Modify: `tools/capture_failures.py` (add `main()` + `if __name__ == "__main__"`)

**Context:** The CLI must accept either a single PDF path or a directory. `_setup_sr` must be called once before any page is processed. If `--easyocr` flag is passed, also call `_init_easyocr`.

- [ ] **Step 1: Add `main()` to `tools/capture_failures.py`**

Add at the end of the file:

```python
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
```

- [ ] **Step 2: Smoke-test the CLI manually**

```bash
source .venv-cuda/Scripts/activate
python tools/capture_failures.py eval/fixtures/real/INS_31docs.pdf
```

Expected output (example):
```
[capture] Initializing SR...
SR Tier-2: PyTorch GPU bicubic 4x (NVIDIA GeForce GTX 1080)
[capture] INS_31docs: 31 pages
  [FAIL] page   1 — saved INS_31docs/p001_20260317_143022.png
  ...
[capture] done: N failures / 31 pages

[capture] Total: N failures captured → data/ocr_failures/failures_index.csv
```

Verify the output:
```bash
ls data/ocr_failures/INS_31docs/
cat data/ocr_failures/failures_index.csv
```

- [ ] **Step 3: Run full test suite one final time**

```bash
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 4: Final commit**

```bash
git add tools/capture_failures.py
git commit -m "feat(capture): add CLI entry point with file/directory support and --easyocr flag"
```
