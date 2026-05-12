# PDFoverseer FASE 2 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OCR scanners for compilation PDFs, manual correction UI with PDF preview, and real-time WebSocket progress to PDFoverseer's existing folder-driven counter.

**Architecture:** Two-pass scan model (filename_glob → opt-in OCR per cell) with a `CancellationToken` for batch interrupts, 4 specialized scanners (`art`, `odi`, `irl`, `charla`) using new OCR utils (`header_detect`, `corner_count`, `page_count_pure`, `pdf_render`), an enriched cell state (`filename_count` + `ocr_count` + `user_override` + `override_note` as independent fields), and a WebSocket protocol broadcasting `cell_scanning` / `cell_done` / `cell_error` / `scan_progress` / `scan_complete` / `scan_cancelled` events bridged from a `ProcessPoolExecutor` orchestrator thread.

**Tech Stack:** Python 3.10+ · FastAPI · openpyxl · PyMuPDF (fitz) · pytesseract · Pillow · pytest · React 18 · Vite · Zustand · Tailwind 3 · openpyxl for Excel · SQLite

**Spec:** `docs/superpowers/specs/2026-05-12-fase-2-design.md`

**Baseline:** branch `po_overhaul`, latest commit `fcf63a9` (spec pass 2). FASE 1 tag `fase-1-mvp`. Bug fix `1b35597` shipped.

---

## Chunk 1: Foundations — cell state v2 + migration + apply_*_result split

This chunk reshapes the per-cell data model from FASE 1's single `count` field into the FASE 2 schema with three independent count slots (`filename_count`, `ocr_count`, `user_override`) plus `override_note`. All later chunks read and write through these methods, so a clean foundation is non-negotiable.

Inputs from FASE 1 (do not modify, verify they exist):
- `api/state.py` exports `SessionManager` with `apply_cell_result`, `apply_user_override` (returns `KeyError` if session missing)
- `core/db/sessions_repo.py` exports `get_session`, `update_session_state`
- `core/scanners/base.py` exports `ScanResult`, `ConfidenceLevel`
- `core/excel/writer.py` reads `cell.get("user_override")` then `cell.get("count")`

Output: cell schema migrated, three `apply_*_result` methods, writer updated to new priority, regression tests cover legacy → v2 migration.

### Task 1: Add legacy → v2 cell migration helper

**Files:**
- Create: `core/state/migrations.py`
- Test: `tests/unit/state/test_migrations.py`

The migration runs lazily on every `get_session_state` call and writes back to DB once via `update_session_state`. Idempotent.

- [ ] **Step 1: Write the failing test**

`tests/unit/state/__init__.py` (empty file) and `tests/unit/state/test_migrations.py`:

```python
"""Cell state migration FASE 1 → FASE 2."""

from __future__ import annotations

from core.state.migrations import migrate_cell_v1_to_v2, migrate_state_v1_to_v2


def test_migrate_cell_renames_count_to_filename_count():
    cell = {"count": 5, "confidence": "high", "method": "filename_glob"}
    result = migrate_cell_v1_to_v2(cell)
    assert result["filename_count"] == 5
    assert "count" not in result
    assert result["ocr_count"] is None
    assert result["override_note"] is None


def test_migrate_cell_idempotent_on_already_v2():
    cell = {
        "filename_count": 5,
        "ocr_count": 17,
        "user_override": None,
        "override_note": "note",
        "confidence": "high",
    }
    result = migrate_cell_v1_to_v2(cell)
    assert result == cell


def test_migrate_cell_preserves_excluded_flag():
    cell = {"count": 0, "excluded": True}
    result = migrate_cell_v1_to_v2(cell)
    assert result["filename_count"] == 0
    assert result["excluded"] is True


def test_migrate_cell_handles_missing_count_field():
    # When the legacy `count` key is absent (cell never scanned), filename_count
    # ends up None via setdefault — no KeyError.
    cell = {"confidence": "high"}
    result = migrate_cell_v1_to_v2(cell)
    assert result["filename_count"] is None
    assert result["ocr_count"] is None
    assert result["override_note"] is None


def test_migrate_state_walks_all_cells_returns_changed_true():
    state = {
        "cells": {
            "HPV": {
                "art": {"count": 767, "confidence": "high"},
                "odi": {"count": 1, "confidence": "low"},
            },
            "HRB": {"odi": {"count": 1, "excluded": False}},
        }
    }
    result, changed = migrate_state_v1_to_v2(state)
    assert changed is True
    assert result["cells"]["HPV"]["art"]["filename_count"] == 767
    assert "count" not in result["cells"]["HPV"]["art"]


def test_migrate_state_returns_changed_false_on_already_v2():
    state = {
        "cells": {
            "HPV": {"art": {"filename_count": 767, "ocr_count": None, "override_note": None}},
        }
    }
    result, changed = migrate_state_v1_to_v2(state)
    assert changed is False


def test_migrate_state_empty_cells_dict_is_fine():
    state = {"cells": {}}
    result, changed = migrate_state_v1_to_v2(state)
    assert result == {"cells": {}}
    assert changed is False


def test_migrate_state_no_cells_key_is_fine():
    state = {"session_id": "2026-04", "status": "active"}
    result, changed = migrate_state_v1_to_v2(state)
    assert result == state
    assert changed is False


```

(See updated `test_migrate_state_*` versions further down — they unpack the new `(state, changed)` tuple return.)

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/state/test_migrations.py -v`
Expected: `ImportError: No module named 'core.state.migrations'`

- [ ] **Step 3: Implement `core/state/migrations.py`**

```python
"""Lazy cell-state migrations between schema versions."""

from __future__ import annotations


def migrate_cell_v1_to_v2(cell: dict) -> dict:
    """Migrate a single cell dict from FASE 1 to FASE 2 schema.

    FASE 1: ``{count, confidence, method, user_override, excluded, ...}``
    FASE 2: ``{filename_count, ocr_count, user_override, override_note,
             confidence, method, excluded, ...}``

    Idempotent. Safe on already-migrated cells. Defensive against missing
    fields. Does not raise on empty or partial cells.
    """
    if "count" in cell:
        cell["filename_count"] = cell.pop("count", None)
    cell.setdefault("filename_count", None)
    cell.setdefault("ocr_count", None)
    cell.setdefault("override_note", None)
    # excluded (bool, FASE 1) preserved as-is. user_override (FASE 1) preserved.
    return cell


def migrate_state_v1_to_v2(state: dict) -> tuple[dict, bool]:
    """Migrate full session state JSON in-place. Idempotent.

    Returns:
        (state, changed) where ``changed`` is True iff any cell was
        actually rewritten. Caller uses this to skip the DB write-back
        when nothing changed (every call after the first one).
    """
    changed = False
    cells = state.get("cells")
    if not cells:
        return state, False
    for hosp_cells in cells.values():
        for cell in hosp_cells.values():
            had_legacy = "count" in cell or "filename_count" not in cell \
                or "ocr_count" not in cell or "override_note" not in cell
            migrate_cell_v1_to_v2(cell)
            if had_legacy:
                changed = True
    return state, changed
```


Also create `core/state/__init__.py` (empty).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/state/test_migrations.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add core/state/__init__.py core/state/migrations.py tests/unit/state/__init__.py tests/unit/state/test_migrations.py
git commit -m "feat(state): cell schema v1→v2 migration helper

Adds lazy idempotent migration from FASE 1 cell schema
(single \`count\` field) to FASE 2 schema (filename_count + ocr_count +
override_note as independent fields). Defensive on missing fields,
preserves user_override and excluded. Tests cover both single-cell
and full-state migrations.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Split `apply_cell_result` into three methods

**Files:**
- Modify: `api/state.py`
- Test: `tests/unit/api/test_state.py` (extend existing)

`SessionManager` gets three fine-grained setters that each touch their own field set without disturbing others. The legacy `apply_cell_result` is kept for one chunk as an alias to ease migration, then deleted in Chunk 2.

- [ ] **Step 1: Read existing api/state.py shape**

Use `mcp__serena__find_symbol` with `name_path_pattern="SessionManager"`, `relative_path="api/state.py"`, `depth=1` to see method names. Note: `apply_cell_result` currently writes `{count, confidence, method, breakdown, flags, errors, duration_ms, files_scanned, user_override, excluded}`. Keep that schema's `excluded` and `user_override` as-is.

- [ ] **Step 2: Write the failing tests**

Append to `tests/unit/api/test_state.py`:

```python
import pytest
from pathlib import Path

from api.state import SessionManager
from core.db.connection import close_all, open_connection
from core.db.migrations import init_schema
from core.scanners.base import ConfidenceLevel, ScanResult


@pytest.fixture
def manager(tmp_path):
    conn = open_connection(tmp_path / "v2.db")
    init_schema(conn)
    mgr = SessionManager(conn=conn)
    mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))
    yield mgr
    close_all()


def _filename_result(count: int) -> ScanResult:
    return ScanResult(
        count=count, confidence=ConfidenceLevel.HIGH, method="filename_glob",
        breakdown={}, flags=[], errors=[], files_scanned=count, duration_ms=10,
    )


def _ocr_result(count: int, method: str = "header_detect") -> ScanResult:
    return ScanResult(
        count=count, confidence=ConfidenceLevel.HIGH, method=method,
        breakdown={}, flags=[], errors=[], files_scanned=1, duration_ms=23000,
    )


def test_apply_filename_result_sets_filename_count_only(manager):
    manager.apply_filename_result("2026-04", "HPV", "art", _filename_result(767))
    state = manager.get_session_state("2026-04")
    cell = state["cells"]["HPV"]["art"]
    assert cell["filename_count"] == 767
    assert cell["ocr_count"] is None
    assert cell["user_override"] is None
    assert cell["override_note"] is None
    assert cell["method"] == "filename_glob"
    assert cell["duration_ms_filename"] == 10
    # Lock the isolation contract from both sides — filename pass never sets OCR duration
    assert cell.get("duration_ms_ocr") is None


def test_apply_ocr_result_sets_ocr_count_and_method_without_touching_filename(manager):
    manager.apply_filename_result("2026-04", "HRB", "odi", _filename_result(1))
    manager.apply_ocr_result("2026-04", "HRB", "odi", _ocr_result(17, "header_detect"))
    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["odi"]
    assert cell["filename_count"] == 1
    assert cell["ocr_count"] == 17
    assert cell["method"] == "header_detect"
    assert cell["duration_ms_ocr"] == 23000


def test_apply_ocr_result_with_filename_glob_fallback_method(manager):
    # OCR scanner failed internally, fell back to filename_glob
    manager.apply_filename_result("2026-04", "HRB", "odi", _filename_result(1))
    fallback = _ocr_result(1, "filename_glob")
    manager.apply_ocr_result("2026-04", "HRB", "odi", fallback)
    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["odi"]
    assert cell["ocr_count"] == 1
    assert cell["method"] == "filename_glob"


def test_apply_user_override_sets_value_and_note(manager):
    manager.apply_filename_result("2026-04", "HRB", "odi", _filename_result(1))
    manager.apply_user_override("2026-04", "HRB", "odi", value=17, note="17 ODIs in 1 PDF")
    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["odi"]
    assert cell["user_override"] == 17
    assert cell["override_note"] == "17 ODIs in 1 PDF"
    assert cell["filename_count"] == 1  # untouched


def test_apply_user_override_with_null_value_clears_override(manager):
    manager.apply_filename_result("2026-04", "HRB", "odi", _filename_result(1))
    manager.apply_user_override("2026-04", "HRB", "odi", value=17, note="initial")
    manager.apply_user_override("2026-04", "HRB", "odi", value=None, note=None)
    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["odi"]
    assert cell["user_override"] is None
    assert cell["override_note"] is None


def test_apply_user_override_can_be_used_before_any_scan(manager):
    manager.apply_user_override("2026-04", "HPV", "chps", value=2, note="manual count")
    cell = manager.get_session_state("2026-04")["cells"]["HPV"]["chps"]
    assert cell["filename_count"] is None
    assert cell["ocr_count"] is None
    assert cell["user_override"] == 2


def test_get_session_state_migrates_legacy_count_on_first_read(manager, tmp_path):
    # Inject legacy state directly via raw connection
    import json
    from core.db.sessions_repo import update_session_state, get_session
    legacy_state = {
        "month_root": str(tmp_path),
        "hospitals_present": ["HPV"],
        "hospitals_missing": [],
        "cells": {"HPV": {"art": {"count": 767, "confidence": "high", "method": "filename_glob"}}},
    }
    update_session_state(manager._conn, "2026-04", state_json=json.dumps(legacy_state))
    cell = manager.get_session_state("2026-04")["cells"]["HPV"]["art"]
    assert cell["filename_count"] == 767
    assert "count" not in cell
    assert cell["ocr_count"] is None
    assert cell["override_note"] is None
    # Idempotent: second read returns the same
    cell2 = manager.get_session_state("2026-04")["cells"]["HPV"]["art"]
    assert cell2 == cell
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/api/test_state.py -v -k "apply_filename or apply_ocr or apply_user_override or migrates_legacy"`
Expected: 7 failures (AttributeError: SessionManager has no apply_filename_result, etc.)

- [ ] **Step 4: Implement the three setters + migration in `api/state.py`**

Find the existing `apply_cell_result` method via Serena (`find_symbol "SessionManager/apply_cell_result" include_body=true`). Replace the method block with the following three:

```python
def _load_and_migrate(self, session_id: str) -> tuple[dict, "SessionRecord"]:
    """Load session state, run lazy migration, return (state, record).

    Internal helper used by all setters + getter. Persists migrated state
    back via update_session_state only when migration actually changed
    something — idempotent on subsequent calls.
    """
    rec = get_session(self._conn, session_id)
    if rec is None:
        raise KeyError(session_id)
    state = json.loads(rec.state_json)
    state, changed = migrate_state_v1_to_v2(state)
    if changed:
        update_session_state(self._conn, session_id, state_json=json.dumps(state))
    return state, rec


def apply_filename_result(
    self, session_id: str, hospital: str, sigla: str, result: ScanResult
) -> None:
    """Persist a filename_glob scanner result. Touches the filename pass
    fields and shared metadata (method, confidence, flags, errors,
    breakdown). Never touches ocr_count, user_override, or override_note."""
    state, _ = self._load_and_migrate(session_id)
    cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
    cell["filename_count"] = result.count
    cell["confidence"] = result.confidence.value
    cell["method"] = result.method
    cell["breakdown"] = result.breakdown
    cell["flags"] = list(result.flags)
    cell["errors"] = list(result.errors)
    cell["files_scanned"] = result.files_scanned
    cell["duration_ms_filename"] = result.duration_ms
    cell.setdefault("ocr_count", None)
    cell.setdefault("user_override", None)
    cell.setdefault("override_note", None)
    cell.setdefault("excluded", False)
    update_session_state(self._conn, session_id, state_json=json.dumps(state))


def apply_ocr_result(
    self, session_id: str, hospital: str, sigla: str, result: ScanResult
) -> None:
    """Persist an OCR scanner result. Touches ocr_count, method,
    confidence, flags, errors, breakdown, duration_ms_ocr. method =
    ``result.method`` (header_detect, corner_count, page_count_pure, or
    filename_glob when the OCR scanner fell back internally).

    flags/errors/breakdown are written unconditionally — an empty list/dict
    means "no flags this run" (NOT "preserve previous"). Stale data from
    a previous OCR run is overwritten, which is the correct semantic for
    a fresh scan."""
    state, _ = self._load_and_migrate(session_id)
    cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
    cell["ocr_count"] = result.count
    cell["confidence"] = result.confidence.value
    cell["method"] = result.method
    cell["breakdown"] = result.breakdown
    cell["flags"] = list(result.flags)
    cell["errors"] = list(result.errors)
    cell["duration_ms_ocr"] = result.duration_ms
    cell.setdefault("filename_count", None)
    cell.setdefault("user_override", None)
    cell.setdefault("override_note", None)
    cell.setdefault("excluded", False)
    update_session_state(self._conn, session_id, state_json=json.dumps(state))


def apply_user_override(
    self,
    session_id: str,
    hospital: str,
    sigla: str,
    *,
    value: int | None,
    note: str | None,
) -> None:
    """Set or clear the user override + note.

    When ``value=None``, both ``user_override`` AND ``override_note`` are
    forced to None regardless of the ``note`` parameter (a note without
    an override is meaningless). When ``value`` is an int, ``note`` is
    persisted verbatim (may be None or a string)."""
    state, _ = self._load_and_migrate(session_id)
    cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
    cell["user_override"] = value
    cell["override_note"] = note if value is not None else None
    cell.setdefault("filename_count", None)
    cell.setdefault("ocr_count", None)
    cell.setdefault("excluded", False)
    update_session_state(self._conn, session_id, state_json=json.dumps(state))
```

Add imports at top of `api/state.py`:

```python
from core.state.migrations import migrate_state_v1_to_v2
```

Modify `get_session_state` to apply migration before returning. Reuses
`_load_and_migrate` for deterministic write-back when migration changed
state:

```python
def get_session_state(self, session_id: str) -> dict:
    state, rec = self._load_and_migrate(session_id)
    state["session_id"] = rec.session_id
    state["status"] = rec.status
    return state
```

`_load_and_migrate` already persists when `changed=True`, so first GET on
a legacy session writes back exactly once; subsequent GETs short-circuit
because the helper sees `changed=False`.

**Keep `apply_cell_result` as a deprecated alias** that calls `apply_filename_result` to preserve any callers we haven't migrated yet (orchestrator pase 1):

```python
def apply_cell_result(self, session_id, hospital, sigla, result):
    """Deprecated. Use apply_filename_result for pase 1 results."""
    self.apply_filename_result(session_id, hospital, sigla, result)
```

This alias is removed at end of Chunk 4.

- [ ] **Step 5: Run all state tests**

Run: `pytest tests/unit/api/test_state.py -v`
Expected: all pass (existing + 7 new)

- [ ] **Step 6: Run full unit suite to ensure no regression**

Run: `pytest -m "not slow" -q`
Expected: same pass count as before + 7. Should be ~386 → ~393 passed.

- [ ] **Step 7: Commit**

```bash
git add api/state.py tests/unit/api/test_state.py
git commit -m "feat(state): split apply_cell_result into 3 fine-grained setters

apply_filename_result, apply_ocr_result, apply_user_override each touch
their own field set without disturbing others. get_session_state now
migrates legacy v1 cells to v2 on first read and persists back. Legacy
apply_cell_result kept as deprecated alias for one chunk.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Update Excel writer with new priority cascade

**Files:**
- Modify: `core/excel/writer.py`
- Test: `tests/unit/excel/test_writer.py` (extend)

The writer now resolves the effective count per cell as: `user_override` if not null, else `ocr_count` if not null, else `filename_count` if not null, else `0`. The legacy `count` field continues to be a fallback for sessions that somehow escaped migration.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/excel/test_writer.py`:

```python
def test_writer_priority_override_over_ocr_over_filename(tmp_path):
    from core.excel.writer import resolve_cell_value

    # Override wins
    assert resolve_cell_value({"user_override": 17, "ocr_count": 16, "filename_count": 1}) == 17
    # OCR wins when no override
    assert resolve_cell_value({"user_override": None, "ocr_count": 16, "filename_count": 1}) == 16
    # Filename wins when neither
    assert resolve_cell_value({"user_override": None, "ocr_count": None, "filename_count": 5}) == 5
    # All null → 0
    assert resolve_cell_value({"user_override": None, "ocr_count": None, "filename_count": None}) == 0
    # Excluded → None signals "do not write"
    assert resolve_cell_value({"user_override": 5, "excluded": True}) is None
    # Legacy count field (un-migrated) → still works
    assert resolve_cell_value({"count": 42}) == 42
    # Override of 0 is meaningful (explicit zero), wins over ocr_count
    assert resolve_cell_value({"user_override": 0, "ocr_count": 16, "filename_count": 1}) == 0


def test_writer_uses_priority_in_generate_resumen(tmp_path):
    """Smoke test: generate_resumen uses resolve_cell_value internally."""
    from core.excel.writer import generate_resumen

    cell_values = {
        # Caller pre-resolved values; writer just writes named ranges.
        "HPV_art_count": 767,
        "HRB_odi_count": 17,
    }
    out = tmp_path / "out.xlsx"
    result = generate_resumen(cell_values=cell_values, output_path=out)
    assert result.cells_written == 2
    assert out.exists()
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/excel/test_writer.py::test_writer_priority_override_over_ocr_over_filename -v`
Expected: ImportError (resolve_cell_value not defined)

- [ ] **Step 3: Add `resolve_cell_value` to writer.py**

At the top of `core/excel/writer.py`:

```python
def resolve_cell_value(cell: dict) -> int | None:
    """Compute the effective count for an Excel cell from the FASE 2 schema.

    Priority cascade: user_override > ocr_count > filename_count > legacy count > 0.

    Returns None if the cell is excluded — caller skips writing.
    """
    if cell.get("excluded"):
        return None
    if cell.get("user_override") is not None:
        return cell["user_override"]
    if cell.get("ocr_count") is not None:
        return cell["ocr_count"]
    if cell.get("filename_count") is not None:
        return cell["filename_count"]
    if "count" in cell and cell["count"] is not None:
        return cell["count"]
    return 0
```

This function is pure and stateless. `generate_resumen` itself doesn't need to call it — callers compute values via `resolve_cell_value` first and pass them into `cell_values`. We will wire callers in Chunk 4 (output endpoint).

- [ ] **Step 4: Run the new tests**

Run: `pytest tests/unit/excel/test_writer.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add core/excel/writer.py tests/unit/excel/test_writer.py
git commit -m "feat(excel): resolve_cell_value with FASE 2 priority cascade

user_override > ocr_count > filename_count > legacy count > 0. Pure
function; callers apply it before passing cell_values to generate_resumen.
Excluded cells return None — caller skips. Legacy count fallback kept
for un-migrated sessions.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Wire output endpoint to use `resolve_cell_value`

