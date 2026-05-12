"""Audit ABRIL: scanner count vs raw PDF count per (hospital, sigla).

Usage: python tools/audit_filename_glob.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.domain import HOSPITALS  # noqa: E402
from core.orchestrator import enumerate_month, scan_month  # noqa: E402
from core.scanners.utils.filename_glob import extract_sigla  # noqa: E402

ABRIL = Path("A:/informe mensual/ABRIL")


def main() -> int:
    inv = enumerate_month(ABRIL)
    results = scan_month(inv)

    print(f"{'HOSP':<5} {'SIGLA':<20} {'SCAN':>6} {'RAW':>6} {'NONE':>6} {'NOTES'}")
    print("-" * 90)

    discrepancies = 0
    for hosp in HOSPITALS:
        if hosp not in inv.cells:
            continue
        for cell in inv.cells[hosp]:
            sigla = cell.sigla
            r = results.get((hosp, sigla))
            scan_count = r.count if r else "?"
            folder = cell.folder_path
            if not folder.exists():
                print(f"{hosp:<5} {sigla:<20} {scan_count:>6} {'-':>6} {'-':>6}  folder missing")
                continue
            pdfs = list(folder.rglob("*.pdf"))
            raw = len(pdfs)
            none_count = sum(1 for p in pdfs if extract_sigla(p.name) is None)
            notes = ""
            if scan_count != raw:
                discrepancies += 1
                notes = f"DISCREPANCY: scanner missed {raw - scan_count}"
            elif none_count > 0:
                notes = f"({none_count} unrecognised filenames but counted)"
            print(f"{hosp:<5} {sigla:<20} {scan_count:>6} {raw:>6} {none_count:>6}  {notes}")

    print("-" * 90)
    print(f"Total cells with scanner != raw: {discrepancies}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
