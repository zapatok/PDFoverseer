# Incremento 2 — RN + tratamientos en bloque + tope ≤páginas: Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the RN treatment (a block action "treat as N pages/document" that sets each PENDING file to `round(pages/N)`), "Apply R1" (= ratio N=1), a per-file `RN` chip, an honest backend `all_reliable` green-dot signal (replacing 1B's `confidence` proxy and fixing a 1B gap), and a `count ≤ pages` cap on manual overrides for document-counting cells — with page counts computed lazily.

**Architecture:** Backend-first. A pure module-level `file_origin` helper (extracted from the `_origin_for` closure) becomes the single source of the per-file chip vocabulary, reused by a `compute_settled` reliability calculator. A lazy `cell_page_counts` helper centralizes "open PDFs and count pages." A synchronous `apply-ratio` endpoint reuses 1A's per-file merge. The frontend green dot reads `cell.all_reliable` with a fallback to 1B's logic for un-migrated cells. Validation caps are enforced authoritatively in the backend and previewed live in the frontend.

**Tech Stack:** Python 3.10+, FastAPI, PyMuPDF (`fitz`), pytest (real fixtures, no DB mocking); React 18, Zustand, Vitest (no React Testing Library — UI verified by build + conducted chrome-devtools smoke), Tailwind `po-*` tokens.

**Spec:** `docs/superpowers/specs/2026-06-15-incremento-2-rn-bloque-tope-design.md`

**Guardrails:** `ruff check .` must be 0 before commit. No `core/{pipeline,ocr,inference,image}.py` or `vlm/*.py` edits → no version-tag bump needed. No `shell=True`, no SQL f-strings, no bare `except`, no `print()` in libs.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `api/routes/sessions.py` | `file_origin` (module-level pure); `_origin_for`→thin wrapper + RN; `cell_page_counts` (lazy, DRY with `get_cell_files`); `compute_settled`; `refresh_all_reliable` helper; `apply-ratio` endpoint; cap in `patch_override` + `patch_per_file_override`; `all_reliable` recompute in `_apply_scan_event` cell_done | Modify |
| `api/state.py` | `set_all_reliable` setter; `apply_filename_result` sets `all_reliable` from confidence | Modify |
| `tests/unit/api/test_file_origin.py` | truth table for `file_origin` | Create |
| `tests/unit/api/test_compute_settled.py` | `compute_settled` cases | Create |
| `tests/integration/test_apply_ratio.py` | RN endpoint against real fixture PDFs | Create |
| `tests/unit/api/test_override_cap.py` | ≤pages cap (cell + per-file) | Create |
| `frontend/src/lib/cell-status.js` | `isCellReady` = `confirmed \|\| hasOverride \|\| (all_reliable ?? legacy)` | Modify |
| `frontend/src/lib/cell-status.test.js` | new `all_reliable` cases + legacy fallback intact | Modify |
| `frontend/src/lib/override-input.js` | `parseOverrideInput(raw, { maxPages })` | Modify |
| `frontend/src/lib/override-input.test.js` | maxPages cases | Modify |
| `frontend/src/components/OriginChip.jsx` | `RN` tone | Modify |
| `frontend/src/lib/file-origin.js` | (no-op) RN covered by default branch — test only | Modify (test) |
| `frontend/src/lib/api.js` | `applyRatio(sessionId, hospital, sigla, n)` | Modify |
| `frontend/src/components/DetailPanel.jsx` | block-action cluster (Por archivos); pass `maxPages`+`countType` to OverridePanel | Modify |
| `frontend/src/components/OverridePanel.jsx` | cap via `maxPages`/`countType` | Modify |
| `frontend/src/components/FileList.jsx` | per-file cap via `f.page_count` | Modify |

**Fixture note (Task 4):** the RN integration test needs a cell whose folder has at least one **multipage** PDF (origin "Pendiente") plus one 1-page PDF (origin "R1", must stay untouched). Check `data/samples/` and existing fixtures (`tests/integration/test_scan_ocr_full.py` builds cells with real PDFs — mirror its setup). If no suitable multipage sample exists, build a tiny 3-page PDF with `fitz` in a `tmp_path` fixture. Never fabricate counts — derive expectations from the real page counts.

---

## Chunk 1: Backend — helpers, RN endpoint, reliability, cap

### Task 1: Extract `file_origin` (pure) + add RN chip

**Files:**
- Modify: `api/routes/sessions.py` (the `_origin_for` closure inside `get_cell_files`, ~lines 596–634)
- Test: `tests/unit/api/test_file_origin.py` (create)

Context: `_origin_for` is a nested closure capturing `per_file_method` and `cell_method`. Extract the decision into a module-level pure function with explicit params; `_origin_for` becomes a thin wrapper that resolves the per-file method and delegates. This lets `compute_settled` (Task 3) reuse the exact same chip semantics.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/api/test_file_origin.py`:

```python
from api.routes.sessions import file_origin