**Files:**
- Modify: `api/routes/output.py`
- Test: `tests/unit/api/test_routes_output.py` (extend)

Today's output endpoint reads `cell.get("count")` or `cell.get("user_override")`. Rewire it to use `resolve_cell_value` so it works with both v1 and v2 cells.

- [ ] **Step 1: Read existing output.py**

Use `mcp__serena__find_symbol "_build_cell_values" relative_path="api/routes/output.py" include_body=true`. Note the current logic.

- [ ] **Step 2: Write failing test**

Append to `tests/unit/api/test_routes_output.py`:

```python
def test_output_uses_v2_priority(client, tmp_path, monkeypatch):
    """V2 cells with user_override get the override in the Excel."""
    import openpyxl

    client.post("/api/sessions", json={"year": 2026, "month": 4})
    client.post("/api/sessions/2026-04/scan", json={"scope": "all"})

    # Override HRB/odi to 17 via PATCH (added in Chunk 4 — for this task,
    # we directly mutate state via SessionManager from the test fixture)
    from api.routes.sessions import get_manager
    mgr = client.app.dependency_overrides[get_manager]()
    mgr.apply_user_override("2026-04", "HRB", "odi", value=17, note="manual")

    out = client.post("/api/sessions/2026-04/output", json={}).json()
    wb = openpyxl.load_workbook(out["output_path"])
    dest = list(wb.defined_names["HRB_odi_count"].destinations)[0]
    sheet, coord = dest
    assert wb[sheet][coord].value == 17
```

- [ ] **Step 3: Run to verify it fails**

Run: `pytest tests/unit/api/test_routes_output.py::test_output_uses_v2_priority -v`
Expected: AttributeError on `apply_user_override` if SessionManager not yet exposed publicly, OR test fails because the writer used legacy logic and wrote the OCR-or-scanner value, not the override. The exact failure mode depends on Task 2 completion; if Task 2 commits are clean, this should already fail correctly.

- [ ] **Step 4: Update `_build_cell_values` in `api/routes/output.py`**

Replace the body with:

```python
from core.excel.writer import resolve_cell_value


def _build_cell_values(state: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for hosp, sigla_map in state.get("cells", {}).items():
        for sigla, cell in sigla_map.items():
            value = resolve_cell_value(cell)
            if value is None:
                continue
            out[f"{hosp}_{sigla}_count"] = value
    return out
```

- [ ] **Step 5: Run the test + entire output route tests**

