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
