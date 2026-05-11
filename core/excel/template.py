"""Excel template loader using named ranges (workbook-level defined names)."""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from openpyxl.workbook import Workbook

DEFAULT_TEMPLATE = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "templates"
    / "RESUMEN_template_v1.xlsx"
)


def load_template(path: Path = DEFAULT_TEMPLATE) -> Workbook:
    """Load a template Excel workbook. Use copy-and-modify in writer.

    Args:
        path: Path to the .xlsx template file.

    Returns:
        Opened openpyxl Workbook object.
    """
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {path}")
    return load_workbook(path)


def list_named_ranges(wb: Workbook) -> list[str]:
    """Return all workbook-level defined names.

    Args:
        wb: An openpyxl Workbook.

    Returns:
        List of defined name strings.
    """
    return list(wb.defined_names)


def get_range_cell(wb: Workbook, name: str) -> tuple[str, str]:
    """Resolve a named range to (sheet_name, cell_address). Single-cell only.

    Args:
        wb: An openpyxl Workbook.
        name: The defined name to look up.

    Returns:
        Tuple of (sheet_name, cell_address).
    """
    dn = wb.defined_names[name]
    destinations = list(dn.destinations)
    if len(destinations) != 1:
        raise ValueError(f"Range {name!r} resolves to {len(destinations)} cells")
    sheet, coord = destinations[0]
    return sheet, coord
