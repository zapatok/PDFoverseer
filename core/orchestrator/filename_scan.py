"""Pase-1 filename-glob scan orchestration (parallel over all cells)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.orchestrator.enumeration import CellInventory, MonthInventory

if TYPE_CHECKING:
    from core.scanners.base import ScanResult


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
