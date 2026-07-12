"""Real-sample benchmark: pytesseract vs tesserocr on both production OCR engines.

Track D §2 (D1), Task 3. Measures s/pag (seconds per page) for BOTH production
OCR-consuming engines — the pagination corner engine
(``core.scanners.utils.pagination_count.count_documents_by_pagination``) and
the anchors header-band engine
(``core.scanners.utils.header_band_anchors.count_covers_by_anchors``) —
against both OCR backends (pytesseract default, tesserocr opt-in, selected via
``OVERSEER_OCR_BACKEND``), with per-page threading ON (the engines' own
``OCR_PAGE_THREADS`` default), on 3 real samples from ``data/samples/``:
``CH_9.pdf``, ``ART_674.pdf``, ``CH_74docs.pdf``.

Large samples are capped to ``_MAX_PAGES`` pages via a temp-file slice (the
original sample is never modified) so the benchmark finishes in a couple of
minutes — s/pag is a per-page rate, so a representative subset is sufficient
to measure it (``ART_674.pdf`` alone has 2719 pages).

Also runs a lightweight RSS-stability check: the pagination engine over the
largest capped sample, run twice in a row under the tesserocr backend (the
backend that keeps engine state alive across calls via a thread-local
``PyTessBaseAPI`` — the only one with any plausible per-call leak risk).
Prints RSS before/after each run so growth would be visible; not a hard
pass/fail gate (2 runs on a small capped sample can't prove long-run
stability), just the informational check the plan asks for.

Usage (from repo root, venv active)::

    .venv-cuda/Scripts/python.exe -m eval.pagination_count.tesserocr_bench

DATA-SAFETY: reads only ``data/samples/*.pdf`` (tracked, non-personal
fixtures) — never the real corpus. Page-capped slices are written to a
``tempfile.TemporaryDirectory`` that is cleaned up automatically.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import fitz

from core.scanners.cancellation import CancellationToken
from core.scanners.patterns import PATTERNS
from core.scanners.utils.header_band_anchors import count_covers_by_anchors
from core.scanners.utils.pagination_count import count_documents_by_pagination

try:
    import psutil
except ImportError:  # pragma: no cover - RSS check degrades gracefully without it
    psutil = None

_SAMPLES_DIR = Path(__file__).resolve().parents[2] / "data" / "samples"
_SAMPLE_NAMES = ["CH_9.pdf", "ART_674.pdf", "CH_74docs.pdf"]
_MAX_PAGES = 40  # a per-page rate is representative on a subset; keeps runtime tight
_BACKENDS = ["pytesseract", "tesserocr"]
_ANCHOR_FLAVORS = PATTERNS["charla"]["cover_flavors"]  # drives real 2-pass OCR work


def _capped_copy(src: Path, dest: Path, max_pages: int) -> int:
    """Write the first ``min(max_pages, page_count)`` pages of *src* to *dest*.

    Returns:
        The number of pages written.
    """
    with fitz.open(src) as doc:
        n = min(max_pages, doc.page_count)
        out = fitz.open()
        out.insert_pdf(doc, from_page=0, to_page=n - 1)
        out.save(dest)
        out.close()
    return n


def _rss_mb() -> float | None:
    """Current process RSS in MB, or None if psutil isn't installed."""
    if psutil is None:
        return None
    return psutil.Process().memory_info().rss / (1024 * 1024)


def _time_pagination(pdf_path: Path, backend: str) -> tuple[float, int]:
    os.environ["OVERSEER_OCR_BACKEND"] = backend
    t0 = time.perf_counter()
    result = count_documents_by_pagination(pdf_path, cancel=CancellationToken())
    elapsed = time.perf_counter() - t0
    return elapsed, result.pages_total


def _time_anchors(pdf_path: Path, backend: str) -> tuple[float, int]:
    os.environ["OVERSEER_OCR_BACKEND"] = backend
    t0 = time.perf_counter()
    result = count_covers_by_anchors(pdf_path, flavors=_ANCHOR_FLAVORS)
    elapsed = time.perf_counter() - t0
    return elapsed, result.pages_total


def main() -> None:
    """Run the real-sample s/pag benchmark (both engines x both backends) + RSS check."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        capped: dict[str, Path] = {}
        page_counts: dict[str, int] = {}
        for name in _SAMPLE_NAMES:
            dest = tmp_path / name
            n = _capped_copy(_SAMPLES_DIR / name, dest, _MAX_PAGES)
            capped[name] = dest
            page_counts[name] = n
            print(f"{name}: capped to {n} pages")

        print("\n=== s/pag corner (pagination engine) ===")
        pagination_rows = []
        for name, path in capped.items():
            for backend in _BACKENDS:
                elapsed, pages = _time_pagination(path, backend)
                spp_ms = (elapsed / pages * 1000) if pages else float("nan")
                pagination_rows.append((name, backend, pages, elapsed, spp_ms))
                print(
                    f"{name:16s} {backend:12s} {pages:4d}p  {elapsed:7.2f}s  {spp_ms:7.1f} ms/pag"
                )

        print("\n=== s/pag anclas (anchors engine, worst-case 2-pass) ===")
        anchors_rows = []
        for name, path in capped.items():
            for backend in _BACKENDS:
                elapsed, pages = _time_anchors(path, backend)
                spp_ms = (elapsed / pages * 1000) if pages else float("nan")
                anchors_rows.append((name, backend, pages, elapsed, spp_ms))
                print(
                    f"{name:16s} {backend:12s} {pages:4d}p  {elapsed:7.2f}s  {spp_ms:7.1f} ms/pag"
                )

        print("\n=== speedup (pytesseract ms/pag / tesserocr ms/pag) ===")
        for engine_name, rows in (("pagination", pagination_rows), ("anchors", anchors_rows)):
            by_sample: dict[str, dict[str, float]] = {}
            for name, backend, _pages, _elapsed, spp_ms in rows:
                by_sample.setdefault(name, {})[backend] = spp_ms
            for name, per_backend in by_sample.items():
                pyt, tess = per_backend.get("pytesseract"), per_backend.get("tesserocr")
                if pyt and tess:
                    print(f"{engine_name:12s} {name:16s} {pyt / tess:5.2f}x")

        print("\n=== RSS stability (tesserocr, pagination engine, largest capped sample, 2x) ===")
        largest_name = max(page_counts, key=page_counts.get)
        largest_path = capped[largest_name]
        rss0 = _rss_mb()
        print(f"sample={largest_name} ({page_counts[largest_name]}p)  RSS before: {rss0}")
        for i in range(2):
            elapsed, pages = _time_pagination(largest_path, "tesserocr")
            rss = _rss_mb()
            print(f"run {i + 1}: {pages}p in {elapsed:.2f}s, RSS after: {rss}")


if __name__ == "__main__":
    main()
