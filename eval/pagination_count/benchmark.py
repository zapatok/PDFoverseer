"""Benchmark harness: run the production scanner + pagination engine against GT samples.

Usage (from project root, with venv active)::

    python eval/pagination_count/benchmark.py

Writes rows to ``eval/pagination_count/results/benchmark.json``.  The results
directory is gitignored — it may contain derived artefacts from real corpus PDFs.

DATA-SAFETY: extracted PDF slices are written to a ``tempfile.TemporaryDirectory``
that is cleaned up automatically.  No corpus bytes are persisted to disk.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

import fitz

from core.scanners import _build_scanner_for_sigla
from core.scanners.cancellation import CancellationToken
from eval.pagination_count.engine import count_documents_by_pagination
from eval.pagination_count.samples import SAMPLES, Sample

logger = logging.getLogger(__name__)

_DEFAULT_ROOT = os.getenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")

# Output directory for benchmark results (gitignored).
_RESULTS_DIR = Path(__file__).parent / "results"


def extract_sample(sample: Sample, root: Path, dest_dir: Path) -> Path:
    """Extract *sample* from the corpus into a fresh PDF in *dest_dir*.

    Opens the first file that matches ``root/MAYO/<sample.glob>`` with PyMuPDF,
    copies ``sample.page_range`` pages (or all pages when ``None``) into a new
    PDF, and saves it as ``dest_dir/<sigla>_smp.pdf``.  The sigla token in the
    filename makes the production filename-glob matcher recognise it as belonging
    to that category.

    Args:
        sample: The Sample descriptor (sigla, glob, page_range, gt, …).
        root: Path to the corpus root (``INFORME_MENSUAL_ROOT``).
        dest_dir: Temporary directory; the extracted PDF is written here.

    Returns:
        Path to the extracted (slice) PDF.

    Raises:
        FileNotFoundError: When no file matches the sample glob.
    """
    mayo = root / "MAYO"
    matches = list(mayo.glob(sample.glob))
    if not matches:
        raise FileNotFoundError(f"No corpus file matched glob '{sample.glob}' under {mayo}")
    source_pdf = matches[0]
    dest_path = dest_dir / f"{sample.sigla}_smp.pdf"

    with fitz.open(source_pdf) as src:
        out_doc = fitz.open()
        if sample.page_range is None:
            out_doc.insert_pdf(src)
        else:
            start, end = sample.page_range
            # page_range is (start, end) 0-based half-open — fitz insert_pdf
            # takes from_page / to_page inclusive.
            out_doc.insert_pdf(src, from_page=start, to_page=end - 1)
        out_doc.save(dest_path)
        out_doc.close()

    logger.info(
        "extracted %s → %s (%d pages)",
        source_pdf.name,
        dest_path.name,
        fitz.open(dest_path).page_count,
    )
    return dest_path


def run_one(sample: Sample, root: Path, *, tmp_root: Path) -> dict:
    """Run both scanners against one sample and return a result row.

    Creates a fresh sub-directory under *tmp_root*, extracts the sample PDF
    there, then runs:

    (a) The **production scanner** (``_build_scanner_for_sigla``) via
        ``count_ocr`` — the current baseline.
    (b) The **new pagination engine** (``count_documents_by_pagination``)
        directly — the candidate replacement.

    Args:
        sample: The GT sample to benchmark.
        root: Corpus root path.
        tmp_root: Parent temp directory; a fresh sub-dir is created per call.

    Returns:
        A dict with keys: sigla, file, pages, gt, gt_source, current_count,
        current_method, current_delta, pag_count, pag_delta, recovered, failed,
        dominant_total, codes.
    """
    # Each sample gets its own folder so the production scanner sees exactly one
    # PDF (its filename contains the sigla token → filename_glob fires correctly).
    sample_dir = tmp_root / f"{sample.sigla}_{id(sample)}"
    sample_dir.mkdir(parents=True, exist_ok=True)

    slice_pdf = extract_sample(sample, root, sample_dir)

    with fitz.open(slice_pdf) as doc:
        pages = doc.page_count

    cancel = CancellationToken()

    # --- (a) Production scanner ---
    scanner = _build_scanner_for_sigla(sample.sigla)
    current_result = scanner.count_ocr(sample_dir, cancel=cancel)
    current_count = current_result.count
    current_method = current_result.method

    # --- (b) Pagination engine ---
    pag_result = count_documents_by_pagination(
        slice_pdf,
        cancel=cancel,
        cover_code=sample.cover_code,
    )

    return {
        "sigla": sample.sigla,
        "file": slice_pdf.name,
        "pages": pages,
        "gt": sample.gt,
        "gt_source": sample.gt_source,
        "note": sample.note,
        "current_count": current_count,
        "current_method": current_method,
        "current_delta": current_count - sample.gt,
        "pag_count": pag_result.count,
        "pag_delta": pag_result.count - sample.gt,
        "recovered": pag_result.recovered_reads,
        "failed": pag_result.failed_reads,
        "dominant_total": pag_result.dominant_total,
        "codes": pag_result.codes,
    }


def run_benchmark(
    samples: list[Sample] = SAMPLES,
    root: Path | str = _DEFAULT_ROOT,
) -> list[dict]:
    """Run both scanners over all *samples* and return the rows.

    Extracted PDF slices are written inside a ``TemporaryDirectory`` that is
    deleted automatically when this function returns — no corpus bytes persist.

    Args:
        samples: GT sample list (defaults to ``SAMPLES`` from ``samples.py``).
        root: Corpus root directory (defaults to ``INFORME_MENSUAL_ROOT`` env
            var or ``"A:/informe mensual"``).

    Returns:
        List of result dicts, one per sample.
    """
    root = Path(root)
    rows: list[dict] = []

    with tempfile.TemporaryDirectory(prefix="pag_bench_") as tmp:
        tmp_root = Path(tmp)
        for i, sample in enumerate(samples, 1):
            logger.info("[%d/%d] %s …", i, len(samples), sample.sigla)
            try:
                row = run_one(sample, root, tmp_root=tmp_root)
                rows.append(row)
                logger.info(
                    "  gt=%d  current=%d (Δ%+d)  pag=%d (Δ%+d)",
                    row["gt"],
                    row["current_count"],
                    row["current_delta"],
                    row["pag_count"],
                    row["pag_delta"],
                )
            except FileNotFoundError as exc:
                logger.warning("SKIP %s — %s", sample.sigla, exc)
            except Exception as exc:  # noqa: BLE001
                logger.error("ERROR %s — %s", sample.sigla, exc, exc_info=True)

    return rows


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    rows = run_benchmark()
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = _RESULTS_DIR / "benchmark.json"
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(rows)} rows → {out}")


if __name__ == "__main__":
    main()
