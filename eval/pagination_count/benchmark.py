"""Benchmark harness: run the production scanner + pagination engine against GT samples.

Usage (from project root, with venv active)::

    python eval/pagination_count/benchmark.py

Writes rows to ``eval/pagination_count/results/benchmark.json``.  The results
directory is gitignored — it may contain derived artefacts from real corpus PDFs.

DATA-SAFETY: extracted PDF slices are written to a ``tempfile.TemporaryDirectory``
that is cleaned up automatically.  No corpus bytes are persisted to disk.

The RCH benchmark (``run_rch_benchmark`` / ``main_rch``, Track D / D2 Task 7)
is a SEPARATE entry point that reads only ``data/samples/`` (never the corpus
— the round's "Samples only" rule) — see its own docstring below.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

import fitz

from core.scanners import _build_scanner_for_sigla
from core.scanners.anchors_scanner import AnchorsScanner
from core.scanners.cancellation import CancellationToken
from core.scanners.utils.pagination_count import (
    count_documents_by_pagination as production_count_pagination,
)
from eval.pagination_count.engine import (
    count_by_arithmetic_dedup,
    count_by_hybrid_fallback,
    count_by_region_discriminator,
    count_documents_by_pagination,
    detect_repeated_pattern,
)
from eval.pagination_count.rch_survey import (
    _GT_PATH,
    _SAMPLES_DIR,
    CHARLA_SAMPLES,
    homogeneous_period,
    survey_pdf,
)
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
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")  # Windows cp1252 console safety (→/Δ glyphs)
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


# ---------------------------------------------------------------------------
# RCH benchmark (Track D / D2, Task 7). Compares the production anchors
# scanner against plain production pagination and each Task-6 de-dup
# approach, on the 7 real charla samples under ``data/samples/`` — NEVER the
# corpus (this round's "Samples only" rule). Separate entry point
# (``run_rch_benchmark`` / ``main_rch``) from the corpus-based
# ``run_benchmark`` / ``main`` above.
# ---------------------------------------------------------------------------


def _slice_pdf(src_path: Path, dest_path: Path, max_pages: int) -> int:
    """Copy the first ``min(page_count, max_pages)`` pages of *src_path* into
    *dest_path*. Returns the number of pages written."""
    with fitz.open(src_path) as src:
        n = min(src.page_count, max_pages)
        out = fitz.open()
        out.insert_pdf(src, from_page=0, to_page=n - 1)
        out.save(dest_path)
        out.close()
    return n


def run_rch_benchmark(
    samples: dict[str, str] = CHARLA_SAMPLES,
    *,
    max_pages: int = 60,
) -> list[dict]:
    """Benchmark row per charla sample: production anchors vs plain pagination
    vs each Task-6 de-dup approach.

    Each sample is windowed to ``max_pages`` (spec/plan: "cap survey/benchmark
    page counts sensibly") for a cost-bounded, apples-to-apples comparison —
    CH_39/CH_51/CH_74 exceed 60 pages and are windowed; the other 4 samples
    fit whole. For the 3 homogeneous (exact N-pages-per-doc) samples, a
    ``windowed_gt`` is derived from the window size and the known period
    (``homogeneous_period``, same helper Fase 0 uses) — for non-homogeneous
    samples that don't fit in the window (CH_74 only), ``windowed_gt`` is
    ``None`` and that row is informational (counts are still reported, but
    not compared against a numeric delta).

    Args:
        samples: gt_key -> filename map (default: the 7 named charla samples).
        max_pages: page window per sample.

    Returns:
        One dict per sample: pages/gt columns, each approach's count, and
        wall-clock seconds for the anchors vs plain-pagination production
        calls (the speed comparison — the discriminator's extra top-left-half
        OCR pass is NOT counted here, since the winning approach doesn't ship
        it; see the decision record for that distinction).
    """
    gt = json.loads(_GT_PATH.read_text(encoding="utf-8"))
    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="rch_bench_") as tmp:
        tmp_root = Path(tmp)
        for gt_key, filename in samples.items():
            pdf_path = _SAMPLES_DIR / filename
            if not pdf_path.exists():
                logger.warning("SKIP %s — file not found: %s", gt_key, pdf_path)
                continue
            with fitz.open(pdf_path) as doc:
                full_pages = doc.page_count
            gt_docs = gt.get(gt_key, {}).get("doc_count")
            if gt_docs is None:
                logger.warning("SKIP %s — no ground_truth.json entry", gt_key)
                continue
            window = min(full_pages, max_pages)
            period = homogeneous_period(full_pages, gt_docs)
            if period is not None:
                windowed_gt = window // period
            elif window >= full_pages:
                windowed_gt = gt_docs
            else:
                windowed_gt = None  # CH_74 only — no clean window label, informational row

            # One isolated dir per sample, sigla token in the filename, so the
            # production AnchorsScanner's filename_glob pre-count resolves it.
            sample_dir = tmp_root / gt_key
            sample_dir.mkdir(parents=True, exist_ok=True)
            slice_path = sample_dir / f"charla_{gt_key}.pdf"
            _slice_pdf(pdf_path, slice_path, max_pages)

            cancel = CancellationToken()

            # (a) anchors baseline — instantiated DIRECTLY, not via the
            # registry: since the Task-8 flip, _build_scanner_for_sigla
            # ("charla") returns PaginationScanner, so routing through it
            # would silently benchmark pagination against itself. Direct
            # AnchorsScanner keeps this column an honest, re-runnable
            # anchors measurement (same bypass idiom as column (b)).
            t0 = time.perf_counter()
            anchors_result = AnchorsScanner(sigla="charla").count_ocr(sample_dir, cancel=cancel)
            anchors_seconds = time.perf_counter() - t0
            anchors_count = anchors_result.count

            # (b) plain production pagination — no de-dup.
            t0 = time.perf_counter()
            pag_result = production_count_pagination(slice_path, cancel=cancel)
            pag_seconds = time.perf_counter() - t0

            # (c) the 3 Task-6 approaches, fed from one shared OCR pass
            # (current + top_left_half corners) — reuses the Fase-0 survey
            # reader so counts aren't derived from a second, independent OCR
            # run of the pagination corner.
            survey_rows = survey_pdf(slice_path, max_pages=window)
            current_rows = sorted(
                (r for r in survey_rows if r.region == "current"), key=lambda r: r.page_idx
            )
            tl_rows = sorted(
                (r for r in survey_rows if r.region == "top_left_half"),
                key=lambda r: r.page_idx,
            )
            parsed = [(r.curr, r.total, r.code) for r in current_rows]
            anchor_hits = [len(r.matched_anchors) >= 2 for r in tl_rows]

            rows.append(
                {
                    "sample": gt_key,
                    "pages_total": full_pages,
                    "pages_window": window,
                    "gt_docs": gt_docs,
                    "windowed_gt": windowed_gt,
                    "repeated_pattern_detected": detect_repeated_pattern(parsed),
                    "anchors_count": anchors_count,
                    "anchors_seconds": round(anchors_seconds, 2),
                    "pag_count": pag_result.count,
                    "pag_seconds": round(pag_seconds, 2),
                    "arithmetic_count": count_by_arithmetic_dedup(parsed),
                    "region_discriminator_count": count_by_region_discriminator(
                        parsed, anchor_hits
                    ),
                    "hybrid_count": count_by_hybrid_fallback(
                        parsed, anchors_fallback_count=anchors_count
                    ),
                }
            )
            logger.info(
                "  %s: window=%d/%d windowed_gt=%s anchors=%d(%.1fs) pag=%d(%.1fs) "
                "arith=%s region=%d hybrid=%d",
                gt_key,
                window,
                full_pages,
                windowed_gt,
                anchors_count,
                anchors_seconds,
                pag_result.count,
                pag_seconds,
                rows[-1]["arithmetic_count"],
                rows[-1]["region_discriminator_count"],
                rows[-1]["hybrid_count"],
            )
    return rows


def main_rch() -> None:
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"
    )
    rows = run_rch_benchmark()
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = _RESULTS_DIR / "rch_benchmark.json"
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(rows)} rows → {out}")


if __name__ == "__main__":
    main()
