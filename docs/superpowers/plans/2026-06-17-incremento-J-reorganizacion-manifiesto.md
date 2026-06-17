# Incremento J — Reorganización vía manifiesto al paso 1 · Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the operator mark reorg operations (move file / extract page-range / split-in-place / rotate) that carry document+worker counts across `(hospital, sigla)` cells, correct the month's count in-app via an additive delta, and export a versioned JSON manifest for the paso-1 project to execute physically.

**Architecture:** A new top-level `state["reorg_ops"]` list is the single source of truth. Per-cell `reorg_doc_delta`/`reorg_worker_delta` are recomputed caches (a session-wide `refresh_reorg_deltas`, mirroring the `refresh_all_reliable` pattern), baked additively into `compute_cell_count` / `compute_worker_count` (+ JS mirror) so the corrected count flows to UI/Excel/history with no caller changes. Op CRUD + manifest-export endpoints sit in `api/routes/sessions.py`; pure validation + manifest-building helpers live in a new `api/reorg.py`. Frontend adds a REORGANIZACIÓN panel in `DetailPanel`, a "Reorganizar" menu in `FileList`, and a `mode="reorg"` range-selection mode in `WorkerCountViewer`. Lifecycle is evidence-based (an op's delta is dropped when its source file is gone on re-scan).

**Tech Stack:** Python 3.10+, FastAPI, SQLite (JSON state blob), PyMuPDF (`fitz`); React + Vite, Zustand store, pdf.js (viewer); pytest + vitest.

**Spec:** `docs/superpowers/specs/2026-06-17-incremento-J-reorganizacion-manifiesto-design.md` (read it before starting; this plan implements it verbatim).

**Conventions (non-negotiable):** ruff 0 before each commit; no bare `except`; no `shell=True`; no SQL f-strings; no `print()` in libs (use `logging`); Python 3.10+ types (`X | None`); frontend uses only `po-*` tokens + the 8 shared primitives, never raw `bg-slate-*`, never `/opacity` on `po-*` vars; commit messages `type(scope): message` in English; commit trailer verbatim `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. **No version-tag bump needed** — this incremento does not touch `core/{pipeline,ocr,inference,image}.py` or `vlm/*.py`.

---

## File Structure

**Backend — create:**
- `api/reorg.py` — pure helpers: op-type constants, `validate_op`, `resolve_op_defaults`, `build_manifest`. No I/O, no FastAPI — fully unit-testable.
- `tests/unit/api/test_reorg.py` — unit tests for `api/reorg.py`.
- `tests/unit/api/test_reorg_routes.py` — endpoint tests (TestClient).

**Backend — modify:**
- `core/cell_count.py` — extract `_base_count`; `compute_cell_count` becomes `base + reorg_doc_delta`.
- `api/state.py` — `compute_worker_count += reorg_worker_delta`; new `SessionManager.add_reorg_op` / `delete_reorg_op` / `set_reorg_state`.
- `api/routes/sessions.py` — `refresh_reorg_deltas`; wire it into `POST /scan`; `POST /reorg/ops`, `DELETE /reorg/ops/{op_id}`, `POST /reorg/export` endpoints + Pydantic models.
- `tests/fixtures/cell_count_cases.json` — add `reorg_doc_delta` cases (cross-language parity).
- `tests/unit/api/test_state.py` — `compute_worker_count` delta cases + reorg-op mutator tests (the `manager` fixture lives here).

**Frontend — create:**
- `frontend/src/components/ReorganizacionPanel.jsx` — the per-cell reorg op list + net delta + export button.
- `frontend/src/lib/reorg-range.js` — pure range-validation helper.
- `frontend/src/lib/reorg-range.test.js` — vitest for the helper.
- `frontend/src/components/ReorganizacionPanel.test.jsx` — vitest for the panel.

**Frontend — modify:**
- `frontend/src/lib/cellCount.js` — `_baseCount` + `computeCellCount` additive delta.
- `frontend/src/lib/cellCount.test.js` — delta cases.
- `frontend/src/lib/api.js` — `createReorgOp`, `deleteReorgOp`, `exportManifest`.
- `frontend/src/store/session.js` — `addReorgOp`, `deleteReorgOp`, `exportManifest` actions.
- `frontend/src/components/DetailPanel.jsx` — render `<ReorganizacionPanel>` after the NOTA section.
- `frontend/src/components/FileList.jsx` — "Reorganizar →" menu (whole-file ops).
- `frontend/src/components/WorkerCountViewer.jsx` — `mode="reorg"` range selection + `onCreateOp`.

**Docs — create:**
- `docs/handoff/paso1-manifiesto-reorganizacion.md` — the static contract doc for the paso-1 project.

---

## Chunk 1: Count integration (additive delta layer)

The foundation: pure functions, cross-language parity. Nothing else depends on endpoints yet.

### Task 1: `_base_count` extraction + additive `reorg_doc_delta` (Python)

**Files:**
- Modify: `core/cell_count.py`
- Test: `tests/test_cell_count.py` (create if absent; otherwise append)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cell_count.py
from core.cell_count import compute_cell_count


def test_reorg_doc_delta_is_additive():
    assert compute_cell_count({"per_file": {"a.pdf": 3}}) == 3
    assert compute_cell_count({"per_file": {"a.pdf": 3}, "reorg_doc_delta": 2}) == 5
    assert compute_cell_count({"per_file": {"a.pdf": 3}, "reorg_doc_delta": -1}) == 2


def test_reorg_delta_respects_override_as_base():
    assert compute_cell_count({"user_override": 10, "reorg_doc_delta": 2}) == 12


def test_reorg_delta_applies_to_checks():
    cell = {"worker_marks": {"a.pdf": [{"page": 1, "count": 4}]}, "reorg_doc_delta": 1}
    assert compute_cell_count(cell, count_type="checks", present_files={"a.pdf"}) == 5


def test_no_delta_defaults_to_base():
    assert compute_cell_count({"per_file": {"a.pdf": 2}}) == 2
    assert compute_cell_count({}) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cell_count.py -v`
Expected: PASS for the no-delta cases, FAIL for the delta cases (delta currently ignored → 3≠5).

- [ ] **Step 3: Implement**

Extract the current body of `compute_cell_count` **verbatim** into a private `_base_count`, then make `compute_cell_count` a thin additive wrapper:

```python
def _base_count(
    cell: dict,
    count_type: str = "documents",
    present_files: set[str] | None = None,
) -> int:
    """Base cell count per FASE 4 §6.2 precedence (the pre-Incr-J cascade).

    1. ``user_override`` wins absolutely.
    2. ``count_type == "checks"`` → ``_sum_marks`` filtered by ``present_files``.
    3. ``per_file_overrides`` ∪ ``per_file`` → derived sum.
    4. Fallback: ``ocr_count`` or ``filename_count`` or 0.
    """
    if cell.get("user_override") is not None:
        return cell["user_override"]
    if count_type == "checks":
        return _sum_marks(cell, present_files)
    per_file = cell.get("per_file") or {}
    per_file_overrides = cell.get("per_file_overrides") or {}
    if per_file or per_file_overrides:
        all_files = set(per_file) | set(per_file_overrides)
        return sum(per_file_overrides.get(f, per_file.get(f, 0)) for f in all_files)
    return cell.get("ocr_count") or cell.get("filename_count") or 0


def compute_cell_count(
    cell: dict,
    count_type: str = "documents",
    present_files: set[str] | None = None,
) -> int:
    """Effective cell count = base cascade + the Incr-J reorg delta (additive
    on top of every base path, including ``user_override`` and ``checks``).
    See the module docstring for the single-source-of-truth contract.
    """
    base = _base_count(cell, count_type, present_files)
    return base + (cell.get("reorg_doc_delta") or 0)
```

Keep `compute_cell_count`'s existing docstring `Args:`/`Returns:` content; only the body changes. Do not alter `_sum_marks`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cell_count.py -v` → all PASS.

- [ ] **Step 5: Commit**

```bash
ruff check core/cell_count.py tests/test_cell_count.py
git add core/cell_count.py tests/test_cell_count.py
git commit -m "feat(count): additive reorg_doc_delta in compute_cell_count (Incr J T1)"
```

### Task 2: JS mirror — `computeCellCount` additive delta

**Files:**
- Modify: `frontend/src/lib/cellCount.js`
- Test: `frontend/src/lib/cellCount.test.js`

- [ ] **Step 1: Write the failing test** (append)

```js
import { describe, it, expect } from "vitest";
import { computeCellCount } from "./cellCount";

describe("reorg_doc_delta (Incr J)", () => {
  it("is additive on the per_file base", () => {
    expect(computeCellCount({ per_file: { "a.pdf": 3 } })).toBe(3);
    expect(computeCellCount({ per_file: { "a.pdf": 3 }, reorg_doc_delta: 2 })).toBe(5);
    expect(computeCellCount({ per_file: { "a.pdf": 3 }, reorg_doc_delta: -1 })).toBe(2);
  });
  it("respects user_override as base", () => {
    expect(computeCellCount({ user_override: 10, reorg_doc_delta: 2 })).toBe(12);
  });
  it("applies to checks", () => {
    const cell = { worker_marks: { "a.pdf": [{ page: 1, count: 4 }] }, reorg_doc_delta: 1 };
    expect(computeCellCount(cell, "checks", ["a.pdf"])).toBe(5);
  });
});
```

- [ ] **Step 2: Run** `cd frontend && npx vitest run src/lib/cellCount.test.js` → delta cases FAIL.

- [ ] **Step 3: Implement** — extract a `_baseCount` and add the delta:

```js
function _baseCount(cell, countType = "documents", presentFiles = null) {
  if (cell?.user_override != null) return cell.user_override;
  if (countType === "checks") return _sumMarks(cell, presentFiles);
  return computeFilesCount(cell);
}

// count_type === "checks" (maquinaria) → tally; otherwise the documents cascade.
// Incr J: + reorg_doc_delta additive on top of every base path.
export function computeCellCount(cell, countType = "documents", presentFiles = null) {
  return _baseCount(cell, countType, presentFiles) + (cell?.reorg_doc_delta ?? 0);
}
```

- [ ] **Step 4: Run** vitest → PASS.

- [ ] **Step 5: Commit**

```bash
cd frontend && npx vitest run src/lib/cellCount.test.js
git add frontend/src/lib/cellCount.js frontend/src/lib/cellCount.test.js
git commit -m "feat(count): mirror additive reorg_doc_delta in JS computeCellCount (Incr J T2)"
```

### Task 3: Cross-language parity fixtures

**Files:**
- Modify: `tests/fixtures/cell_count_cases.json`
- Test: `tests/test_cell_count_cross_language.py` (existing — runs automatically)

- [ ] **Step 1:** Read `tests/fixtures/cell_count_cases.json` and `tests/test_cell_count_cross_language.py` to learn the exact case schema (field names for `cell`, `count_type`, `present_files`, `expected`).

- [ ] **Step 2:** Append 3 cases matching that schema:
  - `per_file {a.pdf:3}` + `reorg_doc_delta:2` → expected `5`.
  - `user_override:10` + `reorg_doc_delta:2` → expected `12`.
  - `checks` + `worker_marks {a.pdf:[{page:1,count:4}]}` + `present_files:["a.pdf"]` + `reorg_doc_delta:1` → expected `5`.

- [ ] **Step 3: Run** `pytest tests/test_cell_count_cross_language.py -v` → PASS (Python side already implements the delta from T1; this proves the JS mirror agrees against the same fixtures).

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/cell_count_cases.json
git commit -m "test(count): cross-language reorg_doc_delta parity cases (Incr J T3)"
```

### Task 4: `compute_worker_count` additive `reorg_worker_delta`

**Files:**
- Modify: `api/state.py` (`compute_worker_count`, lines ~56-70)
- Test: `tests/unit/api/test_state.py` (append)

- [ ] **Step 1: Write the failing test**

```python
from api.state import compute_worker_count


def test_compute_worker_count_adds_reorg_worker_delta():
    cell = {"worker_marks": {"a.pdf": [{"page": 1, "count": 5}]}}
    assert compute_worker_count(cell, {"a.pdf"}) == 5
    cell["reorg_worker_delta"] = 3
    assert compute_worker_count(cell, {"a.pdf"}) == 8
    cell["reorg_worker_delta"] = -2
    assert compute_worker_count(cell, {"a.pdf"}) == 3
```

- [ ] **Step 2: Run** `pytest tests/unit/api/test_state.py -k worker_count -v` → FAIL (delta ignored).

- [ ] **Step 3: Implement** — change the return line:

```python
    return _sum_marks(cell, present_files) + (cell.get("reorg_worker_delta") or 0)
```

Update the docstring `Returns:` to note the additive reorg delta.

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
ruff check api/state.py tests/unit/api/test_state.py
git add api/state.py tests/unit/api/test_state.py
git commit -m "feat(count): additive reorg_worker_delta in compute_worker_count (Incr J T4)"
```

---

## Chunk 2: Ops persistence + delta recompute

### Task 5: `SessionManager` reorg-op mutators

**Files:**
- Modify: `api/state.py` (new methods on `SessionManager`)
- Test: `tests/unit/api/test_state.py`

Fixture note: `tests/unit/api/test_state.py` uses a `manager` fixture with session `"2026-04"`. Match it.

- [ ] **Step 1: Write the failing tests**

```python
def test_add_reorg_op_assigns_stable_id(manager):
    op = manager.add_reorg_op("2026-04", {"op_type": "move_file", "source": {}, "dest": {}})
    assert op["id"] == "op_001"
    op2 = manager.add_reorg_op("2026-04", {"op_type": "rotate", "source": {}, "dest": {}})
    assert op2["id"] == "op_002"
    state = manager.get_session_state("2026-04")
    assert [o["id"] for o in state["reorg_ops"]] == ["op_001", "op_002"]


def test_delete_reorg_op(manager):
    manager.add_reorg_op("2026-04", {"op_type": "move_file", "source": {}, "dest": {}})
    assert manager.delete_reorg_op("2026-04", "op_001") is True
    assert manager.delete_reorg_op("2026-04", "op_404") is False
    assert manager.get_session_state("2026-04").get("reorg_ops") == []


def test_id_counter_survives_deletes(manager):
    manager.add_reorg_op("2026-04", {"op_type": "rotate", "source": {}, "dest": {}})
    manager.delete_reorg_op("2026-04", "op_001")
    op = manager.add_reorg_op("2026-04", {"op_type": "rotate", "source": {}, "dest": {}})
    assert op["id"] == "op_002"  # monotonic; no id reuse


def test_set_reorg_state_writes_deltas(manager):
    manager.set_reorg_state(
        "2026-04",
        ops=[{"id": "op_001", "status": "pending"}],
        deltas={("HRB", "art"): {"doc": -1, "worker": 0}, ("HRB", "odi"): {"doc": 1, "worker": 0}},
    )
    state = manager.get_session_state("2026-04")
    assert state["cells"]["HRB"]["art"]["reorg_doc_delta"] == -1
    assert state["cells"]["HRB"]["odi"]["reorg_doc_delta"] == 1
```

- [ ] **Step 2: Run** `pytest tests/unit/api/test_state.py -k reorg -v` → FAIL (methods missing).

- [ ] **Step 3: Implement** — add three `@_synchronized` methods on `SessionManager` (mirror the existing read-modify-write pattern):

```python
    @_synchronized
    def add_reorg_op(self, session_id: str, op: dict) -> dict:
        """Append a reorg op with a stable, monotonic id (``op_NNN``).

        The id counter (``state["reorg_seq"]``) never reuses numbers across
        deletes, so an op's id stays meaningful for the manifest.
        """
        state, _ = self._load_and_migrate(session_id)
        seq = state.get("reorg_seq", 0) + 1
        state["reorg_seq"] = seq
        op = {**op, "id": f"op_{seq:03d}"}
        state.setdefault("reorg_ops", []).append(op)
        update_session_state(self._conn, session_id, state_json=json.dumps(state))
        return op

    @_synchronized
    def delete_reorg_op(self, session_id: str, op_id: str) -> bool:
        """Remove a reorg op by id. Returns True if one was removed."""
        state, _ = self._load_and_migrate(session_id)
        ops = state.get("reorg_ops", [])
        kept = [o for o in ops if o.get("id") != op_id]
        removed = len(kept) != len(ops)
        state["reorg_ops"] = kept
        update_session_state(self._conn, session_id, state_json=json.dumps(state))
        return removed

    @_synchronized
    def set_reorg_state(
        self,
        session_id: str,
        *,
        ops: list[dict],
        deltas: dict[tuple[str, str], dict],
    ) -> None:
        """Replace the op list and rewrite every cell's reorg delta cache.

        Zeros ``reorg_doc_delta``/``reorg_worker_delta`` on all cells, then
        applies ``deltas`` (keyed by (hospital, sigla)). ``deltas`` is in-memory
        only — never serialized — so tuple keys are fine.
        """
        state, _ = self._load_and_migrate(session_id)
        state["reorg_ops"] = ops
        for siglas in state.get("cells", {}).values():
            for cell in siglas.values():
                cell["reorg_doc_delta"] = 0
                cell["reorg_worker_delta"] = 0
        for (hosp, sigla), d in deltas.items():
            cell = state.setdefault("cells", {}).setdefault(hosp, {}).setdefault(sigla, {})
            cell["reorg_doc_delta"] = d.get("doc", 0)
            cell["reorg_worker_delta"] = d.get("worker", 0)
        update_session_state(self._conn, session_id, state_json=json.dumps(state))
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
ruff check api/state.py tests/unit/api/test_state.py
git add api/state.py tests/unit/api/test_state.py
git commit -m "feat(reorg): SessionManager add/delete/set reorg ops + delta cache (Incr J T5)"
```

### Task 6: `refresh_reorg_deltas` (session-wide recompute + evidence-based lifecycle)

**Files:**
- Modify: `api/routes/sessions.py` (new free function near `refresh_all_reliable`, ~line 174)
- Test: `tests/unit/api/test_reorg_routes.py` (create)

**No new imports needed:** `_find_category_folder` (late-imported at `sessions.py:558`, `# noqa: E402`) and `cell_page_counts` (`sessions.py:96`) are already module-scope and resolve at call time — `refresh_reorg_deltas`'s body runs at call time, so it sees them. Do **not** add a duplicate import.

- [ ] **Step 1: Write the failing test with a concrete fixture.** Build a real temp `month_root` (no DB mocking, per convention) mirroring the `client` fixture in `tests/unit/api/test_cells_routes.py` (reuse its `_one_page_pdf()` helper and `CATEGORY_FOLDERS` to name folders). The fixture must: create two HRB category folders (for `art` and `odi`) under the temp root, put one 1-page PDF in the `art` folder, build a `SessionManager` on a temp DB (mirror the `manager` fixture in `test_state.py`), `open_session(year=2026, month=4, month_root=<temp>)`, populate the two cells via `mgr.apply_per_file_ocr_result(...)` (gives `art` a `per_file` entry for the source PDF), and `mgr.add_reorg_op(...)` a pending `move_file` op `HRB/art → HRB/odi` with `doc_count=1`, `worker_count=0`, `status="pending"`.

```python
import pytest
from core.scanners.patterns import CATEGORY_FOLDERS  # confirm exact module via `grep "CATEGORY_FOLDERS ="`

# reuse _one_page_pdf() from test_cells_routes (import or duplicate the 6-line helper)

@pytest.fixture
def reorg_mgr(tmp_path):
    """SessionManager on a temp DB + a temp month_root with HRB art/odi folders.
    The art folder holds one source PDF; the odi folder is empty (move target)."""
    art_dir = tmp_path / "HRB" / CATEGORY_FOLDERS["art"]
    odi_dir = tmp_path / "HRB" / CATEGORY_FOLDERS["odi"]
    art_dir.mkdir(parents=True)
    odi_dir.mkdir(parents=True)
    (art_dir / "art_crs.pdf").write_bytes(_one_page_pdf())
    import sqlite3
    from api.state import SessionManager
    mgr = SessionManager(sqlite3.connect(":memory:"))
    mgr.open_session(year=2026, month=4, month_root=tmp_path)
    mgr.apply_per_file_ocr_result("2026-04", "HRB", "art", "art_crs.pdf",
                                  count=1, method="header_band_anchors", near_matches=[])
    mgr.apply_per_file_ocr_result("2026-04", "HRB", "odi", "placeholder.pdf",
                                  count=0, method="header_band_anchors", near_matches=[])
    mgr.add_reorg_op("2026-04", {
        "op_type": "move_file",
        "source": {"hospital": "HRB", "sigla": "art", "file": "art_crs.pdf"},
        "dest": {"hospital": "HRB", "sigla": "odi"},
        "doc_count": 1, "worker_count": 0, "status": "pending",
    })
    return mgr, art_dir


def test_refresh_recomputes_deltas_from_pending_ops(reorg_mgr):
    from api.routes.sessions import refresh_reorg_deltas
    mgr, _ = reorg_mgr
    refresh_reorg_deltas(mgr, "2026-04", check_applied=False)
    state = mgr.get_session_state("2026-04")
    assert state["cells"]["HRB"]["art"]["reorg_doc_delta"] == -1
    assert state["cells"]["HRB"]["odi"]["reorg_doc_delta"] == 1


def test_check_applied_marks_gone_source_as_applied(reorg_mgr):
    from api.routes.sessions import refresh_reorg_deltas
    mgr, art_dir = reorg_mgr
    (art_dir / "art_crs.pdf").unlink()  # simulate paso-1 having moved it physically
    refresh_reorg_deltas(mgr, "2026-04", check_applied=True)
    state = mgr.get_session_state("2026-04")
    assert state["reorg_ops"][0]["status"] == "applied"
    assert state["cells"]["HRB"]["art"]["reorg_doc_delta"] == 0
    assert state["cells"]["HRB"]["odi"]["reorg_doc_delta"] == 0
```

(If `CATEGORY_FOLDERS` lives in a different module, find it with `grep -rn "CATEGORY_FOLDERS =" core/`. `_find_category_folder` matches a folder under the hospital dir by sigla; the `client` fixture in `test_cells_routes.py` proves `odi → "3.-ODI Visitas"` resolves, so naming folders via `CATEGORY_FOLDERS[sigla]` is the correct precedent.)

- [ ] **Step 2: Run** `pytest tests/unit/api/test_reorg_routes.py -k refresh -v` → FAIL (function missing).

- [ ] **Step 3: Implement** — add near `refresh_all_reliable`:

```python
def refresh_reorg_deltas(
    mgr: SessionManager,
    session_id: str,
    *,
    check_applied: bool = False,
) -> None:
    """Recompute every cell's reorg delta from ``state["reorg_ops"]`` (session-wide).

    Pattern of ``refresh_all_reliable`` (cache derived from the source, refreshed
    after mutations), but session-scoped: it sweeps all cells. Call with
    ``check_applied=True`` only on a pase-1 re-scan — the one moment a source file
    could have moved physically: a ``pending`` op whose ``source.file`` is no longer
    present in its origin folder is marked ``applied`` and stops contributing a delta
    (the move is now physical reality; counting both would double-count).
    """
    state = mgr.get_session_state(session_id)
    ops = state.get("reorg_ops", [])
    month_root = Path(state.get("month_root", ""))

    if check_applied:
        for op in ops:
            if op.get("status") != "pending":
                continue
            src = op["source"]
            folder = _find_category_folder(month_root / src["hospital"], src["sigla"])
            present = set(cell_page_counts(folder)) if folder.exists() else set()
            if src.get("file") not in present:
                op["status"] = "applied"

    deltas: dict[tuple[str, str], dict] = {}
    for op in ops:
        if op.get("status") != "pending":
            continue
        src_key = (op["source"]["hospital"], op["source"]["sigla"])
        dst_key = (op["dest"]["hospital"], op["dest"]["sigla"])
        doc = op.get("doc_count") or 0
        wrk = op.get("worker_count") or 0
        for key in (src_key, dst_key):
            deltas.setdefault(key, {"doc": 0, "worker": 0})
        deltas[src_key]["doc"] -= doc
        deltas[src_key]["worker"] -= wrk
        deltas[dst_key]["doc"] += doc
        deltas[dst_key]["worker"] += wrk

    mgr.set_reorg_state(session_id, ops=ops, deltas=deltas)
```

(`split_in_place`/`rotate` carry `doc_count=0` and `dest==source`, so they net zero — no special-casing.)

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
ruff check api/routes/sessions.py tests/unit/api/test_reorg_routes.py
git add api/routes/sessions.py tests/unit/api/test_reorg_routes.py
git commit -m "feat(reorg): refresh_reorg_deltas session-wide recompute + applied lifecycle (Incr J T6)"
```

### Task 7: Wire `refresh_reorg_deltas(check_applied=True)` into `POST /scan`

**Files:**
- Modify: `api/routes/sessions.py` (the `scan` handler, ~line 314)
- Test: `tests/unit/api/test_reorg_routes.py`

- [ ] **Step 1: Write the failing test** — open+scan a session that already has a pending op whose source file exists; assert the op stays `pending` and the delta is present after `POST /scan`. Then delete/move the source file, `POST /scan` again, assert the op flips to `applied` and the delta is gone (no double count).

- [ ] **Step 2: Run** → FAIL (scan doesn't refresh deltas yet).

- [ ] **Step 3: Implement** — in the `scan` handler, after the apply loop and before `return`:

```python
    for (hosp, sigla), r in results.items():
        mgr.apply_cell_result(session_id, hosp, sigla, r)
    refresh_reorg_deltas(mgr, session_id, check_applied=True)
    return {
        "scanned": len(results),
        "summary": {f"{hosp}_{sigla}": r.count for (hosp, sigla), r in results.items()},
    }
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
ruff check api/routes/sessions.py
git add api/routes/sessions.py tests/unit/api/test_reorg_routes.py
git commit -m "feat(reorg): re-scan refreshes reorg deltas + marks moved files applied (Incr J T7)"
```

---

## Chunk 3: Ops API — validation, endpoints, manifest export

### Task 8: `api/reorg.py` pure helpers (validation + defaults + manifest)

**Files:**
- Create: `api/reorg.py`
- Test: `tests/unit/api/test_reorg.py`

- [ ] **Step 1: Write the failing tests**

```python
from api.reorg import OP_TYPES, build_manifest, resolve_op_defaults, validate_op


def _src_pages():  # source cell folder page counts
    return {"art_crs.pdf": 50, "x.pdf": 1}


def test_validate_move_file_ok():
    op = {"op_type": "move_file", "source": {"hospital": "HRB", "sigla": "art", "file": "art_crs.pdf"},
          "dest": {"hospital": "HRB", "sigla": "odi"}, "doc_count": 1}
    assert validate_op(op, src_pages=_src_pages(), existing_ops=[]) == []


def test_validate_rejects_dest_equals_source_for_move():
    op = {"op_type": "move_file", "source": {"hospital": "HRB", "sigla": "art", "file": "art_crs.pdf"},
          "dest": {"hospital": "HRB", "sigla": "art"}, "doc_count": 1}
    assert validate_op(op, src_pages=_src_pages(), existing_ops=[])  # non-empty errors


def test_validate_extract_requires_range():
    op = {"op_type": "extract_pages", "source": {"hospital": "HRB", "sigla": "art", "file": "art_crs.pdf"},
          "dest": {"hospital": "HRB", "sigla": "odi"}}
    assert validate_op(op, src_pages=_src_pages(), existing_ops=[])


def test_validate_range_bounds_and_doc_cap():
    base = {"op_type": "extract_pages", "source": {"hospital": "HRB", "sigla": "art", "file": "art_crs.pdf"},
            "dest": {"hospital": "HRB", "sigla": "odi"}}
    assert validate_op({**base, "source": {**base["source"], "file": "art_crs.pdf"}, "page_range": [0, 3]},
                       src_pages=_src_pages(), existing_ops=[])           # X<1
    assert validate_op({**base, "page_range": [3, 60]}, src_pages=_src_pages(), existing_ops=[])  # Y>pages
    assert validate_op({**base, "page_range": [5, 3]}, src_pages=_src_pages(), existing_ops=[])   # X>Y
    assert validate_op({**base, "page_range": [1, 2], "doc_count": 5}, src_pages=_src_pages(), existing_ops=[])  # cap


def test_validate_rejects_overlapping_extract_same_file():
    existing = [{"op_type": "extract_pages", "status": "pending",
                 "source": {"hospital": "HRB", "sigla": "art", "file": "art_crs.pdf"},
                 "dest": {"hospital": "HRB", "sigla": "odi"}, "page_range": [3, 7]}]
    op = {"op_type": "extract_pages", "source": {"hospital": "HRB", "sigla": "art", "file": "art_crs.pdf"},
          "dest": {"hospital": "HRB", "sigla": "induccion"}, "page_range": [5, 9]}
    assert validate_op(op, src_pages=_src_pages(), existing_ops=existing)  # overlap → error
    op_disjoint = {**op, "page_range": [8, 9]}
    assert validate_op(op_disjoint, src_pages=_src_pages(), existing_ops=existing) == []


def test_resolve_defaults_move_file_uses_per_file():
    op = {"op_type": "move_file", "source": {"hospital": "HRB", "sigla": "art", "file": "art_crs.pdf"},
          "dest": {"hospital": "HRB", "sigla": "odi"}}
    src_cell = {"per_file": {"art_crs.pdf": 3}, "worker_marks": {}}
    out = resolve_op_defaults(op, src_cell=src_cell)
    assert out["doc_count"] == 3 and out["worker_count"] == 0


def test_build_manifest_includes_only_pending():
    state = {"reorg_ops": [
        {"id": "op_001", "status": "pending", "op_type": "rotate"},
        {"id": "op_002", "status": "applied", "op_type": "rotate"},
    ]}
    m = build_manifest(state, month="2026-06")
    assert m["manifest_version"] == 1 and m["month"] == "2026-06"
    assert [o["id"] for o in m["operations"]] == ["op_001"]
```

- [ ] **Step 2: Run** `pytest tests/unit/api/test_reorg.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement `api/reorg.py`:**

```python
"""Pure helpers for reorg ops: validation, default resolution, manifest build.

No I/O, no FastAPI — unit-testable in isolation. The endpoints in
``api/routes/sessions.py`` gather the filesystem/state inputs and call these.
"""

from __future__ import annotations

from datetime import datetime

OP_TYPES = {"move_file", "extract_pages", "split_in_place", "rotate"}
ROTATIONS = {0, 90, 180, 270}
MANIFEST_VERSION = 1


def _ranges_overlap(a: list[int], b: list[int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def validate_op(op: dict, *, src_pages: dict[str, int], existing_ops: list[dict]) -> list[str]:
    """Return a list of human-readable error strings ([] = valid).

    Args:
        op: the proposed op (without an id yet).
        src_pages: {filename: page_count} of the *source* cell folder.
        existing_ops: the session's current reorg_ops (for overlap checks).
    """
    errors: list[str] = []
    ot = op.get("op_type")
    if ot not in OP_TYPES:
        errors.append(f"op_type inválido: {ot!r}")
        return errors

    src = op.get("source") or {}
    dst = op.get("dest") or {}
    file = src.get("file")
    pr = op.get("page_range")

    same_cell = (src.get("hospital"), src.get("sigla")) == (dst.get("hospital"), dst.get("sigla"))
    if same_cell and ot in ("move_file", "extract_pages"):
        errors.append("dest no puede ser igual a source para move_file/extract_pages")

    if file not in src_pages:
        errors.append(f"archivo origen no presente: {file!r}")
    pages = src_pages.get(file, 0)

    if ot == "move_file" and pr is not None:
        errors.append("move_file no admite page_range")
    if ot == "extract_pages":
        if pr is None:
            errors.append("extract_pages requiere page_range")
        else:
            x, y = pr
            if not (1 <= x <= y <= pages):
                errors.append(f"page_range fuera de límites: {pr} (páginas={pages})")
            for other in existing_ops:
                if (
                    other.get("op_type") == "extract_pages"
                    and other.get("status", "pending") == "pending"
                    and (other.get("source") or {}).get("file") == file
                    and other.get("page_range")
                    and _ranges_overlap(pr, other["page_range"])
                ):
                    errors.append(f"page_range solapa otra op del mismo archivo: {other['page_range']}")

    rot = op.get("rotation_deg", 0)
    if rot not in ROTATIONS:
        errors.append(f"rotation_deg inválido: {rot}")

    dc = op.get("doc_count")
    if dc is not None:
        if dc < 0:
            errors.append("doc_count no puede ser negativo")
        elif ot == "extract_pages" and pr is not None and dc > (pr[1] - pr[0] + 1):
            errors.append("doc_count excede las páginas del rango")
        elif ot == "move_file" and dc > pages:
            errors.append("doc_count excede las páginas del archivo")

    return errors


def resolve_op_defaults(op: dict, *, src_cell: dict) -> dict:
    """Return a copy of ``op`` with doc_count/worker_count filled if absent.

    move_file: doc_count = the file's current cell contribution
      (per_file_overrides | per_file | 1); worker_count = sum of the file's marks.
    extract_pages: doc_count = 1; worker_count = sum of marks on the page range.
    split_in_place / rotate: doc_count = worker_count = 0.
    """
    out = dict(op)
    ot = op["op_type"]
    file = (op.get("source") or {}).get("file")
    pr = op.get("page_range")

    def _marks_total(pred) -> int:
        marks = (src_cell.get("worker_marks") or {}).get(file) or []
        return sum((m.get("count") or 0) for m in marks if pred(m))

    if ot == "move_file":
        per_file = src_cell.get("per_file") or {}
        overrides = src_cell.get("per_file_overrides") or {}
        out.setdefault("doc_count", overrides.get(file, per_file.get(file, 1)))
        out.setdefault("worker_count", _marks_total(lambda m: True))
    elif ot == "extract_pages":
        out.setdefault("doc_count", 1)
        out.setdefault(
            "worker_count",
            _marks_total(lambda m: pr and pr[0] <= (m.get("page") or 0) <= pr[1]),
        )
    else:  # split_in_place, rotate
        out.setdefault("doc_count", 0)
        out.setdefault("worker_count", 0)

    out.setdefault("status", "pending")
    out.setdefault("preserve_date", True)
    out.setdefault("rotation_deg", 0)
    out.setdefault("empresa", None)
    out.setdefault("note", None)
    return out


def build_manifest(state: dict, *, month: str) -> dict:
    """Build the export manifest from a session's pending reorg ops."""
    pending = [o for o in state.get("reorg_ops", []) if o.get("status") == "pending"]
    return {
        "manifest_version": MANIFEST_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_project": "PDFoverseer",
        "month": month,
        "operations": pending,
    }
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
ruff check api/reorg.py tests/unit/api/test_reorg.py
git add api/reorg.py tests/unit/api/test_reorg.py
git commit -m "feat(reorg): pure validation + defaults + manifest helpers (Incr J T8)"
```

### Task 9: `POST /reorg/ops` endpoint

**Files:**
- Modify: `api/routes/sessions.py` (Pydantic models + endpoint)
- Test: `tests/unit/api/test_reorg_routes.py`

- [ ] **Step 1: Write the failing tests** (use the `client` fixture; the ABRIL/HPV/odi cell exists with one 1-page PDF). Test: create a `move_file` op from `HPV/odi`→`HPV/induccion` with `doc_count` omitted → 200, response op has `id == "op_001"`, `doc_count == 1`, `status == "pending"`; GET session shows `reorg_ops` length 1 and `cells.HPV.odi.reorg_doc_delta == -1`, `cells.HPV.induccion.reorg_doc_delta == 1`. Test: invalid op (dest==source) → 400. Test: unknown session → 404; unknown sigla → 404.

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement** — Pydantic models + endpoint (mirror `apply_ratio`'s session/cell guards):

```python
class ReorgSource(BaseModel):
    hospital: str
    sigla: str
    file: str
    page_range: list[int] | None = None


class ReorgDest(BaseModel):
    hospital: str
    sigla: str


class ReorgOpCreate(BaseModel):
    op_type: str
    source: ReorgSource
    dest: ReorgDest
    empresa: str | None = None
    preserve_date: bool = True
    rotation_deg: int = 0
    doc_count: int | None = None
    worker_count: int | None = None
    note: str | None = None


@router.post("/sessions/{session_id}/reorg/ops")
def create_reorg_op(
    session_id: str,
    body: ReorgOpCreate,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Create a reorg op; recompute deltas; return the op + affected cells."""
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc

    op = body.model_dump()
    src = op["source"]
    month_root = Path(state.get("month_root", ""))
    src_folder = _find_category_folder(month_root / src["hospital"], src["sigla"])  # 404 on unknown sigla
    src_cell = (state.get("cells", {}).get(src["hospital"], {}) or {}).get(src["sigla"])
    if src_cell is None:
        raise HTTPException(404, f"Cell not found: {src['hospital']}/{src['sigla']}")
    # validate dest sigla too (folder lookup raises 404 on unknown sigla)
    _find_category_folder(month_root / op["dest"]["hospital"], op["dest"]["sigla"])

    src_pages = cell_page_counts(src_folder) if src_folder.exists() else {}
    errors = validate_op(op, src_pages=src_pages, existing_ops=state.get("reorg_ops", []))
    if errors:
        raise HTTPException(400, "; ".join(errors))

    op = resolve_op_defaults(op, src_cell=src_cell)
    created = mgr.add_reorg_op(session_id, op)
    refresh_reorg_deltas(mgr, session_id, check_applied=False)
    state = mgr.get_session_state(session_id)
    return {"op": created, "cells": state["cells"]}
```

Note: `_find_category_folder` must raise `HTTPException(404)` on an unknown sigla — confirm/guard it the same way `patch_note` does (Incr 3C wrapped a `CATEGORY_FOLDERS[sigla]` KeyError into 404). If it raises `KeyError`, wrap both lookups in try/except → 404.

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
ruff check api/routes/sessions.py tests/unit/api/test_reorg_routes.py
git add api/routes/sessions.py tests/unit/api/test_reorg_routes.py
git commit -m "feat(reorg): POST /reorg/ops endpoint with validation + delta recompute (Incr J T9)"
```

### Task 10: `DELETE /reorg/ops/{op_id}` endpoint

**Files:**
- Modify: `api/routes/sessions.py`
- Test: `tests/unit/api/test_reorg_routes.py`

- [ ] **Step 1: Write the failing test** — create an op, DELETE it → 200, GET session shows `reorg_ops == []` and deltas back to 0; DELETE unknown id → 404.

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement**

```python
@router.delete("/sessions/{session_id}/reorg/ops/{op_id}")
def delete_reorg_op(
    session_id: str,
    op_id: str,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Delete a reorg op; recompute deltas."""
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    try:
        mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if not mgr.delete_reorg_op(session_id, op_id):
        raise HTTPException(404, f"Op not found: {op_id}")
    refresh_reorg_deltas(mgr, session_id, check_applied=False)
    state = mgr.get_session_state(session_id)
    return {"deleted": op_id, "cells": state["cells"]}
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
ruff check api/routes/sessions.py
git add api/routes/sessions.py tests/unit/api/test_reorg_routes.py
git commit -m "feat(reorg): DELETE /reorg/ops/{op_id} endpoint (Incr J T10)"
```

### Task 11: `POST /reorg/export` endpoint (manifest → OVERSEER_OUTPUT_DIR)

**Files:**
- Modify: `api/routes/sessions.py`
- Test: `tests/unit/api/test_reorg_routes.py`

- [ ] **Step 1:** Read `api/routes/output.py` to copy the exact `OVERSEER_OUTPUT_DIR` resolution + atomic-write (tmp→rename) pattern used for the RESUMEN.

- [ ] **Step 2: Write the failing test** — create a pending op, `POST /reorg/export` → 200 with `{path, operation_count: 1}`; the file exists at the returned path; its JSON parses with `manifest_version == 1`, `month == "2026-04"`, one operation. With no pending ops → 400. (Use a `tmp_path` `OVERSEER_OUTPUT_DIR` via monkeypatch, matching the `client` fixture's env setup.)

- [ ] **Step 3: Implement** — derive `month` as the session id (`YYYY-MM`); build via `build_manifest`; atomic-write JSON to `<OVERSEER_OUTPUT_DIR>/reorganizacion_<session_id>.json`:

```python
@router.post("/sessions/{session_id}/reorg/export")
def export_reorg_manifest(
    session_id: str,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Write the reorg manifest (pending ops) to OVERSEER_OUTPUT_DIR."""
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    manifest = build_manifest(state, month=session_id)
    if not manifest["operations"]:
        raise HTTPException(400, "No hay operaciones pendientes para exportar")
    out_dir = Path(os.environ.get("OVERSEER_OUTPUT_DIR", "A:/PROJECTS/PDFoverseer/data/outputs"))
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"reorganizacion_{session_id}.json"
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(dest)  # atomic on the same filesystem
    return {"path": str(dest), "operation_count": len(manifest["operations"])}
```

(`os` is imported at `sessions.py:7`. **`json` is NOT imported at module level — add `import json` to the top imports.** Reuse `output.py`'s exact atomic-write pattern if it differs from the above — that file is the precedent; read it in Step 1.)

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
ruff check api/routes/sessions.py
git add api/routes/sessions.py tests/unit/api/test_reorg_routes.py
git commit -m "feat(reorg): POST /reorg/export writes versioned manifest to output dir (Incr J T11)"
```

---

## Chunk 4: Frontend — store, api, panel, FileList menu

> The implementer reads the named existing files for their exact patterns before editing. Frontend tasks specify the contract + key logic + the pattern to mirror; they do not transcribe whole files.

### Task 12: `api.js` reorg calls

**Files:**
- Modify: `frontend/src/lib/api.js`

- [ ] **Step 1:** Mirror the `patchNote`/`applyRatio` shapes already in `api.js`. Add to the `api` object:

```js
  // Incr J — reorg ops + manifest export.
  createReorgOp: (sessionId, op) =>
    fetch(`${BASE}/sessions/${sessionId}/reorg/ops`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(op),
    }).then(jsonOrThrow),

  deleteReorgOp: (sessionId, opId) =>
    fetch(`${BASE}/sessions/${sessionId}/reorg/ops/${opId}`, { method: "DELETE" }).then(jsonOrThrow),

  exportManifest: (sessionId) =>
    fetch(`${BASE}/sessions/${sessionId}/reorg/export`, { method: "POST" }).then(jsonOrThrow),
```

- [ ] **Step 2: Commit** (no test for thin fetch wrappers — covered by store + endpoint tests):

```bash
git add frontend/src/lib/api.js
git commit -m "feat(reorg): api.js createReorgOp/deleteReorgOp/exportManifest (Incr J T12)"
```

### Task 13: store actions

**Files:**
- Modify: `frontend/src/store/session.js`

- [ ] **Step 1:** Read `session.js` for the store shape (how `session` / `session.cells` / `session.reorg_ops` are held and how `saveNote` updates state). **Match the existing action convention: every `api.*`-calling action takes `sessionId` as its explicit first param** (e.g. `saveNote(sessionId, hospital, sigla, patch)`, `saveOverride(sessionId, hospital, sigla, value)`). Add three actions with these **exact signatures**:
  - `addReorgOp(sessionId, hospital, sigla, opDraft)` → `api.createReorgOp(sessionId, {op_type, source:{hospital, sigla, file, page_range?}, dest:{...}, ...})`; on success, **re-fetch full session** (`api.getSession(sessionId)`) and replace `session` in the store. Re-fetch (not client-side merge) because the backend recomputed deltas across possibly many cells — the server is the source of truth (avoids a fragile, divergent client merge). Confirm against `session.js` that the store holds `session` as a single replaceable object (it does — `setSession`/equivalent is used elsewhere); if the setter has a different name, use it.
  - `deleteReorgOp(sessionId, opId)` → `api.deleteReorgOp`; re-fetch session.
  - `exportManifest(sessionId)` → `api.exportManifest`; on success **call `toast.success(\`Manifiesto exportado — ${operation_count} operación(es)\`)`** (the store owns the success toast, mirroring how other actions toast; the component only invokes the action), then return `{path, operation_count}`.
  - Surface errors via the existing toast/error pattern (sonner) used by `saveOverride`/`saveNote`.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/store/session.js
git commit -m "feat(reorg): store actions addReorgOp/deleteReorgOp/exportManifest (Incr J T13)"
```

### Task 14: `ReorganizacionPanel.jsx` + vitest

**Files:**
- Create: `frontend/src/components/ReorganizacionPanel.jsx`
- Test: `frontend/src/components/ReorganizacionPanel.test.jsx`

- [ ] **Step 1: Write the failing test** — use the project's existing component-test setup (vitest + @testing-library/react — match the `WorkerHud`/cell-status test style). Cover these cases explicitly:
  - (a) `ops=[]` → renders an empty-state line ("Sin operaciones") and the export button is **disabled**.
  - (b) `ops` with one outgoing (`source` = this cell) + one incoming (`dest` = this cell) → the net delta line shows the correct `+/−`; the outgoing row shows `−doc_count → DEST`; the incoming row shows `+doc_count ← SOURCE`.
  - (c) an `applied` op renders with the muted class and **no** eliminar button.
  - (d) export button enabled when ≥1 `pending` op; clicking it fires `onExport`.
  - (e) clicking a row's eliminar button fires `onDelete` with that op's `id`.

- [ ] **Step 2: Run** `cd frontend && npx vitest run src/components/ReorganizacionPanel.test.jsx` → FAIL.

- [ ] **Step 3: Implement** — a presentational component:
  - Props: `{ hospital, sigla, ops, onDelete, onExport }` (the container wires `ops` from `session.reorg_ops`, callbacks from the store).
  - Filter ops into `outgoing` (`op.source.hospital/sigla === this cell`) and `incoming` (`op.dest...`).
  - Net delta = `Σ incoming.doc_count − Σ outgoing.doc_count` over **pending** ops.
  - Each row: a `Badge` (type chip — same family/shape, color/text by `op_type`), the file/range, the arrow + count, and an eliminar button (only for `pending`).
  - `applied` ops: muted (use a `po-*` muted token, NOT `/opacity`).
  - Export button calls `onExport`; disabled when no pending ops.
  - Tokens: `po-*` only; chips via the shared `Badge` primitive. Match the NOTA/`NotePanel` section styling for consistency.

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
cd frontend && npx vitest run src/components/ReorganizacionPanel.test.jsx
git add frontend/src/components/ReorganizacionPanel.jsx frontend/src/components/ReorganizacionPanel.test.jsx
git commit -m "feat(reorg): ReorganizacionPanel — op list + net delta + export (Incr J T14)"
```

### Task 15: `DetailPanel` + `FileList` integration

**Files:**
- Modify: `frontend/src/components/DetailPanel.jsx`, `frontend/src/components/FileList.jsx`

- [ ] **Step 1 (DetailPanel):** Read `DetailPanel.jsx` to find where the NOTA section (`<NotePanel>`) renders and how it pulls from the store (it currently reads only `session?.session_id`). Add the needed Zustand selectors near that read:
  ```jsx
  const sessionId = useSessionStore((s) => s.session?.session_id);
  const reorgOps = useSessionStore((s) => s.session?.reorg_ops ?? []);
  const deleteReorgOp = useSessionStore((s) => s.deleteReorgOp);
  const exportManifest = useSessionStore((s) => s.exportManifest);
  ```
  (`reorg_ops` needs its **own selector** so the panel re-renders when ops change — reading it off a non-subscribed `session` object would not trigger a re-render.) Then add a **REORGANIZACIÓN** section (same always-visible pattern as NOTA) **after** NOTA, rendering:
  ```jsx
  <ReorganizacionPanel
    hospital={hospital}
    sigla={sigla}
    ops={reorgOps}
    onDelete={(opId) => deleteReorgOp(sessionId, opId)}
    onExport={() => exportManifest(sessionId)}
  />
  ```

- [ ] **Step 2 (FileList):** Read `FileList.jsx`. Its rows use a fixed CSS grid (currently `grid-cols-[minmax(0,1fr)_3rem_1.25rem_3.5rem_5.5rem]`). **Append a `2rem` column** for a `⋯` "Reorganizar" trigger (matches the existing chip-column widths; do not widen existing columns). The trigger opens a small menu/popover to create whole-file ops: choose `op_type` (`move_file` / `rotate` / reclasificar=`move_file`), destination `(hospital, sigla)` via selectors, optional empresa, optional rotation. On confirm, call the store action `addReorgOp(sessionId, srcHospital, srcSigla, draft)` with `source.file = file.name`, no `page_range`. Use `po-*` tokens + shared primitives; keep alignment consistent with existing FileList rows.

- [ ] **Step 3: Verify** `cd frontend && npm run build` succeeds; run the full vitest suite `npx vitest run`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/DetailPanel.jsx frontend/src/components/FileList.jsx
git commit -m "feat(reorg): wire ReorganizacionPanel into DetailPanel + FileList move menu (Incr J T15)"
```

### Task 15b: worker total reflects `reorg_worker_delta` (JS UI)

**Why:** T4 made the Python `compute_worker_count` delta-aware (feeds Excel N15) — but the frontend has a **separate** mirror `frontend/src/lib/worker-count.js::computeWorkerCount(marks, fileNames)` that the viewer/HUD and cell rows use to show the cell's worker total. It takes `worker_marks` (not the cell), so it is delta-blind. Left unfixed, a worker reorg would change Excel/N15 but **not** the UI worker total → a UI/Excel divergence (the exact class of bug this project fights). Keep the delta addition in **one** place (don't scatter `+ delta` across call sites).

**Files:**
- Modify: `frontend/src/lib/worker-count.js` (add a thin cell-level wrapper)
- Test: `frontend/src/lib/worker-count.test.js` (create or append)
- Modify: the call sites that render the **cell** worker total (not per-file subtotals).

- [ ] **Step 1:** Read `worker-count.js`. Add a wrapper that mirrors the `cellCount.js` pattern (base + delta in one spot):

```js
// Cell worker total including the Incr-J reorg delta. Per-file subtotals
// (fileSubtotal) stay raw — the delta is a cell-level quantity, not per-file.
export function cellWorkerCount(cell, fileNames) {
  return computeWorkerCount(cell?.worker_marks ?? {}, fileNames) + (cell?.reorg_worker_delta ?? 0);
}
```

- [ ] **Step 2: Write the failing test** — `cellWorkerCount` returns the marks sum plus `reorg_worker_delta` (absent key → no-op; positive and negative deltas); `computeWorkerCount`/`fileSubtotal` unchanged.

- [ ] **Step 3:** `grep`-find call sites of `computeWorkerCount(` in `frontend/src/`. For each that computes a **cell's total** (e.g. in `WorkerCountViewer`/HUD, `DetailPanel`, or cell rows), switch to `cellWorkerCount(cell, fileNames)` so the displayed total includes the delta. Leave any per-file subtotal usage (`fileSubtotal`) alone. Confirm none is missed with a second grep.

- [ ] **Step 4: Run** `cd frontend && npx vitest run src/lib/worker-count.test.js`; then `npx vitest run` (full) + `npm run build`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/worker-count.js frontend/src/lib/worker-count.test.js frontend/src/components/*.jsx
git commit -m "feat(reorg): cell worker total includes reorg_worker_delta in UI (Incr J T15b)"
```

---

## Chunk 5: Frontend — viewer reorg mode + handoff doc

### Task 16: `reorg-range.js` pure range-validation helper + vitest

**Files:**
- Create: `frontend/src/lib/reorg-range.js`, `frontend/src/lib/reorg-range.test.js`

- [ ] **Step 1: Write the failing test**

```js
import { describe, it, expect } from "vitest";
import { isValidRange, normalizeRange } from "./reorg-range";

describe("reorg range", () => {
  it("accepts in-bounds start<=end", () => {
    expect(isValidRange(1, 3, 10)).toBe(true);
    expect(isValidRange(5, 5, 10)).toBe(true);
  });
  it("rejects out-of-bounds or inverted", () => {
    expect(isValidRange(0, 3, 10)).toBe(false);
    expect(isValidRange(3, 11, 10)).toBe(false);
    expect(isValidRange(5, 3, 10)).toBe(false);
    expect(isValidRange(null, 3, 10)).toBe(false);
  });
  it("normalizes [start,end] sorted", () => {
    expect(normalizeRange(5, 3)).toEqual([3, 5]);
    expect(normalizeRange(2, 4)).toEqual([2, 4]);
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement**

```js
// Pure helpers for the viewer reorg-mode range selection (1-based, inclusive).
export function isValidRange(start, end, totalPages) {
  if (start == null || end == null) return false;
  return Number.isInteger(start) && Number.isInteger(end)
    && start >= 1 && end <= totalPages && start <= end;
}

export function normalizeRange(a, b) {
  return a <= b ? [a, b] : [b, a];
}
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
cd frontend && npx vitest run src/lib/reorg-range.test.js
git add frontend/src/lib/reorg-range.js frontend/src/lib/reorg-range.test.js
git commit -m "feat(reorg): pure range-validation helper for viewer reorg mode (Incr J T16)"
```

### Task 17: `WorkerCountViewer` reorg mode

**Files:**
- Modify: `frontend/src/components/WorkerCountViewer.jsx`

- [ ] **Step 1:** Read `WorkerCountViewer.jsx` to learn its current props, page-nav state, the keyboard handler (~lines 216-230: digits → pending buffer, PageDown → advance), and the autosave (`useDebouncedCallback` ~line 79 + the unmount `flushSave` ~lines 87-93). Add:
  - A new prop `mode` (`"worker"` default = current behavior; `"reorg"` = range selection). In `"reorg"`, do **not** render the worker-count HUD.
  - **Gate the worker machinery in reorg mode (load-bearing — prevents silent data corruption):**
    - **Keyboard handler:** wrap its body with `if (mode !== "reorg") { ... }` so digit/PageDown keys do **not** write worker marks while the operator is selecting a range.
    - **Autosave/unmount flush:** skip the worker-count POST in reorg mode — `if (mode === "reorg") return;` before the debounced save and before the unmount `flushSave`. Otherwise stale worker marks would be POSTed to the worker-count endpoint on unmount.
  - Local state `reorgStartPage` / `reorgEndPage` (1-based, `null` until marked).
  - UI in reorg mode: "marcar inicio" / "marcar fin" buttons on the active page (and/or click two thumbnails); highlight the selected range on the thumbnail strip (a `po-*` highlight, not `/opacity`); a "Crear operación" control that picks `op_type` (`extract_pages` / `split_in_place` / `rotate`) + destination, validates with `isValidRange(start, end, totalPages)` (from `reorg-range.js`), and calls a new prop `onCreateOp(opDraft)` where `opDraft` carries `source.page_range = normalizeRange(start, end)`.
  - `onCreateOp` is wired by the container to the store's `addReorgOp`.

- [ ] **Step 2: Verify** `cd frontend && npm run build` succeeds; `npx vitest run` (full suite green). Range logic is covered by T16; the viewer wiring + the mode gating are verified by build + the live smoke (confirm that opening the viewer in reorg mode and navigating pages does **not** mutate the cell's worker marks).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/WorkerCountViewer.jsx
git commit -m "feat(reorg): WorkerCountViewer mode=reorg visual page-range selection (Incr J T17)"
```

### Task 18: paso-1 handoff contract doc

**Files:**
- Create: `docs/handoff/paso1-manifiesto-reorganizacion.md`

- [ ] **Step 1:** Write the static contract doc (Spanish neutro) covering, per spec §10:
  1. Qué es y por qué existe (PDFoverseer cuenta + detecta colados; el paso 1 deja el archivo físico coherente con los libros).
  2. Dónde leerlo: `<carpeta de outputs de PDFoverseer>/reorganizacion_<YYYY-MM>.json`. **No** dentro de `A:\informe mensual`.
  3. Cuándo: entre el Step 3 (contar) y el Step 4 (totalizar a nombres de carpeta).
  4. Contrato campo por campo — copy the §4 table **verbatim** (op_type, source{hospital,sigla,file,page_range?}, dest{hospital,sigla}, empresa, preserve_date, rotation_deg, doc_count, worker_count, note, status) + a full JSON example.
  5. En qué fijarse: destino = intención (el paso 1 arma el nombre con su convención `fecha_sigla_descriptor_empresa.pdf` + `COMPANY_CORRECTIONS`); `preserve_date`; **orden de extracciones** (rangos disjuntos garantizados; aplicar descendente o contra copia intacta); idempotencia (no duplicar; verificar destino antes de mover); reportar remanentes; `--ejecutar` dry-run-first; `status` es informativo (puede registrar `applied` en su log; PDFoverseer no lo lee de vuelta).

- [ ] **Step 2: Commit**

```bash
git add docs/handoff/paso1-manifiesto-reorganizacion.md
git commit -m "docs(reorg): paso-1 manifest handoff contract (Incr J T18)"
```

---

## Final verification (after all tasks)

- [ ] `ruff check .` → 0 violations.
- [ ] `pytest` → full suite green (no skips beyond the known 52).
- [ ] `cd frontend && npx vitest run` → green; `npm run build` → succeeds.
- [ ] Dispatch a final holistic code-reviewer over the whole branch.
- [ ] **Live API smoke (data-safe):** back up `overseer.db` (record SHA256); against a real backend on **ABRIL** (session `2026-04`, never MAYO `2026-05`): create a `move_file` op odi→induccion, confirm origin/dest deltas + Excel/history reflect it, export the manifest and inspect the JSON, then re-scan and confirm the op flips to `applied` only after the (simulated) file move. Restore `overseer.db` by hash; confirm MAYO untouched.
- [ ] Push `po_overhaul` to origin; tag `incremento-J`.
- [ ] Update memory: `project_incremento_J_shipped` + roadmap pointer.
