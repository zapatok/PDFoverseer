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
    monkeypatch.setattr("core.scanners.anchors_scanner.get_page_count", lambda p: 1)

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


def test_scan_cells_ocr_cell_done_carries_per_file(tmp_path, monkeypatch):
    """Regression (review #2/#3): the cell_done event must carry per_file.

    The scanner computes a per-PDF document count, but the orchestrator event
    used to drop it, so apply_ocr_result wiped the cell's per_file to None and
    the FileList/lightbox fell back to a flat "1" per file. The event now
    forwards result.per_file end to end.
    """
    folder = tmp_path / "3.-ODI Visitas"
    folder.mkdir()
    for name in ("a.pdf", "b.pdf"):
        (folder / name).write_bytes(b"%PDF-1.4\n%%EOF\n")
    # A7 path: each 1-page PDF counts as 1 document, no Tesseract.
    monkeypatch.setattr("core.scanners.anchors_scanner.get_page_count", lambda p: 1)

    events: list[dict] = []
    scan_cells_ocr(
        [("HPV", "odi", folder)],
        on_progress=events.append,
        cancel=CancellationToken(),
        max_workers=1,
    )
    done = next(e for e in events if e["type"] == "cell_done")
    assert done["result"]["per_file"] == {"a.pdf": 1, "b.pdf": 1}


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