Run: `pytest tests/unit/api/test_routes_output.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add api/routes/output.py tests/unit/api/test_routes_output.py
git commit -m "feat(api): output endpoint resolves cells via FASE 2 cascade

POST /sessions/{id}/output now uses resolve_cell_value to compute
effective count per cell — respects v2 schema (user_override > ocr_count
> filename_count) while still working on legacy v1 cells that haven't
been re-scanned yet.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Chunk 1 sanity — full suite green

- [ ] **Step 1: Run fast tests**

Run: `pytest -m "not slow" -q`
Expected: 0 failures, ~393 passed.

- [ ] **Step 2: Run slow tests (integration + e2e)**

Run: `pytest -m slow -q`
Expected: 6 passed (FASE 1 baseline) — verifies legacy compat through migration.

- [ ] **Step 3: Ruff clean**

Run: `ruff check .`
Expected: 0 violations.

- [ ] **Step 4: Branch check before moving to Chunk 2**

Run: `git log --oneline -5`
Expected: 4 new commits (migration helper, state setters, writer cascade, output wiring) on top of `fcf63a9`.

---

## Chunk 2: OCR utils (pdf_render + page_count_pure + header_detect + corner_count)

This chunk introduces the four reusable OCR primitives used by the specialized scanners. Each util is stateless, takes a `Path`, and returns a simple result dataclass.

Inputs: PyMuPDF (`fitz`), Pillow (`PIL.Image`), `pytesseract` already in requirements (CPU path); none of these need to be added.

Outputs: 4 modules in `core/scanners/utils/`, fixtures extracted from real ABRIL corpus into `tests/fixtures/scanners_ocr/` (folder-shaped, one PDF per sub-folder so the Chunk 3 scanners' `folder.glob("*.pdf")` finds them).

### Task 6: Extract real fixtures from ABRIL corpus

**Files:**
- Create: `tests/fixtures/scanners_ocr/README.md`
- Create: `tests/fixtures/scanners_ocr/odi_compilation/HRB_odi_compilation.pdf` (copy from corpus)
- Create: `tests/fixtures/scanners_ocr/irl_compilation/<sample>.pdf`
- Create: `tests/fixtures/scanners_ocr/art_multidoc/<sample>.pdf`
- Create: `tests/fixtures/scanners_ocr/charla_compilation/HPV_charla_single.pdf`
- Create: `tests/fixtures/scanners_ocr/corrupted/corrupted.pdf` (0-byte synthetic)
- Create: `tools/extract_fase2_fixtures.py`

Per memory `feedback_art670_fixture_disaster` — no fabricated data for count tests. The 0-byte `corrupted.pdf` is allowed because it's a degenerate-input error-handling fixture, not a substitute for real data.

**Layout rationale.** Each fixture lives in a sub-folder containing exactly one PDF. The scanners in Chunk 3 use `folder.glob("*.pdf")` so they need a folder, not a flat file. The folder names match the names the Chunk 3 tests import (`FIXTURE_ROOT / "art_multidoc"` etc.).

**Threshold check.** `flag_compilation_suspect(folder, sigla)` triggers when ` page_count ≥ EXPECTED_PAGES_PER_DOC[sigla] × _TIGHT_FACTOR (5)`. For the four siglas that means:

| Sigla | `EXPECTED_PAGES_PER_DOC` | × 5 | Fixture must have ≥ |
|---|---|---|---|
| art | 10 | 50 | 50 pages |
| odi | 2 | 10 | 10 pages |
| irl | 2 | 10 | 10 pages |
| charla | 2 | 10 | 10 pages |

The extractor below asserts these thresholds and **fails loudly** if any picked PDF is below — so a non-compilation can't sneak in.

- [ ] **Step 1: Identify source paths from the ABRIL corpus**

Use the Glob tool to verify source PDFs exist (works cross-platform; bash
on Windows mangles paths with spaces):

```
Glob: "A:/informe mensual/ABRIL/HRB/3.-ODI Visitas/**/*.pdf"
Glob: "A:/informe mensual/ABRIL/HLU/3.-ODI Visitas/**/*.pdf"
Glob: "A:/informe mensual/ABRIL/HPV/4.-Charlas/**/*.pdf"
Glob: "A:/informe mensual/ABRIL/HPV/7.-ART/**/*.pdf"
Glob: "A:/informe mensual/ABRIL/HRB/8.-IRL/**/*.pdf"
```

Expected: at least 1 PDF returned per glob. The `art` and `irl` paths may produce many PDFs — the largest (highest page count) is the compilation candidate.

- [ ] **Step 2: Write `tools/extract_fase2_fixtures.py`**

```python
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
# flag_compilation_suspect — see core/scanners/utils/page_count_heuristic.py)
FIXTURES = [
    ("art_multidoc",       "art_multidoc.pdf",          SRC_ROOT / "HPV" / "7.-ART",          "art",    50),
    ("odi_compilation",    "HRB_odi_compilation.pdf",   SRC_ROOT / "HRB" / "3.-ODI Visitas",  "odi",    10),
    ("irl_compilation",    "HRB_irl_compilation.pdf",   SRC_ROOT / "HRB" / "8.-IRL",          "irl",    10),
    ("charla_compilation", "HPV_charla_single.pdf",     SRC_ROOT / "HPV" / "4.-Charlas",      "charla", 10),
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
    except Exception:                                        # noqa: BLE001
        return -1


def main() -> int:
    DST_ROOT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    for subfolder, dst_name, src_folder, sigla, min_pages in FIXTURES:
        src = pick_largest_pdf(src_folder)
        if src is None:
            failures.append(f"  MISSING {subfolder}/{dst_name} — no PDFs in {src_folder}")
            continue
        target_folder = DST_ROOT / subfolder
        target_folder.mkdir(parents=True, exist_ok=True)
        dst = target_folder / dst_name
        shutil.copy(src, dst)
        pp = _page_count(dst)
        if pp < min_pages:
            failures.append(
                f"  BELOW THRESHOLD {subfolder}/{dst_name}: {pp}pp < required {min_pages}pp "
                f"for sigla={sigla} — picked PDF is NOT a compilation candidate. "
                f"Pick a different source or extend FIXTURES with an explicit override."
            )
            continue
        print(f"  OK {subfolder}/{dst_name} ← {src.name} ({dst.stat().st_size:,} bytes, {pp}pp ≥ {min_pages})")

    # Synthetic 0-byte corrupted PDF for error-handling tests.
    # Allowed exception to the "real fixtures only" rule per
    # feedback_art670_fixture_disaster — degenerate input for error tests, not
    # data substitution.
    corrupted_folder = DST_ROOT / "corrupted"
    corrupted_folder.mkdir(parents=True, exist_ok=True)
    (corrupted_folder / "corrupted.pdf").write_bytes(b"")
    print(f"  OK corrupted/corrupted.pdf (0 bytes, synthetic)")

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
```

- [ ] **Step 3: Run the extractor**

Run: `python tools/extract_fase2_fixtures.py`
Expected: 5 lines of "OK" output (4 real folder-shaped fixtures + 1 synthetic corrupted folder), exit code 0. If exit code is 1, address the "BELOW THRESHOLD" or "MISSING" failure(s) before continuing — a sub-threshold PDF will make the Chunk 3 OCR tests assert against `method="filename_glob"` instead of the OCR method, masking the bug rather than catching it.

- [ ] **Step 4: Write `tests/fixtures/scanners_ocr/README.md`**

```markdown
# Scanners OCR fixtures

Real PDFs extracted from `A:\informe mensual\ABRIL\` via
`tools/extract_fase2_fixtures.py`. Each fixture lives in a sub-folder
containing exactly one PDF — scanners use `folder.glob("*.pdf")`, so
they need a folder shape, not a flat file.

| Folder | PDF | Source | Min pages (compilation threshold) | Used by |
|---|---|---|---|---|
| art_multidoc/ | art_multidoc.pdf | HPV/7.-ART | 50 | corner_count, art_scanner tests |
| odi_compilation/ | HRB_odi_compilation.pdf | HRB/3.-ODI Visitas | 10 | header_detect, odi_scanner tests |
| irl_compilation/ | HRB_irl_compilation.pdf | HRB/8.-IRL | 10 | header_detect, irl_scanner tests |
| charla_compilation/ | HPV_charla_single.pdf | HPV/4.-Charlas | 10 | page_count_pure, charla_scanner tests |
| corrupted/ | corrupted.pdf | synthetic (0-byte) | — | error handling tests only |

Per memory `feedback_art670_fixture_disaster`: real fixtures only.
`corrupted.pdf` is allowed because it's a degenerate-input fixture for
error tests, not data substitution.

**Refreshing.** Re-run `python tools/extract_fase2_fixtures.py` after
the source corpus changes. The script asserts the page-count threshold
per sigla and exits non-zero if any picked PDF is below the
compilation_suspect cutoff — fix that before committing the refreshed
fixtures.
```

- [ ] **Step 5: Verify fixtures are git-tracked**

```bash
ls tests/fixtures/scanners_ocr/
git status tests/fixtures/scanners_ocr/
```

Expected: 5 untracked sub-folders (art_multidoc, odi_compilation, irl_compilation, charla_compilation, corrupted) + README.md.

- [ ] **Step 6: Commit**

```bash
git add tools/extract_fase2_fixtures.py tests/fixtures/scanners_ocr/
git commit -m "test(fixtures): extract real ABRIL PDFs for FASE 2 OCR tests

Adds tools/extract_fase2_fixtures.py and 5 folder-shaped fixtures (4
real compilation PDFs from HPV/HRB ABRIL corpus + 1 synthetic 0-byte
corrupted.pdf for error handling). README documents the source mapping
and per-sigla page-count thresholds. Extractor asserts thresholds and
exits non-zero if a picked PDF would not trigger compilation_suspect.
Re-run the extractor
to refresh when the corpus changes.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: `pdf_render.py` — PyMuPDF wrapper

**Files:**
- Create: `core/scanners/utils/pdf_render.py`
- Test: `tests/unit/scanners/utils/test_pdf_render.py`

- [ ] **Step 1: Write failing test**

`tests/unit/scanners/utils/__init__.py` (empty) and `test_pdf_render.py`:

```python
"""pdf_render utility — PyMuPDF wrappers for rendering and counting."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from core.scanners.utils.pdf_render import (
    PdfRenderError,
    get_page_count,
    render_page_image,
    render_page_region,
)

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "scanners_ocr"
HRB_ODI = FIXTURES / "odi_compilation" / "HRB_odi_compilation.pdf"
CORRUPTED = FIXTURES / "corrupted" / "corrupted.pdf"


def test_get_page_count_on_real_pdf():
    n = get_page_count(HRB_ODI)
    assert n > 1  # compilation has multiple pages


def test_get_page_count_on_corrupted_raises():
    with pytest.raises(PdfRenderError):
        get_page_count(CORRUPTED)


def test_get_page_count_on_missing_file_raises():
    with pytest.raises(PdfRenderError):
        get_page_count(Path("/does/not/exist.pdf"))


def test_render_page_image_returns_pil_image():
    img = render_page_image(HRB_ODI, page_idx=0, dpi=150)
    assert isinstance(img, Image.Image)
    assert img.width > 100
    assert img.height > 100


def test_render_page_image_invalid_page_raises():
    with pytest.raises(PdfRenderError):
        render_page_image(HRB_ODI, page_idx=9999, dpi=150)


def test_render_page_region_clips_to_bbox():
    # Top-right quadrant
    full = render_page_image(HRB_ODI, page_idx=0, dpi=150)
    region = render_page_region(HRB_ODI, page_idx=0, bbox=(0.5, 0.0, 1.0, 0.5), dpi=150)
    assert region.width < full.width
    assert region.height < full.height
    # bbox uses relative coords [0..1]; top-right ≈ quarter of full area
    assert abs(region.width - full.width / 2) < 5
    assert abs(region.height - full.height / 2) < 5


def test_render_page_region_validates_bbox():
    with pytest.raises(ValueError):
        render_page_region(HRB_ODI, page_idx=0, bbox=(0.0, 0.0, 2.0, 1.0), dpi=150)
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/unit/scanners/utils/test_pdf_render.py -v`
Expected: ImportError on `core.scanners.utils.pdf_render`.

- [ ] **Step 3: Implement `core/scanners/utils/pdf_render.py`**

```python
"""PyMuPDF wrapper: render pages or page regions as PIL images, count pages."""

from __future__ import annotations

import io
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image


class PdfRenderError(RuntimeError):
    """Raised when a PDF cannot be opened, parsed, or rendered."""


def get_page_count(pdf_path: Path) -> int:
    """Return the page count of *pdf_path*. Raises PdfRenderError on failure."""
    try:
        with fitz.open(pdf_path) as doc:
            return len(doc)
    except (fitz.FileDataError, OSError, ValueError, RuntimeError) as exc:
        raise PdfRenderError(f"cannot read {pdf_path}: {exc}") from exc


def render_page_image(pdf_path: Path, page_idx: int, *, dpi: int = 150) -> Image.Image:
    """Render a full page at *dpi* and return as PIL.Image (RGB)."""
    try:
        with fitz.open(pdf_path) as doc:
            if not (0 <= page_idx < len(doc)):
                raise PdfRenderError(f"page_idx={page_idx} out of range for {pdf_path}")
            page = doc[page_idx]
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            return img
    except (fitz.FileDataError, OSError, ValueError, RuntimeError) as exc:
        raise PdfRenderError(f"cannot render {pdf_path}:{page_idx}: {exc}") from exc


def render_page_region(
    pdf_path: Path,
    page_idx: int,
    *,
    bbox: tuple[float, float, float, float],
    dpi: int = 200,
) -> Image.Image:
    """Render a region of a page.

    Args:
        bbox: ``(x0, y0, x1, y1)`` in *relative* coordinates [0..1].
              ``(0, 0)`` is top-left of the page.
        dpi: target DPI. OCR usually wants 200 or higher.
    """
    x0, y0, x1, y1 = bbox
    if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
        raise ValueError(f"invalid bbox {bbox}: expected [0..1] with x0<x1, y0<y1")
    try:
        with fitz.open(pdf_path) as doc:
            if not (0 <= page_idx < len(doc)):
                raise PdfRenderError(f"page_idx={page_idx} out of range for {pdf_path}")
            page = doc[page_idx]
            page_rect = page.rect
            clip = fitz.Rect(
                page_rect.x0 + (page_rect.width * x0),
                page_rect.y0 + (page_rect.height * y0),
                page_rect.x0 + (page_rect.width * x1),
                page_rect.y0 + (page_rect.height * y1),
            )
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
            return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    except (fitz.FileDataError, OSError, ValueError, RuntimeError) as exc:
        raise PdfRenderError(f"cannot render {pdf_path}:{page_idx} region {bbox}: {exc}") from exc
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/scanners/utils/test_pdf_render.py -v`
Expected: 6 passed (or 7 if your environment renders without issues).

**Performance note for the implementer:** `render_page_image` and
`render_page_region` open the PDF on every call. Scanners iterating N
pages currently incur N `fitz.open()` costs. If the perf budget in
spec §9 (<45s for 34pp) is missed during Task 11 verification, refactor
to a context-managed batched iterator like:

```python
def iter_page_regions(pdf_path, *, bbox, dpi):
    with fitz.open(pdf_path) as doc:
        for page in doc:
            yield _render_clip(page, bbox, dpi)
```

Defer this optimization until measured — premature otherwise.

- [ ] **Step 5: Commit**

```bash
git add core/scanners/utils/pdf_render.py tests/unit/scanners/utils/__init__.py tests/unit/scanners/utils/test_pdf_render.py
git commit -m "feat(scanners/utils): pdf_render — PyMuPDF page + region wrappers

Three pure functions: get_page_count, render_page_image, render_page_region.
Region rendering takes relative bbox in [0..1] for top-right cropping in
corner_count later. Custom PdfRenderError for clean exception handling
in scanners. Tests use real HRB/odi compilation fixture + synthetic
corrupted PDF.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: `page_count_pure.py` — 1pp = 1doc

**Files:**
- Create: `core/scanners/utils/page_count_pure.py`
- Test: `tests/unit/scanners/utils/test_page_count_pure.py`

- [ ] **Step 1: Write failing test**

```python
"""page_count_pure — count documents in a single PDF as N pages."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.scanners.utils.page_count_pure import count_documents_in_pdf
from core.scanners.utils.pdf_render import PdfRenderError

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "scanners_ocr"


def test_count_equals_page_count():
    result = count_documents_in_pdf(FIXTURES / "odi_compilation" / "HRB_odi_compilation.pdf")
    assert result.count > 1
    assert result.method == "page_count_pure"
    assert result.pages_total == result.count


def test_count_on_corrupted_raises():
    with pytest.raises(PdfRenderError):
        count_documents_in_pdf(FIXTURES / "corrupted" / "corrupted.pdf")
```

- [ ] **Step 2: Run, verify ImportError**

Run: `pytest tests/unit/scanners/utils/test_page_count_pure.py -v`

- [ ] **Step 3: Implement `core/scanners/utils/page_count_pure.py`**

```python
"""Trivial scanner util: assume 1 PDF page == 1 document.

Used by charla_scanner when the carpeta has a single compilation PDF.
Multi-PDF charla folders fall back to filename_glob — they don't sum
page counts (that would count pages, not documents).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.scanners.utils.pdf_render import get_page_count


@dataclass(frozen=True)
class PageCountPureResult:
    count: int
    pages_total: int
    method: str = "page_count_pure"


def count_documents_in_pdf(pdf_path: Path) -> PageCountPureResult:
    """Open *pdf_path*, return count = page_count. Raises PdfRenderError on
    invalid/missing PDF."""
    n = get_page_count(pdf_path)
    return PageCountPureResult(count=n, pages_total=n)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/scanners/utils/test_page_count_pure.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add core/scanners/utils/page_count_pure.py tests/unit/scanners/utils/test_page_count_pure.py
git commit -m "feat(scanners/utils): page_count_pure (1pp = 1doc)

Trivial helper used by charla_scanner for single-PDF compilations.
Multi-PDF charla folders fall back to filename_glob — they don't sum
page counts (that would count pages, not documents).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: `header_detect.py` — find `F-CRS-XXX/NN` codes

**Files:**
- Create: `core/scanners/utils/header_detect.py`
- Test: `tests/unit/scanners/utils/test_header_detect.py`

- [ ] **Step 1: Write failing test**

```python
"""header_detect — find F-CRS-XXX/NN form codes on each page via OCR."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.scanners.utils.header_detect import HeaderDetectResult, count_form_codes
from core.scanners.utils.pdf_render import PdfRenderError

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "scanners_ocr"


@pytest.mark.slow
def test_header_detect_on_hrb_odi_compilation():
    result = count_form_codes(FIXTURES / "odi_compilation" / "HRB_odi_compilation.pdf", sigla_code="ODI")
    assert isinstance(result, HeaderDetectResult)
    # The HRB ODI compilation should have ~17 forms; allow wide range due to OCR variance
    assert 5 <= result.count <= 50
    assert all(re.match(r"F-CRS-ODI/\d+", m, re.IGNORECASE) for m in result.matches)
    assert len(result.pages_with_match) <= result.pages_total
    assert all(0 <= p < result.pages_total for p in result.pages_with_match)
    assert result.count == len(result.matches)  # matches set ↔ count consistency


def test_header_detect_on_corrupted_raises():
    with pytest.raises(PdfRenderError):
        count_form_codes(FIXTURES / "corrupted" / "corrupted.pdf", sigla_code="ODI")


def test_header_detect_sigla_code_filters_match():
    # Calling with a sigla that doesn't appear in the doc returns 0
    result = count_form_codes(FIXTURES / "odi_compilation" / "HRB_odi_compilation.pdf", sigla_code="NOPE")
    assert result.count == 0
    assert result.matches == []
```

- [ ] **Step 2: Run, verify ImportError**

- [ ] **Step 3: Implement `core/scanners/utils/header_detect.py`**

```python
"""Find `F-CRS-XXX/NN` form codes in the top-third of each PDF page.

Used by odi_scanner and irl_scanner to count documents in compilations.
The form code pattern is canonical to CRS prevention paperwork:
`F-CRS-ODI/03`, `F-CRS-IRL/45`, etc.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pytesseract
from PIL import Image

from core.scanners.utils.pdf_render import get_page_count, render_page_region


@dataclass(frozen=True)
class HeaderDetectResult:
    count: int
    matches: list[str] = field(default_factory=list)
    pages_with_match: list[int] = field(default_factory=list)
    pages_total: int = 0
    method: str = "header_detect"


_TOP_THIRD_BBOX = (0.0, 0.0, 1.0, 0.35)  # full width, top 35% of page


def _build_pattern(sigla_code: str) -> re.Pattern[str]:
    # Tolerant of OCR noise around dashes/slashes and case
    return re.compile(
        rf"F[\s\-_]*CRS[\s\-_]*{re.escape(sigla_code)}[\s\-_/]+(\d{{1,3}})",
        re.IGNORECASE,
    )


def count_form_codes(
    pdf_path: Path,
    *,
    sigla_code: str,
    dpi: int = 200,
) -> HeaderDetectResult:
    """OCR the top-third of each page; count unique form codes.

    Args:
        pdf_path: Source PDF.
        sigla_code: Uppercase sigla (``"ODI"``, ``"IRL"``, ...). Matches
                    ``F-CRS-<sigla>/<number>``.
        dpi: rendering DPI (default 200 — sufficient for form codes).

    Returns:
        :class:`HeaderDetectResult` with the count of unique codes matched.
    """
    pages_total = get_page_count(pdf_path)
    pattern = _build_pattern(sigla_code)
    matches: set[str] = set()
    pages_with_match: list[int] = []

    for page_idx in range(pages_total):
        img: Image.Image = render_page_region(
            pdf_path, page_idx, bbox=_TOP_THIRD_BBOX, dpi=dpi
        )
        text = pytesseract.image_to_string(img, config="--psm 6 --oem 1", lang="spa+eng")
        page_matches = pattern.findall(text)
        if page_matches:
            for m in page_matches:
                matches.add(f"F-CRS-{sigla_code.upper()}/{m}")
            pages_with_match.append(page_idx)

    return HeaderDetectResult(
        count=len(matches),
        matches=sorted(matches),
        pages_with_match=pages_with_match,
        pages_total=pages_total,
    )
```

The `--psm 6 --oem 1` matches the project's existing OCR config (per `core/CLAUDE.md`). Tolerant regex handles OCR noise on the dashes/slashes.

- [ ] **Step 4: Run tests (slow, real OCR)**

Run: `pytest tests/unit/scanners/utils/test_header_detect.py -v -m slow`
Expected: 3 passed. First run may take 30-60s.

- [ ] **Step 5: Verify ruff clean for new modules**

Run: `ruff check core/scanners/utils/`
Expected: 0 violations.

- [ ] **Step 6: Commit**

```bash
git add core/scanners/utils/header_detect.py tests/unit/scanners/utils/test_header_detect.py
git commit -m "feat(scanners/utils): header_detect — OCR F-CRS-XXX/NN form codes

Renders the top 35%% of each page at 200 DPI, runs Tesseract with
--psm 6 --oem 1, matches a tolerant regex (handles OCR noise on dashes
and slashes), returns unique codes. Used by odi_scanner and irl_scanner.
Tests use real HRB/odi compilation fixture — marked slow.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: `corner_count.py` — "Página N de M" transitions

**Files:**
- Create: `core/scanners/utils/corner_count.py`
- Test: `tests/unit/scanners/utils/test_corner_count.py`

The corner-count technique looks for Spanish pagination strings ("Página 1 de 3") in the upper-right corner. Each transition from `N/M` to `1/M'` marks a new document boundary.

Reuses `core/utils._PAGE_PATTERNS` regex registry per spec §3.2.

- [ ] **Step 1: Verify `_PAGE_PATTERNS` exists in core/utils.py**

Use `mcp__serena__find_symbol "_PAGE_PATTERNS" relative_path="core/utils.py"`. Confirm it's a list of compiled patterns. If absent, the scanner defines its own (see fallback in step 3).

- [ ] **Step 2: Write failing test**

```python
"""corner_count — count document transitions via Página N de M pagination."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.scanners.utils.corner_count import CornerCountResult, count_paginations
from core.scanners.utils.pdf_render import PdfRenderError

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "scanners_ocr"


@pytest.mark.slow
def test_corner_count_on_real_pdf_runs_and_is_consistent():
    # HRB/odi may or may not have corner pagination; verify invariants only.
    result = count_paginations(FIXTURES / "odi_compilation" / "HRB_odi_compilation.pdf")
    assert isinstance(result, CornerCountResult)
    assert result.method == "corner_count"
    assert result.pages_total > 0
    assert result.count <= result.pages_total
    # Every transition entry must be a (1..M, M) tuple with positive M
    assert all(0 < n <= m and m > 0 for n, m in result.transitions)


def test_corner_count_on_corrupted_raises():
    with pytest.raises(PdfRenderError):
        count_paginations(FIXTURES / "corrupted" / "corrupted.pdf")


def test_corner_count_transitions_logic():
    """Unit-level: given a series of (N, M) tuples, count doc boundaries."""
    from core.scanners.utils.corner_count import _count_transitions

    # Each new document is a 1/M after a previous N/M sequence
    series = [(1, 3), (2, 3), (3, 3), (1, 2), (2, 2)]
    assert _count_transitions(series) == 2  # two docs

    # Single page docs
    assert _count_transitions([(1, 1), (1, 1), (1, 1)]) == 3

    # Empty input
    assert _count_transitions([]) == 0

    # Page numbers with same total — one doc
    assert _count_transitions([(1, 5), (2, 5), (3, 5), (4, 5), (5, 5)]) == 1
```

- [ ] **Step 3: Implement `core/scanners/utils/corner_count.py`**

```python
"""Count document boundaries by detecting "Página N de M" transitions.

Used by art_scanner when ART folders contain a compilation PDF.
Each new document starts at page 1 of a new pagination series.

Reuses regex + digit normalization from core/utils when available, falls
back to a local pattern otherwise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pytesseract
from PIL import Image

from core.scanners.utils.pdf_render import get_page_count, render_page_region

# Top-right corner: rightmost 30%, top 22% (matches project CROP defaults)
_CORNER_BBOX = (0.70, 0.0, 1.0, 0.22)

# Spanish pagination: tolerant of OCR noise ("Pag", "Pagina", "Página", optional accent)
_FALLBACK_PATTERN = re.compile(
    r"P[áa]?g(?:ina|\.)?\s*(\d{1,3})\s*(?:de|\/)\s*(\d{1,3})",
    re.IGNORECASE,
)


def _get_patterns() -> list[re.Pattern[str]]:
    """Reuse core/utils._PAGE_PATTERNS if available; else use fallback."""
    try:
        from core import utils as _u
        return list(_u._PAGE_PATTERNS) if hasattr(_u, "_PAGE_PATTERNS") else [_FALLBACK_PATTERN]
    except ImportError:
        return [_FALLBACK_PATTERN]


def _normalize_digits(text: str) -> str:
    """OCR digit normalization (per core/CLAUDE.md OCR Assumptions)."""
    table = str.maketrans({"O": "0", "I": "1", "l": "1", "L": "1", "i": "1",
                           "z": "2", "Z": "2", "|": "1", "t": "1", "T": "1", "'": "1"})
    return text.translate(table)


@dataclass(frozen=True)
class CornerCountResult:
    count: int
    transitions: list[tuple[int, int]] = field(default_factory=list)
    pages_total: int = 0
    method: str = "corner_count"


def _count_transitions(series: list[tuple[int, int]]) -> int:
    """Given a list of (N, M) per page, count how many distinct documents exist.

    Each new doc starts at page 1; consecutive page 1s with different M values
    indicate distinct compilations.
    """
    if not series:
        return 0
    docs = 0
    prev: tuple[int, int] | None = None
    for n, m in series:
        if prev is None:
            docs = 1
        else:
            # New document if we see a page 1 again
            if n == 1:
                docs += 1
        prev = (n, m)
    return docs


def count_paginations(pdf_path: Path, *, dpi: int = 200) -> CornerCountResult:
    """OCR the upper-right corner of each page, parse "Página N de M",
    count document transitions."""
    pages_total = get_page_count(pdf_path)
    patterns = _get_patterns()
    series: list[tuple[int, int]] = []

    for page_idx in range(pages_total):
        img: Image.Image = render_page_region(
            pdf_path, page_idx, bbox=_CORNER_BBOX, dpi=dpi
        )
        text = pytesseract.image_to_string(img, config="--psm 7 --oem 1", lang="spa+eng")
        text = _normalize_digits(text)
        match = None
        for pattern in patterns:
            m = pattern.search(text)
            if m and len(m.groups()) >= 2:
                match = m
                break
        if match:
            try:
                n, total = int(match.group(1)), int(match.group(2))
                if 0 < n <= total <= 99:
                    series.append((n, total))
            except (ValueError, IndexError):
                continue

    count = _count_transitions(series)
    return CornerCountResult(count=count, transitions=series, pages_total=pages_total)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/scanners/utils/test_corner_count.py -v`
Expected: 3 passed (the slow one runs real OCR; the unit transition test is fast).

- [ ] **Step 5: Commit**

```bash
git add core/scanners/utils/corner_count.py tests/unit/scanners/utils/test_corner_count.py
git commit -m "feat(scanners/utils): corner_count — Página N de M transitions

OCRs the upper-right corner of each PDF page (rightmost 30%%, top 22%%),
parses pagination via the project's _PAGE_PATTERNS regex registry (with
local fallback), counts distinct documents by detecting transitions to
page 1. Pure transition-counting helper (_count_transitions) is unit
tested without OCR.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Chunk 2 sanity — all OCR utils green

- [ ] **Step 1: Run unit fast**

Run: `pytest -m "not slow" tests/unit/scanners/utils/ -v`
Expected: ~10 passed (pdf_render + page_count_pure + corner_count transitions logic).

- [ ] **Step 2: Run slow OCR tests**

Run: `pytest -m slow tests/unit/scanners/utils/ -v`
Expected: ~5 passed (real OCR on real fixtures).

- [ ] **Step 3: Ruff**

Run: `ruff check core/scanners/utils/`
Expected: 0 violations.

- [ ] **Step 4: Git log**

Run: `git log --oneline -10`
Expected: ~5 commits for Chunk 2 (fixtures, pdf_render, page_count_pure, header_detect, corner_count) on top of Chunk 1.

---

## Chunk 3: Specialized scanners (art / odi / irl / charla) + cancellation

**Goal:** Four sigla-specific scanners that pick OCR primary technique + filename_glob fallback per the decision rule in spec §3.2. Plus a 20-line `CancellationToken` helper that scanners and the orchestrator share.

**Shared decision rule (all four scanners):**

```python
def count_ocr(self, folder: Path, *, cancel: CancellationToken) -> ScanResult:
    cancel.check()                                  # pre-flight
    pdfs = sorted(folder.glob("*.pdf"))             # alphabetical, deterministic
    if not pdfs:
        return self._filename_glob(folder)          # delegates to existing path

    # Heuristic: 1 PDF whose page_count is way above what filename_glob alone
    # would produce → compilation. Run OCR primary.
    is_compilation = (len(pdfs) == 1
                      and flag_compilation_suspect(folder, sigla=self.sigla))

    if not is_compilation:
        return self._filename_glob(folder)          # N normal PDFs → no OCR

    # OCR primary path
    try:
        ocr_result = self._run_primary(pdfs[0], cancel=cancel)
        if ocr_result.count > 0:
            return ocr_result                       # primary succeeded
        # primary returned 0 → fall through to fallback with ocr_failed flag
    except CancelledError:
        raise                                        # propagate to orchestrator
    except (PdfRenderError, OCRError) as exc:
        return self._fallback(folder, error=str(exc))

    return self._fallback(folder, error="no_matches")
```

`_filename_glob` reuses `SimpleFilenameScanner.count(folder)` internally
(no code duplication). The happy-path OCR result preserves `base.flags`
(from the same filename_glob call) so flags like `compilation_suspect` /
`no_matching_sigla_in_folder` propagate. `_fallback` wraps the same call
but adds `confidence=LOW` + `flags=[*base.flags, "ocr_failed"]` +
`errors=[error_msg]`.

**Cancellation contract:** scanners check `cancel.check()` at three checkpoints:

1. Pre-flight (before any work).
2. Between PDFs (only `charla`/`art` may iterate; in FASE 2 we OCR one PDF max).
3. Between pages inside a PDF (delegated to the OCR util — `header_detect` and `corner_count` will accept an optional `cancel` callable).

For Chunk 3 we keep `header_detect`/`corner_count` as written in Chunk 2 (no `cancel` kwarg yet) and only check between PDFs / pre-flight. Page-level cancellation in chunks 2 utils is a refinement landed in Chunk 4 alongside the orchestrator — the spec target is `<3s` to cancel, and a single-PDF render loop tops at ~30s, so per-page cancel is a polish, not a blocker. **Trade-off accepted:** cancelling mid-render of one 30-page PDF will take up to ~30s instead of <3s for that single cell. We log this as a known limitation in DoD Chunk 6 and revisit if it bites in real use.

**Cross-process visibility caveat for `CancellationToken`:** the Chunk 3 token is a plain dataclass — fine for unit tests (`max_workers=1` serial path). The orchestrator in Chunk 4 will wrap it around a `multiprocessing.Event` so workers in subprocesses observe the cancellation. The scanner code does NOT need to change between Chunks 3 and 4 (it just calls `cancel.check()`); only the construction site changes.

**Folder discovery vs compilation flag:** all four scanners build their PDF list with non-recursive `folder.glob("*.pdf")`, while `flag_compilation_suspect` uses `rglob`. If a compilation PDF lives inside a sub-folder (e.g. `7.-ART/TITAN/2026-04-15_art_multidoc.pdf`), `len(pdfs) == 0` at the scanner level but `flag_compilation_suspect == True`. The branch order — empty-folder check **before** the compilation check — means scanners correctly fall through to filename_glob in that case (the legacy `per_empresa_breakdown` is recursive and handles sub-folder layouts). Assumption documented here; revisit if real-world cell layouts violate it.

### Task 12: CancellationToken helper

**Files:**
- Create: `core/scanners/cancellation.py`
- Test: `tests/unit/scanners/test_cancellation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/scanners/test_cancellation.py
import pytest
from core.scanners.cancellation import CancellationToken, CancelledError


def test_token_starts_uncancelled() -> None:
    token = CancellationToken()
    assert token.cancelled is False
    token.check()  # no-op, must not raise


def test_cancel_flips_flag() -> None:
    token = CancellationToken()
    token.cancel()
    assert token.cancelled is True


def test_check_after_cancel_raises() -> None:
    token = CancellationToken()
    token.cancel()
    with pytest.raises(CancelledError):
        token.check()


def test_cancel_is_idempotent() -> None:
    token = CancellationToken()
    token.cancel()
    token.cancel()
    assert token.cancelled is True


def test_cancelled_error_is_exception() -> None:
    assert issubclass(CancelledError, Exception)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/scanners/test_cancellation.py -v`
Expected: FAIL — `ModuleNotFoundError: core.scanners.cancellation`.

- [ ] **Step 3: Implement**

```python
# core/scanners/cancellation.py
"""Cooperative cancellation primitive shared by OCR scanners and the orchestrator.

Plain mutable state — no threading.Event. Workers run in subprocesses and the
orchestrator iterates `as_completed` on the main thread; the token is set on
the main thread and read by workers via the subprocess they were dispatched
into. Each scanner calls `cancel.check()` at natural checkpoints; if cancelled
the call raises `CancelledError`, which the orchestrator catches and converts
to a `scan_cancelled` WS event (see Chunk 4).
"""

from __future__ import annotations

from dataclasses import dataclass


class CancelledError(Exception):
    """Raised by CancellationToken.check() when cancel() has been invoked."""


@dataclass
class CancellationToken:
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True

    def check(self) -> None:
        if self.cancelled:
            raise CancelledError()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/scanners/test_cancellation.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add core/scanners/cancellation.py tests/unit/scanners/test_cancellation.py
git commit -m "feat(scanners): CancellationToken + CancelledError primitive

Shared cooperative cancellation between OCR scanners and the orchestrator
(Chunk 4). Plain mutable bool — no threading primitives needed because
the token is mutated on the orchestrator thread and checked from worker
subprocesses via os-level shared state (set in Chunk 4 dispatch).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 13: art_scanner (corner_count primary)

**Files:**
- Create: `core/scanners/art_scanner.py`
- Test: `tests/unit/scanners/test_art_scanner.py`

- [ ] **Step 1: Write the failing test**

Use the fixtures pinned in Chunk 2 Task 6 (`tests/fixtures/scanners_ocr/`). The decision rule is exercised with three folder shapes.

```python
# tests/unit/scanners/test_art_scanner.py
from pathlib import Path

import pytest

from core.scanners.art_scanner import ArtScanner
from core.scanners.base import ConfidenceLevel
from core.scanners.cancellation import CancellationToken, CancelledError

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "scanners_ocr"


def test_normal_folder_uses_filename_glob(tmp_path: Path) -> None:
    """N normal PDFs in 7.-ART/ → no OCR, filename_glob direct."""
    art_folder = tmp_path / "7.-ART"
    art_folder.mkdir()
    # Three trivially-named singletons; one page each.
    for empresa in ("TITAN", "KOHLER", "ARAYA"):
        (art_folder / f"2026-04-15_art_{empresa}.pdf").write_bytes(
            _one_page_pdf_bytes()
        )

    scanner = ArtScanner()
    result = scanner.count_ocr(art_folder, cancel=CancellationToken())

    assert result.method == "filename_glob"
    assert result.count == 3
    assert "ocr_failed" not in result.flags
    assert result.confidence == ConfidenceLevel.HIGH


@pytest.mark.slow
def test_compilation_pdf_uses_corner_count() -> None:
    """1 PDF flagged compilation_suspect → corner_count primary."""
    fixture = FIXTURE_ROOT / "art_multidoc"  # pinned in Chunk 2 Task 6
    scanner = ArtScanner()
    result = scanner.count_ocr(fixture, cancel=CancellationToken())

    assert result.method == "corner_count"
    assert result.count >= 2          # multi-doc compilation
    assert result.confidence == ConfidenceLevel.HIGH


def test_empty_folder_returns_filename_glob_zero(tmp_path: Path) -> None:
    empty = tmp_path / "7.-ART"
    empty.mkdir()
    scanner = ArtScanner()
    result = scanner.count_ocr(empty, cancel=CancellationToken())

    assert result.count == 0
    assert result.method == "filename_glob"


def test_precancelled_token_raises_before_work(tmp_path: Path) -> None:
    folder = tmp_path / "7.-ART"
    folder.mkdir()
    token = CancellationToken()
    token.cancel()
    with pytest.raises(CancelledError):
        ArtScanner().count_ocr(folder, cancel=token)


def _one_page_pdf_bytes() -> bytes:
    """Minimal 1-page PDF — generated via PyMuPDF helper used in Chunk 2."""
    import fitz
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    buf = doc.tobytes()
    doc.close()
    return buf
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/scanners/test_art_scanner.py -v`
Expected: FAIL — `ModuleNotFoundError: core.scanners.art_scanner`.

- [ ] **Step 3: Implement**

```python
# core/scanners/art_scanner.py
"""Scanner for sigla `art` — Análisis de Riesgo de Tarea.

Decision rule (spec §3.2):
- Folder has N normal PDFs → filename_glob (pase 1 result is already correct).
- Folder has 1 PDF flagged compilation_suspect → corner_count OCR on that PDF.
- corner_count returns 0 or raises → fallback to filename_glob with
  confidence=LOW and flag `ocr_failed`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from core.scanners.base import ConfidenceLevel, ScanResult
from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.simple_factory import SimpleFilenameScanner
from core.scanners.utils.corner_count import count_paginations
from core.scanners.utils.page_count_heuristic import flag_compilation_suspect
from core.scanners.utils.pdf_render import PdfRenderError


@dataclass
class ArtScanner:
    sigla: str = "art"

    def count(
        self,
        folder: Path,
        *,
        override_method: str | None = None,
    ) -> ScanResult:
        """Pase 1 entry point — uses filename_glob like every other scanner."""
        return SimpleFilenameScanner(sigla=self.sigla).count(
            folder, override_method=override_method
        )

    def count_ocr(
        self,
        folder: Path,
        *,
        cancel: CancellationToken,
    ) -> ScanResult:
        cancel.check()
        pdfs = sorted(folder.glob("*.pdf"))
        if not pdfs:
            return self._filename_glob(folder)

        is_compilation = (
            len(pdfs) == 1
            and flag_compilation_suspect(folder, sigla=self.sigla)
        )
        if not is_compilation:
            return self._filename_glob(folder)

        cancel.check()
        base = self._filename_glob(folder)          # captures flags for happy-path too
        start = time.perf_counter()
        try:
            ocr = count_paginations(pdfs[0])
        except CancelledError:
            raise
        except (PdfRenderError, OSError, RuntimeError) as exc:
            return self._fallback_from_base(base, error=f"corner_count_failed: {exc}")

        if ocr.count <= 0:
            return self._fallback_from_base(base, error="no_matches")

        duration_ms = int((time.perf_counter() - start) * 1000)
        return ScanResult(
            count=ocr.count,
            confidence=ConfidenceLevel.HIGH,
            method="corner_count",
            breakdown=None,
            flags=list(base.flags),                  # preserves compilation_suspect + any other
            errors=[],
            duration_ms=duration_ms,
            files_scanned=1,
        )

    def _filename_glob(self, folder: Path) -> ScanResult:
        return SimpleFilenameScanner(sigla=self.sigla).count(folder)

    def _fallback(self, folder: Path, *, error: str) -> ScanResult:
        return self._fallback_from_base(self._filename_glob(folder), error=error)

    def _fallback_from_base(self, base: ScanResult, *, error: str) -> ScanResult:
        return ScanResult(
            count=base.count,
            confidence=ConfidenceLevel.LOW,
            method="filename_glob",
            breakdown=base.breakdown,
            flags=[*base.flags, "ocr_failed"],
            errors=[*base.errors, error],
            duration_ms=base.duration_ms,
            files_scanned=base.files_scanned,
        )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/scanners/test_art_scanner.py -v`
Expected: 3 fast passed + 1 slow passed (4 total). The slow one renders + OCRs the real fixture.

- [ ] **Step 5: Commit**

```bash
git add core/scanners/art_scanner.py tests/unit/scanners/test_art_scanner.py
git commit -m "feat(scanners): ArtScanner — corner_count primary, filename_glob fallback

Decision rule per spec §3.2: N normal PDFs → filename_glob direct; 1 PDF
flagged compilation_suspect → corner_count OCR on that PDF; OCR returns 0
or raises → fallback to filename_glob with confidence=LOW + flag
ocr_failed. Pre-flight + per-PDF cancellation checkpoints. Pase 1
(.count()) delegates to SimpleFilenameScanner unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 14: HeaderDetectScanner base + odi_scanner + irl_scanner

`odi` and `irl` share the exact same primary technique (`header_detect`), differing only in the `sigla_code` they pass (`ODI` vs `IRL`). Pulling a parameterized base avoids two near-identical files.

**Files:**
- Create: `core/scanners/_header_detect_base.py`
- Create: `core/scanners/odi_scanner.py`
- Create: `core/scanners/irl_scanner.py`
- Test: `tests/unit/scanners/test_odi_scanner.py`
- Test: `tests/unit/scanners/test_irl_scanner.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/scanners/test_odi_scanner.py
from pathlib import Path

import pytest

from core.scanners.base import ConfidenceLevel
from core.scanners.cancellation import CancellationToken
from core.scanners.odi_scanner import OdiScanner

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "scanners_ocr"


@pytest.mark.slow
def test_compilation_pdf_uses_header_detect() -> None:
    """1 PDF flagged compilation_suspect → header_detect on F-CRS-ODI/NN."""
    fixture = FIXTURE_ROOT / "odi_compilation"
    scanner = OdiScanner()
    result = scanner.count_ocr(fixture, cancel=CancellationToken())

    assert result.method == "header_detect"
    assert result.count >= 2
    assert result.confidence == ConfidenceLevel.HIGH


def test_n_normal_pdfs_use_filename_glob(tmp_path: Path) -> None:
    folder = tmp_path / "3.-ODI Visitas"
    folder.mkdir()
    for empresa in ("AGUASAN", "TITAN"):
        (folder / f"2026-04-10_odi_{empresa}.pdf").write_bytes(_one_page_pdf())
    result = OdiScanner().count_ocr(folder, cancel=CancellationToken())
    assert result.method == "filename_glob"
    assert result.count == 2


def _one_page_pdf() -> bytes:
    import fitz
    doc = fitz.open(); doc.new_page(width=595, height=842)
    buf = doc.tobytes(); doc.close()
    return buf
```

```python
# tests/unit/scanners/test_irl_scanner.py
from pathlib import Path

import pytest

from core.scanners.base import ConfidenceLevel
from core.scanners.cancellation import CancellationToken
from core.scanners.irl_scanner import IrlScanner

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "scanners_ocr"


@pytest.mark.slow
def test_compilation_pdf_uses_header_detect() -> None:
    fixture = FIXTURE_ROOT / "irl_compilation"
    scanner = IrlScanner()
    result = scanner.count_ocr(fixture, cancel=CancellationToken())
    assert result.method == "header_detect"
    assert result.count >= 1
    assert result.confidence == ConfidenceLevel.HIGH


def test_empty_folder_zero(tmp_path: Path) -> None:
    folder = tmp_path / "irl"
    folder.mkdir()
    result = IrlScanner().count_ocr(folder, cancel=CancellationToken())
    assert result.method == "filename_glob"
    assert result.count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/scanners/test_odi_scanner.py tests/unit/scanners/test_irl_scanner.py -v`
Expected: FAIL — `ModuleNotFoundError: core.scanners.odi_scanner` / `irl_scanner`.

- [ ] **Step 3: Implement the shared base + the two scanners**

```python
# core/scanners/_header_detect_base.py
"""Parameterized base for sigla scanners whose primary technique is
`header_detect` (regex F-CRS-<SIGLA_CODE>/NN). Used by OdiScanner and
IrlScanner. Not a public scanner — leading underscore.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from core.scanners.base import ConfidenceLevel, ScanResult
from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.simple_factory import SimpleFilenameScanner
from core.scanners.utils.header_detect import count_form_codes
from core.scanners.utils.page_count_heuristic import flag_compilation_suspect
from core.scanners.utils.pdf_render import PdfRenderError


@dataclass(kw_only=True)
class HeaderDetectScanner:
    """Concrete subclasses set ``sigla`` and ``sigla_code`` (e.g. "ODI", "IRL").

    ``kw_only=True`` keeps subclass inheritance safe: subclasses can override
    field defaults without tripping the "non-default field after default field"
    dataclass rule.
    """

    sigla: str
    sigla_code: str

    def count(
        self,
        folder: Path,
        *,
        override_method: str | None = None,
    ) -> ScanResult:
        return SimpleFilenameScanner(sigla=self.sigla).count(
            folder, override_method=override_method
        )

    def count_ocr(
        self,
        folder: Path,
        *,
        cancel: CancellationToken,
    ) -> ScanResult:
        cancel.check()
        pdfs = sorted(folder.glob("*.pdf"))
        if not pdfs:
            return self._filename_glob(folder)

        is_compilation = (
            len(pdfs) == 1
            and flag_compilation_suspect(folder, sigla=self.sigla)
        )
        if not is_compilation:
            return self._filename_glob(folder)

        cancel.check()
        base = self._filename_glob(folder)           # capture flags for happy path
        start = time.perf_counter()
        try:
            ocr = count_form_codes(pdfs[0], sigla_code=self.sigla_code)
        except CancelledError:
            raise
        except (PdfRenderError, OSError, RuntimeError) as exc:
            return self._fallback_from_base(base, error=f"header_detect_failed: {exc}")

        if ocr.count <= 0:
            return self._fallback_from_base(base, error="no_matches")

        duration_ms = int((time.perf_counter() - start) * 1000)
        return ScanResult(
            count=ocr.count,
            confidence=ConfidenceLevel.HIGH,
            method="header_detect",
            breakdown=None,
            flags=list(base.flags),                  # preserves compilation_suspect + others
            errors=[],
            duration_ms=duration_ms,
            files_scanned=1,
        )

    def _filename_glob(self, folder: Path) -> ScanResult:
        return SimpleFilenameScanner(sigla=self.sigla).count(folder)

    def _fallback_from_base(self, base: ScanResult, *, error: str) -> ScanResult:
        return ScanResult(
            count=base.count,
            confidence=ConfidenceLevel.LOW,
            method="filename_glob",
            breakdown=base.breakdown,
            flags=[*base.flags, "ocr_failed"],
            errors=[*base.errors, error],
            duration_ms=base.duration_ms,
            files_scanned=base.files_scanned,
        )
```

```python
# core/scanners/odi_scanner.py
"""Scanner for sigla `odi` — Observación de Incidentes / ODI Visitas."""

from __future__ import annotations

from dataclasses import dataclass

from core.scanners._header_detect_base import HeaderDetectScanner


@dataclass(kw_only=True)
class OdiScanner(HeaderDetectScanner):
    sigla: str = "odi"
    sigla_code: str = "ODI"
```

```python
# core/scanners/irl_scanner.py
"""Scanner for sigla `irl` — Inspecciones de Riesgo Laboral."""

from __future__ import annotations

from dataclasses import dataclass

from core.scanners._header_detect_base import HeaderDetectScanner


@dataclass(kw_only=True)
class IrlScanner(HeaderDetectScanner):
    sigla: str = "irl"
    sigla_code: str = "IRL"
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/scanners/test_odi_scanner.py tests/unit/scanners/test_irl_scanner.py -v`
Expected: 2 fast + 2 slow passed (4 total).

- [ ] **Step 5: Commit**

```bash
git add core/scanners/_header_detect_base.py core/scanners/odi_scanner.py core/scanners/irl_scanner.py tests/unit/scanners/test_odi_scanner.py tests/unit/scanners/test_irl_scanner.py
git commit -m "feat(scanners): OdiScanner + IrlScanner via parameterized HeaderDetectScanner

Both scanners share the same primary technique — header_detect on the
F-CRS-<sigla_code>/NN regex — differing only in sigla_code (\"ODI\" vs
\"IRL\"). Pulled into a private parameterized base
(_header_detect_base.py) to avoid two near-identical files. Decision
rule and fallback identical to ArtScanner.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 15: charla_scanner (page_count_pure primary)

**Files:**
- Create: `core/scanners/charla_scanner.py`
- Test: `tests/unit/scanners/test_charla_scanner.py`

`charla` is the simplest specialized scanner: in a compilation PDF, 1 page = 1 charla. No OCR — `page_count_pure` is a metadata read.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/scanners/test_charla_scanner.py
from pathlib import Path

import pytest

from core.scanners.base import ConfidenceLevel
from core.scanners.cancellation import CancellationToken
from core.scanners.charla_scanner import CharlaScanner

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "scanners_ocr"


@pytest.mark.slow
def test_compilation_uses_page_count_pure() -> None:
    """1 PDF flagged compilation → page_count_pure (1pp = 1 charla)."""
    fixture = FIXTURE_ROOT / "charla_compilation"
    scanner = CharlaScanner()
    result = scanner.count_ocr(fixture, cancel=CancellationToken())

    assert result.method == "page_count_pure"
    assert result.count >= 2
    assert result.confidence == ConfidenceLevel.HIGH


def test_n_normal_pdfs_use_filename_glob(tmp_path: Path) -> None:
    folder = tmp_path / "charla"
    folder.mkdir()
    for empresa in ("TITAN", "KOHLER"):
        (folder / f"2026-04-10_charla_{empresa}.pdf").write_bytes(_one_page_pdf())
    result = CharlaScanner().count_ocr(folder, cancel=CancellationToken())
    assert result.method == "filename_glob"
    assert result.count == 2


def _one_page_pdf() -> bytes:
    import fitz
    doc = fitz.open(); doc.new_page(width=595, height=842)
    buf = doc.tobytes(); doc.close()
    return buf
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/scanners/test_charla_scanner.py -v`
Expected: FAIL — `ModuleNotFoundError: core.scanners.charla_scanner`.

- [ ] **Step 3: Implement**

```python
# core/scanners/charla_scanner.py
"""Scanner for sigla `charla` — Charla de Seguridad.

Decision rule (spec §3.2): compilation PDFs for charla are 1 page = 1 charla.
`page_count_pure` is a PyMuPDF metadata read, not OCR, so it's effectively
free (~5ms). Fallback to filename_glob only if the PDF can't be opened.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from core.scanners.base import ConfidenceLevel, ScanResult
from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.simple_factory import SimpleFilenameScanner
from core.scanners.utils.page_count_heuristic import flag_compilation_suspect
from core.scanners.utils.page_count_pure import count_documents_in_pdf
from core.scanners.utils.pdf_render import PdfRenderError


@dataclass
class CharlaScanner:
    sigla: str = "charla"

    def count(
        self,
        folder: Path,
        *,
        override_method: str | None = None,
    ) -> ScanResult:
        return SimpleFilenameScanner(sigla=self.sigla).count(
            folder, override_method=override_method
        )

    def count_ocr(
        self,
        folder: Path,
        *,
        cancel: CancellationToken,
    ) -> ScanResult:
        cancel.check()
        pdfs = sorted(folder.glob("*.pdf"))
        if not pdfs:
            return self._filename_glob(folder)

        is_compilation = (
            len(pdfs) == 1
            and flag_compilation_suspect(folder, sigla=self.sigla)
        )
        if not is_compilation:
            return self._filename_glob(folder)

        cancel.check()
        base = self._filename_glob(folder)           # capture flags for happy path
        start = time.perf_counter()
        try:
            ocr = count_documents_in_pdf(pdfs[0])    # returns PageCountPureResult
        except CancelledError:
            raise                                     # consistent with Art/Header scanners
        except (PdfRenderError, OSError, RuntimeError) as exc:
            return self._fallback_from_base(base, error=f"page_count_pure_failed: {exc}")

        if ocr.count <= 0:
            return self._fallback_from_base(base, error="zero_pages")

        duration_ms = int((time.perf_counter() - start) * 1000)
        return ScanResult(
            count=ocr.count,
            confidence=ConfidenceLevel.HIGH,
            method="page_count_pure",
            breakdown=None,
            flags=list(base.flags),                  # preserves compilation_suspect
            errors=[],
            duration_ms=duration_ms,
            files_scanned=1,
        )

    def _filename_glob(self, folder: Path) -> ScanResult:
        return SimpleFilenameScanner(sigla=self.sigla).count(folder)

    def _fallback_from_base(self, base: ScanResult, *, error: str) -> ScanResult:
        return ScanResult(
            count=base.count,
            confidence=ConfidenceLevel.LOW,
            method="filename_glob",
            breakdown=base.breakdown,
            flags=[*base.flags, "ocr_failed"],
            errors=[*base.errors, error],
            duration_ms=base.duration_ms,
            files_scanned=base.files_scanned,
        )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/scanners/test_charla_scanner.py -v`
Expected: 1 fast + 1 slow passed (the slow one only opens the PDF, no Tesseract, so it's still <500ms).

- [ ] **Step 5: Commit**

```bash
git add core/scanners/charla_scanner.py tests/unit/scanners/test_charla_scanner.py
git commit -m "feat(scanners): CharlaScanner — page_count_pure primary (1pp = 1 charla)

For compilation PDFs in the charla folder, 1 page = 1 charla. Uses
PyMuPDF metadata read (~5ms), no OCR. Decision rule and fallback shape
match Art/Odi/Irl scanners.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 16: Register specialized scanners in `core/scanners/__init__.py`

The current `register_defaults()` registers `SimpleFilenameScanner` for all 18
siglas. We override the four specialized ones *before* the default loop runs
so they win.

**Files:**
- Modify: `core/scanners/__init__.py:56-60`
- Test: `tests/unit/scanners/test_registration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/scanners/test_registration.py
"""Specialized scanners must be the ones returned by get(sigla) after
register_defaults(). simple_factory still wins for the other 14 siglas."""

from core.scanners import all_siglas, clear, get, register_defaults
from core.scanners.art_scanner import ArtScanner
from core.scanners.charla_scanner import CharlaScanner
from core.scanners.irl_scanner import IrlScanner
from core.scanners.odi_scanner import OdiScanner
from core.scanners.simple_factory import SimpleFilenameScanner


def test_art_uses_art_scanner() -> None:
    clear(); register_defaults()
    assert isinstance(get("art"), ArtScanner)


def test_odi_uses_odi_scanner() -> None:
    clear(); register_defaults()
    assert isinstance(get("odi"), OdiScanner)


def test_irl_uses_irl_scanner() -> None:
    clear(); register_defaults()
    assert isinstance(get("irl"), IrlScanner)


def test_charla_uses_charla_scanner() -> None:
    clear(); register_defaults()
    assert isinstance(get("charla"), CharlaScanner)


def test_non_specialized_uses_simple_factory() -> None:
    clear(); register_defaults()
    # 4 specialized + 14 simple = 18 total
    specialized = {"art", "odi", "irl", "charla"}
    for sigla in all_siglas():
        scanner = get(sigla)
        if sigla in specialized:
            assert not isinstance(scanner, SimpleFilenameScanner), sigla
        else:
            assert isinstance(scanner, SimpleFilenameScanner), sigla
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/scanners/test_registration.py -v`
Expected: FAIL on the four `isinstance(... SpecializedScanner)` checks — the registry still returns `SimpleFilenameScanner` because `register_defaults` hasn't been updated.

- [ ] **Step 3: Modify `register_defaults`**

Replace the existing body of `register_defaults`:

```python
# core/scanners/__init__.py
from core.scanners.art_scanner import ArtScanner  # noqa: E402
from core.scanners.charla_scanner import CharlaScanner  # noqa: E402
from core.scanners.irl_scanner import IrlScanner  # noqa: E402
from core.scanners.odi_scanner import OdiScanner  # noqa: E402

_SPECIALIZED = (ArtScanner(), OdiScanner(), IrlScanner(), CharlaScanner())


def register_defaults() -> None:
    """Register all 18 sigla scanners.

    Specialized scanners (art/odi/irl/charla) are registered first; the
    remaining 14 fall back to SimpleFilenameScanner via _make. Idempotent —
    safe to call after clear().
    """
    for scanner in _SPECIALIZED:
        if not has(scanner.sigla):
            register(scanner)
    for sigla in _SIGLAS:
        if not has(sigla):
            register(_make(sigla))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/scanners/test_registration.py -v`
Expected: 5 passed.

- [ ] **Step 5: Re-run prior scanner tests to confirm no regressions**

Run: `pytest tests/unit/scanners/ -v -m "not slow"`
Expected: all fast scanner unit tests pass (registration + 4 specialized + cancellation + utils from Chunk 2).

- [ ] **Step 6: Commit**

```bash
git add core/scanners/__init__.py tests/unit/scanners/test_registration.py
git commit -m "feat(scanners): register Art/Odi/Irl/Charla scanners over simple_factory

register_defaults() now installs the four specialized scanners first;
the remaining 14 siglas fall back to SimpleFilenameScanner. Idempotent
(safe after clear()), order-independent (specialized always wins because
they're registered first and has() short-circuits).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 17: Chunk 3 sanity — all scanner tests green

- [ ] **Step 1: Run fast scanner suite**

Run: `pytest -m "not slow" tests/unit/scanners/ -v`
Expected: **17 passed** (5 cancellation + 3 art + 1 odi + 1 irl + 1 charla + 5 registration + 1 corner_count transitions + Chunk 2 fast pieces).

- [ ] **Step 2: Run slow scanner suite (real OCR)**

Run: `pytest -m slow tests/unit/scanners/ -v`
Expected: **9 passed** (1 art_multidoc + 1 odi_compilation + 1 irl_compilation + 1 charla_compilation + 5 Chunk 2 OCR slow tests). If a fixture-page-count assertion fails first, see fix instructions in Chunk 2 Task 6 Step 4.

- [ ] **Step 3: Ruff**

Run: `ruff check core/scanners/ tests/unit/scanners/`
Expected: 0 violations.

- [ ] **Step 4: Verify the legacy Pase 1 path still works end-to-end**

Run: `pytest tests/integration/test_abril_full.py -v`
Expected: unchanged — Chunk 3 does not touch the `.count()` (filename_glob) path consumed by `scan_month`, so the ABRIL fixture audit (54 cells, expected counts) must remain green.

- [ ] **Step 5: Git log**

Run: `git log --oneline -10`
Expected: ~5 new commits for Chunk 3 (cancellation, art, odi+irl, charla, registration) on top of Chunks 1+2.

---

## Chunk 4: Orchestrator OCR + WS broadcast + API endpoints

**Goal:** Wire the OCR pass end-to-end. The orchestrator's new `scan_cells_ocr` dispatches specialized scanners across a `ProcessPoolExecutor(2)` with a shared `CancellationToken`, emits progress via a callback, and the API layer routes that callback into a WebSocket broadcaster. Three new endpoints (`POST /scan-ocr`, `POST /cancel`, PATCH override), two new GETs for files + PDF streaming.

**Architecture decisions baked in:**

1. **Token sharing across subprocesses.** `ProcessPoolExecutor` serializes work — a plain dataclass token mutated on the main thread is invisible to the workers. The `CancellationToken.from_event` constructor (Task 18) wraps a `multiprocessing.Event`, which is OS-level shared state visible to every subprocess. The event is constructed in the route handler and injected into each worker via the executor's `initializer` argument so each worker process sees the live event without needing to serialize it per call.

2. **Callback bridge.** Workers cannot reach the asyncio event loop directly. The orchestrator iterates `as_completed(futures)` *in a background thread* (started by a `ThreadPoolExecutor` from the route handler) and the callback runs in that thread. The callback calls `app.state.loop.call_soon_threadsafe(asyncio.ensure_future, broadcast(...))` — `broadcast` is async and runs on the main event loop. `app.state.loop` is captured during `lifespan` startup.

3. **One batch at a time per session.** `app.state.batches: dict[session_id, BatchHandle]`. A second `POST /scan-ocr` while a batch is in flight returns 409. `POST /cancel` is always 200 (no-op if no batch).

4. **Reusing `scan_month`.** Pase 1's `scan_month` orchestrator is untouched. The new `scan_cells_ocr` lives in the same file but operates on `count_ocr` instead of `count`. The worker function dispatches `getattr(scanner, "count_ocr", None)` — falls back to `count()` for the 14 non-specialized siglas (which don't have `count_ocr` and therefore can't usefully OCR; they just return filename_glob with no new info).

### Task 18: `multiprocessing.Event`–backed CancellationToken

The Chunk 3 `CancellationToken` is a plain dataclass — fine for unit tests but invisible across processes. We extend it to optionally wrap an `mp.Event` so it works in the real pool.

**Files:**
- Modify: `core/scanners/cancellation.py` (extend, don't break existing API)
- Modify: `tests/unit/scanners/test_cancellation.py` (add cross-process tests)

- [ ] **Step 1: Write the failing test**

Append to existing test file:

```python
# tests/unit/scanners/test_cancellation.py — additions

import multiprocessing as mp

from core.scanners.cancellation import CancellationToken


def _worker_check_then_signal(event, ready, done):
    """Subprocess worker that waits for ready, then checks cancellation, then signals done."""
    ready.wait()
    token = CancellationToken.from_event(event)
    try:
        token.check()
    except Exception as exc:                                 # noqa: BLE001
        done.put(type(exc).__name__)
        return
    done.put("ok")


def test_event_backed_token_visible_across_processes() -> None:
    """Setting cancel in parent must be visible in a child subprocess."""
    ctx = mp.get_context("spawn")
    event = ctx.Event()
    ready = ctx.Event()
    done = ctx.Queue()
    proc = ctx.Process(target=_worker_check_then_signal, args=(event, ready, done))
    proc.start()
    event.set()                  # cancel BEFORE the child checks
    ready.set()
    result = done.get(timeout=10)
    proc.join(timeout=5)
    assert result == "CancelledError"


def test_event_backed_token_uncancelled_passes() -> None:
    ctx = mp.get_context("spawn")
    event = ctx.Event()
    ready = ctx.Event()
    done = ctx.Queue()
    proc = ctx.Process(target=_worker_check_then_signal, args=(event, ready, done))
    proc.start()
    ready.set()                  # don't cancel
    result = done.get(timeout=10)
    proc.join(timeout=5)
    assert result == "ok"
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `pytest tests/unit/scanners/test_cancellation.py -v`
Expected: 5 existing pass, 2 new FAIL — `AttributeError: type object 'CancellationToken' has no attribute 'from_event'`.

- [ ] **Step 3: Extend CancellationToken**

Replace `core/scanners/cancellation.py`:

```python
"""Cooperative cancellation primitive shared by OCR scanners and the orchestrator.

Two construction modes:

- ``CancellationToken()`` — plain in-process bool. Use in unit tests.
- ``CancellationToken.from_event(mp_event)`` — wraps a ``multiprocessing.Event``.
  Use in production: the orchestrator creates the event, the executor's
  ``initializer`` injects it into each worker subprocess, and any process
  observes the cancellation immediately after ``.set()`` is called.

Both modes expose the same ``cancelled`` property + ``cancel()`` + ``check()`` API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class CancelledError(Exception):
    """Raised by CancellationToken.check() when cancel() has been invoked."""


@dataclass
class CancellationToken:
    _event: Any = field(default=None, repr=False)
    _flag: bool = False

    @classmethod
    def from_event(cls, event: Any) -> "CancellationToken":
        """Construct a token backed by a multiprocessing.Event (or similar)."""
        return cls(_event=event)

    @property
    def cancelled(self) -> bool:
        if self._event is not None:
            return bool(self._event.is_set())
        return self._flag

    def cancel(self) -> None:
        if self._event is not None:
            self._event.set()
        else:
            self._flag = True

    def check(self) -> None:
        if self.cancelled:
            raise CancelledError()
```

- [ ] **Step 4: Run all tests**

Run: `pytest tests/unit/scanners/test_cancellation.py -v`
Expected: 7 passed (5 in-process + 2 cross-process).

- [ ] **Step 5: Commit**

```bash
git add core/scanners/cancellation.py tests/unit/scanners/test_cancellation.py
git commit -m "feat(scanners): extend CancellationToken with from_event(mp_event)

Plain dataclass mode is invisible across ProcessPoolExecutor workers.
Adds an optional multiprocessing.Event wrapper — the orchestrator
creates the event, the executor initializer injects it per worker, and
.cancel() in the parent process is observed immediately by all workers.
Existing in-process API unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 19: `scan_cells_ocr` in `core/orchestrator.py`

**Files:**
- Modify: `core/orchestrator.py` (add `scan_cells_ocr` + `_ocr_worker` + `_init_ocr_worker`)
- Test: `tests/unit/test_orchestrator_ocr.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_orchestrator_ocr.py
"""Unit tests for scan_cells_ocr orchestration.

Scanners are stubbed via a tiny FakeScanner registered into the registry so we
exercise the orchestration shape (callback firing, cancellation propagation,
exception handling) without paying real-OCR latency. Run with max_workers=1
so the synchronous in-process path is exercised — the multi-worker path is
covered by the integration test in Chunk 4 Task 23.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core import scanners as scanner_registry
from core.orchestrator import scan_cells_ocr
from core.scanners.base import ConfidenceLevel, ScanResult
from core.scanners.cancellation import CancellationToken


def _make_result(count: int) -> ScanResult:
    return ScanResult(
        count=count,
        confidence=ConfidenceLevel.HIGH,
        method="header_detect",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=10,
        files_scanned=1,
    )


@pytest.fixture(autouse=True)
def restore_registry():
    yield
    scanner_registry.clear()
    scanner_registry.register_defaults()


def test_callback_fires_for_each_cell(tmp_path: Path) -> None:
    folder = tmp_path / "f"; folder.mkdir()
    cells = [("HPV", "odi", folder), ("HRB", "art", folder)]

    events: list[dict] = []
    def on_progress(ev: dict) -> None:
        events.append(ev)

    scanner_registry.clear()
    for sigla in ("odi", "art"):
        s = MagicMock(sigla=sigla)
        s.count_ocr = MagicMock(return_value=_make_result(3))
        scanner_registry.register(s)

    results = scan_cells_ocr(
        cells, on_progress=on_progress, cancel=CancellationToken(), max_workers=1
    )

    assert (("HPV", "odi") in results) and (("HRB", "art") in results)
    types = [e["type"] for e in events]
    assert types.count("cell_scanning") == 2
    assert types.count("cell_done") == 2
    assert types[-1] == "scan_complete"


def test_cancellation_short_circuits(tmp_path: Path) -> None:
    folder = tmp_path / "f"; folder.mkdir()
    cells = [("HPV", "odi", folder)] * 5

    cancel = CancellationToken()
    events: list[dict] = []

    def on_progress(ev: dict) -> None:
        events.append(ev)
        if ev.get("type") == "cell_done" and \
           sum(1 for e in events if e["type"] == "cell_done") == 2:
            cancel.cancel()

    scanner_registry.clear()
    s = MagicMock(sigla="odi")
    s.count_ocr = MagicMock(return_value=_make_result(1))
    scanner_registry.register(s)

    scan_cells_ocr(
        cells, on_progress=on_progress, cancel=cancel, max_workers=1
    )

    types = [e["type"] for e in events]
    assert "scan_cancelled" in types
    assert "scan_complete" not in types


def test_worker_exception_emits_cell_error(tmp_path: Path) -> None:
    folder = tmp_path / "f"; folder.mkdir()
    cells = [("HPV", "odi", folder)]

    events: list[dict] = []
    def on_progress(ev: dict) -> None:
        events.append(ev)

    scanner_registry.clear()
    s = MagicMock(sigla="odi")
    s.count_ocr = MagicMock(side_effect=RuntimeError("boom"))
    scanner_registry.register(s)

    results = scan_cells_ocr(
        cells, on_progress=on_progress, cancel=CancellationToken(), max_workers=1
    )

    assert ("HPV", "odi") not in results
    assert any(e["type"] == "cell_error" for e in events)


def test_pre_cancelled_token_emits_scan_cancelled_zero(tmp_path: Path) -> None:
    """A token already cancelled before the call → scan_cancelled(scanned=0) only."""
    folder = tmp_path / "f"; folder.mkdir()
    cells = [("HPV", "odi", folder)]

    events: list[dict] = []
    def on_progress(ev: dict) -> None:
        events.append(ev)

    cancel = CancellationToken()
    cancel.cancel()

    scan_cells_ocr(cells, on_progress=on_progress, cancel=cancel, max_workers=1)

    assert len(events) == 1
    assert events[0] == {"type": "scan_cancelled", "scanned": 0, "total": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_orchestrator_ocr.py -v`
Expected: FAIL — `ImportError: cannot import name 'scan_cells_ocr' from 'core.orchestrator'`.

- [ ] **Step 3: Implement**

Append to `core/orchestrator.py` (imports at top of file already include `Path`, `ScanResult`):

```python
# ----------------------------------------------------------------------
# Pase 2 — OCR orchestration
# ----------------------------------------------------------------------

from typing import Any, Callable  # noqa: E402  (add only if missing from current imports — check first via Grep)

_WORKER_EVENT: Any = None  # set per-subprocess by _init_ocr_worker


def _init_ocr_worker(event: Any) -> None:
    """ProcessPoolExecutor initializer — caches the cancellation event in the
    subprocess so the worker can build a CancellationToken without re-sending
    the event with every call."""
    global _WORKER_EVENT
    _WORKER_EVENT = event


def _ocr_worker(
    cell_tuple: tuple[str, str, str],
) -> tuple[str, str, ScanResult | None, str | None]:
    """Run OCR for a single cell. Runs in a worker subprocess.

    Returns:
        ``(hospital, sigla, ScanResult | None, error_str | None)`` — exactly
        one of ScanResult or error_str is non-None.
    """
    from core import scanners as scanner_registry  # noqa: E402
    from core.scanners.cancellation import CancellationToken, CancelledError  # noqa: E402

    hosp, sigla, folder_str = cell_tuple
    folder = Path(folder_str)
    scanner = scanner_registry.get(sigla)
    token = CancellationToken.from_event(_WORKER_EVENT) if _WORKER_EVENT else CancellationToken()

    fn = getattr(scanner, "count_ocr", None)
    try:
        if fn is None:
            result = scanner.count(folder)                  # filename_glob fallback
        else:
            result = fn(folder, cancel=token)
    except CancelledError:
        return (hosp, sigla, None, "cancelled")
    except Exception as exc:                                # noqa: BLE001
        return (hosp, sigla, None, f"{type(exc).__name__}: {exc}")
    return (hosp, sigla, result, None)


def scan_cells_ocr(
    cells: list[tuple[str, str, Path]],
    *,
    on_progress: Callable[[dict], None],
    cancel: "CancellationToken",
    max_workers: int = 2,
) -> dict[tuple[str, str], ScanResult]:
    """Pase 2 — OCR scan a subset of cells with progress events.

    Args:
        cells: ``[(hospital, sigla, folder_path), ...]`` to scan.
        on_progress: Invoked on the orchestrator thread with event dicts.
            Events: ``cell_scanning`` (before each cell), ``cell_done`` /
            ``cell_error`` (after each cell), ``scan_progress`` (after each
            cell), and the terminal ``scan_complete`` or ``scan_cancelled``.
        cancel: Pre-flight short-circuits with ``scan_cancelled(scanned=0)``.
        max_workers: ProcessPoolExecutor size. Default 2 (OCR is CPU+RAM
            heavy). Tests pass ``max_workers=1`` to run synchronously without
            spawning subprocesses.

    Returns:
        Dict of successful ``(hospital, sigla) → ScanResult``. Cells that
        errored or were cancelled are absent from the dict — their state is
        reported only via events.
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed  # noqa: E402
    from core.scanners.cancellation import CancellationToken  # noqa: E402, F401

    results: dict[tuple[str, str], ScanResult] = {}
    total = len(cells)
    cell_tuples = [(h, s, str(f)) for (h, s, f) in cells]

    if cancel.cancelled:
        on_progress({"type": "scan_cancelled", "scanned": 0, "total": total})
        return results

    if max_workers == 1:
        scanned = 0
        errors = 0
        for ct in cell_tuples:
            if cancel.cancelled:
                on_progress({"type": "scan_cancelled", "scanned": scanned, "total": total})
                return results
            hosp, sigla, _ = ct
            on_progress({"type": "cell_scanning", "hospital": hosp, "sigla": sigla})
            h, s, result, err = _ocr_worker(ct)
            if err == "cancelled":
                on_progress({"type": "scan_cancelled", "scanned": scanned, "total": total})
                return results
            if err:
                errors += 1
                on_progress({"type": "cell_error", "hospital": h, "sigla": s, "error": err})
            else:
                results[(h, s)] = result  # type: ignore[assignment]
                on_progress({
                    "type": "cell_done",
                    "hospital": h,
                    "sigla": s,
                    "result": {
                        "ocr_count": result.count,
                        "method": result.method,
                        "confidence": result.confidence.value,
                        "duration_ms_ocr": result.duration_ms,
                    },
                })
            scanned += 1
            on_progress({"type": "scan_progress", "done": scanned, "total": total})
        on_progress({"type": "scan_complete", "scanned": scanned, "errors": errors, "cancelled": 0})
        return results

    # Multi-worker path — real ProcessPoolExecutor.
    event = getattr(cancel, "_event", None)
    scanned = 0
    errors = 0
    cancelled = 0
    with ProcessPoolExecutor(
        max_workers=max_workers,
        initializer=_init_ocr_worker,
        initargs=(event,),
    ) as pool:
        future_to_cell = {pool.submit(_ocr_worker, ct): ct for ct in cell_tuples}
        for fut in as_completed(future_to_cell):
            # Cancel-fast: if the user pressed Cancel mid-batch, do NOT wait for
            # every in-flight future to drain. Workers observe the event and
            # return err="cancelled" at their next checkpoint (≤ a few seconds);
            # we just stop processing results and break out. The `with` block
            # exits and waits for the pool to settle.
            if cancel.cancelled and cancelled == 0:
                # First time we notice — request the pool to discard queued
                # futures (Python 3.9+). In-flight will still need to wind
                # down at their own next checkpoint.
                pool.shutdown(wait=False, cancel_futures=True)
            h, s, result, err = fut.result()
            on_progress({"type": "cell_scanning", "hospital": h, "sigla": s})
            if err == "cancelled":
                cancelled += 1
            elif err:
                errors += 1
                on_progress({"type": "cell_error", "hospital": h, "sigla": s, "error": err})
            else:
                results[(h, s)] = result  # type: ignore[assignment]
                on_progress({
                    "type": "cell_done",
                    "hospital": h,
                    "sigla": s,
                    "result": {
                        "ocr_count": result.count,
                        "method": result.method,
                        "confidence": result.confidence.value,
                        "duration_ms_ocr": result.duration_ms,
                    },
                })
            scanned += 1
            on_progress({"type": "scan_progress", "done": scanned, "total": total})

    if cancelled > 0:
        on_progress({"type": "scan_cancelled", "scanned": scanned, "total": total})
    else:
        on_progress({"type": "scan_complete", "scanned": scanned, "errors": errors, "cancelled": 0})
    return results
```

> **Note on `cell_scanning` ordering in multi-worker mode:** With `ProcessPoolExecutor`,
> work begins as soon as `submit()` returns — by the time `as_completed` yields, the
> cell has already finished. We emit `cell_scanning` immediately followed by
> `cell_done` in the same iteration so the frontend animation has a brief flash. If
> we ever want true "start of work" notifications, the worker would need to post a
> message via `mp.Queue` before doing OCR; that's deferred to Chunk 6 polish.

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_orchestrator_ocr.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add core/orchestrator.py tests/unit/test_orchestrator_ocr.py
git commit -m "feat(orchestrator): scan_cells_ocr — pase 2 OCR with progress callback

ProcessPoolExecutor(max_workers=2) dispatches _ocr_worker per cell with a
shared multiprocessing.Event-backed CancellationToken (injected via
initializer). Workers call scanner.count_ocr (falls back to .count()
for the 14 non-specialized siglas). Progress events fire via the
on_progress callback on the orchestrator thread. Pre-cancelled token
short-circuits with scan_cancelled(scanned=0). max_workers=1 path used
by unit tests, runs synchronously in-process.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 20: WebSocket broadcast in `api/main.py` + `api/routes/ws.py`

Captures the asyncio loop in `lifespan` and exposes a `broadcast` helper that the orchestrator callback can schedule from any thread.

**Files:**
- Modify: `api/main.py:27-34` (extend lifespan)
- Modify: `api/routes/ws.py` (track connections, expose `broadcast`)
- Test: `tests/unit/api/test_ws_broadcast.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/api/test_ws_broadcast.py
"""WS broadcast helper must deliver JSON events to all connections for a session."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.routes.ws import broadcast


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "ws_test.db"))
    return create_app()


def test_broadcast_with_no_connections_is_noop(app) -> None:
    """No connections for session → broadcast returns without error."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(broadcast("nonexistent-session", {"type": "ping"}))
    finally:
        loop.close()


def test_ws_connect_and_receive_broadcast(app) -> None:
    """A connected WS receives broadcasts addressed to its session."""
    client = TestClient(app)
    sess_id = "2026-04-prueba"
    with client.websocket_connect(f"/ws/sessions/{sess_id}") as ws:
        loop = app.state.loop
        future = asyncio.run_coroutine_threadsafe(
            broadcast(sess_id, {"type": "cell_scanning", "hospital": "HPV", "sigla": "odi"}),
            loop,
        )
        future.result(timeout=2)
        msg = ws.receive_text()
        evt = json.loads(msg)
        assert evt["type"] == "cell_scanning"
        assert evt["hospital"] == "HPV"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/api/test_ws_broadcast.py -v`
Expected: FAIL — `ImportError: cannot import name 'broadcast' from 'api.routes.ws'`.

- [ ] **Step 3: Modify `api/routes/ws.py`**

```python
# api/routes/ws.py
"""WebSocket endpoint + broadcast helper for FASE 2 progress events."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

_CONNECTIONS: dict[str, set[WebSocket]] = defaultdict(set)


async def broadcast(session_id: str, event: dict) -> None:
    """Send a JSON event to all WS connections for a session.

    Dead connections are pruned silently; no exception escapes. Callers on a
    non-asyncio thread should marshal via ``asyncio.run_coroutine_threadsafe``
    or ``loop.call_soon_threadsafe(asyncio.ensure_future, broadcast(...))``.
    """
    payload = json.dumps(event)
    dead: list[WebSocket] = []
    for ws in list(_CONNECTIONS.get(session_id, ())):
        try:
            await ws.send_text(payload)
        except Exception:                                       # noqa: BLE001
            dead.append(ws)
    for ws in dead:
        _CONNECTIONS[session_id].discard(ws)


@router.websocket("/ws/sessions/{session_id}")
async def session_socket(ws: WebSocket, session_id: str) -> None:
    await ws.accept()
    _CONNECTIONS[session_id].add(ws)
    try:
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=15.0)
            except asyncio.TimeoutError:
                await ws.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        return
    finally:
        _CONNECTIONS[session_id].discard(ws)
```

- [ ] **Step 4: Modify `api/main.py`**

Update the `lifespan` function (currently at lines 27-34):

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = open_connection(_db_path())
    init_schema(conn)
    manager = SessionManager(conn=conn)
    app.dependency_overrides[get_manager] = lambda: manager
    # FASE 2: capture loop for cross-thread WS broadcasts; init batch registry;
    # expose manager on app.state for tests that need to invoke setters directly
    # (e.g. Chunk 6 Task 31 history-method tests). Production code still goes
    # through Depends(get_manager).
    app.state.loop = asyncio.get_running_loop()
    app.state.batches = {}
    app.state.manager = manager
    yield
    close_all()
```

Add `import asyncio` at the top of `api/main.py` if not present.

- [ ] **Step 5: Run test**

Run: `pytest tests/unit/api/test_ws_broadcast.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add api/main.py api/routes/ws.py tests/unit/api/test_ws_broadcast.py
git commit -m "feat(ws): connection registry + broadcast helper for FASE 2 events

session_socket now tracks live connections in a per-session set
(_CONNECTIONS) and tears down cleanly on disconnect or send failure.
broadcast(session_id, event) sends a JSON payload to all live WS for
that session; dead connections pruned silently. Lifespan captures the
asyncio loop on app.state.loop and initializes app.state.batches for
the batch registry in Task 21.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 21: BatchHandle + `POST /scan-ocr` + `POST /cancel`

**Files:**
- Create: `api/batch.py` (BatchHandle dataclass + factory)
- Modify: `api/routes/sessions.py` (add 2 endpoints)
- Test: `tests/unit/api/test_scan_ocr_routes.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/api/test_scan_ocr_routes.py
"""POST /scan-ocr and POST /cancel route behavior."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test.db"))
    # Pre-create a minimal ABRIL/HPV/3.-ODI Visitas folder with 1 PDF
    odi = tmp_path / "ABRIL" / "HPV" / "3.-ODI Visitas"
    odi.mkdir(parents=True)
    (odi / "2026-04-10_odi_TITAN.pdf").write_bytes(_one_page_pdf())
    app = create_app()
    with TestClient(app) as c:
        yield c


def _one_page_pdf() -> bytes:
    import fitz
    doc = fitz.open(); doc.new_page(width=595, height=842)
    buf = doc.tobytes(); doc.close()
    return buf


def _open_and_scan(client) -> str:
    r = client.post("/api/sessions", json={"year": 2026, "month": 4})
    sid = r.json()["session_id"]
    client.post(f"/api/sessions/{sid}/scan")        # populates cell folder_path
    return sid


def test_scan_ocr_unknown_session_returns_404(client) -> None:
    # Format-valid (yyyy-mm) but no such session — exercises the manager 404 path,
    # not the regex 400 path.
    r = client.post("/api/sessions/2027-12/scan-ocr", json={"cells": [["HPV", "odi"]]})
    assert r.status_code == 404


def test_scan_ocr_malformed_session_id_returns_400(client) -> None:
    r = client.post("/api/sessions/does-not-exist/scan-ocr", json={"cells": [["HPV", "odi"]]})
    assert r.status_code == 400


def test_scan_ocr_empty_cells_returns_400(client) -> None:
    sid = _open_and_scan(client)
    r = client.post(f"/api/sessions/{sid}/scan-ocr", json={"cells": []})
    assert r.status_code == 400


def test_scan_ocr_dispatches(client) -> None:
    sid = _open_and_scan(client)
    r = client.post(f"/api/sessions/{sid}/scan-ocr", json={"cells": [["HPV", "odi"]]})
    assert r.status_code == 200
    assert r.json()["accepted"] is True
    assert r.json()["total"] == 1


def test_cancel_no_active_batch_is_idempotent(client) -> None:
    """POST cancel without a batch returns 200 (no-op per spec §3.5)."""
    r = client.post("/api/sessions/2027-12/cancel")          # format-valid, no batch
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_scan_ocr_409_when_batch_already_running(client) -> None:
    """Plant a fake handle and verify the second POST is rejected."""
    from api.batch import make_handle
    sid = _open_and_scan(client)
    client.app.state.batches[sid] = make_handle(session_id=sid, total=1)
    try:
        r = client.post(f"/api/sessions/{sid}/scan-ocr", json={"cells": [["HPV", "odi"]]})
        assert r.status_code == 409
    finally:
        client.app.state.batches.pop(sid, None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/api/test_scan_ocr_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.batch'`.

- [ ] **Step 3: Create `api/batch.py`**

```python
"""Batch lifecycle for pase 2 OCR scans.

A BatchHandle ties together: the session it belongs to, the multiprocessing
Event for cancellation, and the concurrent.futures.Future that resolves when
the orchestrator thread is done. Stored in ``app.state.batches[session_id]``
while the batch runs and removed on completion (terminal event sent).
"""

from __future__ import annotations

import multiprocessing as mp
from dataclasses import dataclass
from typing import Any


@dataclass
class BatchHandle:
    session_id: str
    total: int
    cancel_event: Any          # mp.Event (or None for tests that don't dispatch)
    future: Any                # concurrent.futures.Future (or None)


def make_handle(session_id: str, total: int) -> BatchHandle:
    """Create a fresh handle with a new mp.Event."""
    ctx = mp.get_context("spawn")
    return BatchHandle(
        session_id=session_id,
        total=total,
        cancel_event=ctx.Event(),
        future=None,
    )
```

- [ ] **Step 4: Add `scan_ocr` + `cancel` routes**

Add to the top imports of `api/routes/sessions.py` (extend the existing imports — `Body`, `Depends`, `HTTPException` already imported):

```python
import asyncio  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402

from fastapi import Request  # noqa: E402

from api.batch import BatchHandle, make_handle  # noqa: E402, F401
from api.routes.ws import broadcast  # noqa: E402
from core.orchestrator import scan_cells_ocr  # noqa: E402
from core.scanners.base import ConfidenceLevel, ScanResult  # noqa: E402
from core.scanners.cancellation import CancellationToken  # noqa: E402

# Single thread per session is plenty — Daniel's machine has one user, and
# scan_cells_ocr already uses a ProcessPoolExecutor internally for parallelism.
_DISPATCH_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ocr-batch")
```

Append the two route handlers:

```python
@router.post("/sessions/{session_id}/scan-ocr")
def scan_ocr(
    request: Request,
    session_id: str,
    body: dict = Body(...),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Pase 2 — launch OCR batch for the given cells.

    Body: ``{"cells": [["HPV", "odi"], ["HRB", "art"], ...]}``
    """
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, f"Session not found: {session_id}") from exc

    cells_pairs = body.get("cells", [])
    if not isinstance(cells_pairs, list) or not cells_pairs:
        raise HTTPException(400, "cells must be a non-empty list of [hospital, sigla] pairs")

    app = request.app

    cells_with_paths: list[tuple[str, str, Path]] = []
    for pair in cells_pairs:
        if not (isinstance(pair, list) and len(pair) == 2):
            raise HTTPException(400, f"Invalid cell pair: {pair}")
        hosp, sigla = pair
        cell_state = state.get("cells", {}).get(hosp, {}).get(sigla)
        if not cell_state:
            raise HTTPException(404, f"Cell not found: {hosp}/{sigla}")
        folder_path = Path(cell_state.get("folder_path", ""))
        if not folder_path.exists():
            raise HTTPException(404, f"Folder missing for {hosp}/{sigla}")
        cells_with_paths.append((hosp, sigla, folder_path))

    # Atomic check-then-set: setdefault returns the value already in the dict if
    # it existed, otherwise installs and returns the new one. The two cases are
    # distinguishable by identity.
    handle = make_handle(session_id=session_id, total=len(cells_with_paths))
    if app.state.batches.setdefault(session_id, handle) is not handle:
        raise HTTPException(409, "another batch is already running for this session")
    loop = app.state.loop

    def on_progress(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(broadcast(session_id, event), loop)
        if event.get("type") == "cell_done":
            r = event["result"]
            result = ScanResult(
                count=r["ocr_count"],
                confidence=ConfidenceLevel(r["confidence"]),
                method=r["method"],
                breakdown=None,
                flags=[],
                errors=[],
                duration_ms=r["duration_ms_ocr"],
                files_scanned=1,
            )
            mgr.apply_ocr_result(session_id, event["hospital"], event["sigla"], result)

    cancel_token = CancellationToken.from_event(handle.cancel_event)

    def _run():
        try:
            scan_cells_ocr(
                cells_with_paths,
                on_progress=on_progress,
                cancel=cancel_token,
                max_workers=2,
            )
        finally:
            app.state.batches.pop(session_id, None)

    handle.future = _DISPATCH_POOL.submit(_run)
    return {"accepted": True, "total": len(cells_with_paths)}


@router.post("/sessions/{session_id}/cancel")
def cancel(request: Request, session_id: str) -> dict:
    """Always returns 200. If a batch is active, sets its cancel event."""
    handle = request.app.state.batches.get(session_id)
    if handle is not None and handle.cancel_event is not None:
        handle.cancel_event.set()
    return {"ok": True}
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/api/test_scan_ocr_routes.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add api/batch.py api/routes/sessions.py tests/unit/api/test_scan_ocr_routes.py
git commit -m "feat(api): POST /scan-ocr + POST /cancel endpoints

scan-ocr resolves cells against the session state, creates a BatchHandle
with a fresh mp.Event, dispatches scan_cells_ocr on a thread pool, and
marshals progress events through app.state.loop into the WS broadcast
helper via asyncio.run_coroutine_threadsafe. Cell results are persisted
via SessionManager.apply_ocr_result as they arrive. cancel is always
200; if a batch is active, it sets the event (workers observe via their
CancellationToken). 409 on concurrent batch per session.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 22: PATCH override + GET files + GET pdf

**Files:**
- Modify: `api/routes/sessions.py` (add 3 endpoints)
- Test: `tests/unit/api/test_cells_routes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/api/test_cells_routes.py
"""PATCH override + GET files + GET pdf route behavior."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test.db"))
    odi = tmp_path / "ABRIL" / "HPV" / "3.-ODI Visitas"
    odi.mkdir(parents=True)
    (odi / "2026-04-10_odi_TITAN.pdf").write_bytes(_one_page_pdf())
    app = create_app()
    with TestClient(app) as c:
        yield c


def _one_page_pdf() -> bytes:
    import fitz
    doc = fitz.open(); doc.new_page(width=595, height=842)
    buf = doc.tobytes(); doc.close()
    return buf


def _open_and_scan(client) -> str:
    r = client.post("/api/sessions", json={"year": 2026, "month": 4})
    sid = r.json()["session_id"]
    client.post(f"/api/sessions/{sid}/scan")
    return sid


def test_patch_override_sets_value(client) -> None:
    sess = _open_and_scan(client)
    r = client.patch(
        f"/api/sessions/{sess}/cells/HPV/odi/override",
        json={"value": 17, "note": "compilation"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user_override"] == 17
    assert body["override_note"] == "compilation"


def test_patch_override_null_clears(client) -> None:
    sess = _open_and_scan(client)
    client.patch(
        f"/api/sessions/{sess}/cells/HPV/odi/override",
        json={"value": 17, "note": "x"},
    )
    r = client.patch(
        f"/api/sessions/{sess}/cells/HPV/odi/override",
        json={"value": None, "note": None},
    )
    assert r.status_code == 200
    assert r.json()["user_override"] is None


def test_patch_override_validates_range(client) -> None:
    sess = _open_and_scan(client)
    for bad in (-1, 999_999, "seventeen"):
        r = client.patch(
            f"/api/sessions/{sess}/cells/HPV/odi/override",
            json={"value": bad, "note": None},
        )
        assert r.status_code == 400, f"expected 400 for value={bad!r}"


def test_get_files_lists_pdfs(client) -> None:
    sess = _open_and_scan(client)
    r = client.get(f"/api/sessions/{sess}/cells/HPV/odi/files")
    assert r.status_code == 200
    files = r.json()
    assert len(files) == 1
    assert files[0]["name"] == "2026-04-10_odi_TITAN.pdf"
    assert files[0]["page_count"] == 1


def test_get_files_missing_cell_returns_404(client) -> None:
    sess = _open_and_scan(client)
    r = client.get(f"/api/sessions/{sess}/cells/HPV/inexistente/files")
    assert r.status_code == 404


def test_get_pdf_streams_file(client) -> None:
    sess = _open_and_scan(client)
    r = client.get(f"/api/sessions/{sess}/cells/HPV/odi/pdf?index=0")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")


def test_get_pdf_out_of_range_returns_400(client) -> None:
    sess = _open_and_scan(client)
    r = client.get(f"/api/sessions/{sess}/cells/HPV/odi/pdf?index=99")
    assert r.status_code == 400


def test_get_pdf_negative_index_returns_400(client) -> None:
    sess = _open_and_scan(client)
    r = client.get(f"/api/sessions/{sess}/cells/HPV/odi/pdf?index=-1")
    assert r.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/api/test_cells_routes.py -v`
Expected: FAIL on all — endpoints don't exist yet.

- [ ] **Step 3: Implement**

Add to imports in `api/routes/sessions.py`:

```python
from fastapi.responses import FileResponse  # noqa: E402
import fitz  # noqa: E402

_MAX_REASONABLE_COUNT = 10_000
```

Append the three handlers:

```python
@router.patch("/sessions/{session_id}/cells/{hospital}/{sigla}/override")
def patch_override(
    session_id: str,
    hospital: str,
    sigla: str,
    body: dict = Body(...),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    value = body.get("value")
    note = body.get("note")
    if value is not None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise HTTPException(400, "value must be int or null")
        if value < 0 or value > _MAX_REASONABLE_COUNT:
            raise HTTPException(400, f"value must be in [0, {_MAX_REASONABLE_COUNT}]")
    try:
        mgr.apply_user_override(session_id, hospital, sigla, value=value, note=note)
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    cell = state["cells"].get(hospital, {}).get(sigla, {})
    return {
        "user_override": cell.get("user_override"),
        "override_note": cell.get("override_note"),
    }


@router.get("/sessions/{session_id}/cells/{hospital}/{sigla}/files")
def get_cell_files(
    session_id: str,
    hospital: str,
    sigla: str,
    mgr: SessionManager = Depends(get_manager),
) -> list[dict]:
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, f"Session not found: {session_id}") from exc
    cell = state.get("cells", {}).get(hospital, {}).get(sigla)
    if cell is None:
        raise HTTPException(404, f"Cell not found: {hospital}/{sigla}")
    folder = Path(cell.get("folder_path", ""))
    if not folder.exists():
        return []
    out: list[dict] = []
    for pdf in sorted(folder.rglob("*.pdf")):
        try:
            with fitz.open(pdf) as doc:
                page_count = doc.page_count
        except Exception:                                       # noqa: BLE001
            page_count = 0
        subfolder = pdf.parent.name if pdf.parent != folder else None
        out.append({
            "name": pdf.name,
            "subfolder": subfolder,
            "page_count": page_count,
            "suspect": page_count >= 10,
        })
    return out


@router.get("/sessions/{session_id}/cells/{hospital}/{sigla}/pdf")
def get_cell_pdf(
    session_id: str,
    hospital: str,
    sigla: str,
    index: int = 0,
    mgr: SessionManager = Depends(get_manager),
) -> FileResponse:
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    if index < 0:
        raise HTTPException(400, "index must be ≥ 0")
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    cell = state.get("cells", {}).get(hospital, {}).get(sigla)
    if cell is None:
        raise HTTPException(404, f"Cell not found: {hospital}/{sigla}")
    folder = Path(cell.get("folder_path", ""))
    pdfs = sorted(folder.rglob("*.pdf")) if folder.exists() else []
    if not pdfs:
        raise HTTPException(404, "no_pdfs_in_cell")
    if index >= len(pdfs):
        raise HTTPException(400, f"index out of range: {index} >= {len(pdfs)}")

    pdf_path = pdfs[index].resolve()
    cell_folder = folder.resolve()
    informe_root = _informe_root().resolve()
    # Two layers of containment per spec §4.6: PDF inside cell folder, cell
    # folder inside INFORME_MENSUAL_ROOT. Both must hold.
    if not pdf_path.is_relative_to(cell_folder):
        raise HTTPException(400, "invalid path")
    if not cell_folder.is_relative_to(informe_root):
        raise HTTPException(400, "cell folder outside informe root")

    return FileResponse(pdf_path, media_type="application/pdf")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/api/test_cells_routes.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add api/routes/sessions.py tests/unit/api/test_cells_routes.py
git commit -m "feat(api): PATCH override + GET files/pdf endpoints for cells

PATCH /cells/{h}/{s}/override validates value ∈ [0, 10000] or null,
delegates to SessionManager.apply_user_override (Chunk 1 setter), returns
resulting override + note. GET /cells/{h}/{s}/files lists PDFs in the
cell folder with name/subfolder/page_count/suspect, using rglob so
empresa sub-folders show up. GET /cells/{h}/{s}/pdf?index=N streams the
Nth PDF (sorted) with FileResponse; path traversal hardened via
is_relative_to check; 400 on out-of-range/negative index.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 23: Chunk 4 integration smoke + sanity

- [ ] **Step 1: Multi-worker integration test**

Verifies the real `ProcessPoolExecutor(2)` path with real subprocess cancellation. Run only if the corpus fixtures from Chunk 2 are present (skipped otherwise).

**Files:**
- Test: `tests/integration/test_scan_ocr_full.py`

```python
# tests/integration/test_scan_ocr_full.py
"""Integration: real ProcessPoolExecutor path over scanners_ocr fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from core import scanners as scanner_registry
from core.orchestrator import scan_cells_ocr
from core.scanners.cancellation import CancellationToken

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "scanners_ocr"


@pytest.mark.slow
def test_scan_cells_ocr_two_workers_real_scanners() -> None:
    """Dispatch 2 cells across 2 workers using real specialized scanners."""
    if not (FIXTURE_ROOT / "odi_compilation").exists():
        pytest.skip("scanners_ocr fixtures missing — run tools/extract_fase2_fixtures.py")
    scanner_registry.clear()
    scanner_registry.register_defaults()

    cells = [
        ("HRB", "odi", FIXTURE_ROOT / "odi_compilation"),
        ("HPV", "charla", FIXTURE_ROOT / "charla_compilation"),
    ]
    events: list[dict] = []
    cancel = CancellationToken.from_event(
        __import__("multiprocessing").get_context("spawn").Event()
    )
    results = scan_cells_ocr(
        cells, on_progress=events.append, cancel=cancel, max_workers=2
    )
    assert len(results) == 2
    assert events[-1]["type"] == "scan_complete"
    assert events[-1]["errors"] == 0
```

Run: `pytest tests/integration/test_scan_ocr_full.py -v -m slow`
Expected: 1 passed.

- [ ] **Step 2: Run all FASE 2 backend tests**

Run: `pytest tests/unit/scanners/ tests/unit/test_orchestrator_ocr.py tests/unit/api/ -v`
Expected: all pass (cancellation + scanners + orchestrator + ws broadcast + scan-ocr routes + cells routes).

- [ ] **Step 3: Ruff**

Run: `ruff check core/ api/`
Expected: 0 violations.

- [ ] **Step 4: Verify Pase 1 + Excel output paths still work**

Run: `pytest tests/integration/test_abril_full.py -v`
Expected: existing ABRIL full-corpus integration test passes — Chunk 4 only adds endpoints, doesn't touch the existing `POST /scan` or `POST /output` paths.

- [ ] **Step 5: Smoke test end-to-end with curl**

(Manual check before moving to Chunk 5.) Start `python server.py`, then:

```bash
# Open session
curl -s -X POST http://localhost:8000/api/sessions -H 'content-type: application/json' \
  -d '{"year": 2026, "month": 4}' | jq .

# Pase 1
curl -s -X POST http://localhost:8000/api/sessions/<sid>/scan | jq .summary

# Pase 2 OCR for one cell
curl -s -X POST http://localhost:8000/api/sessions/<sid>/scan-ocr \
  -H 'content-type: application/json' \
  -d '{"cells": [["HRB", "odi"]]}' | jq .

# Open WS in browser dev tools console:
# new WebSocket("ws://localhost:8000/ws/sessions/<sid>").onmessage = e => console.log(e.data)

# Override
curl -s -X PATCH http://localhost:8000/api/sessions/<sid>/cells/HRB/odi/override \
  -H 'content-type: application/json' -d '{"value": 17, "note": "compilation"}' | jq .
```

Expected: `scan-ocr` returns `{accepted: true, total: 1}`; WS prints `cell_scanning` then `cell_done` then `scan_complete`.

- [ ] **Step 6: Git log**

Run: `git log --oneline -15`
Expected: ~6 new commits for Chunk 4 (cancel-mp-event extension, scan_cells_ocr, ws broadcast, scan-ocr+cancel routes, cells routes, integration test) on top of Chunks 1-3.

---

## Chunk 5: Frontend — FileList + Lightbox + ScanControls + ScanProgress + WS client

**Goal:** Daniel sees per-cell OCR progress in real time, can override counts inline + write notes, and can open a floating PDF lightbox to verify. The store extends with WS-driven `scanningCells` + `scanProgress`; the layout grows a third column (FileList) on wide screens and stacks on narrow ones.

**Components touched/created (recap from spec §5):**

| File | Status | Responsibility |
|---|---|---|
| `frontend/src/lib/ws.js` | NEW | WS client: connect, reconnect with backoff, dispatch events to store |
| `frontend/src/lib/api.js` | MODIFY | Add 5 new endpoints (scan-ocr, cancel, override, files, pdf URL builder) |
| `frontend/src/store/session.js` | MODIFY | Add `scanningCells`, `scanProgress`, `lightbox`, plus actions for override/scan-ocr/cancel/WS event handlers |
| `frontend/src/components/FileList.jsx` | NEW | 3rd column listing PDFs in selected cell with click-to-preview |
| `frontend/src/components/PDFLightbox.jsx` | NEW | Floating modal with PDF iframe + override panel; X/backdrop/Esc closes |
| `frontend/src/components/OverridePanel.jsx` | NEW | Input + textarea reused in detail panel and lightbox |
| `frontend/src/components/ScanControls.jsx` | NEW | HospitalDetail header with bulk-OCR buttons |
| `frontend/src/components/ScanProgress.jsx` | NEW | Sticky footer with progress bar + cancel |
| `frontend/src/components/CategoryRow.jsx` | MODIFY | Add checkbox, spinner, error indicator |
| `frontend/src/views/HospitalDetail.jsx` | MODIFY | 3-column layout, integrate new components |

**State flow:**

```
backend WS event → ws.js → useSessionStore actions → React re-render
   cell_scanning  ↳ add (hospital, sigla) to scanningCells set
   cell_done      ↳ remove from scanningCells, patch session.cells[h][s] with ocr_count/method/confidence
   cell_error     ↳ remove from scanningCells, append to cell.errors
   scan_progress  ↳ update scanProgress {done, total, etaMs}
   scan_complete  ↳ clear scanProgress after 5s (toast-style)
   scan_cancelled ↳ clear scanProgress immediately, show "Cancelado · 3/10"
```

### Task 24: WS client (`frontend/src/lib/ws.js`)

**Files:**
- Create: `frontend/src/lib/ws.js`
- Test: `frontend/tests/lib/ws.test.js` (uses `vitest` if configured; else skip and rely on integration smoke)

- [ ] **Step 1: Verify the test runner**

Run: `cd frontend && npm test -- --version` (or `npx vitest --version`)
If vitest is configured, write the test below. If not, mark Step 1 as "no JS test infra; verify behavior in Step 5 manual smoke" and skip Steps 2-3.

- [ ] **Step 2: Write the failing test (if vitest available)**

```javascript
// frontend/tests/lib/ws.test.js
import { describe, expect, it, vi } from "vitest";
import { createWSClient } from "../../src/lib/ws";

class FakeWS {
  constructor(url) { this.url = url; this.handlers = {}; }
  addEventListener(name, fn) { this.handlers[name] = fn; }
  removeEventListener(name) { delete this.handlers[name]; }
  close() { this.handlers.close?.({}); }
  emit(name, data) { this.handlers[name]?.(data); }
}

describe("createWSClient", () => {
  it("dispatches parsed JSON events to onEvent", () => {
    const fakeFactory = (url) => new FakeWS(url);
    const onEvent = vi.fn();
    const client = createWSClient("sess-1", { onEvent, factory: fakeFactory });
    const ws = client._currentSocket;
    ws.emit("open", {});
    ws.emit("message", { data: JSON.stringify({ type: "cell_scanning", hospital: "HPV", sigla: "odi" }) });
    expect(onEvent).toHaveBeenCalledWith({ type: "cell_scanning", hospital: "HPV", sigla: "odi" });
  });

  it("reconnects with backoff after close", async () => {
    vi.useFakeTimers();
    const factory = vi.fn((url) => new FakeWS(url));
    const client = createWSClient("sess-1", { onEvent: () => {}, factory, initialBackoffMs: 100 });
    const ws = client._currentSocket;
    ws.emit("close", {});
    await vi.advanceTimersByTimeAsync(100);
    expect(factory).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
    client.close();
  });

  it("ignores malformed JSON without throwing", () => {
    const onEvent = vi.fn();
    const factory = (url) => new FakeWS(url);
    const client = createWSClient("sess-1", { onEvent, factory });
    const ws = client._currentSocket;
    ws.emit("message", { data: "not json" });
    expect(onEvent).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `ws.js` doesn't exist.

- [ ] **Step 4: Implement `frontend/src/lib/ws.js`**

```javascript
// frontend/src/lib/ws.js
/**
 * WebSocket client with reconnect + JSON event dispatch.
 *
 * createWSClient(sessionId, { onEvent, factory?, initialBackoffMs? }) → client
 *   - onEvent(event): callback for each parsed JSON message
 *   - factory(url): optional WebSocket constructor (for tests)
 *   - client.close(): closes connection and disables reconnect
 *
 * Reconnect: exponential backoff capped at 30s. Connection lifecycle:
 *   open → message → close (auto-reconnect) | manual close (no reconnect)
 */

const WS_BASE = (() => {
  if (typeof window === "undefined") return "ws://127.0.0.1:8000";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  // Vite dev server proxies /api — for /ws we point at the FastAPI port directly
  return `${proto}//127.0.0.1:8000`;
})();

export function createWSClient(sessionId, { onEvent, factory, initialBackoffMs = 1000 } = {}) {
  const url = `${WS_BASE}/ws/sessions/${sessionId}`;
  const makeWS = factory || ((u) => new WebSocket(u));
  let socket = null;
  let backoff = initialBackoffMs;
  let closedByUser = false;
  let reconnectTimer = null;

  function connect() {
    socket = makeWS(url);
    socket.addEventListener("open", () => { backoff = initialBackoffMs; });
    socket.addEventListener("message", (evt) => {
      try {
        const parsed = JSON.parse(evt.data);
        onEvent(parsed);
      } catch {
        // Ignore non-JSON frames (pings as text are fine, malformed payloads dropped silently)
      }
    });
    socket.addEventListener("close", () => {
      if (closedByUser) return;
      reconnectTimer = setTimeout(() => {
        // Re-check inside the callback: client.close() may have been called
        // between the close-event-firing and this timer firing.
        if (closedByUser) return;
        backoff = Math.min(backoff * 2, 30000);
        connect();
      }, backoff);
    });
    socket.addEventListener("error", () => {
      // close handler will fire after error; don't double-schedule
    });
    client._currentSocket = socket;
  }

  const client = {
    close() {
      closedByUser = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
    },
    _currentSocket: null,
  };

  connect();
  return client;
}
```

- [ ] **Step 5: Run tests**

Run: `cd frontend && npm test`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/ws.js frontend/tests/lib/ws.test.js
git commit -m "feat(frontend): WS client with JSON dispatch + exponential reconnect

createWSClient(sessionId, {onEvent}) connects to /ws/sessions/{id} and
calls onEvent for each parsed JSON message. Malformed payloads dropped
silently (pings from server are JSON, not text). Auto-reconnect with
exponential backoff capped at 30s; .close() disables reconnect. Accepts
a factory override for tests.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 25: Extend `api.js` with FASE 2 endpoints

**Files:**
- Modify: `frontend/src/lib/api.js`

- [ ] **Step 1: Modify file**

Append to the `api` object:

```javascript
// frontend/src/lib/api.js — additions
export const api = {
  // ... existing methods ...

  scanOcr: (sessionId, cells) =>
    fetch(`${BASE}/sessions/${sessionId}/scan-ocr`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cells }),
    }).then(jsonOrThrow),

  cancelScan: (sessionId) =>
    fetch(`${BASE}/sessions/${sessionId}/cancel`, {
      method: "POST",
    }).then(jsonOrThrow),

  patchOverride: (sessionId, hospital, sigla, value, note) =>
    fetch(`${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/override`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value, note }),
    }).then(jsonOrThrow),

  getCellFiles: (sessionId, hospital, sigla) =>
    fetch(`${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/files`).then(jsonOrThrow),

  cellPdfUrl: (sessionId, hospital, sigla, index = 0) =>
    `${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/pdf?index=${index}`,
};
```

- [ ] **Step 2: Verify no regressions**

Run: `cd frontend && npm run build`
Expected: build succeeds, 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api.js
git commit -m "feat(frontend): add FASE 2 endpoints to api client

scanOcr, cancelScan, patchOverride, getCellFiles, cellPdfUrl (helper
that returns the PDF streaming URL without fetching — used as iframe
src). All point at the same BASE as pase 1 endpoints.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 26: Extend the Zustand store with WS state and actions

**Files:**
- Modify: `frontend/src/store/session.js`

- [ ] **Step 1: Replace the store with the extended version**

```javascript
// frontend/src/store/session.js
import { create } from "zustand";
import { api } from "../lib/api";
import { createWSClient } from "../lib/ws";

export const useSessionStore = create((set, get) => ({
  view: "month",
  hospital: null,
  months: [],
  session: null,
  loading: false,
  error: null,

  // FASE 2 additions
  scanningCells: new Set(),            // "HPV|odi" strings, mirrored in CategoryRow
  scanProgress: null,                  // {done, total, etaMs, terminal?} | null
  lightbox: null,                      // {hospital, sigla, fileIndex} | null
  _ws: null,

  setView: (view) => set({ view }),

  loadMonths: async () => {
    set({ loading: true, error: null });
    try {
      const { months } = await api.listMonths();
      set({ months, loading: false });
    } catch (error) {
      set({ error: String(error), loading: false });
    }
  },

  openMonth: async (sessionId, year, month) => {
    set({ loading: true, error: null });
    try {
      await api.createSession(year, month);
      const session = await api.getSession(sessionId);
      // Tear down any prior WS and reconnect for the new session
      get()._ws?.close();
      const ws = createWSClient(sessionId, { onEvent: get()._handleWSEvent });
      set({ session, loading: false, _ws: ws, scanningCells: new Set(), scanProgress: null });
    } catch (error) {
      set({ error: String(error), loading: false });
    }
  },

  selectHospital: (hospital) => set({ view: "hospital", hospital }),

  runScan: async (sessionId) => {
    set({ loading: true, error: null });
    try {
      await api.scanSession(sessionId);
      const session = await api.getSession(sessionId);
      set({ session, loading: false });
    } catch (error) {
      set({ error: String(error), loading: false });
    }
  },

  scanOcr: async (sessionId, cellPairs) => {
    try {
      await api.scanOcr(sessionId, cellPairs);
      set({ scanProgress: { done: 0, total: cellPairs.length } });
    } catch (error) {
      set({ error: String(error) });
    }
  },

  cancelScan: async (sessionId) => {
    try { await api.cancelScan(sessionId); }
    catch (error) { set({ error: String(error) }); }
  },

  saveOverride: async (sessionId, hospital, sigla, value, note) => {
    try {
      const result = await api.patchOverride(sessionId, hospital, sigla, value, note);
      // Patch the local session state in place
      const { session } = get();
      if (!session) return;
      const cells = { ...session.cells };
      const hosp = { ...cells[hospital] };
      hosp[sigla] = { ...hosp[sigla], user_override: result.user_override, override_note: result.override_note };
      cells[hospital] = hosp;
      set({ session: { ...session, cells } });
    } catch (error) { set({ error: String(error) }); }
  },

  openLightbox: (hospital, sigla, fileIndex = 0) => set({ lightbox: { hospital, sigla, fileIndex } }),
  closeLightbox: () => set({ lightbox: null }),

  generateOutput: async (sessionId) => {
    set({ loading: true, error: null });
    try {
      const result = await api.generateOutput(sessionId);
      set({ loading: false });
      return result;
    } catch (error) {
      set({ error: String(error), loading: false });
      throw error;
    }
  },

  // ---------- WS event handler ----------
  _handleWSEvent: (event) => {
    const state = get();
    const cellKey = (h, s) => `${h}|${s}`;

    switch (event.type) {
      case "cell_scanning": {
        const next = new Set(state.scanningCells);
        next.add(cellKey(event.hospital, event.sigla));
        set({ scanningCells: next });
        break;
      }
      case "cell_done": {
        const next = new Set(state.scanningCells);
        next.delete(cellKey(event.hospital, event.sigla));
        const session = state.session;
        if (session) {
          const cells = { ...session.cells };
          const hosp = { ...cells[event.hospital] };
          hosp[event.sigla] = {
            ...hosp[event.sigla],
            ocr_count: event.result.ocr_count,
            method: event.result.method,
            confidence: event.result.confidence,
            duration_ms_ocr: event.result.duration_ms_ocr,
          };
          cells[event.hospital] = hosp;
          set({ scanningCells: next, session: { ...session, cells } });
        } else {
          set({ scanningCells: next });
        }
        break;
      }
      case "cell_error": {
        const next = new Set(state.scanningCells);
        next.delete(cellKey(event.hospital, event.sigla));
        const session = state.session;
        if (session) {
          const cells = { ...session.cells };
          const hosp = { ...cells[event.hospital] };
          const prev = hosp[event.sigla] || {};
          hosp[event.sigla] = { ...prev, errors: [...(prev.errors || []), event.error] };
          cells[event.hospital] = hosp;
          set({ scanningCells: next, session: { ...session, cells } });
        } else {
          set({ scanningCells: next });
        }
        break;
      }
      case "scan_progress":
        set({ scanProgress: { done: event.done, total: event.total, etaMs: event.eta_ms } });
        break;
      case "scan_complete":
        set({ scanProgress: { ...state.scanProgress, terminal: "complete", done: event.scanned, total: event.scanned + (event.errors || 0) } });
        // Auto-dismiss after 5s
        setTimeout(() => set((s) => (s.scanProgress?.terminal === "complete" ? { scanProgress: null } : s)), 5000);
        break;
      case "scan_cancelled":
        set({ scanProgress: { ...state.scanProgress, terminal: "cancelled", done: event.scanned, total: event.total } });
        setTimeout(() => set((s) => (s.scanProgress?.terminal === "cancelled" ? { scanProgress: null } : s)), 5000);
        break;
      case "ping":
        break;     // keepalive — no-op
      default:
        // Unknown event types ignored
    }
  },
}));
```

- [ ] **Step 2: Verify the store builds**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/store/session.js
git commit -m "feat(frontend/store): extend with WS state, OCR actions, lightbox

Adds scanningCells (Set<\"hospital|sigla\">), scanProgress
({done,total,etaMs,terminal}), lightbox ({hospital,sigla,fileIndex}),
plus actions scanOcr/cancelScan/saveOverride/openLightbox/closeLightbox
and a private _handleWSEvent that mutates store state in response to
each backend event type. openMonth now constructs a WS client and tears
down any prior one. cell_done patches the local session.cells[h][s]
with ocr_count/method/confidence so React re-renders instantly.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 27: OverridePanel + FileList + ScanControls + ScanProgress components

Four small leaf components. Group them in one task to keep the chunk size reasonable.

**Files:**
- Create: `frontend/src/components/OverridePanel.jsx`
- Create: `frontend/src/components/FileList.jsx`
- Create: `frontend/src/components/ScanControls.jsx`
- Create: `frontend/src/components/ScanProgress.jsx`

- [ ] **Step 1: OverridePanel.jsx**

```jsx
import { useEffect, useState } from "react";
import { useSessionStore } from "../store/session";

export default function OverridePanel({ hospital, sigla, cell }) {
  const { session, saveOverride } = useSessionStore();
  const [value, setValue] = useState(cell?.user_override ?? "");
  const [note, setNote] = useState(cell?.override_note ?? "");

  // Reset local state when the selected cell changes
  useEffect(() => {
    setValue(cell?.user_override ?? "");
    setNote(cell?.override_note ?? "");
  }, [hospital, sigla, cell?.user_override, cell?.override_note]);

  const persist = () => {
    if (!session) return;
    const v = value === "" ? null : Number.parseInt(value, 10);
    if (v !== null && (Number.isNaN(v) || v < 0)) return;
    saveOverride(session.session_id, hospital, sigla, v, note || null);
  };

  return (
    <div className="space-y-2 text-sm">
      <label className="block">
        <span className="text-slate-400">Override:</span>
        <input
          type="number"
          min={0}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onBlur={persist}
          className="ml-2 w-24 bg-slate-800 border border-slate-700 rounded px-2 py-1"
        />
      </label>
      <label className="block">
        <span className="text-slate-400">Nota:</span>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onBlur={persist}
          rows={3}
          className="mt-1 w-full bg-slate-800 border border-slate-700 rounded px-2 py-1"
        />
      </label>
    </div>
  );
}
```

- [ ] **Step 2: FileList.jsx**

```jsx
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useSessionStore } from "../store/session";

export default function FileList({ hospital, sigla }) {
  const { session, openLightbox } = useSessionStore();
  const [files, setFiles] = useState(null);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!session || !hospital || !sigla) { setFiles(null); return; }
    setError(null);
    let cancelled = false;        // ignore stale responses when the user
                                  // rapidly clicks between cells
    api.getCellFiles(session.session_id, hospital, sigla)
      .then((data) => { if (!cancelled) setFiles(data); })
      .catch((e) => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; };
  }, [session?.session_id, hospital, sigla]);

  if (!hospital || !sigla) return <p className="text-slate-500 text-sm">Selecciona una categoría</p>;
  if (error) return <p className="text-red-400 text-sm">{error}</p>;
  if (!files) return <p className="text-slate-500 text-sm">Cargando…</p>;
  if (files.length === 0) return <p className="text-slate-500 text-sm">Sin PDFs</p>;

  const filtered = query
    ? files.filter((f) => f.name.toLowerCase().includes(query.toLowerCase()))
    : files;

  return (
    <div className="space-y-2">
      <input
        type="search"
        placeholder="buscar…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1 text-sm"
      />
      <ul className="space-y-0.5 max-h-[60vh] overflow-y-auto">
        {filtered.map((f, i) => {
          const actualIndex = files.indexOf(f);
          return (
            <li key={f.name}>
              <button
                onClick={() => openLightbox(hospital, sigla, actualIndex)}
                className="w-full text-left text-xs px-2 py-1 rounded hover:bg-slate-800 font-mono"
              >
                {f.subfolder && <span className="text-slate-500">{f.subfolder}/</span>}
                {f.name}
                <span className="ml-2 text-slate-500">· {f.page_count}pp</span>
                {f.suspect && <span className="ml-1 text-amber-400">⚠</span>}
              </button>
            </li>
          );
        })}
      </ul>
      <p className="text-xs text-slate-500">{filtered.length} de {files.length}</p>
    </div>
  );
}
```

- [ ] **Step 3: ScanControls.jsx**

```jsx
import { useSessionStore } from "../store/session";

export default function ScanControls({ hospital, selectedSiglas }) {
  const { session, scanOcr, scanningCells } = useSessionStore();
  const busy = scanningCells.size > 0;

  const onSelected = () => {
    if (!session || selectedSiglas.length === 0) return;
    const pairs = selectedSiglas.map((s) => [hospital, s]);
    scanOcr(session.session_id, pairs);
  };

  const onSuspects = () => {
    if (!session) return;
    const cells = session.cells?.[hospital] || {};
    const suspectSiglas = Object.entries(cells)
      .filter(([_, c]) => (c.flags || []).includes("compilation_suspect"))
      .map(([s]) => s);
    if (suspectSiglas.length === 0) return;
    scanOcr(session.session_id, suspectSiglas.map((s) => [hospital, s]));
  };

  return (
    <div className="flex items-center gap-2 text-sm">
      <button
        onClick={onSelected}
        disabled={busy || selectedSiglas.length === 0}
        className="px-3 py-1 rounded bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-500"
      >
        OCR {selectedSiglas.length} seleccionadas
      </button>
      <button
        onClick={onSuspects}
        disabled={busy}
        className="px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-50"
      >
        OCR suspects de {hospital}
      </button>
    </div>
  );
}
```

- [ ] **Step 4: ScanProgress.jsx**

```jsx
import { useSessionStore } from "../store/session";

export default function ScanProgress() {
  const { session, scanProgress, cancelScan } = useSessionStore();
  if (!scanProgress) return null;
  const { done, total, terminal } = scanProgress;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;

  let label = `Escaneando · ${done}/${total}`;
  let color = "bg-blue-600";
  if (terminal === "complete") { label = `Completado · ${done}/${total}`; color = "bg-emerald-600"; }
  if (terminal === "cancelled") { label = `Cancelado · ${done}/${total}`; color = "bg-amber-600"; }

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-slate-900 border-t border-slate-700 px-4 py-2 flex items-center gap-4 text-sm z-40">
      <span className="font-medium">{label}</span>
      <div className="flex-1 h-2 bg-slate-800 rounded overflow-hidden">
        <div className={`h-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      {!terminal && session && (
        <button
          onClick={() => cancelScan(session.session_id)}
          className="px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 text-xs"
        >
          Cancel
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Verify the build**

Run: `cd frontend && npm run build`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/OverridePanel.jsx frontend/src/components/FileList.jsx frontend/src/components/ScanControls.jsx frontend/src/components/ScanProgress.jsx
git commit -m "feat(frontend): OverridePanel + FileList + ScanControls + ScanProgress

OverridePanel: number input + textarea, autosaves on blur via
saveOverride. FileList: fetches /cells/{h}/{s}/files on selection,
search filter, click opens lightbox via openLightbox. ScanControls:
two buttons (OCR selected, OCR suspects) wired to scanOcr action.
ScanProgress: fixed-bottom progress bar that auto-dismisses 5s after
terminal event; cancel button calls cancelScan.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 28: PDFLightbox.jsx — floating modal with iframe + override

**Files:**
- Create: `frontend/src/components/PDFLightbox.jsx`

- [ ] **Step 1: Implement**

```jsx
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useSessionStore } from "../store/session";
import OverridePanel from "./OverridePanel";

export default function PDFLightbox() {
  const { session, lightbox, closeLightbox } = useSessionStore();
  const [files, setFiles] = useState(null);

  useEffect(() => {
    if (!lightbox || !session) { setFiles(null); return; }
    let cancelled = false;        // ignore stale responses if lightbox swaps cells
    api.getCellFiles(session.session_id, lightbox.hospital, lightbox.sigla)
      .then((data) => { if (!cancelled) setFiles(data); })
      .catch(() => { if (!cancelled) setFiles([]); });
    return () => { cancelled = true; };
  }, [lightbox, session?.session_id]);

  useEffect(() => {
    if (!lightbox) return;
    const onKey = (e) => { if (e.key === "Escape") closeLightbox(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lightbox, closeLightbox]);

  if (!lightbox || !session) return null;

  const { hospital, sigla, fileIndex } = lightbox;
  const cell = session.cells?.[hospital]?.[sigla] || {};
  const file = files?.[fileIndex];
  const pdfUrl = file
    ? api.cellPdfUrl(session.session_id, hospital, sigla, fileIndex)
    : null;

  return (
    <div
      onClick={closeLightbox}
      className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-8"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-slate-900 border border-slate-700 rounded-lg w-full max-w-7xl h-full max-h-[90vh] flex flex-col overflow-hidden"
      >
        <header className="flex items-center justify-between px-4 py-2 border-b border-slate-700 text-sm">
          <span className="font-mono">
            {hospital} / {sigla}
            {file && <span className="ml-2 text-slate-400">· {file.name}</span>}
          </span>
          <button onClick={closeLightbox} className="text-slate-400 hover:text-slate-200">✕</button>
        </header>
        <div className="flex-1 flex overflow-hidden">
          <div className="flex-1 bg-slate-950 overflow-hidden">
            {pdfUrl ? (
              <iframe src={pdfUrl} className="w-full h-full" title="PDF preview" />
            ) : (
              <div className="h-full flex items-center justify-center text-slate-500">
                {files === null ? "Cargando…" : "Sin PDF"}
              </div>
            )}
          </div>
          <aside className="w-80 border-l border-slate-700 p-4 overflow-y-auto">
            <h3 className="text-sm uppercase text-slate-400 mb-2">Counts</h3>
            <div className="space-y-1 text-sm mb-4">
              <p>Filename: <span className="font-mono">{cell.filename_count ?? "—"}</span></p>
              <p>OCR: <span className="font-mono">{cell.ocr_count ?? "—"}</span></p>
              {cell.method && <p className="text-xs text-slate-500">via {cell.method}</p>}
            </div>
            <OverridePanel hospital={hospital} sigla={sigla} cell={cell} />
          </aside>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify the build**

Run: `cd frontend && npm run build`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/PDFLightbox.jsx
git commit -m "feat(frontend): PDFLightbox floating modal with iframe + OverridePanel

Renders nothing when lightbox state is null; otherwise overlay with
backdrop (click outside closes), iframe at /cells/{h}/{s}/pdf?index=N,
and right-side panel with filename_count + ocr_count + method +
OverridePanel reused from the detail panel. Esc + X both close. The
backdrop's onClick fires closeLightbox; the inner box stops
propagation so clicks inside don't dismiss.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 29: Modify CategoryRow + HospitalDetail + App

**Files:**
- Modify: `frontend/src/components/CategoryRow.jsx`
- Modify: `frontend/src/views/HospitalDetail.jsx`
- Modify: `frontend/src/App.jsx` (mount PDFLightbox + ScanProgress)

- [ ] **Step 1: Extend CategoryRow.jsx**

```jsx
import { useSessionStore } from "../store/session";

export default function CategoryRow({ sigla, cell, selected, onClick, hospital, checked, onCheckChange }) {
  const { scanningCells } = useSessionStore();
  const isScanning = scanningCells.has(`${hospital}|${sigla}`);
  const count = cell?.user_override ?? cell?.ocr_count ?? cell?.filename_count ?? cell?.count ?? 0;
  const conf = cell?.confidence || "—";
  const hasErrors = (cell?.errors || []).length > 0;
  const isSuspect = (cell?.flags || []).includes("compilation_suspect");

  return (
    <div
      onClick={onClick}
      className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer text-sm ${selected ? "bg-slate-800" : "hover:bg-slate-800/50"}`}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => { e.stopPropagation(); onCheckChange(e.target.checked); }}
        onClick={(e) => e.stopPropagation()}
      />
      <span className="flex-1 font-mono">{sigla}</span>
      <span className="text-xs text-slate-400 uppercase">{conf}</span>
      <span className="font-mono w-12 text-right">{count}</span>
      {isScanning && <span className="text-blue-400 animate-pulse">⟳</span>}
      {hasErrors && <span className="text-red-400">✕</span>}
      {isSuspect && !isScanning && <span className="text-amber-400">⚠</span>}
    </div>
  );
}
```

- [ ] **Step 2: Replace HospitalDetail.jsx with 3-column layout**

```jsx
import { useState } from "react";
import { useSessionStore } from "../store/session";
import CategoryRow from "../components/CategoryRow";
import FileList from "../components/FileList";
import OverridePanel from "../components/OverridePanel";
import ScanControls from "../components/ScanControls";

const SIGLAS = [
  "reunion", "irl", "odi", "charla", "chintegral", "dif_pts", "art",
  "insgral", "bodega", "maquinaria", "ext", "senal", "exc",
  "altura", "caliente", "herramientas_elec", "andamios", "chps",
];

export default function HospitalDetail({ hospital, onBack }) {
  const { session } = useSessionStore();
  const [selected, setSelected] = useState(null);
  const [selectedSet, setSelectedSet] = useState(new Set());

  const cells = session?.cells?.[hospital] || {};
  const total = Object.values(cells).reduce(
    (s, c) => s + (c.user_override ?? c.ocr_count ?? c.filename_count ?? c.count ?? 0), 0,
  );
  const selectedCell = selected ? cells[selected] : null;

  const onCheck = (sigla, checked) => {
    setSelectedSet((prev) => {
      const next = new Set(prev);
      if (checked) next.add(sigla); else next.delete(sigla);
      return next;
    });
  };

  return (
    <div>
      <header className="flex items-center gap-4 mb-6">
        <button onClick={onBack} className="text-sm text-slate-400 hover:text-slate-200">← Volver</button>
        <h2 className="text-xl font-semibold">{hospital}</h2>
        <span className="text-sm text-slate-400">Total: {total}</span>
        <div className="ml-auto"><ScanControls hospital={hospital} selectedSiglas={[...selectedSet]} /></div>
      </header>

      <div className="grid gap-6 grid-cols-1 xl:grid-cols-[1fr_1fr_1fr]">
        <section>
          <h3 className="text-sm uppercase text-slate-400 mb-2">Categorías</h3>
          <div className="space-y-0.5">
            {SIGLAS.map((s) => (
              <CategoryRow
                key={s}
                sigla={s}
                cell={cells[s]}
                hospital={hospital}
                selected={selected === s}
                onClick={() => setSelected(s)}
                checked={selectedSet.has(s)}
                onCheckChange={(c) => onCheck(s, c)}
              />
            ))}
          </div>
        </section>

        <section>
          <h3 className="text-sm uppercase text-slate-400 mb-2">Detalle</h3>
          {!selectedCell && <p className="text-slate-500">Selecciona una categoría</p>}
          {selectedCell && (
            <div className="space-y-3 text-sm">
              <p><span className="text-slate-400">Sigla:</span> {selected}</p>
              <p><span className="text-slate-400">Filename:</span> {selectedCell.filename_count ?? selectedCell.count ?? "—"}</p>
              <p><span className="text-slate-400">OCR:</span> {selectedCell.ocr_count ?? "—"} {selectedCell.method && <span className="text-xs text-slate-500">via {selectedCell.method}</span>}</p>
              <p><span className="text-slate-400">Confidence:</span> {selectedCell.confidence}</p>
              {(selectedCell.flags || []).length > 0 && (
                <p><span className="text-slate-400">Flags:</span> {selectedCell.flags.join(", ")}</p>
              )}
              <OverridePanel hospital={hospital} sigla={selected} cell={selectedCell} />
            </div>
          )}
        </section>

        <section>
          <h3 className="text-sm uppercase text-slate-400 mb-2">Archivos</h3>
          <FileList hospital={hospital} sigla={selected} />
        </section>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Mount ScanProgress + PDFLightbox in `App.jsx`**

Add to the existing App component (single place — wrap the routed content or append at root):

```jsx
// frontend/src/App.jsx — additions
import PDFLightbox from "./components/PDFLightbox";
import ScanProgress from "./components/ScanProgress";

export default function App() {
  // ... existing return statement ...
  return (
    <>
      {/* existing layout */}
      <PDFLightbox />
      <ScanProgress />
    </>
  );
}
```

(Adapt to the actual structure of the existing `App.jsx` — these two components render `null` when their store state is empty, so they're safe to always mount.)

- [ ] **Step 4: Verify the full build**

Run: `cd frontend && npm run build`
Expected: 0 errors. Bundle size delta should be small (single iframe, no PDF.js).

- [ ] **Step 5: Manual smoke**

```bash
# Terminal 1 — backend
python server.py
# Terminal 2 — frontend dev
cd frontend && npm run dev
```

Open `http://localhost:5173`, navigate to ABRIL → HPV. Verify:
1. Click `odi` → detail panel shows filename/OCR/confidence sections.
2. Check 1-2 categories → "OCR N seleccionadas" enabled.
3. Click OCR button → spinner appears next to row, progress bar at bottom advances.
4. Click a file in the right column → lightbox opens with PDF iframe.
5. Type a number in the override field, blur → field persists.
6. Esc / X / backdrop click → lightbox closes.
7. Cancel mid-batch → progress shows "Cancelado · K/N", auto-dismisses after 5s.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/CategoryRow.jsx frontend/src/views/HospitalDetail.jsx frontend/src/App.jsx
git commit -m "feat(frontend): 3-column HospitalDetail + WS-driven CategoryRow status

CategoryRow now reads scanningCells from the store to render a ⟳
spinner while a cell is scanning, ✕ on errors, ⚠ on compilation_suspect.
Adds a checkbox + onCheckChange callback for multi-select. HospitalDetail
moves to a 3-column grid on xl screens (categorías | detalle | archivos),
single-column on narrow. Detail panel now renders filename / OCR /
override-section via the new OverridePanel. App.jsx mounts the global
PDFLightbox + ScanProgress components (both render null when idle).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 30: Chunk 5 sanity

- [ ] **Step 1: Build clean**

Run: `cd frontend && npm run build`
Expected: 0 errors, 0 warnings other than the usual bundle-size note.

- [ ] **Step 2: Backend integration still works**

Run from project root: `python -c "from api.main import create_app; create_app()"`
Expected: no exceptions.

- [ ] **Step 3: Lint Python (any backend changes from misclicks)**

Run: `ruff check .`
Expected: 0 violations.

- [ ] **Step 4: Git log**

Run: `git log --oneline -10`
Expected: ~6 Chunk-5 commits (ws client, api extension, store, 4 small components, lightbox, layout) on top of Chunks 1-4.

---

## Chunk 6: historical_counts UPSERT + DoD verification + tag `fase-2-mvp`

**Goal:** Wire the historical_counts write at the end of `/output`, verify the full DoD checklist passes, commit a curated postmortem doc, and tag the release.

### Task 31: `_method_for_history` helper + UPSERT after Excel generation

**Files:**
- Modify: `api/routes/output.py` (UPSERT after `generate_resumen`)
- Test: `tests/unit/api/test_output_history.py`

The Excel writer already exists and works; we hook the historical write on the success path only. If the Excel generation throws, no rows are written — the next regeneration will overwrite anyway.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/api/test_output_history.py
"""POST /output writes historical_counts after successful Excel generation."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from core.db.connection import open_connection
from core.db.historical_repo import get_counts_for_month


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "history.db"))
    monkeypatch.setenv("OVERSEER_OUTPUT_DIR", str(tmp_path / "out"))
    # Minimal corpus: 1 cell in HPV/odi to write to history.
    odi = tmp_path / "ABRIL" / "HPV" / "3.-ODI Visitas"
    odi.mkdir(parents=True)
    (odi / "2026-04-10_odi_TITAN.pdf").write_bytes(_one_page_pdf())
    app = create_app()
    with TestClient(app) as c:
        yield c, tmp_path / "history.db"


