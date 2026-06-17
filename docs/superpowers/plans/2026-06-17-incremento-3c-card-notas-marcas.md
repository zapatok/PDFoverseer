# Incremento 3C — card worker indicator + notes-with-state + marks list (Implementation Plan)

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking. Each subagent must also follow @superpowers:test-driven-development.

**Goal:** Close the Incr 3 UX series with three small, independent features: an aggregate worker-counting status chip on each hospital card (M2), per-cell notes-with-state decoupled from the manual override that force the dot amber when `por_resolver` (N1), and current-page highlight + auto-scroll in the worker marks list (F4).

**Architecture:** N1 introduces two new cell-JSON fields (`note`, `note_status`) and a one-time idempotent `v2→v3` migration that moves the legacy `override_note` into them (status `resuelto`) and **removes `override_note` from the data model entirely** — which requires stripping its `setdefault` from the v1→v2 migration and the four `state.py` setters that re-add it, so the chained lazy migration stays churn-free. The note rides its own `PATCH …/note` endpoint + store action, fully decoupled from `saveOverride`. M2 and F4 are pure-frontend additions (one helper in `cell-status.js`, one Badge in `HospitalCard`, a ref+effect in `WorkerHud`).

**Tech Stack:** Python 3.10+ / FastAPI / SQLite (state as JSON blob in `sessions.state_json`); React + Vite (Zustand store); pytest (real fixtures, no DB mocking) + vitest.

**Spec:** `docs/superpowers/specs/2026-06-17-incremento-3c-card-notas-marcas-design.md`

