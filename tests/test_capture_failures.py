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