def _one_page_pdf() -> bytes:
    import fitz
    doc = fitz.open(); doc.new_page(width=595, height=842)
    buf = doc.tobytes(); doc.close()
    return buf


def test_output_writes_history_with_filename_glob_method(client) -> None:
    test_client, db_path = client
    r = test_client.post("/api/sessions", json={"year": 2026, "month": 4})
    sid = r.json()["session_id"]
    test_client.post(f"/api/sessions/{sid}/scan")
    test_client.post(f"/api/sessions/{sid}/output")

    conn = open_connection(db_path)
    rows = get_counts_for_month(conn, year=2026, month=4)
    assert any(r.hospital == "HPV" and r.sigla == "odi" for r in rows)
    odi_row = next(r for r in rows if r.hospital == "HPV" and r.sigla == "odi")
    assert odi_row.count == 1
    assert odi_row.method == "filename_glob"


def test_output_history_method_reflects_override(client) -> None:
    test_client, db_path = client
    r = test_client.post("/api/sessions", json={"year": 2026, "month": 4})
    sid = r.json()["session_id"]
    test_client.post(f"/api/sessions/{sid}/scan")
    test_client.patch(
        f"/api/sessions/{sid}/cells/HPV/odi/override",
        json={"value": 17, "note": "compilation"},
    )
    test_client.post(f"/api/sessions/{sid}/output")

    conn = open_connection(db_path)
    odi_row = next(
        r for r in get_counts_for_month(conn, year=2026, month=4)
        if r.hospital == "HPV" and r.sigla == "odi"
    )
    assert odi_row.count == 17
    assert odi_row.method == "override"


