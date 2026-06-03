"""scan_cells_ocr reports per-PDF progress (audit finding #1).

The synchronous path (max_workers=1) drives on_pdf directly; the multi-worker
path routes per-PDF progress through an IPC queue drained on the main thread.
"""

from core.orchestrator import scan_cells_ocr
from core.scanners.cancellation import CancellationToken


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
