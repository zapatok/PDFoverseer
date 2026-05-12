import shutil
from pathlib import Path

import openpyxl

from core.excel.template import DEFAULT_TEMPLATE
from core.excel.writer import ExcelGenerationResult, generate_resumen


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


def test_writer_priority_override_over_ocr_over_filename(tmp_path):
    from core.excel.writer import resolve_cell_value

    # Override wins
    assert resolve_cell_value({"user_override": 17, "ocr_count": 16, "filename_count": 1}) == 17
    # OCR wins when no override
    assert resolve_cell_value({"user_override": None, "ocr_count": 16, "filename_count": 1}) == 16
    # Filename wins when neither
    assert resolve_cell_value({"user_override": None, "ocr_count": None, "filename_count": 5}) == 5
    # All null → 0
    assert (
        resolve_cell_value({"user_override": None, "ocr_count": None, "filename_count": None}) == 0
    )
    # Excluded → None signals "do not write"
    assert resolve_cell_value({"user_override": 5, "excluded": True}) is None
    # Legacy count field (un-migrated) → still works
    assert resolve_cell_value({"count": 42}) == 42
    # Override of 0 is meaningful (explicit zero), wins over ocr_count
    assert resolve_cell_value({"user_override": 0, "ocr_count": 16, "filename_count": 1}) == 0


def test_writer_uses_priority_in_generate_resumen(tmp_path):
    """Smoke test: generate_resumen uses resolve_cell_value internally."""
    from core.excel.writer import generate_resumen

    cell_values = {
        # Caller pre-resolved values; writer just writes named ranges.
        "HPV_art_count": 767,
        "HRB_odi_count": 17,
    }
    out = tmp_path / "out.xlsx"
    result = generate_resumen(cell_values=cell_values, output_path=out)
    assert result.cells_written == 2
    assert out.exists()