def test_output_history_method_reflects_ocr_when_present(client) -> None:
    """When ocr_count is the winner over filename_count, method should reflect
    the technique that produced ocr_count, not 'filename_glob'."""
    test_client, db_path = client
    r = test_client.post("/api/sessions", json={"year": 2026, "month": 4})
    sid = r.json()["session_id"]
    test_client.post(f"/api/sessions/{sid}/scan")

    # Simulate an OCR result by hitting the same setter the orchestrator uses.
    # Reach the SessionManager that lifespan registered into the app under test
    # — Chunk 1 Task 4 amends `create_app` to expose it as `app.state.manager`
    # for exactly this use case (test-only access; production code still goes
    # through Depends(get_manager)).
    from core.scanners.base import ConfidenceLevel, ScanResult
    mgr = test_client.app.state.manager
    mgr.apply_ocr_result(
        sid, "HPV", "odi",
        ScanResult(
            count=17, confidence=ConfidenceLevel.HIGH, method="header_detect",
            breakdown=None, flags=[], errors=[],
            duration_ms=100, files_scanned=1,
        ),
    )

    test_client.post(f"/api/sessions/{sid}/output")

    conn = open_connection(db_path)
    odi_row = next(
        r for r in get_counts_for_month(conn, year=2026, month=4)
        if r.hospital == "HPV" and r.sigla == "odi"
    )
    assert odi_row.count == 17
    assert odi_row.method == "header_detect"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/api/test_output_history.py -v`
Expected: FAIL on all three — current `/output` doesn't write history yet.

- [ ] **Step 3: Implement**

Modify `api/routes/output.py`:

```python
# api/routes/output.py — additions

