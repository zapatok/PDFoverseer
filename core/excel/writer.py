"""Excel writer: fill named ranges + atomic write-then-rename."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook

from core.excel.template import DEFAULT_TEMPLATE, get_range_cell


@dataclass(frozen=True)
class ExcelGenerationResult:
    output_path: Path
    cells_written: int
    warnings: list[str] = field(default_factory=list)
    duration_ms: int = 0


def generate_resumen(
    *,
    cell_values: dict[str, int | float | str],
    output_path: Path,
    template_path: Path = DEFAULT_TEMPLATE,
) -> ExcelGenerationResult:
    """Fill named ranges in a template and write atomically to output_path.

    Behavior:
    1. Load template (copy in memory, do NOT modify on disk)
    2. For each (named_range, value) in cell_values: set the cell
    3. Save to <output_path>.tmp
    4. If <output_path> exists, rename it to <output_path>.bak
    5. Rename <output_path>.tmp → <output_path>

    Args:
        cell_values: Mapping of named-range → value to write.
        output_path: Destination .xlsx path.
        template_path: Source template (default: RESUMEN_template_v1.xlsx).

    Returns:
        ExcelGenerationResult with cells_written count, warnings, and timing.
    """
    start = time.perf_counter()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wb = load_workbook(template_path)
    warnings: list[str] = []
    cells_written = 0

    for name, value in cell_values.items():
        if name not in wb.defined_names:
            warnings.append(f"named range not found: {name}")
            continue
        try:
            sheet_name, coord = get_range_cell(wb, name)
        except ValueError as exc:
            warnings.append(f"{name}: {exc}")
            continue
        wb[sheet_name][coord] = value
        cells_written += 1

    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    wb.save(tmp_path)

    bak_path = output_path.with_suffix(output_path.suffix + ".bak")
    if output_path.exists():
        if bak_path.exists():
            bak_path.unlink()
        output_path.rename(bak_path)
    tmp_path.rename(output_path)

    duration_ms = int((time.perf_counter() - start) * 1000)
    return ExcelGenerationResult(
        output_path=output_path,
        cells_written=cells_written,
        warnings=warnings,
        duration_ms=duration_ms,
    )
