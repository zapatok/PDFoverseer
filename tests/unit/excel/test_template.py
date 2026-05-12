from pathlib import Path

import pytest

from core.excel.template import DEFAULT_TEMPLATE, list_named_ranges, load_template


def test_default_template_exists():
    assert DEFAULT_TEMPLATE.exists()


def test_load_template_returns_workbook():
    wb = load_template(DEFAULT_TEMPLATE)
    assert any("Cump" in s for s in wb.sheetnames)


def test_list_named_ranges_includes_expected_count_cells():
    wb = load_template(DEFAULT_TEMPLATE)
    names = list_named_ranges(wb)
    # 72 cantidad cells expected
    cantidad_names = [n for n in names if n.endswith("_count")]
    assert len(cantidad_names) == 72
    assert "HPV_art_count" in names
    assert "HLL_reunion_count" in names
