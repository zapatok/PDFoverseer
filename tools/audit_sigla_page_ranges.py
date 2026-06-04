"""One-off audit: typical page-count range per sigla, from the real corpus.

Walks ``INFORME_MENSUAL_ROOT`` (every month folder × hospital), resolves each
sigla's category folder the same way the app does, opens each PDF for its page
count, and prints ``{sigla: {p25, median, p75, min, max, n}}`` as JSON.

The p25–p75 band feeds ``frontend/src/lib/sigla-info.js`` (rev-2 §6.3); it is
robust to outliers (e.g. a 399-page charla compilation). This is a standalone
tool — ``print()`` is intentional — and is NOT part of the test suite.

Usage:
    python tools/audit_sigla_page_ranges.py            # all months under the root
    INFORME_MENSUAL_ROOT=A:/informe mensual python tools/audit_sigla_page_ranges.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

# Standalone tool: put the repo root on sys.path so `core` imports resolve when
# run as `python tools/audit_sigla_page_ranges.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz  # PyMuPDF  # noqa: E402

from core.domain import SIGLAS  # noqa: E402
from core.orchestrator import _find_category_folder  # noqa: E402
from core.scanners.utils.cell_enumeration import enumerate_cell_pdfs  # noqa: E402

HOSPITALS = ["HPV", "HRB", "HLU", "HLL"]


def _quantile(sorted_vals: list[int], q: float) -> int:
    """Nearest-rank quantile (good enough for a typical-range display)."""
    n = len(sorted_vals)
    idx = min(n - 1, max(0, round(q * (n - 1))))
    return sorted_vals[idx]


def main() -> None:
    root = Path(os.environ.get("INFORME_MENSUAL_ROOT", "A:/informe mensual"))
    if not root.exists():
        print(f"root not found: {root}", file=sys.stderr)
        sys.exit(1)

    pages_by_sigla: dict[str, list[int]] = defaultdict(list)
    for month_dir in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        for hosp in HOSPITALS:
            hosp_dir = month_dir / hosp
            if not hosp_dir.exists():
                continue
            for sigla in SIGLAS:
                folder = _find_category_folder(hosp_dir, sigla)
                if not folder.exists():
                    continue
                for pdf in enumerate_cell_pdfs(folder):
                    try:
                        with fitz.open(pdf) as doc:
                            pages_by_sigla[sigla].append(doc.page_count)
                    except Exception as exc:  # noqa: BLE001 — skip unreadable files
                        print(f"skip {pdf}: {exc}", file=sys.stderr)
        print(f"done month {month_dir.name}", file=sys.stderr)

    out: dict[str, dict | None] = {}
    for sigla in SIGLAS:
        vals = sorted(pages_by_sigla[sigla])
        if not vals:
            out[sigla] = None
            continue
        out[sigla] = {
            "p25": _quantile(vals, 0.25),
            "median": _quantile(vals, 0.5),
            "p75": _quantile(vals, 0.75),
            "min": vals[0],
            "max": vals[-1],
            "n": len(vals),
        }

    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