def test_manual_override_wins():
    assert file_origin(method="v4", override=3, page_count=10, per_file_count=0) == "Manual"
    assert file_origin(method="filename_glob", override=0, page_count=1, per_file_count=1) == "Manual"


def test_unreadable_is_error():
    assert file_origin(method="filename_glob", override=None, page_count=0, per_file_count=None) == "Error"


def test_ocr_methods():
    for m in ("header_detect", "corner_count", "header_band_anchors", "v4"):
        assert file_origin(method=m, override=None, page_count=5, per_file_count=2) == "OCR"
        assert file_origin(method=m, override=None, page_count=5, per_file_count=0) == "Revisar"


def test_ratio_n_is_rn():
    assert file_origin(method="ratio_n", override=None, page_count=10, per_file_count=5) == "RN"


def test_page_count_pure_is_r1():
    assert file_origin(method="page_count_pure", override=None, page_count=3, per_file_count=3) == "R1"


def test_filename_glob_r1_vs_pendiente():
    assert file_origin(method="filename_glob", override=None, page_count=1, per_file_count=1) == "R1"
    assert file_origin(method="filename_glob", override=None, page_count=8, per_file_count=None) == "Pendiente"


def test_unknown_defaults_r1():
    assert file_origin(method="something_else", override=None, page_count=2, per_file_count=1) == "R1"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/api/test_file_origin.py -v`
Expected: FAIL — `ImportError: cannot import name 'file_origin'`.

- [ ] **Step 3: Implement `file_origin` + refactor `_origin_for`**

In `api/routes/sessions.py`, add at module level (near the other helpers, before `get_cell_files`):

```python
_OCR_METHODS = ("header_detect", "corner_count", "header_band_anchors", "v4")


def file_origin(
    *,
    method: str | None,
    override: int | None,
    page_count: int,
    per_file_count: int | None,
) -> str:
    """Per-file chip vocabulary (single source — reused by _origin_for and
    compute_settled). Priority: Manual override > unreadable Error > OCR/Revisar >
    RN (ratio_n) > R1 (page_count_pure) > R1/Pendiente (filename_glob by page count)
    > R1 default.
    """
    if override is not None:
        return "Manual"
    if page_count == 0:  # unreadable PDF
        return "Error"
    if method in _OCR_METHODS:
        return "Revisar" if per_file_count == 0 else "OCR"
    if method == "ratio_n":
        return "RN"
    if method == "page_count_pure":
        return "R1"
    if method == "filename_glob":
        return "R1" if page_count == 1 else "Pendiente"
    return "R1"
```

Then replace the body of the nested `_origin_for` (inside `get_cell_files`) so it delegates:

```python
    def _origin_for(filename, override, page_count, per_file_count):
        method = per_file_method.get(filename) or cell_method
        return file_origin(
            method=method,
            override=override,
            page_count=page_count,
            per_file_count=per_file_count,
        )
```

(Keep the existing call sites of `_origin_for(...)` unchanged.)

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/api/test_file_origin.py -v` → PASS.
Run: `pytest tests/unit/api/ -q` → existing `get_cell_files`-related tests still PASS (no behavior change).

- [ ] **Step 5: Commit**

```bash
git add api/routes/sessions.py tests/unit/api/test_file_origin.py
git commit -m "refactor(2): extract file_origin pure helper + add RN chip (ratio_n)"
```

---

### Task 2: `cell_page_counts` lazy helper (DRY with `get_cell_files`)

**Files:**
- Modify: `api/routes/sessions.py` (`get_cell_files` page-count loop, ~lines 637–641)

Context: `get_cell_files` opens each PDF with `fitz` to read `page_count`. Extract that into a reusable `cell_page_counts(folder) -> dict[str, int]` so RN, the cap, and `compute_settled` share one lazy implementation. Keyed by PDF `.name` (bare filename), matching how `per_file` is keyed.

- [ ] **Step 1: Add the helper**

In `api/routes/sessions.py` (module level):

```python
def cell_page_counts(folder: Path) -> dict[str, int]:
    """Lazy per-file page counts for a cell's folder: {pdf.name: page_count}.
    0 when a PDF can't be opened. Today reads from disk; the Incr-J persistence
    (per_file_pages) would slot in here without touching callers.
    """
    out: dict[str, int] = {}
    for pdf in sorted(folder.rglob("*.pdf")):
        try:
            with fitz.open(pdf) as doc:
                out[pdf.name] = doc.page_count
        except Exception:  # noqa: BLE001 — any fitz/IO failure → unreadable (0)
            out[pdf.name] = 0
    return out
```