**Conventions (every task):**
- `ruff check .` must report **0** before each commit; vitest green; Python 3.10+ typing (`X | None`, `list[X]`).
- No bare `except`, no `shell=True`, no SQL f-strings, no `print()` in libs. No DB mocking — use the real `SessionManager` + temp sqlite fixture already used by `tests/unit/api/test_state.py`.
- Frontend: only `po-*` design tokens; **never** the `/opacity` modifier on a `po-*` CSS-var token.
- Commits: `type(scope): message`; last line of every commit body verbatim: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` (match the trailer already on `po_overhaul`).
- **No version bump:** this plan touches none of `core/{pipeline,ocr,inference,image}.py` nor `vlm/*` (the `bump-version-tags` hook only fires on those).

---

## File Structure

**Backend (Chunk 1 — N1):**
- `core/state/migrations.py` — add `migrate_cell_v2_to_v3` + `migrate_state_v2_to_v3`; **remove** `override_note` from `migrate_cell_v1_to_v2` (setdefault) and `migrate_state_v1_to_v2` (`had_legacy` clause).
- `api/state.py` — add `SessionManager.set_note`; chain `migrate_state_v2_to_v3` in `_load_and_migrate`; drop the `note` param + `override_note` write from `apply_user_override`; **remove** the four `cell.setdefault("override_note", None)` lines in `apply_filename_result`/`apply_ocr_result`/`finalize_cell_ocr`.
- `api/routes/sessions.py` — add `NotePatch` model + `patch_note` endpoint; add the `note_status=="por_resolver"` gate as the **first line** of `compute_settled`; drop `note`/`override_note` from `patch_override`.

**Frontend (Chunk 2 — N1):**
- `frontend/src/lib/cell-status.js` — add the `por_resolver` gate as the **first line** of `isCellReady`.
- `frontend/src/lib/api.js` — drop `note` from `patchOverride`; add `patchNote`.
- `frontend/src/store/session.js` — drop `note` param + `override_note` merge from `saveOverride`; add `saveNote` action.
- `frontend/src/components/OverridePanel.jsx` — remove the note textarea + its state; keep the numeric input + validation hint.
- `frontend/src/components/{CategoryRow,FileList}.jsx` — stop passing `note` to `saveOverride`.
- `frontend/src/components/DetailPanel.jsx` — `saveOverride` clear call drops the note arg; render a new always-visible **NOTA** section after AJUSTE MANUAL.
- `frontend/src/components/NotePanel.jsx` — **new** component (textarea + state control).

**Frontend (Chunk 3 — M2 + F4):**
- `frontend/src/lib/cell-status.js` — add `hospitalWorkerStatus(cells)`.
- `frontend/src/components/HospitalCard.jsx` — render the aggregate worker Badge.
- `frontend/src/components/WorkerHud.jsx` — highlight the `m.page === pageInFile` row + auto-scroll.

**Tests:**
- `tests/unit/state/test_migrations.py` — update v1→v2 override_note asserts; add v2→v3 + no-churn tests.
- `tests/unit/api/test_state.py` — update `apply_user_override` note asserts + the override_note setdefault asserts; add `set_note` tests.
- `tests/unit/api/test_cells_routes.py` — update override response asserts; add `PATCH …/note` tests + `compute_settled` note-gate test.
- `frontend/src/lib/cell-status.test.js` — note-gate cases on `isCellReady`/`dotVariantFor`; `hospitalWorkerStatus` cases.

---

## Chunk 1: N1 backend — migration, state, route, override decouple

> Self-contained: after this chunk the backend stores/serves `note`/`note_status`, gates `all_reliable` on `por_resolver`, exposes `PATCH …/note`, and no longer accepts/persists any note via the override path. The frontend (Chunk 2) still sends a `note` field in the override body until Task 7 — this is harmless: `patch_override` simply ignores it. **Run the full backend suite green at the end of every task.**

### Task 1: v2→v3 migration + relinquish `override_note` from v1→v2

**Why this shape:** v2→v3 owns the `override_note → note/note_status` transition and *removes* `override_note`. For the chained lazy migration to be idempotent (no DB rewrite on every load), nothing else may re-introduce `override_note`. So v1→v2 must stop defaulting it and stop treating its absence as "legacy". (The four `state.py` setters that also re-add it are handled in Task 3.)

**Files:**
- Modify: `core/state/migrations.py`
- Test: `tests/unit/state/test_migrations.py`

- [ ] **Step 1: Update the existing v1→v2 tests that assert on `override_note`**

In `tests/unit/state/test_migrations.py`, the v1→v2 migration will no longer manage `override_note`. Edit these two tests to drop the now-invalid asserts (a v1 cell has no note to preserve; `override_note` becomes v2→v3's concern):

In `test_migrate_cell_renames_count_to_filename_count` — delete the line:
```python
    assert result["override_note"] is None
```
In `test_migrate_cell_handles_missing_count_field` — delete the line:
```python
    assert result["override_note"] is None
```
Leave `test_migrate_cell_idempotent_on_already_v2` (a v2 cell with `override_note: "note"` → `result == cell`) and `test_migrate_state_returns_changed_false_on_already_v2` unchanged: removing the setdefault does not add/remove an already-present field, so both still pass.

- [ ] **Step 2: Write the failing v2→v3 tests**

Append to `tests/unit/state/test_migrations.py` (add the imports to the existing `from core.state.migrations import ...` line):

```python
from core.state.migrations import (
    migrate_cell_v1_to_v2,
    migrate_cell_v2_to_v3,
    migrate_state_v1_to_v2,
    migrate_state_v2_to_v3,
)


def test_v2_to_v3_migrates_override_note_to_resuelto_note():
    cell = {"user_override": 5, "override_note": "17 ODIs en 1 PDF"}
    result = migrate_cell_v2_to_v3(cell)
    assert result["note"] == "17 ODIs en 1 PDF"
    assert result["note_status"] == "resuelto"
    assert "override_note" not in result


def test_v2_to_v3_no_legacy_note_yields_none_none():
    # A cell with override_note=None (or absent) gets note=None / note_status=None,
    # NOT "resuelto" — there was never a real note.
    cell = {"user_override": None, "override_note": None}
    result = migrate_cell_v2_to_v3(cell)
    assert result["note"] is None
    assert result["note_status"] is None
    assert "override_note" not in result


def test_v2_to_v3_absent_override_note_yields_none_none():
    cell = {"filename_count": 3}
    result = migrate_cell_v2_to_v3(cell)
    assert result["note"] is None
    assert result["note_status"] is None


def test_v2_to_v3_idempotent_preserves_existing_note():
    cell = {"note": "ya migrada", "note_status": "por_resolver"}
    result = migrate_cell_v2_to_v3(cell)
    # Already at v3: note untouched, status untouched, no override_note added.
    assert result["note"] == "ya migrada"
    assert result["note_status"] == "por_resolver"
    assert "override_note" not in result


def test_migrate_state_v2_to_v3_changed_then_idempotent():
    state = {
        "cells": {
            "HLL": {"dif_pts": {"user_override": 2, "override_note": "compilado"}},
            "HPV": {"art": {"override_note": None}},
        }
    }
    state, changed = migrate_state_v2_to_v3(state)
    assert changed is True
    assert state["cells"]["HLL"]["dif_pts"]["note"] == "compilado"
    assert state["cells"]["HLL"]["dif_pts"]["note_status"] == "resuelto"
    assert "override_note" not in state["cells"]["HLL"]["dif_pts"]
    assert state["cells"]["HPV"]["art"]["note"] is None
    assert state["cells"]["HPV"]["art"]["note_status"] is None
    # Second pass: nothing left to migrate → no DB rewrite.
    state, changed2 = migrate_state_v2_to_v3(state)
    assert changed2 is False


def test_chained_v1_v2_then_v2_v3_idempotent_no_churn():
    # The real load path runs both, chained. After one full pass, a second full
    # pass must report changed=False on BOTH steps (no override_note re-introduced).
    state = {
        "cells": {
            "HRB": {"odi": {"count": 4, "override_note": "x"}},
        }
    }
    state, c1 = migrate_state_v1_to_v2(state)
    state, c2 = migrate_state_v2_to_v3(state)
    assert (c1 or c2) is True
    assert "override_note" not in state["cells"]["HRB"]["odi"]
    assert state["cells"]["HRB"]["odi"]["note"] == "x"
    assert state["cells"]["HRB"]["odi"]["note_status"] == "resuelto"
    # Second full chained pass: zero changes.
    state, c1b = migrate_state_v1_to_v2(state)
    state, c2b = migrate_state_v2_to_v3(state)
    assert c1b is False
    assert c2b is False
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `pytest tests/unit/state/test_migrations.py -q`
Expected: FAIL — `ImportError: cannot import name 'migrate_cell_v2_to_v3'`.

- [ ] **Step 4: Implement v2→v3 + relinquish override_note from v1→v2**

In `core/state/migrations.py`:

(a) In `migrate_cell_v1_to_v2`, **delete** the line `cell.setdefault("override_note", None)`. Update its docstring to drop `override_note` from the FASE 2 field list (now `{filename_count, ocr_count, user_override, confidence, method, excluded, ...}`).

(b) In `migrate_state_v1_to_v2`, **delete** the `had_legacy` clause `or "override_note" not in cell` (leaving the `count` / `filename_count` / `ocr_count` checks).

(c) Append the new functions:

```python
def migrate_cell_v2_to_v3(cell: dict) -> dict:
    """FASE 2 → FASE 3: decouple the note from the override.

    ``override_note`` (a string coupled to ``user_override``) becomes the
    independent pair ``note`` / ``note_status``. A legacy note is non-blocking,
    so it migrates as ``note_status="resuelto"``. ``override_note`` is removed.

    Idempotent: once ``note`` exists the value transfer is skipped; the pop is a
    no-op when ``override_note`` is already gone.
    """
    if "note" not in cell:
        legacy = cell.get("override_note")
        cell["note"] = legacy or None
        cell["note_status"] = "resuelto" if legacy else None
    cell.pop("override_note", None)
    return cell


def migrate_state_v2_to_v3(state: dict) -> tuple[dict, bool]:
    """Migrate full session state JSON in-place. Idempotent.

    Returns ``(state, changed)`` where ``changed`` is True iff any cell still
    carried ``override_note`` or lacked ``note`` (so the caller can skip the
    DB write-back on every subsequent load).
    """
    changed = False
    cells = state.get("cells")
    if not cells:
        return state, False
    for hosp_cells in cells.values():
        for cell in hosp_cells.values():
            had_legacy = "override_note" in cell or "note" not in cell
            migrate_cell_v2_to_v3(cell)
            if had_legacy:
                changed = True
    return state, changed
```

- [ ] **Step 5: Run the migration tests to verify they pass**

Run: `pytest tests/unit/state/test_migrations.py -q`
Expected: PASS (all, including the two edited v1→v2 tests).

- [ ] **Step 6: Commit**

```bash
git add core/state/migrations.py tests/unit/state/test_migrations.py
git commit -m "feat(state): v2->v3 cell migration — override_note to note/note_status"
```

### Task 2: chain v2→v3 in `_load_and_migrate`

**Files:**
- Modify: `api/state.py` (`SessionManager._load_and_migrate`, lines ~149-163; import line at top)
- Test: `tests/unit/api/test_state.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/api/test_state.py`. Use the **existing `manager` fixture** (it yields a `SessionManager` with an already-open session `"2026-04"`; do **not** mock the DB; `json` is already imported at the top of the file). The test seeds a session whose `state_json` carries a legacy `override_note`, then asserts a load migrates it:

```python
def test_load_and_migrate_chains_v2_to_v3(manager):
    mgr = manager
    from core.db.sessions_repo import update_session_state  # same import api/state.py uses

    # Seed a legacy override_note directly in the stored state (bypass setters).
    state = mgr.get_session_state("2026-04")
    state.setdefault("cells", {}).setdefault("HPV", {})["odi"] = {
        "user_override": 2,
        "override_note": "compilado",
    }
    update_session_state(mgr._conn, "2026-04", state_json=json.dumps(state))

    migrated = mgr.get_session_state("2026-04")  # triggers _load_and_migrate
    cell = migrated["cells"]["HPV"]["odi"]
    assert cell["note"] == "compilado"
    assert cell["note_status"] == "resuelto"
    assert "override_note" not in cell
```

> The `manager` fixture lives at `tests/unit/api/test_state.py` (~line 56: opens session `2026-04` on a temp sqlite, yields `mgr`). `update_session_state` is imported in `api/state.py` from `core.db.sessions_repo` — match that import. This is a REAL round-trip through sqlite.

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/api/test_state.py -q -k load_and_migrate_chains`
Expected: FAIL — `cell` still has `override_note`, no `note`.

- [ ] **Step 3: Implement the chaining**

In `api/state.py`, update the import to include the v2→v3 state function (wherever `migrate_state_v1_to_v2` is imported from `core.state.migrations`), then in `_load_and_migrate` replace the single-migration body:

```python
        state = json.loads(rec.state_json)
        state, changed1 = migrate_state_v1_to_v2(state)
        state, changed2 = migrate_state_v2_to_v3(state)
        if changed1 or changed2:
            update_session_state(self._conn, session_id, state_json=json.dumps(state))
        return state, rec
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/api/test_state.py -q -k load_and_migrate_chains`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/state.py tests/unit/api/test_state.py
git commit -m "feat(state): chain v2->v3 migration in _load_and_migrate"
```

### Task 3: `set_note` + decouple `apply_user_override` + drop setter setdefaults

**Why:** `set_note` is the single writer for `note`/`note_status`. `apply_user_override` must stop touching any note (clearing an override must not clear the note). The four `cell.setdefault("override_note", None)` lines in the other setters must go, or they re-introduce `override_note` after the migration popped it (→ churn, Task 1's invariant).

**Files:**
- Modify: `api/state.py` — add `set_note`; edit `apply_user_override` (lines ~338-376); delete `override_note` setdefaults in `apply_filename_result` (~192), `apply_ocr_result` (~224), `finalize_cell_ocr` (~286, ~332); fix the `apply_filename_result` docstring (~172).
- Test: `tests/unit/api/test_state.py`

- [ ] **Step 1: Write the failing tests**

Use the existing `manager` fixture (session `"2026-04"`); target the `HPV/odi` cell (`set_note` creates the cell via `setdefault`, so the folder need not exist):

```python
def test_set_note_writes_text_and_status(manager):
    mgr = manager
    mgr.set_note("2026-04", "HPV", "odi", text="revisar firma", status="por_resolver")
    cell = mgr.get_session_state("2026-04")["cells"]["HPV"]["odi"]
    assert cell["note"] == "revisar firma"
    assert cell["note_status"] == "por_resolver"


def test_set_note_blank_clears_to_none(manager):
    mgr = manager
    mgr.set_note("2026-04", "HPV", "odi", text="algo", status="por_resolver")
    mgr.set_note("2026-04", "HPV", "odi", text="   ", status="resuelto")
    cell = mgr.get_session_state("2026-04")["cells"]["HPV"]["odi"]
    assert cell["note"] is None
    assert cell["note_status"] is None


def test_clear_override_does_not_touch_note(manager):
    mgr = manager
    mgr.set_note("2026-04", "HPV", "odi", text="ojo", status="por_resolver")
    mgr.apply_user_override("2026-04", "HPV", "odi", value=7)
    mgr.apply_user_override("2026-04", "HPV", "odi", value=None)  # clear override
    cell = mgr.get_session_state("2026-04")["cells"]["HPV"]["odi"]
    assert cell["user_override"] is None
    assert cell["note"] == "ojo"
    assert cell["note_status"] == "por_resolver"
```

> Note: after this task `apply_user_override`'s signature is `(session_id, hospital, sigla, *, value, manual=False)` — `value` is keyword-only and there is no `note` param.

Then update the **existing** override tests in `test_state.py` that reference the dropped `note` param / `override_note` field. Run `git grep -n "note=\|override_note" tests/unit/api/test_state.py` to find them (the reviewer located them near lines ~104, ~448-471, ~489):
- For each `apply_user_override(..., note="...")` call → remove the `note=` kwarg.
- For each `assert cell["override_note"] == "..."` / `is None` → replace with the note path (`assert cell.get("note") == ...` / `is None`), or delete if it was only asserting the legacy coupling. The new behavior is "override carries no note".

- [ ] **Step 2: Run to verify the new tests fail**

Run: `pytest tests/unit/api/test_state.py -q -k "set_note or clear_override_does_not_touch_note"`
Expected: FAIL — `AttributeError: 'SessionManager' object has no attribute 'set_note'`.

- [ ] **Step 3: Implement**

(a) Add `set_note` to `SessionManager` (place it next to `apply_worker_count`; mirror that method's `@_synchronized` + `_load_and_migrate` + `update_session_state` shape):

```python
    @_synchronized
    def set_note(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        *,
        text: str | None,
        status: str,
    ) -> None:
        """Set or clear a cell's note (independent of the user override).

        Blank/whitespace-only text clears the note: ``note`` and ``note_status``
        both become None. Otherwise the stripped text is stored with the given
        status (``"por_resolver"`` | ``"resuelto"``). The cell is created if
        absent.

        Args:
            session_id: Target session identifier (``YYYY-MM``).
            hospital: Hospital code (e.g. ``"HLL"``).
            sigla: Category code (e.g. ``"reunion"``).
            text: Note body, or None/blank to clear.
            status: ``"por_resolver"`` or ``"resuelto"`` (ignored when clearing).
        """
        state, _ = self._load_and_migrate(session_id)
        cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
        clean = (text or "").strip()
        if clean:
            cell["note"] = clean
            cell["note_status"] = status
        else:
            cell["note"] = None
            cell["note_status"] = None
        update_session_state(self._conn, session_id, state_json=json.dumps(state))
```

(b) In `apply_user_override`: remove the `note: str | None,` parameter; remove the line `cell["override_note"] = note if value is not None else None`; rewrite the docstring to drop all note language (it now sets only `user_override` + `manual_entry`).

(c) Delete **every** `cell.setdefault("override_note", None)` line in `api/state.py`. There are **four**, at lines ~192, ~224, ~286, ~332 — distributed as **`apply_filename_result` (TWO: ~192 in its guarded branch and ~224 in its main branch)**, `apply_ocr_result` (one, ~286), and `finalize_cell_ocr` (one, ~332). Drive it by grep, not by function name: after the deletions, `git grep -nc 'setdefault("override_note"' api/state.py` must return **0**. In the `apply_filename_result` docstring, change "Never touches ocr_count, user_override, or override_note." to "Never touches ocr_count, user_override, note, or note_status." (`apply_per_file_ocr_result` was audited: it has **no** `override_note` setdefault — only `per_file`/`per_file_method`/`near_matches` — so no change there.)

> **Why all four:** these setters run **after** `_load_and_migrate` (which popped `override_note` and added `note`/`note_status`). If any of them re-`setdefault`s `override_note`, the next load's v2→v3 pops it again → `changed=True` on every load → DB rewritten every load (the churn Task 1 prevents). Removing all four re-adders is what keeps the chained migration idempotent.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/api/test_state.py -q`
Expected: PASS (new + edited).

- [ ] **Step 5: Commit**

```bash
git add api/state.py tests/unit/api/test_state.py
git commit -m "feat(state): set_note + decouple note from apply_user_override"
```

### Task 4: `compute_settled` note gate

**Files:**
- Modify: `api/routes/sessions.py` (`compute_settled`, lines ~112-142)
- Test: `tests/unit/api/test_cells_routes.py` (or the file that tests `compute_settled`; grep `compute_settled` to locate)

- [ ] **Step 1: Write the failing test**

```python
def test_compute_settled_por_resolver_forces_false(tmp_path):
    from api.routes.sessions import compute_settled
    folder = tmp_path  # empty folder is fine; the gate short-circuits before the walk
    cell = {"worker_status": "terminado", "note_status": "por_resolver"}
    assert compute_settled(cell, folder, count_type="checks") is False


def test_compute_settled_resuelto_does_not_block(tmp_path):
    from api.routes.sessions import compute_settled
    cell = {"worker_status": "terminado", "note_status": "resuelto"}
    assert compute_settled(cell, tmp_path, count_type="checks") is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/api/test_cells_routes.py -q -k compute_settled_por_resolver`
Expected: FAIL — returns True (gate not yet present).

- [ ] **Step 3: Implement the gate**

In `compute_settled`, add as the **first line of the body** (before the `if count_type == "checks":` branch):

```python
    if cell.get("note_status") == "por_resolver":
        return False  # an unresolved note keeps the cell amber regardless of provenance
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/api/test_cells_routes.py -q -k compute_settled`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/routes/sessions.py tests/unit/api/test_cells_routes.py
git commit -m "feat(sessions): compute_settled gates amber on por_resolver note"
```

### Task 5: `PATCH …/note` endpoint + drop note from `patch_override`

**Files:**
- Modify: `api/routes/sessions.py` (add `NotePatch` + `patch_note`; edit `patch_override`, lines ~618-658)
- Test: `tests/unit/api/test_cells_routes.py`

- [ ] **Step 1: Write the failing tests**

Use the module's existing `client` fixture + the `_open_and_scan(client)` helper (returns the session-id **string**); target the `HPV/odi` cell the fixture scans into existence (no DB mock):

```python
def test_patch_note_persists_text_and_status(client):
    sess = _open_and_scan(client)
    r = client.patch(
        f"/api/sessions/{sess}/cells/HPV/odi/note",
        json={"text": "revisar firma", "status": "por_resolver"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["note"] == "revisar firma"
    assert body["note_status"] == "por_resolver"


def test_patch_note_blank_clears(client):
    sess = _open_and_scan(client)
    client.patch(
        f"/api/sessions/{sess}/cells/HPV/odi/note",
        json={"text": "algo", "status": "por_resolver"},
    )
    r = client.patch(
        f"/api/sessions/{sess}/cells/HPV/odi/note",
        json={"text": "", "status": "resuelto"},
    )
    assert r.json()["note"] is None
    assert r.json()["note_status"] is None


def test_patch_note_rejects_bad_status(client):
    sess = _open_and_scan(client)
    r = client.patch(
        f"/api/sessions/{sess}/cells/HPV/odi/note",
        json={"text": "x", "status": "no_existe"},
    )
    assert r.status_code == 422  # Literal validation


def test_patch_note_unknown_session_404(client):
    r = client.patch(
        "/api/sessions/2099-01/cells/HPV/odi/note",
        json={"text": "x", "status": "por_resolver"},
    )
    assert r.status_code == 404


def test_patch_override_response_has_no_note(client):
    sess = _open_and_scan(client)
    # value=1 stays within the ≤páginas cap (odi PDF is 1 page).
    r = client.patch(
        f"/api/sessions/{sess}/cells/HPV/odi/override",
        json={"value": 1},
    )
    assert r.status_code == 200
    assert "override_note" not in r.json()
```

Also update the **existing** override tests in `test_cells_routes.py` that mention a note (run `git grep -n '"note"\|override_note' tests/unit/api/test_cells_routes.py`):
- `test_patch_override_sets_value` (~lines 40-51): currently sends `json={"value": 1, "note": "revisado"}` and asserts `body["override_note"] == "revisado"`. Drop `"note": "revisado"` from the body and delete the `assert body["override_note"] == "revisado"` line (keep `assert body["user_override"] == 1`).
- `test_patch_override_null_clears` (~lines 54-65): drop the now-meaningless `"note"` keys from its request bodies (the asserts there are on `user_override`, so they stay green either way — this is just cleanup).

- [ ] **Step 2: Run to verify failures**

Run: `pytest tests/unit/api/test_cells_routes.py -q -k "patch_note or override_response_has_no_note"`
Expected: FAIL — 404/405 for the note route (not defined); `override_note` still in override response.

- [ ] **Step 3: Implement**

(a) Add the request model near `WorkerCountPatch` (ensure `Literal` is imported — it already is, used by `WorkerCountPatch`):

```python
class NotePatch(BaseModel):
    """Body del PATCH note. text vacío/None borra la nota."""

    text: str | None = None
    status: Literal["por_resolver", "resuelto"] = "por_resolver"
```

(b) Add the endpoint (mirror `patch_worker_count`'s folder resolution + `refresh_all_reliable`; re-read the cell after the refresh so the returned `all_reliable` is current):

```python
@router.patch("/sessions/{session_id}/cells/{hospital}/{sigla}/note")
def patch_note(
    session_id: str,
    hospital: str,
    sigla: str,
    body: NotePatch,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Set or clear a cell's note; refresh all_reliable (por_resolver → amber)."""
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(status_code=422, detail="session_id inválido")
    try:
        mgr.set_note(session_id, hospital, sigla, text=body.text, status=body.status)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Sesión {session_id} no encontrada") from exc
    state = mgr.get_session_state(session_id)
    month_root = Path(state.get("month_root", ""))
    folder = _find_category_folder(month_root / hospital, sigla)
    refresh_all_reliable(mgr, session_id, hospital, sigla, folder, count_type=count_type_for(sigla))
    cell = mgr.get_session_state(session_id)["cells"].get(hospital, {}).get(sigla, {})
    return {
        "note": cell.get("note"),
        "note_status": cell.get("note_status"),
        "all_reliable": cell.get("all_reliable"),
    }
```

> If `_find_category_folder` is not the exact helper name used by `patch_worker_count` in your checkout, copy that endpoint's folder-resolution lines verbatim.

(c) In `patch_override`: delete `note = body.get("note")`; in the `mgr.apply_user_override(...)` call drop `note=note`; in the returned dict drop the `"override_note": cell.get("override_note"),` entry (leaving `{"user_override": cell.get("user_override")}`). **Leave `body: dict = Body(...)` as-is** — keeping the permissive dict body means a stray `note` field from an as-yet-unupdated frontend (Chunk 2 hasn't run) is harmlessly ignored, not a 422.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/api/test_cells_routes.py -q`
Expected: PASS.

- [ ] **Step 5: Run the whole backend suite + ruff**

Run: `ruff check . && pytest tests/unit -q`
Expected: ruff 0 violations; all unit tests pass. (The full suite incl. slow integration runs at end-of-chunk review.)

- [ ] **Step 6: Commit**

```bash
git add api/routes/sessions.py tests/unit/api/test_cells_routes.py
git commit -m "feat(sessions): PATCH cells note endpoint; drop note from override"
```

---

## Chunk 2: N1 frontend — gate, override decouple, NotePanel, DetailPanel

> Self-contained: after this chunk the dot goes amber on `por_resolver`, the note lives in its own NOTA section editable without an override, and `saveOverride` carries no note anywhere. Verify `npm run build` + vitest after the chunk.

### Task 6: `isCellReady` note gate (frontend)

**Files:**
- Modify: `frontend/src/lib/cell-status.js` (`isCellReady`, lines ~56-62)
- Test: `frontend/src/lib/cell-status.test.js`

- [ ] **Step 1: Write the failing vitest cases**

Add to `cell-status.test.js`:

```js
import { isCellReady, dotVariantFor } from "./cell-status";

describe("isCellReady — por_resolver note gate", () => {
  it("forces not-ready even when confirmed", () => {
    expect(isCellReady({ confirmed: true, note_status: "por_resolver" })).toBe(false);
  });
  it("forces not-ready even with an override", () => {
    expect(isCellReady({ user_override: 5, note_status: "por_resolver" })).toBe(false);
  });
  it("forces not-ready even when checks terminado", () => {
    expect(
      isCellReady({ worker_status: "terminado", note_status: "por_resolver" }, "checks"),
    ).toBe(false);
  });
  it("resuelto does not block (confirmed stays ready)", () => {
    expect(isCellReady({ confirmed: true, note_status: "resuelto" })).toBe(true);
  });
  it("no note behaves as before", () => {
    expect(isCellReady({ confirmed: true })).toBe(true);
  });
  it("dotVariantFor → confidence-low when por_resolver", () => {
    expect(dotVariantFor({ confirmed: true, note_status: "por_resolver" })).toBe("confidence-low");
  });
});
```

- [ ] **Step 2: Run to verify fail**

Run: `cd frontend && npx vitest run src/lib/cell-status.test.js`
Expected: FAIL (gate not present).

- [ ] **Step 3: Implement**

In `isCellReady`, add as the **first line of the body**:

```js
  if (cell?.note_status === "por_resolver") return false;
```

- [ ] **Step 4: Run to verify pass**

Run: `cd frontend && npx vitest run src/lib/cell-status.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/cell-status.js frontend/src/lib/cell-status.test.js
git commit -m "feat(ui): isCellReady gates amber on por_resolver note"
```

### Task 7: decouple `note` from `saveOverride` (store, api, all callers, OverridePanel)

**Why:** the note no longer rides the override path. Drop the param from the store action + api client, update all four callers, and strip the note textarea from `OverridePanel`.

**Files:**
- Modify: `frontend/src/store/session.js` (`saveOverride`, ~192-269), `frontend/src/lib/api.js` (`patchOverride`, ~47-55), `frontend/src/components/OverridePanel.jsx`, `frontend/src/components/CategoryRow.jsx` (~36), `frontend/src/components/FileList.jsx` (~101), `frontend/src/components/DetailPanel.jsx` (~259).

- [ ] **Step 1: api client — drop `note`**

In `api.js`, change `patchOverride`:
```js
  patchOverride: async (sessionId, hospital, sigla, value, opts = {}) => {
    const body = { value };
    if (opts.manual) body.manual = true;
    // ...rest unchanged (fetch PATCH .../override, jsonOrThrow)
  },
```

- [ ] **Step 2: store — drop `note` param + `override_note` merge**

In `session.js` `saveOverride`: change the signature to `(sessionId, hospital, sigla, value, opts = {})`; update the `api.patchOverride(...)` call to `api.patchOverride(sessionId, hospital, sigla, value, { signal: controller.signal, manual: opts.manual })`; in the success `set`, drop the `override_note: result.override_note,` line from the `hosp[sigla] = { ...hosp[sigla], user_override: result.user_override }` merge.

- [ ] **Step 3: update the four callers**

- `OverridePanel.jsx:45` (`flushSave`): `saveOverride(session.session_id, hospital, sigla, numericValue);` (drop `n || null`). Also collapse the debounce: `useDebouncedCallback((v) => { ... saveOverride(..., numericValue); }, 400)` taking only `v`.
- `CategoryRow.jsx:36`: `saveOverride(session.session_id, hospital, sigla, v, { manual: mode === "manual" });`
- `FileList.jsx:101`: `saveOverride(session.session_id, hospital, sigla, null)`
- `DetailPanel.jsx:259`: `saveOverride(sessionId, hospital, sigla, null);` and update the adjacent comment (it currently explains note-dropping — make it say the override clears to the files sum).

- [ ] **Step 4: strip the note textarea from OverridePanel**

In `OverridePanel.jsx`: remove the `note`/`setNote` state (line ~16), the `cell?.override_note` resync `useEffect` (lines ~31-33), the `focused.note` handling, `onChangeNote` (lines ~55-60), and the entire `<textarea>` block (lines ~89-102). Keep the numeric input, the `invalid` máx-páginas hint, and `SaveIndicator`.

**Critical — collapse `flushSave` + its call to drop the `note` arg** (otherwise deleting `note` leaves a dangling reference → build error):
```js
  const flushSave = useDebouncedCallback((v) => {
    const numericValue = v === "" || v === null ? null : parseInt(v, 10);
    saveOverride(session.session_id, hospital, sigla, numericValue);
  }, 400);
```
and update `onChangeValue`'s call from `flushSave(parsed === null ? "" : String(parsed), note)` to `flushSave(parsed === null ? "" : String(parsed))` (line ~53). `setFocused`/`focused` can drop the `note` key (only `value` remains).

- [ ] **Step 5: verify — no caller passes a note; build + lint**

Run: `git grep -n "saveOverride(" frontend/src` → confirm **no** occurrence passes a 5th note argument (only `value` then optional `opts`).
Run: `git grep -n "override_note" frontend/src` → expect **zero** matches (all gone).
Run: `cd frontend && npm run build`
Expected: clean build; grep checks clean. Also update any vitest that asserted the old `saveOverride(note)` signature (grep tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/store/session.js frontend/src/lib/api.js frontend/src/components/OverridePanel.jsx frontend/src/components/CategoryRow.jsx frontend/src/components/FileList.jsx frontend/src/components/DetailPanel.jsx
git commit -m "refactor(ui): decouple note from saveOverride across all callers"
```

### Task 8: `api.patchNote` + store `saveNote`

**Files:**
- Modify: `frontend/src/lib/api.js`, `frontend/src/store/session.js`

- [ ] **Step 1: api client — add `patchNote`**

In `api.js`, next to `patchWorkerCount`:
```js
  patchNote: async (sessionId, hospital, sigla, { text, status }, opts = {}) => {
    const r = await fetch(
      `${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/note`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, status }),
        signal: opts.signal,
      },
    );
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
```

- [ ] **Step 2: store — add `saveNote`**

In `session.js`, add a `saveNote` action modeled on `saveWorkerCount` (abort-aware + pending indicator). Key = `${hospital}|${sigla}|note`. On success merge `note`, `note_status`, `all_reliable` into `hosp[sigla]`:
```js
  saveNote: async (sessionId, hospital, sigla, { text, status }) => {
    const key = `${hospital}|${sigla}|note`;
    const controller = new AbortController();
    set((prev) => {
      const existing = prev._pendingSave.get(key);
      if (existing?.controller) existing.controller.abort();
      const nextPending = new Map(prev._pendingSave);
      nextPending.set(key, { controller });
      return {
        _pendingSave: nextPending,
        pendingSaves: { ...prev.pendingSaves, [key]: "saving" },
      };
    });
    try {
      const result = await api.patchNote(
        sessionId, hospital, sigla, { text, status }, { signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      set((prev) => {
        if (!prev.session) return {};
        const cells = { ...prev.session.cells };
        const hosp = { ...cells[hospital] };
        hosp[sigla] = {
          ...hosp[sigla],
          note: result.note,
          note_status: result.note_status,
          all_reliable: result.all_reliable,
        };
        cells[hospital] = hosp;
        const cleanedPending = new Map(prev._pendingSave);
        if (cleanedPending.get(key)?.controller === controller) cleanedPending.delete(key);
        return {
          session: { ...prev.session, cells },
          _pendingSave: cleanedPending,
          pendingSaves: { ...prev.pendingSaves, [key]: "saved" },
        };
      });
      setTimeout(() => {
        set((prev) => {
          if (prev.pendingSaves[key] !== "saved") return {};
          const np = { ...prev.pendingSaves };
          delete np[key];
          return { pendingSaves: np };
        });
      }, 2000);
    } catch (error) {
      if (controller.signal.aborted) return;
      set((prev) => {
        const cleanedPending = new Map(prev._pendingSave);
        if (cleanedPending.get(key)?.controller === controller) cleanedPending.delete(key);
        return {
          _pendingSave: cleanedPending,
          pendingSaves: { ...prev.pendingSaves, [key]: "error" },
          error: String(error),
        };
      });
    }
  },
```

- [ ] **Step 3: verify build**

Run: `cd frontend && npm run build`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.js frontend/src/store/session.js
git commit -m "feat(ui): patchNote api + saveNote store action"
```

### Task 9: `NotePanel.jsx`

**Files:**
- Create: `frontend/src/components/NotePanel.jsx`

> No render-test infra exists (only vitest for pure logic) — this component is verified in the conducted smoke. Match `OverridePanel`'s focus-resync pattern so an in-flight edit isn't clobbered by a store update.

- [ ] **Step 1: Create the component**

```jsx
import { useEffect, useState } from "react";
import { useSessionStore } from "../store/session";
import { useDebouncedCallback } from "../lib/hooks/useDebouncedCallback";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import SaveIndicator from "../ui/SaveIndicator";

// N1 (Incr 3C): per-cell note with state, decoupled from the override.
// por_resolver = amber chip + editable; forces the cell dot amber (cell-status).
// resuelto = jade chip + read-only; reopen to edit again. Blank clears the note.
export default function NotePanel({ hospital, sigla, cell }) {
  const session = useSessionStore((s) => s.session);
  const saveNote = useSessionStore((s) => s.saveNote);
  const pendingSaves = useSessionStore((s) => s.pendingSaves);

  const status = cell?.note_status ?? null; // server truth
  const saveStatus = pendingSaves[`${hospital}|${sigla}|note`] ?? "idle";

  const [text, setText] = useState(cell?.note ?? "");
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) setText(cell?.note ?? "");
  }, [cell?.note, focused]);

  const flush = useDebouncedCallback((value, nextStatus) => {
    saveNote(session.session_id, hospital, sigla, { text: value, status: nextStatus });
  }, 400);

  const readOnly = status === "resuelto";

  const onChange = (e) => {
    const v = e.target.value;
    setText(v);
    // A fresh note is born por_resolver (D4); an existing por_resolver stays so.
    flush(v, "por_resolver");
  };

  const markResolved = () => saveNote(session.session_id, hospital, sigla, { text, status: "resuelto" });
  const reopen = () => saveNote(session.session_id, hospital, sigla, { text, status: "por_resolver" });

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        {status === "por_resolver" && <Badge variant="amber">Por resolver</Badge>}
        {status === "resuelto" && <Badge variant="jade">Resuelta</Badge>}
        <SaveIndicator status={saveStatus} />
      </div>
      <textarea
        value={text}
        placeholder="Anota algo por resolver en esta celda (opcional)"
        onChange={onChange}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        disabled={readOnly}
        rows={3}
        className={`w-full rounded border px-2 py-1.5 text-sm placeholder-po-text-subtle outline-none resize-none ${
          readOnly
            ? "cursor-not-allowed border-po-border bg-po-bg text-po-text-muted"
            : "border-po-border bg-po-bg focus:border-po-accent"
        }`}
      />
      {status === "por_resolver" && (
        <Button variant="secondary" onClick={markResolved}>Marcar resuelta</Button>
      )}
      {status === "resuelto" && (
        <Button variant="ghost" onClick={reopen}>Reabrir</Button>
      )}
    </div>
  );
}
```

> `Badge` (`frontend/src/ui/Badge.jsx`) exposes the `amber` and `jade` tones used here (they map to `po-*` tokens — `feedback_chip_consistency`). Use them directly. Never use `/opacity`.

- [ ] **Step 2: verify build**

Run: `cd frontend && npm run build`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/NotePanel.jsx
git commit -m "feat(ui): NotePanel — per-cell note with por_resolver/resuelto state"
```

### Task 10: render NOTA section in DetailPanel

**Files:**
- Modify: `frontend/src/components/DetailPanel.jsx` (import + render, after the AJUSTE MANUAL block ~435, before the worker module ~437)

- [ ] **Step 1: import NotePanel**

Add to the imports: `import NotePanel from "./NotePanel";`

- [ ] **Step 2: render the always-visible NOTA section**

Between the closing `)}` of the `{!isChecks && (<> … Ajuste manual … </>)}` block and the `{/* Worker/checks counting module … */}` comment, insert:

```jsx
      <h4 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mt-6 mb-2">Nota</h4>
      <NotePanel hospital={hospital} sigla={sigla} cell={cell} />
