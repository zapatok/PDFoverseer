"""Orchestrator: enumerate month folder + dispatch scans to scanners."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.domain import CATEGORY_FOLDERS, HOSPITALS, SIGLAS


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
    cells: dict[str, list[CellInventory]]  # hospital → list of 18 cells


def _find_category_folder(hosp_dir: Path, sigla: str) -> Path:
    """Locate the folder for `sigla` inside a hospital dir, tolerating
    TOTAL/' 0' suffixes.

    Args:
        hosp_dir: Path to the hospital directory.
        sigla: The category sigla to look up.

    Returns:
        Path to the category folder (nominal path even if it doesn't exist).
    """
    canonical = CATEGORY_FOLDERS[sigla]
    direct = hosp_dir / canonical
    if direct.exists():
        return direct
    # search for a directory matching canonical name with a numeric/text suffix
    for sub in hosp_dir.iterdir():
        if not sub.is_dir():
            continue
        if sub.name == canonical or sub.name.startswith(canonical + " "):
            return sub
    return direct  # nominal path even if it doesn't exist


def enumerate_month(month_root: Path) -> MonthInventory:
    """Discover hospitals and their 18 category cells inside a month folder.

    A hospital directory is considered *present* only if at least one of its
    18 canonical category folders exists inside it.  Directories that exist on
    disk but contain no recognised category subfolders (e.g. HLL with only a
    OneDrive zip) are classified as *missing*.

    Args:
        month_root: Path to the month folder (e.g. ``A:/informe mensual/ABRIL``).

    Returns:
        A :class:`MonthInventory` with hospitals_present, hospitals_missing,
        and a cells dict mapping each present hospital to its 18
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

        # Build the 18 cells regardless of whether the hospital dir exists.
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


def scan_cell(cell: CellInventory) -> ScanResult:
    """Run the registered scanner for this cell's sigla.

    Args:
        cell: A :class:`CellInventory` describing the folder to scan.

    Returns:
        A :class:`ScanResult` with count, confidence, method, and flags.
    """
    from core import scanners as scanner_registry  # noqa: E402
    from core.scanners.base import ScanResult  # noqa: E402, F401

    scanner = scanner_registry.get(cell.sigla)
    return scanner.count(cell.folder_path)


def _scan_cell_worker(cell_tuple: tuple[str, str, str]) -> tuple[str, str, ScanResult]:
    """Pool worker entry — re-imports happen in subprocess.

    Args:
        cell_tuple: ``(hospital, sigla, folder_str)`` packed for pickling.

    Returns:
        ``(hospital, sigla, ScanResult)`` tuple.
    """
    from core import scanners as scanner_registry  # noqa: E402
    from core.scanners.base import ScanResult  # noqa: E402, F401

    hosp, sigla, folder_str = cell_tuple
    folder = Path(folder_str)
    scanner = scanner_registry.get(sigla)
    return (hosp, sigla, scanner.count(folder))


def scan_month(
    inv: MonthInventory,
    *,
    max_workers: int | None = None,
) -> dict[tuple[str, str], ScanResult]:
    """Scan all cells in the inventory in parallel.

    Args:
        inv: A :class:`MonthInventory` from :func:`enumerate_month`.
        max_workers: Process pool size. Defaults to ``min(8, cpu_count-1)``.

    Returns:
        Dict keyed by ``(hospital, sigla)`` mapping to :class:`ScanResult`.
    """
    import os  # noqa: E402
    from concurrent.futures import ProcessPoolExecutor  # noqa: E402

    from core.scanners.base import ScanResult  # noqa: E402, F401

    if max_workers is None:
        max_workers = max(1, min(8, (os.cpu_count() or 4) - 1))

    cell_tuples = [
        (c.hospital, c.sigla, str(c.folder_path)) for cells in inv.cells.values() for c in cells
    ]

    results: dict[tuple[str, str], ScanResult] = {}

    if max_workers == 1:
        for ct in cell_tuples:
            hosp, sigla, r = _scan_cell_worker(ct)
            results[(hosp, sigla)] = r
        return results

    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        for hosp, sigla, r in pool.map(_scan_cell_worker, cell_tuples):
            results[(hosp, sigla)] = r
    return results
