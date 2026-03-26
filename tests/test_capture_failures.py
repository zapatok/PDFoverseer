import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime

from tools.capture_failures import _build_csv_row, _make_image_filename, _make_image_path


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

from pathlib import Path

import pytest

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