```

This sits after AJUSTE MANUAL (D6) and is **always visible** — not gated by `isChecks` or `mode`, so a checks cell (maquinaria) and a worker cell both get it.

- [ ] **Step 3: verify build**

Run: `cd frontend && npm run build`
Expected: clean.

- [ ] **Step 4: lint + vitest**

Run: `ruff check . ` (Python untouched here but keep the gate green) and `cd frontend && npx vitest run`
Expected: ruff 0; vitest green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DetailPanel.jsx
git commit -m "feat(ui): NOTA section in DetailPanel after AJUSTE MANUAL"
```

---

## Chunk 3: M2 (card worker chip) + F4 (marks list)

> Two independent pure-frontend features. `hospitalWorkerStatus` is vitest-tested; the HospitalCard Badge and the WorkerHud highlight/scroll are verified in the conducted smoke (no render infra).

### Task 11: `hospitalWorkerStatus` helper

**Files:**
- Modify: `frontend/src/lib/cell-status.js` (add import + export)
- Test: `frontend/src/lib/cell-status.test.js`

- [ ] **Step 1: Write the failing vitest cases**

```js
import { hospitalWorkerStatus } from "./cell-status";

describe("hospitalWorkerStatus", () => {
  const filesCell = (extra) => ({ per_file: { "a.pdf": 1 }, ...extra });

  it("null when no worker cells have files", () => {
    expect(hospitalWorkerStatus({ reunion: filesCell() })).toBe(null); // reunion = documents
    expect(hospitalWorkerStatus({ charla: { per_file: {} } })).toBe(null);
    expect(hospitalWorkerStatus({})).toBe(null);
    expect(hospitalWorkerStatus(null)).toBe(null);
  });

  it("listo when all relevant worker cells terminado", () => {
    const cells = {
      charla: filesCell({ worker_status: "terminado" }),
      maquinaria: filesCell({ worker_status: "terminado" }),
    };
    expect(hospitalWorkerStatus(cells)).toBe("listo");
  });

  it("pendiente when none started", () => {
    const cells = { charla: filesCell(), dif_pts: filesCell() };
    expect(hospitalWorkerStatus(cells)).toBe("pendiente");
  });

  it("en_proceso when some started but not all done", () => {
    const cells = {
      charla: filesCell({ worker_status: "terminado" }),
      chintegral: filesCell({ worker_marks: { "a.pdf": [{ page: 1, count: 2 }] } }),
    };
    expect(hospitalWorkerStatus(cells)).toBe("en_proceso");
  });

  it("worker cell without files is ignored", () => {
    const cells = {
      charla: filesCell({ worker_status: "terminado" }),
      dif_pts: { per_file: {}, worker_status: "en_progreso" }, // no files → excluded
    };
    expect(hospitalWorkerStatus(cells)).toBe("listo");
  });
});
```

