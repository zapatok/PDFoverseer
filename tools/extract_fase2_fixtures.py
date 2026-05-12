"""Copy real PDFs from A:/informe mensual/ABRIL into folder-shaped fixtures
under tests/fixtures/scanners_ocr/.

Run from project root:
    python tools/extract_fase2_fixtures.py

Idempotent. Picks the largest PDF in each source folder as the most likely
compilation candidate. Creates a 0-byte corrupted.pdf for error tests.
Asserts page-count thresholds and exits non-zero if any fixture would
fall below the compilation_suspect cutoff for its sigla.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = Path("A:/informe mensual/ABRIL")
DST_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "scanners_ocr"

# (subfolder_name, dest_filename, source_folder, sigla, min_pages)
# min_pages = EXPECTED_PAGES_PER_DOC[sigla] * 5 (the _TIGHT_FACTOR used by
# flag_compilation_suspect - see core/scanners/utils/page_count_heuristic.py)
FIXTURES = [
    ("art_multidoc", "art_multidoc.pdf", SRC_ROOT / "HLU" / "7.-ART", "art", 50),
    ("odi_compilation", "HRB_odi_compilation.pdf", SRC_ROOT / "HRB" / "3.-ODI Visitas", "odi", 10),
    (
        "irl_compilation",
        "HRB_irl_compilation.pdf",
        SRC_ROOT / "HRB" / "2.-Induccion IRL",
        "irl",
        10,
    ),
    (
        "charla_compilation",
        "HRB_charla_compilation.pdf",
        SRC_ROOT / "HRB" / "4.-Charlas",
        "charla",
        10,
    ),
]


def pick_largest_pdf(folder: Path) -> Path | None:
    pdfs = list(folder.rglob("*.pdf"))
    if not pdfs:
        return None
    return max(pdfs, key=lambda p: p.stat().st_size)


def _page_count(path: Path) -> int:
    """Best-effort page count for verification. Returns -1 on failure."""
    try:
        import fitz  # PyMuPDF

        with fitz.open(path) as doc:
            return len(doc)
    except Exception:  # noqa: BLE001
        return -1


def main() -> int:
    DST_ROOT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    for subfolder, dst_name, src_folder, sigla, min_pages in FIXTURES:
        src = pick_largest_pdf(src_folder)
        if src is None:
            failures.append(f"  MISSING {subfolder}/{dst_name} - no PDFs in {src_folder}")
            continue
        target_folder = DST_ROOT / subfolder
        target_folder.mkdir(parents=True, exist_ok=True)
        dst = target_folder / dst_name
        shutil.copy(src, dst)
        pp = _page_count(dst)
        if pp < min_pages:
            failures.append(
                f"  BELOW THRESHOLD {subfolder}/{dst_name}: {pp}pp < required {min_pages}pp "
                f"for sigla={sigla} - picked PDF is NOT a compilation candidate. "
                f"Pick a different source or extend FIXTURES with an explicit override."
            )
            continue
        print(
            f"  OK {subfolder}/{dst_name} from {src.name} ({dst.stat().st_size:,} bytes, {pp}pp >= {min_pages})"
        )

    # Synthetic 0-byte corrupted PDF for error-handling tests.
    # Allowed exception to the "real fixtures only" rule per
    # feedback_art670_fixture_disaster - degenerate input for error tests, not
    # data substitution.
    corrupted_folder = DST_ROOT / "corrupted"
    corrupted_folder.mkdir(parents=True, exist_ok=True)
    (corrupted_folder / "corrupted.pdf").write_bytes(b"")
    print("  OK corrupted/corrupted.pdf (0 bytes, synthetic)")

    if failures:
        print()
        print("FAILURES:")
        for f in failures:
            print(f)
        print()
        print("Fix: locate a real compilation PDF for the failing sigla and either")
        print(" 1) ensure it is the largest PDF in its source folder, or")
        print(" 2) edit FIXTURES with an explicit Path override to the desired PDF.")
        return 1

    print()
    print(f"All {len(FIXTURES)} real fixtures + 1 synthetic written to {DST_ROOT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