- [ ] **Step 2: Use it in `get_cell_files`**

Replace the inline `with fitz.open(pdf) as doc: page_count = doc.page_count` loop in `get_cell_files` so it calls `pages = cell_page_counts(folder)` once and reads `pages.get(pdf.name, 0)` per file. Keep all other per-file fields identical.

- [ ] **Step 3: Run to verify no regression**

Run: `pytest tests/unit/api/ tests/integration/ -q -k "files or cell"` → PASS (the file-list response shape is unchanged).

- [ ] **Step 4: Commit**

```bash
git add api/routes/sessions.py
git commit -m "refactor(2): extract cell_page_counts lazy helper (DRY get_cell_files)"
```

---

### Task 3: `compute_settled` + `all_reliable` setter + pase-1 shortcut

**Files:**
- Modify: `api/routes/sessions.py` (add `compute_settled`)
- Modify: `api/state.py` (`set_all_reliable`; `apply_filename_result` sets `all_reliable`)
- Test: `tests/unit/api/test_compute_settled.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/api/test_compute_settled.py`. `compute_settled(cell, folder)` opens PDFs, so build a real folder with `fitz`:

```python
import fitz
from api.routes.sessions import compute_settled


def _make_pdf(path, n_pages):
    doc = fitz.open()
    for _ in range(n_pages):
        doc.new_page()
    doc.save(str(path))
    doc.close()


def test_all_r1_single_page_is_settled(tmp_path):
    _make_pdf(tmp_path / "a.pdf", 1)
    _make_pdf(tmp_path / "b.pdf", 1)
    cell = {"per_file": {"a.pdf": 1, "b.pdf": 1},
            "per_file_method": {"a.pdf": "filename_glob", "b.pdf": "filename_glob"},
            "per_file_overrides": {}, "method": "filename_glob"}
    assert compute_settled(cell, tmp_path) is True


def test_a_pending_multipage_is_not_settled(tmp_path):
    _make_pdf(tmp_path / "a.pdf", 1)
    _make_pdf(tmp_path / "big.pdf", 8)  # filename_glob multipage → Pendiente
    cell = {"per_file": {"a.pdf": 1, "big.pdf": 1},
            "per_file_method": {"a.pdf": "filename_glob", "big.pdf": "filename_glob"},
            "per_file_overrides": {}, "method": "filename_glob"}
    assert compute_settled(cell, tmp_path) is False


def test_ocr_file_is_not_settled(tmp_path):
    _make_pdf(tmp_path / "a.pdf", 5)
    cell = {"per_file": {"a.pdf": 2}, "per_file_method": {"a.pdf": "v4"},
            "per_file_overrides": {}, "method": "v4"}
    assert compute_settled(cell, tmp_path) is False


def test_ratio_n_is_settled(tmp_path):
    _make_pdf(tmp_path / "big.pdf", 8)
    cell = {"per_file": {"big.pdf": 4}, "per_file_method": {"big.pdf": "ratio_n"},
            "per_file_overrides": {}, "method": "filename_glob"}
    assert compute_settled(cell, tmp_path) is True


def test_pending_overridden_per_file_is_settled(tmp_path):
    _make_pdf(tmp_path / "big.pdf", 8)
    cell = {"per_file": {"big.pdf": 1}, "per_file_method": {"big.pdf": "filename_glob"},
            "per_file_overrides": {"big.pdf": 3}, "method": "filename_glob"}
    assert compute_settled(cell, tmp_path) is True  # Manual via per-file override


def test_empty_folder_is_not_settled(tmp_path):
    cell = {"per_file": {}, "per_file_method": {}, "per_file_overrides": {}, "method": "filename_glob"}
    assert compute_settled(cell, tmp_path) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/api/test_compute_settled.py -v` → FAIL (ImportError).

- [ ] **Step 3: Implement `compute_settled`**

In `api/routes/sessions.py` (module level):

```python
def compute_settled(cell: dict, folder: Path) -> bool:
    """True iff every PDF in *folder* is reliable (origin ∈ {R1, RN, Manual}).
    Empty/missing folder → False (a cell with no files is not 'listo'). Lazy pages.
    """
    pages = cell_page_counts(folder)
    files = sorted(folder.rglob("*.pdf"))
    if not files:
        return False
    per_file = cell.get("per_file") or {}
    per_file_method = cell.get("per_file_method") or {}
    per_file_overrides = cell.get("per_file_overrides") or {}
    cell_method = cell.get("method") or "filename_glob"
    for f in files:
        origin = file_origin(
            method=per_file_method.get(f.name) or cell_method,
            override=per_file_overrides.get(f.name),
            page_count=pages.get(f.name, 0),
            per_file_count=per_file.get(f.name),
        )
        if origin not in ("R1", "RN", "Manual"):
            return False
    return True
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/api/test_compute_settled.py -v` → PASS.