- [ ] **Step 2: Run to verify fail**

Run: `cd frontend && npx vitest run src/lib/cell-status.test.js`
Expected: FAIL — `hospitalWorkerStatus is not a function`.

- [ ] **Step 3: Implement**

At the top of `cell-status.js` add (sibling-module import, no cycle — `sigla-info.js` imports nothing):
```js
import { countTypeFor } from "./sigla-info";
```
Then add:
```js
// A worker/checks cell is "relevant" to the aggregate iff it has files.
function cellHasFiles(cell) {
  const pf = cell?.per_file;
  if (pf && Object.keys(pf).length > 0) return true;
  return (cell?.user_override ?? cell?.ocr_count ?? cell?.filename_count ?? 0) > 0;
}

// M2 (Incr 3C): aggregate worker-counting status across a hospital's worker cells
// (count_type ∈ {documents_workers, checks}). "relevant" = cell has files.
// listo = all relevant terminado; pendiente = none started; en_proceso = the rest;
// null = no relevant worker cells (→ no chip).
export function hospitalWorkerStatus(cells) {
  if (!cells) return null;
  let total = 0;
  let done = 0;
  let started = 0;
  for (const [sigla, cell] of Object.entries(cells)) {
    if (!showsWorkerCounter(countTypeFor(sigla))) continue;
    if (!cellHasFiles(cell)) continue;
    total += 1;
    const status = cell?.worker_status;
    const hasMarks = cell?.worker_marks && Object.keys(cell.worker_marks).length > 0;
    if (status === "terminado") done += 1;
    if (status || hasMarks) started += 1;
  }
  if (total === 0) return null;
  if (done === total) return "listo";
  if (started === 0) return "pendiente";
  return "en_proceso";
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd frontend && npx vitest run src/lib/cell-status.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/cell-status.js frontend/src/lib/cell-status.test.js
git commit -m "feat(ui): hospitalWorkerStatus aggregate helper (M2)"
```

