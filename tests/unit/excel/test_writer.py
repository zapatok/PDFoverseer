import shutil
from pathlib import Path

import openpyxl
import pytest
from core.excel.writer import ExcelGenerationResult, generate_resumen

from core.excel.template import DEFAULT_TEMPLATE


def test_generate_writes_atomic_file(tmp_path):
    output = tmp_path / "RESUMEN_TEST.xlsx"
    cell_values = {
        "HPV_art_count": 767,
        "HRB_irl_count": 92,
    }
    result = generate_resumen(
        cell_values=cell_values,
        output_path=output,
        template_path=DEFAULT_TEMPLATE,
    )
    assert isinstance(result, ExcelGenerationResult)
    assert output.exists()
    # no leftover tmp file
    assert not Path(str(output) + ".tmp").exists()
    assert result.cells_written == 2


def test_generated_file_has_correct_values(tmp_path):
    output = tmp_path / "RESUMEN_VALUES.xlsx"
    generate_resumen(
        cell_values={"HPV_art_count": 767},
        output_path=output,
        template_path=DEFAULT_TEMPLATE,
    )
    wb = openpyxl.load_workbook(output)
    sheet_name, coord = next(iter(wb.defined_names["HPV_art_count"].destinations))
    assert wb[sheet_name][coord].value == 767


def test_existing_target_is_backed_up(tmp_path):
    output = tmp_path / "RESUMEN_BAK.xlsx"
    shutil.copy(DEFAULT_TEMPLATE, output)  # pre-existing file
    generate_resumen(
        cell_values={"HPV_art_count": 100},
        output_path=output,
        template_path=DEFAULT_TEMPLATE,
    )
    assert output.exists()
    assert (output.parent / (output.name + ".bak")).exists()


def test_unknown_range_emits_warning(tmp_path):
    output = tmp_path / "RESUMEN_WARN.xlsx"
    result = generate_resumen(
        cell_values={"NONEXISTENT_RANGE": 42},
        output_path=output,
        template_path=DEFAULT_TEMPLATE,
    )
    assert any("NONEXISTENT_RANGE" in w for w in result.warnings)
    assert result.cells_written == 0