from core.db.historical_repo import upsert_count  # noqa: E402


def _method_for_history(cell: dict) -> str:
    """Derive the historical_counts.method value from a cell's state.

    Priority cascade (matches Excel writer in Chunk 1):
      user_override -> 'override'
      ocr_count     -> cell['method'] (header_detect / corner_count / page_count_pure / filename_glob)
      filename_count -> 'filename_glob'
      legacy count  -> 'filename_glob'
      none          -> 'filename_glob' (default for un-scanned)
    """
    if cell.get("user_override") is not None:
        return "override"
    if cell.get("ocr_count") is not None:
        return cell.get("method") or "filename_glob"
    return "filename_glob"
```

Update the `generate` route — after `result = generate_resumen(...)`, before the return:

```python
    # Persist to historical_counts (UPSERT). Idempotent — regenerating the
    # same month overwrites with the same values. Excluded cells (FASE 1
    # carryover) are NOT written.
    year, month = int(session_id[:4]), int(session_id[5:7])
    for hospital, hosp_cells in state.get("cells", {}).items():
        for sigla, cell in hosp_cells.items():
            if cell.get("excluded"):
                continue
            effective_count = (
                cell.get("user_override")
                if cell.get("user_override") is not None
                else cell.get("ocr_count")
                if cell.get("ocr_count") is not None
                else cell.get("filename_count")
                if cell.get("filename_count") is not None
                else cell.get("count", 0)
            )
            upsert_count(
                mgr._conn,
                year=year,
                month=month,
                hospital=hospital,
                sigla=sigla,
                count=int(effective_count or 0),
                confidence=cell.get("confidence", "high"),
                method=_method_for_history(cell),
            )
    mgr._conn.commit()