- [ ] **Step 5: Add `set_all_reliable` + pase-1 shortcut in `state.py`**

In `api/state.py`, add a setter method (decorate with `@_synchronized` like the others):

```python
@_synchronized
def set_all_reliable(self, session_id: str, hospital: str, sigla: str, value: bool) -> None:
    """Persist the honest 'all files reliable' flag for the green dot (Incr 2 §6)."""
    state, _ = self._load_and_migrate(session_id)
    cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
    cell["all_reliable"] = bool(value)
    update_session_state(self._conn, session_id, state_json=json.dumps(state))
```

In `apply_filename_result`, after line 214 (`cell["per_file_method"] = ...`), add the cheap shortcut (no PDF I/O — the scanner already determined all-1-page via confidence):

```python
        # all_reliable shortcut (Incr 2 §6.3): HIGH ⟺ every filename_glob file is
        # single-page (= all R1) for the non-OCR scanners. bool(per_file) guards the
        # empty/missing-folder case (simple_factory returns HIGH + per_file={}) so a
        # cell with no PDFs is NOT 'listo', matching compute_settled.
        cell["all_reliable"] = (result.confidence.value == "high" and bool(result.per_file))
```

Also add `cell.setdefault("all_reliable", False)` to the other `setdefault` blocks in `apply_filename_result` (the early-return path ~line 199 area and the tail ~226) and in `finalize_cell_ocr` (~line 333) so the field always exists.

- [ ] **Step 6: Run the suite**

Run: `pytest tests/unit/api/ -q` → PASS (new + existing).
Run: `ruff check api/` → 0 violations.

- [ ] **Step 7: Commit**

```bash
git add api/routes/sessions.py api/state.py tests/unit/api/test_compute_settled.py
git commit -m "feat(2): compute_settled + all_reliable signal (honest green dot foundation)"
```

---

### Task 4: `apply-ratio` endpoint (RN + Apply R1)

**Files:**
- Modify: `api/routes/sessions.py` (new endpoint + `refresh_all_reliable` helper)
- Test: `tests/integration/test_apply_ratio.py` (create)

