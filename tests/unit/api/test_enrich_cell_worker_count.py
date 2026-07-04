"""enrich_cell_worker_count — the ONE producer of worker_count (F1) and, for
checks cells, of the canonical effective cell count ``checks_count`` (M4).

M4 rationale: Excel/history derive the maquinaria cell number present-filtered
on the backend; the JS mirror can't know present files, so the payload ships
the canonical number and the frontend prefers it (cellCount.js).
"""

from __future__ import annotations

from api.routes.sessions._common import enrich_cell_worker_count


def _make_folder(tmp_path, *pdf_names):
    folder = tmp_path / "18.-Maquinarias y Equipos"
    folder.mkdir()
    for name in pdf_names:
        (folder / name).write_bytes(b"%PDF-1.4 test stub")
    return folder


def _marks_cell():
    return {
        "worker_marks": {
            "present.pdf": [{"page": 1, "count": 5}],
            "orphan.pdf": [{"page": 1, "count": 9}],
        },
        "per_file": {"present.pdf": 1},
    }


def test_checks_cell_gets_present_filtered_checks_count(tmp_path):
    folder = _make_folder(tmp_path, "present.pdf")
    out = enrich_cell_worker_count(_marks_cell(), tmp_path, "HPV", "maquinaria", folder)
    # Orphan mark (9) dropped by the present filter in BOTH canonical numbers.
    assert out["worker_count"] == 5
    assert out["checks_count"] == 5


def test_checks_count_matches_full_cascade_override_and_delta(tmp_path):
    folder = _make_folder(tmp_path, "present.pdf")
    cell = {**_marks_cell(), "user_override": 3, "reorg_doc_delta": 2}
    out = enrich_cell_worker_count(cell, tmp_path, "HPV", "maquinaria", folder)
    # checks_count is compute_cell_count verbatim: override (3) + doc delta (2).
    assert out["checks_count"] == 5
    # worker_count stays the marks total (no override in that derivation).
    assert out["worker_count"] == 5


def test_documents_workers_cell_gets_no_checks_count(tmp_path):
    folder = _make_folder(tmp_path, "present.pdf")
    out = enrich_cell_worker_count(_marks_cell(), tmp_path, "HPV", "charla", folder)
    assert out["worker_count"] == 5
    assert "checks_count" not in out


def test_document_cell_untouched(tmp_path):
    cell = {"per_file": {"a.pdf": 1}}
    out = enrich_cell_worker_count(cell, tmp_path, "HPV", "odi", tmp_path / "nope")
    assert out is cell
    assert "worker_count" not in out
    assert "checks_count" not in out


def test_missing_folder_falls_back_to_legacy_filter(tmp_path):
    # Folder absent → present=None → legacy filter by per_file keys: the orphan
    # mark is still excluded here because per_file names only present.pdf.
    missing = tmp_path / "does-not-exist"
    out = enrich_cell_worker_count(_marks_cell(), tmp_path, "HPV", "maquinaria", missing)
    assert out["worker_count"] == 5
    assert out["checks_count"] == 5