```

> **Note on `mgr._conn`:** SessionManager exposes its connection as a private
> attribute, but the alternative is plumbing the connection through every
> route as a separate dependency. For this single use site, accessing the
> attribute is the cleanest option. If/when historical writes happen in more
> places, refactor to a `historical_repo` dependency in Chunk N+1.

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/api/test_output_history.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add api/routes/output.py tests/unit/api/test_output_history.py
git commit -m "feat(api): UPSERT historical_counts after Excel generation

Adds _method_for_history(cell) which derives the historical method
value from the priority cascade (user_override -> 'override' / ocr_count
-> cell.method / filename_count -> 'filename_glob'). After
generate_resumen succeeds, iterates state.cells and UPSERTs one row per
non-excluded cell. Idempotent — regenerating the same month overwrites
with the same values; method='override' marks human intervention for
audit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 32: DoD verification — run the full test suite + ABRIL smoke

This is a manual checklist task — no new code, just confidence-building before tagging.

- [ ] **Step 1: Full backend test suite**

Run: `pytest -v --tb=short`
Expected: all unit + integration tests pass. Tally per module:

| Module | Expected count |
|---|---|
| tests/unit/db/ | unchanged from FASE 1 |
| tests/unit/scanners/ | ~26 (17 fast + 9 slow) — see Task 17 §3 |
| tests/unit/api/ | new: ws (2) + scan-ocr (5) + cells (8) + output history (3) |
| tests/unit/test_orchestrator_ocr.py | 4 |
| tests/integration/test_abril_full.py | unchanged from FASE 1 |
| tests/integration/test_scan_ocr_full.py | 1 slow |

- [ ] **Step 2: Ruff clean**

Run: `ruff check .`
Expected: 0 violations.

- [ ] **Step 3: Frontend build clean**

Run: `cd frontend && npm run build`
Expected: 0 errors.

- [ ] **Step 4: ABRIL end-to-end smoke**

```bash
# Backend
python server.py &
SERVER_PID=$!
sleep 2