Context: synchronous endpoint. For each **Pendiente** file, set `round(pages/N)` via 1A's `apply_per_file_ocr_result(..., method="ratio_n", near_matches=[])`, then `finalize_cell_ocr`, then recompute `all_reliable`. Reuses the clobber-guard by skipping any file whose current origin ≠ "Pendiente".

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/test_apply_ratio.py`. Mirror the session/fixture setup of `tests/integration/test_scan_ocr_full.py` (real `SessionManager`, a real month folder with PDFs). Build a cell folder with one 1-page PDF (`a.pdf`) and one 8-page PDF (`big.pdf`); run pase-1 (filename scan) so `a.pdf`→R1, `big.pdf`→Pendiente; then POST apply-ratio n=2.

```python
def test_apply_ratio_treats_pending_only(client, session_with_pending_cell):
    sid, hosp, sigla = session_with_pending_cell  # a.pdf=1pg (R1), big.pdf=8pg (Pendiente)
    r = client.post(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/apply-ratio", json={"n": 2})
    assert r.status_code == 200
    files = client.get(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/files").json()
    by_name = {f["name"]: f for f in files}
    assert by_name["big.pdf"]["origin"] == "RN"
    assert by_name["big.pdf"]["per_file_count"] == 4   # round(8/2)
    assert by_name["a.pdf"]["origin"] == "R1"          # untouched
    assert by_name["a.pdf"]["per_file_count"] == 1

def test_apply_r1_is_ratio_n1(client, session_with_pending_cell):
    sid, hosp, sigla = session_with_pending_cell
    client.post(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/apply-ratio", json={"n": 1})
    files = {f["name"]: f for f in client.get(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/files").json()}
    assert files["big.pdf"]["per_file_count"] == 8     # each page a document
    assert files["big.pdf"]["origin"] == "RN"

def test_ratio_lights_green(client, session_with_pending_cell):
    sid, hosp, sigla = session_with_pending_cell
    client.post(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/apply-ratio", json={"n": 2})
    state = client.get(f"/api/sessions/{sid}").json()
    assert state["cells"][hosp][sigla]["all_reliable"] is True
```

(Define the `session_with_pending_cell` fixture in the test module or `conftest.py`, mirroring the existing integration fixtures. Build PDFs with `fitz` in a tmp month dir; never fabricate counts.)

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/integration/test_apply_ratio.py -v` → FAIL (404, endpoint missing).

- [ ] **Step 3: Implement the endpoint + `refresh_all_reliable`**

In `api/routes/sessions.py`:

```python
def refresh_all_reliable(mgr, session_id: str, hospital: str, sigla: str, folder: Path) -> None:
    """Recompute and persist all_reliable after an interactive per-file mutation."""
    state = mgr.get_session_state(session_id)
    cell = state["cells"][hospital][sigla]
    mgr.set_all_reliable(session_id, hospital, sigla, compute_settled(cell, folder))


class ApplyRatioRequest(BaseModel):
    n: int = Field(ge=1)


@router.post("/sessions/{session_id}/cells/{hospital}/{sigla}/apply-ratio")
def apply_ratio(session_id, hospital, sigla, body: ApplyRatioRequest,
                mgr: SessionManager = Depends(get_manager)) -> dict:
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    cell = state["cells"].get(hospital, {}).get(sigla)
    if cell is None:
        raise HTTPException(404, f"Cell not found: {hospital}/{sigla}")
    month_root = Path(state.get("month_root", ""))
    folder = _find_category_folder(month_root / hospital, sigla)
    if not folder.exists():
        raise HTTPException(404, "Cell folder not found")
    pages = cell_page_counts(folder)
    per_file = cell.get("per_file") or {}
    per_file_method = cell.get("per_file_method") or {}
    per_file_overrides = cell.get("per_file_overrides") or {}
    cell_method = cell.get("method") or "filename_glob"
    n = body.n
    for pdf in sorted(folder.rglob("*.pdf")):
        origin = file_origin(
            method=per_file_method.get(pdf.name) or cell_method,
            override=per_file_overrides.get(pdf.name),
            page_count=pages.get(pdf.name, 0),
            per_file_count=per_file.get(pdf.name),
        )
        if origin != "Pendiente":
            continue  # clobber-guard: only untouched multipage files
        count = max(1, round(pages.get(pdf.name, 0) / n))
        mgr.apply_per_file_ocr_result(
            session_id, hospital, sigla, pdf.name,
            count=count, method="ratio_n", near_matches=[],
        )
    # finalize metadata (ocr_count = sum per_file) using a lightweight ScanResult
    mgr.finalize_cell_ocr(session_id, hospital, sigla, _ratio_finalize_result(cell_method))
    refresh_all_reliable(mgr, session_id, hospital, sigla, folder)
    state = mgr.get_session_state(session_id)
    return state["cells"][hospital][sigla]
```

For `_ratio_finalize_result`: `finalize_cell_ocr` only reads `result.method/confidence/breakdown/flags/errors/duration_ms`. Build a minimal `ScanResult` (import from `core.scanners.base`) with `method=cell_method` (or `"ratio_n"`), `confidence=ConfidenceLevel.LOW` (the dot is driven by `all_reliable`, not this), empty flags/errors, `duration_ms=0`, `per_file={}` (ignored). Verify the exact required fields against `core/scanners/base.py:ScanResult` and the `finalize_cell_ocr` body before constructing.

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/integration/test_apply_ratio.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add api/routes/sessions.py tests/integration/test_apply_ratio.py
git commit -m "feat(2): apply-ratio endpoint (RN + Apply R1), pending-only, lights green"
```

---

### Task 5: Recompute `all_reliable` on OCR finalize + per-file override

**Files:**
- Modify: `api/routes/sessions.py` (`_apply_scan_event` cell_done branch; `patch_per_file_override`)

Context: reliability also changes when OCR finishes a cell and when a per-file override is set. Both must refresh `all_reliable` (OCR → typically False; overriding all pendings → True, the 1B gap fix).

- [ ] **Step 1: Write the failing test**

Add to `tests/integration/test_apply_ratio.py` (or a sibling): override the lone pending file per-file and assert the cell becomes settled.

```python
def test_per_file_override_of_all_pendings_lights_green(client, session_with_pending_cell):
    sid, hosp, sigla = session_with_pending_cell  # a.pdf=R1, big.pdf=Pendiente
    client.patch(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/files/big.pdf/override", json={"count": 3})
    state = client.get(f"/api/sessions/{sid}").json()
    assert state["cells"][hosp][sigla]["all_reliable"] is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/integration/test_apply_ratio.py::test_per_file_override_of_all_pendings_lights_green -v`
Expected: FAIL (all_reliable still False — not recomputed after per-file override).

- [ ] **Step 3: Wire the recompute**

In `patch_per_file_override` (after `apply_per_file_override`, before building the response): resolve the folder (`month_root/hospital` → `_find_category_folder`) and call `refresh_all_reliable(mgr, session_id, hospital, sigla, folder)`.

In `_apply_scan_event`, the `cell_done` branch (after `finalize_cell_ocr`): resolve the folder from the session's `month_root` + event hospital/sigla and call `refresh_all_reliable(...)`. (If `_apply_scan_event` lacks `month_root`, read it from `mgr.get_session_state(session_id)["month_root"]`.)

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/integration/test_apply_ratio.py -v` → PASS.
Run: `pytest tests/integration/test_scan_ocr_full.py -v` → still PASS (OCR finalize now also sets all_reliable=False for OCR cells; assert it doesn't break the existing flow — if that test checks the dot/confidence, confirm it tolerates the new field).

- [ ] **Step 5: Commit**

```bash
git add api/routes/sessions.py tests/integration/test_apply_ratio.py
git commit -m "feat(2): recompute all_reliable on OCR finalize + per-file override (1B gap fix)"
```

---

### Task 6: `≤ pages` cap (cell + per-file)

**Files:**
- Modify: `api/routes/sessions.py` (`patch_override`, `patch_per_file_override`)
- Test: `tests/unit/api/test_override_cap.py` (create)

Context: cap applies to the **document count** of `count_type in {"documents","documents_workers"}` siglas. `checks` (maquinaria) is exempt. `count_type_for` is importable from `core.scanners.patterns`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/api/test_override_cap.py` (integration-style with a real cell folder; reuse the apply-ratio fixture pattern). A documents sigla with total pages = 9 (a.pdf 1 + big.pdf 8):

```python
def test_cell_override_capped_for_documents(client, session_with_pending_cell):
    sid, hosp, sigla = session_with_pending_cell  # assume sigla is a 'documents' sigla, total pages 9
    r = client.patch(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/override", json={"value": 50})
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "count_exceeds_pages"
    r_ok = client.patch(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/override", json={"value": 9})
    assert r_ok.status_code == 200

def test_per_file_override_capped(client, session_with_pending_cell):
    sid, hosp, sigla = session_with_pending_cell
    r = client.patch(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/files/big.pdf/override", json={"count": 99})
    assert r.status_code == 422  # big.pdf has 8 pages

def test_checks_sigla_uncapped(client, session_with_checks_cell):
    sid, hosp, sigla = session_with_checks_cell  # maquinaria
    r = client.patch(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/override", json={"value": 9999})
    assert r.status_code == 200
```

(Pick the fixture's sigla deliberately: use a `documents` sigla for the cap tests and `maquinaria` for the uncapped test. Verify each sigla's `count_type` via `count_type_for` when building the fixture.)

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/api/test_override_cap.py -v` → FAIL (currently 200/no cap).

- [ ] **Step 3: Implement the cap**

Add a module-level predicate + helper in `sessions.py`:

```python
from core.scanners.patterns import count_type_for

def _is_capped_sigla(sigla: str) -> bool:
    return count_type_for(sigla) in ("documents", "documents_workers")

def _cell_total_pages(state: dict, hospital: str, sigla: str) -> int:
    month_root = Path(state.get("month_root", ""))
    folder = _find_category_folder(month_root / hospital, sigla)
    return sum(cell_page_counts(folder).values()) if folder.exists() else 0
```

In `patch_override`, after the existing `0 ≤ value ≤ _MAX_REASONABLE_COUNT` check and before `apply_user_override`:

```python
    if value is not None and _is_capped_sigla(sigla):
        state = mgr.get_session_state(session_id)
        total = _cell_total_pages(state, hospital, sigla)
        if value > total:
            raise HTTPException(422, {"error": "count_exceeds_pages", "max": total})
```

In `patch_per_file_override`, before `apply_per_file_override`:

```python
    if _is_capped_sigla(sigla):
        state = mgr.get_session_state(session_id)
        month_root = Path(state.get("month_root", ""))
        folder = _find_category_folder(month_root / hospital, sigla)
        pages = cell_page_counts(folder).get(filename, 0)
        if body.count > pages:
            raise HTTPException(422, {"error": "count_exceeds_pages", "max": pages})
```

(Confirm `HTTPException(422, detail_dict)` serializes as `{"detail": {...}}` — FastAPI wraps `detail`. Adjust the test's `.json()["detail"]["error"]` accordingly, which it already does.)

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/api/test_override_cap.py -v` → PASS.
Run: `pytest tests/ -q -k "override"` → existing override tests still PASS (non-documents or within-bounds unaffected).

- [ ] **Step 5: Commit**

```bash
git add api/routes/sessions.py tests/unit/api/test_override_cap.py
git commit -m "feat(2): count<=pages cap on cell + per-file overrides (documents/_workers only)"
```

---

### Task 7: Backend chunk verification

- [ ] **Step 1:** `ruff check .` → 0 violations.
- [ ] **Step 2:** `pytest tests/unit/api tests/integration/test_apply_ratio.py -q` → all green.
- [ ] **Step 3:** Confirm no `core/{pipeline,ocr,inference,image}.py` / `vlm/*.py` were touched (no version bump needed): `git diff --name-only incremento-1b..HEAD | grep -E 'core/(pipeline|ocr|inference|image)\.py|vlm/' || echo "clean"`.

---

## Chunk 2: Frontend — honest dot, RN chip, cluster, cap

### Task 8: `cell-status.js` reads `all_reliable` with legacy fallback

**Files:**
- Modify: `frontend/src/lib/cell-status.js`
- Test: `frontend/src/lib/cell-status.test.js`

- [ ] **Step 1: Write the failing tests** (append to the existing file)

```js
describe("isCellReady (Incr 2 — all_reliable signal)", () => {
  it("all_reliable true -> ready", () => {
    expect(isCellReady({ all_reliable: true })).toBe(true);
  });
  it("all_reliable false -> not ready (even if confidence high)", () => {
    expect(isCellReady({ all_reliable: false, confidence: "high" })).toBe(false);
  });
  it("all_reliable absent -> falls back to 1B legacy rule", () => {
    // legacy: confidence high + no unreliable OCR file
    expect(isCellReady({ confidence: "high", per_file_method: { "a.pdf": "filename_glob" } })).toBe(true);
    expect(isCellReady({ confidence: "high", per_file_method: { "a.pdf": "v4" } })).toBe(false);
  });
  it("confirmed / cell override still win regardless of all_reliable", () => {
    expect(isCellReady({ all_reliable: false, confirmed: true })).toBe(true);
    expect(isCellReady({ all_reliable: false, user_override: 5 })).toBe(true);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/lib/cell-status.test.js` → FAIL (all_reliable not consulted).

- [ ] **Step 3: Implement**

In `frontend/src/lib/cell-status.js`, rename the current reliability check to `legacyAllReliable` and have `isCellReady` prefer `all_reliable`:

```js
// 1B fallback for cells not yet migrated to the backend all_reliable signal
// (e.g. MAYO scanned before Incr 2). Identical to 1B's behavior.
export function legacyAllReliable(cell) {
  return cell?.confidence === "high" && !anyUnreliableOcrFile(cell);
}

export function isCellReady(cell) {
  if (!!cell?.confirmed || hasOverride(cell)) return true;
  return cell?.all_reliable ?? legacyAllReliable(cell);
}
```

Keep `OCR_METHODS`, `anyUnreliableOcrFile`, `hasOverride`, `dotVariantFor` unchanged. (Rename `allFilesReliable`→`legacyAllReliable`; update its one internal caller / export.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npx vitest run src/lib/cell-status.test.js` → PASS (new + existing 1B cases).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/cell-status.js frontend/src/lib/cell-status.test.js
git commit -m "feat(2): green dot reads backend all_reliable, legacy 1B fallback"
```

---

### Task 9: `parseOverrideInput` page cap + `RN` chip

**Files:**
- Modify: `frontend/src/lib/override-input.js` + test
- Modify: `frontend/src/components/OriginChip.jsx`
- Modify: `frontend/src/lib/file-origin.js` test only (RN already covered)

- [ ] **Step 1: Write failing tests**

`override-input.test.js` (append):

```js
describe("parseOverrideInput maxPages cap", () => {
  it("rejects value above maxPages", () => {
    expect(parseOverrideInput("10", { maxPages: 8 })).toEqual({ value: null, valid: false });
  });
  it("accepts value equal to maxPages", () => {
    expect(parseOverrideInput("8", { maxPages: 8 })).toEqual({ value: 8, valid: true });
  });
  it("no maxPages -> unchanged 1B behavior", () => {
    expect(parseOverrideInput("9999")).toEqual({ value: 9999, valid: true });
  });
});
```

`file-origin.test.js` (find or create `frontend/src/lib/__tests__/file-origin.test.js`): add `expect(fileCountDisplay("RN", 4)).toEqual({ value: 4, placeholder: undefined })`.

- [ ] **Step 2: Run to verify they fail**

Run: `cd frontend && npx vitest run src/lib/override-input.test.js` → FAIL.

- [ ] **Step 3: Implement**

`override-input.js` — add optional opts:

```js
export function parseOverrideInput(raw, { maxPages = null } = {}) {
  if (raw === "" || raw === null || raw === undefined) return { value: null, valid: true };
  const n = Number(raw);
  if (!Number.isInteger(n) || n < 0) return { value: null, valid: false };
  if (maxPages != null && n > maxPages) return { value: null, valid: false };
  return { value: n, valid: true };
}
```

`OriginChip.jsx` — add `RN` to `ORIGIN_VARIANT`. Verify available `Badge` tones in `frontend/src/ui/Badge.jsx`; pick a reliable-but-distinct tone (e.g. a teal/green that isn't `jade`=R1 or `iris`=OCR). If no distinct reliable tone exists, reuse `"jade"` (the "RN" text distinguishes it from R1) — do NOT introduce a raw color token.

- [ ] **Step 4: Run to verify they pass**

Run: `cd frontend && npx vitest run src/lib/override-input.test.js src/lib/__tests__/file-origin.test.js` → PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/override-input.js frontend/src/lib/override-input.test.js frontend/src/components/OriginChip.jsx frontend/src/lib/__tests__/file-origin.test.js
git commit -m "feat(2): override maxPages cap + RN origin chip"
```

---

### Task 10: `api.js applyRatio` + UI (cluster, caps)

**Files:**
- Modify: `frontend/src/lib/api.js`, `frontend/src/components/DetailPanel.jsx`, `frontend/src/components/OverridePanel.jsx`, `frontend/src/components/FileList.jsx`

Verified by build + smoke (Task 11), not unit tests.

- [ ] **Step 1: `api.js`** — add `applyRatio`:

```js
applyRatio: (sessionId, hospital, sigla, n) =>
  postJson(`/api/sessions/${sessionId}/cells/${hospital}/${sigla}/apply-ratio`, { n }),
```

(Match the existing `api.js` request-helper style — find how other POSTs are written, e.g. `scanOcr`, and mirror it. Trigger the same `filesTick` refresh the per-file OCR uses so the FileList + dot update.)

- [ ] **Step 2: `DetailPanel.jsx`** — block-action cluster (Por archivos mode only):
  - Below the toggle / above "Conteo automático", render a row visible only when `mode === "files"`:
    - Button **"Aplicar R1"** → `api.applyRatio(sessionId, hospital, sigla, 1)` then refresh.
    - Button **"Aplicar ratio N…"** → reveals an inline number input (default 2, min 1) + a confirm button → `api.applyRatio(..., n)`.
  - Derive `totalPages` for the cap: fetch `api.getCellFiles(sessionId, hospital, sigla)` (same call FileList uses) and sum `page_count`, OR read it from a shared store value if one exists — keep it simple, a parallel fetch is acceptable. Pass `maxPages={countType-capped ? totalPages : null}` and `countType={scanInfo?.count_type}` to `OverridePanel`.
  - Capped predicate (frontend): `["documents","documents_workers"].includes(scanInfo?.count_type)`.

- [ ] **Step 3: `OverridePanel.jsx`** — accept `maxPages` + `countType`; pass `{ maxPages }` to `parseOverrideInput` in `onChangeValue` (only when capped). On cap rejection, reuse the existing `invalid` error-border path; show inline "máx. {maxPages} (páginas)".

- [ ] **Step 4: `FileList.jsx`** — for the per-file `InlineEditCount`, when the sigla is capped, clamp/validate against `f.page_count` (the row already has it). On over-cap entry, reject (don't save) with a visual cue. (If `InlineEditCount` doesn't support a max, pass one through; keep the change minimal.)

- [ ] **Step 5: Build**

Run: `cd frontend && npm run build` → succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api.js frontend/src/components/DetailPanel.jsx frontend/src/components/OverridePanel.jsx frontend/src/components/FileList.jsx
git commit -m "feat(2): RN/R1 block-action cluster + page caps in DetailPanel/OverridePanel/FileList"
```

---

### Task 11: Verification — suite + conducted smoke + tag

- [ ] **Step 1:** `cd frontend && npm test && npm run build` → all green.
- [ ] **Step 2:** `ruff check .` → 0; `pytest tests/unit/api tests/integration/test_apply_ratio.py -q` → green.
- [ ] **Step 3: Conducted smoke** (chrome-devtools, SANDBOX — back up `data/overseer.db` first like the 1B smoke, use a cell you restore; do NOT mutate real counted data without backup):
  1. A cell with a multipage Pendiente compilado → **"Aplicar ratio 2"** → that file shows chip **RN** with `round(pages/2)`; an R1/Manual file in the same cell is untouched; the cell dot goes **green**.
  2. **"Aplicar R1"** on a pending file → count == pages.
  3. In a `documents` cell, typing a manual count **> total pages** is rejected (cell-level); a per-file count **> that file's pages** is rejected. A `maquinaria` (checks) cell is **not** capped.
  4. Restore the cell (clear overrides / re-scan) and verify clean; keep the backup.
- [ ] **Step 4: Tag**

```bash
git tag incremento-2
```

(Push at end of round per convention: `git push origin po_overhaul --follow-tags && git push origin incremento-2`.)

---

## Out of scope (do not implement here)

- Persisting `per_file_pages` → Incr J (reorg manifest). RN-via-keyboard / maquinaria=checks counting → Incr 3. Multiplayer → after Incr J.
- "Smart" remainder distribution across files for RN rounding — simple per-file `round`, manual fix for exceptions (triage B-b caveat).
- A new per-cell "OCR this cell" trigger — Incr 2 only adds the two ratio actions; the existing OCR flow is unchanged.
