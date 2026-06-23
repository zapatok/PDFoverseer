"""Month/cell enumeration: discover hospitals + their 20 category cells."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.domain import CATEGORY_FOLDERS, HOSPITALS, SIGLAS, folder_to_sigla


@dataclass(frozen=True)
class CellInventory:
    hospital: str
    sigla: str
    folder_path: Path
    folder_exists: bool
    pdf_count_hint: int  # quick rglob count, no parsing


@dataclass(frozen=True)
class MonthInventory:
    month_root: Path
    hospitals_present: list[str]
    hospitals_missing: list[str]
    cells: dict[str, list[CellInventory]]  # hospital → list of 20 cells


def _find_category_folder(hosp_dir: Path, sigla: str) -> Path:
    """Locate the folder for `sigla` inside a hospital dir, tolerating numeric
    renumbering and TOTAL/' 0' suffixes.

    Args:
        hosp_dir: Path to the hospital directory.
        sigla: The category sigla to look up.

    Returns:
        Path to the category folder (nominal canonical path even if absent).
    """
    canonical = CATEGORY_FOLDERS[sigla]
    direct = hosp_dir / canonical
    if direct.exists():
        return direct
    if not hosp_dir.exists():
        return direct  # nominal path when hospital dir is absent
    # Renumber-tolerant: return the subdirectory whose name resolves to this sigla.
    for sub in hosp_dir.iterdir():
        if sub.is_dir() and folder_to_sigla(sub.name) == sigla:
            return sub
    return direct  # nominal path even if it doesn't exist


def enumerate_month(month_root: Path) -> MonthInventory:
    """Discover hospitals and their 20 category cells inside a month folder.

    A hospital directory is considered *present* only if at least one of its
    20 canonical category folders exists inside it.  Directories that exist on
    disk but contain no recognised category subfolders (e.g. HLL with only a
    OneDrive zip) are classified as *missing*.

    Args:
        month_root: Path to the month folder (e.g. ``A:/informe mensual/ABRIL``).

    Returns:
        A :class:`MonthInventory` with hospitals_present, hospitals_missing,
        and a cells dict mapping each present hospital to its 20
        :class:`CellInventory` entries.

    Raises:
        FileNotFoundError: If ``month_root`` does not exist.
    """
    if not month_root.exists():
        raise FileNotFoundError(f"Month folder not found: {month_root}")

    present: list[str] = []
    missing: list[str] = []
    cells: dict[str, list[CellInventory]] = {}

    for hosp in HOSPITALS:
        hosp_dir = month_root / hosp

        # Build the 20 cells regardless of whether the hospital dir exists.
        cell_list: list[CellInventory] = []
        if hosp_dir.exists():
            for sigla in SIGLAS:
                folder = _find_category_folder(hosp_dir, sigla)
                exists = folder.exists()
                pdf_hint = len(list(folder.rglob("*.pdf"))) if exists else 0
                cell_list.append(
                    CellInventory(
                        hospital=hosp,
                        sigla=sigla,
                        folder_path=folder,
                        folder_exists=exists,
                        pdf_count_hint=pdf_hint,
                    )
                )
        else:
            # Hospital directory is entirely absent — build nominal cells.
            for sigla in SIGLAS:
                folder = hosp_dir / CATEGORY_FOLDERS[sigla]
                cell_list.append(
                    CellInventory(
                        hospital=hosp,
                        sigla=sigla,
                        folder_path=folder,
                        folder_exists=False,
                        pdf_count_hint=0,
                    )
                )

        # A hospital is "present" if its directory exists AND either:
        #   (a) it has at least one recognised category folder, or
        #   (b) it is completely empty (newly created, no content yet).
        # A directory that exists but contains only non-canonical files/folders
        # (e.g. HLL with a OneDrive zip) is treated as "missing".
        has_any_category = any(c.folder_exists for c in cell_list)
        dir_is_empty = hosp_dir.exists() and not any(hosp_dir.iterdir())
        if has_any_category or dir_is_empty:
            present.append(hosp)
            cells[hosp] = cell_list
        else:
            missing.append(hosp)

    return MonthInventory(
        month_root=month_root,
        hospitals_present=present,
        hospitals_missing=missing,
        cells=cells,
    )