# Run the full ABRIL flow
SID=$(curl -s -X POST http://localhost:8000/api/sessions \
  -H 'content-type: application/json' -d '{"year": 2026, "month": 4}' \
  | python -c 'import sys,json; print(json.load(sys.stdin)["session_id"])')

# Pase 1
curl -s -X POST "http://localhost:8000/api/sessions/$SID/scan" >/dev/null

# Pase 2: OCR the known compilation cell HRB/odi
curl -s -X POST "http://localhost:8000/api/sessions/$SID/scan-ocr" \
  -H 'content-type: application/json' -d '{"cells": [["HRB", "odi"]]}' >/dev/null

# Wait for WS events to settle (in real use the frontend would show this live)
sleep 30

# Override one cell
curl -s -X PATCH "http://localhost:8000/api/sessions/$SID/cells/HPV/charla/override" \
  -H 'content-type: application/json' -d '{"value": 250, "note": "audit override"}' >/dev/null

# Generate Excel
curl -s -X POST "http://localhost:8000/api/sessions/$SID/output" | python -m json.tool

kill $SERVER_PID
```

Expected:
- Excel file in `OVERSEER_OUTPUT_DIR` (default `data/output_sample/`) named `RESUMEN_2026-04.xlsx`.
- Open it: the HRB/odi cell should hold the OCR count (≥17), HPV/charla should hold 250.
- `sqlite3 data/sessions.db 'SELECT count, method FROM historical_counts WHERE year=2026 AND month=4'` shows 54 rows — HRB/odi with `method='header_detect'` (or whatever the OCR picked), HPV/charla with `method='override'`, rest with `method='filename_glob'`.

- [ ] **Step 5: Frontend UI walkthrough**

Start the dev server and walk through the spec §6 user flows:

```bash
cd frontend && npm run dev   # Vite at :5173
```

1. Open ABRIL → 4 hospital tiles.
2. Click HPV → 3-column layout: categories | detail | files.
3. Check `odi` and `charla` → "OCR 2 seleccionadas" button enabled.
4. Click → progress bar appears at bottom; rows show `⟳`.
5. After completion, click a row → detail panel shows filename + OCR counts.
6. Click a file → lightbox opens, PDF visible in iframe.
7. Type override → blur → field persists.
8. Esc → lightbox closes.
9. Generar Resumen → Excel downloads, success toast.

If any flow breaks, fix before tagging.

- [ ] **Step 6: Document known limitations**

Append to `docs/superpowers/plans/2026-05-12-pdfoverseer-fase-2.md` (this file):

```markdown
## Known limitations (deferred to FASE 3)

- **Page-level cancellation latency.** In the multi-worker path, a single
  PDF mid-render can take up to ~30s to abandon (no per-page
  `cancel.check()`). Spec §3.5 targets `<3s`; the documented gap is
  acceptable because Daniel's typical cancel-action follows a user error
  (selected wrong cell), and 30s is tolerable. Fix: thread `cancel`
  through `header_detect` and `corner_count` page loops.
- **`cell_scanning` event ordering in multi-worker mode.** Fires
  alongside `cell_done` (work has already completed by the time
  `as_completed` yields). Frontend renders both immediately; visually OK
  but conceptually a stretch.
- **Single WS client per browser tab.** Reconnect works, but if Daniel
  opens two tabs against the same session, both receive every event
  (intentional broadcast). Not a problem in practice.
- **No retry on OCR failure.** A cell that errors stays in error state
  until manually re-scanned. FASE 3 may add auto-retry with backoff.
- **No cancellation of an Excel-in-progress.** `/output` is synchronous;
  there's no cancel endpoint for it. Generation is fast (<5s for ABRIL)
  so unlikely to matter.
```

- [ ] **Step 7: Commit known-limitations + tag the release**

```bash
git add docs/superpowers/plans/2026-05-12-pdfoverseer-fase-2.md
git commit -m "docs(fase-2): document known limitations deferred to FASE 3

Captures the page-level cancellation latency, multi-worker event
ordering quirk, and other items that are known and accepted for the
FASE 2 MVP. Each entry includes the user-visible impact and the
specific code change required to address it.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"

git tag -a fase-2-mvp -m "FASE 2 MVP — OCR scanners + manual correction UI

Highlights:
- 4 specialized scanners (art/odi/irl/charla) with OCR primary +
  filename_glob fallback decision rule
- New OCR utils: pdf_render, page_count_pure, header_detect, corner_count
- Orchestrator pase 2: scan_cells_ocr over ProcessPoolExecutor(2) with
  multiprocessing.Event-based CancellationToken
- WebSocket protocol for real-time per-cell progress
- Frontend: FileList + PDFLightbox + OverridePanel + ScanProgress
- historical_counts UPSERT after Excel generation with method audit"
```

### Task 33: Update CLAUDE.md + memory + close out

**Files:**
- Modify: `CLAUDE.md` (FASE 1 → FASE 2 shipping note)
- Modify: `C:\Users\Daniel\.claude\projects\a--PROJECTS-PDFoverseer\memory\MEMORY.md` (FASE 2 entry)

- [ ] **Step 1: Update `CLAUDE.md`**

Replace the "FASE 1 MVP" section with:

```markdown
## FASE 2 MVP — `po_overhaul` branch (shipped 2026-05-12)

Pase 1 (filename_glob, ~4s on ABRIL) + pase 2 (OCR per cell, opt-in
via UI) + manual override + PDF preview lightbox. Cell state stores
`filename_count`, `ocr_count`, `user_override`, `override_note` as
independent fields; Excel writer applies the priority cascade. The
`/output` endpoint now also UPSERTs `historical_counts` with a `method`
audit (`override` vs OCR technique vs `filename_glob`).

- **Spec:** `docs/superpowers/specs/2026-05-12-fase-2-design.md`
- **Plan:** `docs/superpowers/plans/2026-05-12-pdfoverseer-fase-2.md`
- **Tag:** `fase-2-mvp`
- **Next (FASE 3):** auto-retry on OCR failure, page-level cancellation,
  multi-month overview.
```

- [ ] **Step 2: Update memory index**

```markdown
# C:\Users\Daniel\.claude\projects\a--PROJECTS-PDFoverseer\memory\project_pdfoverseer_purpose.md
# (or wherever the live project state file is)

The product now handles both regimes end-to-end:
  - Regime 1 (filename-trivial, ~90%): filename_glob in pase 1, ~4s ABRIL.
  - Regime 2 (implicit-compilation, ~10%): pase 2 OCR via art/odi/irl/charla
    specialized scanners; manual override + note as backstop.
```

- [ ] **Step 3: Commit (push deferred)**

```bash
git add CLAUDE.md
git commit -m "docs(fase-2): update CLAUDE.md with shipping note + FASE 3 pointers

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 4: STOP — ask Daniel before pushing**

Do NOT run `git push` from this task. Surface the question to Daniel:

> "Plan complete, all 34 tasks done, branch `po_overhaul` ahead of `master` by ~30 commits with tag `fase-2-mvp`. Want me to push the branch + tag to origin?"

If approved, then (and only then) run:

```bash
git push origin po_overhaul
git push origin fase-2-mvp
```

Per CLAUDE.md global guidance: never push to remote without explicit user approval.

### Task 34: Chunk 6 sanity

- [ ] **Step 1: Verify tag exists**

Run: `git tag -l 'fase-2-*'`
Expected: `fase-2-mvp` listed.

- [ ] **Step 2: Final ruff + tests**

Run: `ruff check . && pytest -v`
Expected: 0 violations, all tests pass.

- [ ] **Step 3: Frontend build**

Run: `cd frontend && npm run build`
Expected: 0 errors.

- [ ] **Step 4: Git log review**

Run: `git log --oneline po_overhaul ^master`
Expected: ~30 commits total covering all 6 chunks, each with a single-purpose commit message.

---

## Done. Total tasks: 34 across 6 chunks.
