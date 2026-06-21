"""scan_cells_ocr reports per-PDF progress (audit finding #1).

The synchronous path (max_workers=1) drives on_pdf directly; the multi-worker
path routes per-PDF progress through an IPC queue drained on the main thread.
"""

from core.orchestrator import scan_cells_ocr, scan_one_file_ocr
from core.scanners.cancellation import CancellationToken


def test_scan_one_file_ocr_emits_file_events(tmp_path, monkeypatch):
    """rev-2 #1: scan_one_file_ocr emits file_scan_started/page_progress/done
    for a single PDF, wiring the scanner's on_page hook to file_page_progress."""
    import core.scanners as scanner_registry
    from core.scanners.anchors_scanner import AnchorsScanner
    from core.scanners.base import ConfidenceLevel, ScanResult

    folder = tmp_path / "3.-ODI Visitas"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")

    # get_page_count drives file_scan_started.pages_total (local import in the fn).
    monkeypatch.setattr("core.scanners.utils.pdf_render.get_page_count", lambda _: 2)

    def fake_count_ocr(self, folder, *, cancel, on_pdf=None, only=None, on_page=None):
        if on_page is not None:
            on_page(0, 2)
            on_page(1, 2)
        return ScanResult(
            count=2,
            confidence=ConfidenceLevel.HIGH,
            method="header_band_anchors",
            breakdown=None,
            flags=[],
            errors=[],
            duration_ms=1,
            files_scanned=1,
            per_file={only: 2},
        )

    monkeypatch.setattr(AnchorsScanner, "count_ocr", fake_count_ocr)
    scanner_registry.clear()
    scanner_registry.register(AnchorsScanner(sigla="odi"))
    try:
        events: list[dict] = []
        scan_one_file_ocr(
            "HRB",
            "odi",
            folder,
            "a.pdf",
            on_progress=events.append,
            cancel=CancellationToken(),
        )
    finally:
        scanner_registry.clear()
        scanner_registry.register_defaults()

    started = next(e for e in events if e["type"] == "file_scan_started")
    assert started["pages_total"] == 2
    pp = [e for e in events if e["type"] == "file_page_progress"]
    assert [e["page"] for e in pp] == [1, 2]
    assert all(e["pages_total"] == 2 for e in pp)
    done = next(e for e in events if e["type"] == "file_scan_done")
    assert done["result"]["per_file"] == {"a.pdf": 2}
    assert done["result"]["method"] == "header_band_anchors"


def test_scan_cells_ocr_emits_pdf_progress(tmp_path, monkeypatch):
    folder = tmp_path / "3.-ODI Visitas"
    folder.mkdir()
    for name in ("a.pdf", "b.pdf", "c.pdf"):
        (folder / name).write_bytes(b"%PDF-1.4\n%%EOF\n")
    # Force the A7 path (1-page) so no Tesseract runs.
    # odi is scan_strategy="pagination" (v4) → its scanner is PaginationScanner.
    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda p: 1)

    events: list[dict] = []
    scan_cells_ocr(
        [("HPV", "odi", folder)],
        on_progress=events.append,
        cancel=CancellationToken(),
        max_workers=1,
    )
    types = [e["type"] for e in events]
    assert "scan_started" in types
    started = next(e for e in events if e["type"] == "scan_started")
    assert started["total_pdfs"] == 3

    pdf_events = [e for e in events if e["type"] == "pdf_progress"]
    assert [e["done"] for e in pdf_events] == [1, 2, 3]
    assert pdf_events[-1]["total"] == 3
    assert pdf_events[-1]["pdf_name"] == "c.pdf"
    assert types[-1] == "scan_complete"


def test_scan_cells_ocr_emits_per_file_via_file_result(tmp_path, monkeypatch):
    """Incr. 1A: per-file counts flow through ``file_result`` (one per PDF).

    Supersedes the rev-2 "cell_done carries per_file" guard. The anti-regression
    intent — each PDF's document count reaches the cell, instead of the lightbox
    falling back to a flat "1" — is preserved, but the channel moved: the route
    merges each ``file_result`` incrementally (cancel-safe), and ``cell_done`` now
    carries only run metadata (the full ``per_file`` is re-injected by the route
    from the merged cell). So at the orchestrator layer we assert on file_result.
    """
    folder = tmp_path / "3.-ODI Visitas"
    folder.mkdir()
    for name in ("a.pdf", "b.pdf"):
        (folder / name).write_bytes(b"%PDF-1.4\n%%EOF\n")
    # A7 path: each 1-page PDF counts as 1 document, no Tesseract.
    # odi is scan_strategy="pagination" (v4) → its scanner is PaginationScanner.
    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda p: 1)

    events: list[dict] = []
    scan_cells_ocr(
        [("HPV", "odi", folder)],
        on_progress=events.append,
        cancel=CancellationToken(),
        max_workers=1,
    )
    file_results = [e for e in events if e["type"] == "file_result"]
    assert {e["filename"]: e["count"] for e in file_results} == {"a.pdf": 1, "b.pdf": 1}
    # A7 (1-page) files are counted trivially as filename_glob (chip R1), not OCR.
    assert all(e["method"] == "filename_glob" for e in file_results)
    # cell_done carries metadata only now — per_file is merged per-file upstream.
    done = next(e for e in events if e["type"] == "cell_done")
    assert "per_file" not in done["result"]
    assert done["result"]["ocr_count"] == 2  # _cell_done_meta uses result.count


def test_scan_cells_ocr_zero_pdfs_still_completes(tmp_path):
    folder = tmp_path / "empty"
    folder.mkdir()
    events: list[dict] = []
    scan_cells_ocr(
        [("HPV", "odi", folder)],
        on_progress=events.append,
        cancel=CancellationToken(),
        max_workers=1,
    )
    started = next(e for e in events if e["type"] == "scan_started")
    assert started["total_pdfs"] == 0
    assert events[-1]["type"] == "scan_complete"


def test_scan_cells_ocr_multiworker_pdf_progress(tmp_path):
    # Cannot monkeypatch across spawn; use fake PDFs. get_page_count raises in
    # the subprocess -> the handled-error path still ticks on_pdf (finally), so
    # the drain thread must deliver at least one pdf_progress event.
    folder = tmp_path / "3.-ODI Visitas"
    folder.mkdir()
    for name in ("a.pdf", "b.pdf"):
        (folder / name).write_bytes(b"%PDF-1.4\n%%EOF\n")

    events: list[dict] = []
    scan_cells_ocr(
        [("HPV", "odi", folder)],
        on_progress=events.append,
        cancel=CancellationToken(),
        max_workers=2,
    )
    assert any(e["type"] == "pdf_progress" for e in events)
    assert events[-1]["type"] in ("scan_complete", "scan_cancelled")

    # Incr. 1A FIFO ordering invariant: in the multi-worker path the worker
    # enqueues cell_meta AFTER all its pdf_done on the same IPC queue, so the
    # single drain thread emits every file_result for a cell BEFORE its cell_done.
    # This is exactly what lets the route's finalize_cell_ocr see a complete
    # per_file. Assert it here (the multi-worker path is otherwise unasserted).
    types = [e["type"] for e in events]
    if "cell_done" in types:
        done_idx = types.index("cell_done")
        file_result_idx = [i for i, t in enumerate(types) if t == "file_result"]
        assert file_result_idx, "expected file_result events before cell_done"
        assert max(file_result_idx) < done_idx