### Task 12: HospitalCard worker Badge (M2)

**Files:**
- Modify: `frontend/src/components/HospitalCard.jsx`

- [ ] **Step 1: imports**

Add `import Badge from "../ui/Badge";` and extend the cell-status import to `import { dotVariantFor, hospitalWorkerStatus } from "../lib/cell-status";`.

- [ ] **Step 2: compute + render the chip**

Inside `HospitalCard`, in the **present** branch (the `<button>` return), compute near the top of that branch:
```jsx
  const workerStatus = hospitalWorkerStatus(cells);
  const WORKER_CHIP = {
    listo: { variant: "jade", label: "Trabajadores: listos" },
    en_proceso: { variant: "amber", label: "Trabajadores: en proceso" },
    pendiente: { variant: "neutral", label: "Trabajadores: pendientes" },
  };
  const workerChip = workerStatus ? WORKER_CHIP[workerStatus] : null;
```
In the header row `<div className="flex items-center justify-between mb-3">` (which already has the hospital name on the left and an empty right side), add the chip on the right:
```jsx
        {workerChip && <Badge variant={workerChip.variant}>{workerChip.label}</Badge>}
```

> `Badge` exposes `jade`/`amber`/`neutral` (the shared primitive used by `WorkerHud`/`DetailPanel`/`HospitalCard`'s Dots). Use them directly. Never use `/opacity`.

- [ ] **Step 3: verify build + that worker fields survive store updates**

Run: `cd frontend && npm run build`
Run: `git grep -n "hosp\[sigla\] = " frontend/src/store/session.js` → confirm every handler **spreads** `...hosp[sigla]` (preserving `worker_status`/`worker_marks`/`per_file`); none replaces the cell wholesale. (Spot-checked already; this is the guard against M2 reading stale/missing fields.)
Expected: clean build; all merges spread.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/HospitalCard.jsx
git commit -m "feat(ui): aggregate worker status chip on hospital card (M2)"
```

### Task 13: WorkerHud current-page highlight + auto-scroll (F4)

**Files:**
- Modify: `frontend/src/components/WorkerHud.jsx`

- [ ] **Step 1: add imports + ref + effect**

`WorkerHud.jsx` has no React import yet (only the `lucide-react` line). **Add a new line** at the top, before the lucide import: `import { useEffect, useRef } from "react";`. Inside `WorkerHud`, after `const pageMarks = …`:
```jsx
  const currentRowRef = useRef(null);
  useEffect(() => {
    currentRowRef.current?.scrollIntoView({ block: "nearest" });
  }, [pageInFile]);
```

- [ ] **Step 2: highlight the current row**

Replace the `pageMarks.map(...)` `<li>` block with one that flags `m.page === pageInFile`, attaches the ref to that row, and tints it with `po-*` tokens (no `/opacity`):
```jsx
            {pageMarks.map((m) => {
              const isCurrent = m.page === pageInFile;
              return (
                <li
                  key={m.page}
                  ref={isCurrent ? currentRowRef : null}
                  className={`flex justify-between py-0.5 px-1 rounded ${
                    isCurrent ? "bg-po-panel-hover border-l-2 border-po-accent" : ""
                  }`}
                >
                  <span className={isCurrent ? "font-medium text-po-text" : "text-po-text-muted"}>
                    Página {m.page}
                  </span>
                  <span className="font-mono tabular-nums text-po-text">{m.count}</span>
                </li>
              );
            })}
```
When the current page has no mark, no row holds the ref → `scrollIntoView` no-ops (D3: no fabricated row).

- [ ] **Step 3: verify build**

Run: `cd frontend && npm run build`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/WorkerHud.jsx
git commit -m "feat(ui): highlight + auto-scroll current page in marks list (F4)"
```

---

## After all tasks (controller — not a subagent task)

1. **Final holistic review** — dispatch a final reviewer over the whole 3C diff (spec compliance + cross-cutting: migration churn-free, no `override_note` anywhere in `frontend/src` or live code paths, note gate consistent front/back).
2. **Full suite:** `ruff check .` (0) + `pytest -q` (full, incl. slow integration/e2e, ~15 min) + `cd frontend && npx vitest run` + `npm run build`.
3. **Conducted smoke (chrome-devtools, data-safe — mirror Incr 3B):**
   - **Back up `data/overseer.db`** (record its SHA256). Operate only on a **past** month (ABRIL). **Never** touch MAYO (live).
   - N1: open a green ABRIL cell → add a note (born `por_resolver`) → dot goes **amber**; "Marcar resuelta" → dot returns to its provenance/terminado color; "Reabrir" → amber again. The note edits **without** entering Manual mode and lives in its section after AJUSTE MANUAL.
   - M2: a hospital card shows the aggregate worker chip reflecting its worker-cell counting state.
   - F4: open the worker viewer, advance pages — the current page row highlights and stays visible.
   - **Restore `data/overseer.db`** and confirm the SHA256 matches the backup; restore any touched output `.bak`.
4. Push `po_overhaul`; tag `incremento-3c`; write the `project_incremento_3c_shipped` memory + update `MEMORY.md` and `project_roadmap_next`.

## Out of scope (do not build)
Hard-blocking the note (disabling "Terminé"); coupling M2 to notes; Incr J / manifiesto; any change to counting, Excel, or history; subtotals; presence badges; new-flavor flow.
