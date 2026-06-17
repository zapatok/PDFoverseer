# Incremento 3B — dif_pts worker count + N15 mapping — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the keyboard worker counter for `dif_pts` and route the Puerto Varas (HPV) dif_pts worker total into Excel cell N15 (HH-capacitación), with 0 (no formula fallback) when uncounted and a "pending" warning via the existing worker-warnings path.

**Architecture:** dif_pts is already `documents_workers` end-to-end (Incr 1A); the wiring is mostly existing. (1) Template: add named range `HPV_workers_difpts → N15` and clear N15's `=M15*0.5` formula to `0`. (2) Backend: a hospital-scoped constant `DIFPTS_WORKER_HOSPITALS = {"HPV"}` drives a new emission loop in `_build_worker_values` (always emits, 0 if uncounted) and a warning loop in `_build_worker_warnings`. (3) Frontend: flip the DetailPanel worker-module gate from a sigla-name list to a count_type predicate, tested via a pure helper (no component-test infra exists).

**Tech Stack:** Python 3.10+ / FastAPI / openpyxl (Excel), React + Vite / vitest (frontend). Tests: pytest with real fixtures (no DB mocking), vitest for pure JS.

**Spec:** `docs/superpowers/specs/2026-06-16-incremento-3b-difpts-workers-n15-design.md` (read it; decisions D1–D6 are authoritative).

---

## Conventions & pre-flight (read once)

- Work **directly on `po_overhaul`** (single active branch). No feature worktrees.
- `ruff check .` must be **0** before every commit. Hooks BLOCK: bare-except, `shell=True`, SQL f-strings; WARN: print() in libs, legacy typing. Python 3.10+ types (`X | None`, `list[X]`).
- **No version bump needed:** this plan does NOT touch `core/{pipeline,ocr,inference,image}.py` or `vlm/*` (the `bump-version-tags` hook only guards those).
- Commit messages: `type(scope): message`, English. **Last line verbatim:**
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **Task ordering is intentional:** Template (Chunk 1) → Backend (Chunk 2) → Frontend (Chunk 3) → Verify (Chunk 4). The backend writes to the `HPV_workers_difpts` named range; creating it first keeps every chunk's suite green.
- **Excel layout facts** (from `data/templates/build_template_v1.py`): `dif_pts` = **row 15**; HH columns `{HLL:H, HLU:J, HRB:L, HPV:N}`; cantidad columns `{HLL:G, HLU:I, HRB:K, HPV:M}`. So **N15 = HPV HH cell at the dif_pts row**, `M15 = HPV_dif_pts_count`. Current fila-15 HH formulas: `H15=G15*0.5, J15=I15*0.5, L15=K15*0.5, N15=M15*0.5`.
- **Worktree fact:** `compute_worker_count(cell, present_files)` sums `worker_marks` page counts; `present_files=None` → sums ALL marks (legacy), a set → filters to present files (F1 fix). `_build_worker_values`/`_build_worker_warnings` are pure-ish functions of `state` (warnings reads only `state["cells"]`; values also reads `state["month_root"]` for the present-files filter).

---

## Chunk 1: Template — `HPV_workers_difpts → N15` + clear formula

**Why first:** the backend (Chunk 2) writes this named range. Creating it now (and clearing N15) leaves the suite green and de-risks the binary-file edit before any logic depends on it.

### Task 1: Add the named range + clear N15 in the authoritative template

**Files:**
- Modify (binary): `data/templates/RESUMEN_template_v1.xlsx` (authoritative artifact — hand-patched; openpyxl round-trip risk, see protocol)
- Create: `tests/unit/test_template_difpts_n15.py`

> ⚠️ **Data-safety + round-trip risk.** The `.xlsx` carries hand-patches openpyxl may not round-trip (logo image, merges, number formats). The PreToolUse deliverable-guard hook does NOT fire on a subprocess/openpyxl write, so **back up manually**. After editing, **render-compare** against the backup and **assert the logo image survived** before trusting it. If anything regressed, revert to the backup and fall back to a surgical XML edit (see fallback note).

- [ ] **Step 1: Write the regression test (fails first)**

```python
# tests/unit/test_template_difpts_n15.py
"""Incr 3B: the template wires HPV dif_pts worker total to N15 (no =M15*0.5 fallback)."""
from pathlib import Path

import openpyxl

TEMPLATE = Path("data/templates/RESUMEN_template_v1.xlsx")


def _load():
    return openpyxl.load_workbook(TEMPLATE)


def test_hpv_workers_difpts_named_range_points_at_n15():
    wb = _load()
    assert "HPV_workers_difpts" in wb.defined_names
    dest = list(wb.defined_names["HPV_workers_difpts"].destinations)
    assert dest == [(wb.active.title, "$N$15")]


def test_n15_formula_cleared_to_zero():
    wb = _load()
    n15 = wb.active["N15"].value
    assert n15 != "=M15*0.5"
    assert n15 in (0, None) or isinstance(n15, (int, float))


def test_other_hospitals_row15_hh_formula_intact():
    wb = _load()
    ws = wb.active
    assert ws["H15"].value == "=G15*0.5"
    assert ws["J15"].value == "=I15*0.5"
    assert ws["L15"].value == "=K15*0.5"


def test_existing_named_ranges_intact():
    wb = _load()
    names = set(wb.defined_names)
    for n in ("HLL_dif_pts_count", "HPV_dif_pts_count",
              "HLL_workers_chgen", "HPV_workers_chintegral", "report_title"):
        assert n in names
    worker_ranges = sorted(n for n in names if "_workers_" in n)
    assert len(worker_ranges) == 9  # 8 chgen/chintegral + HPV_workers_difpts


def test_logo_image_survived_round_trip():
    wb = _load()
    # The constructora logo (B2) must survive any openpyxl re-save.
    assert len(wb.active._images) >= 1
```

- [ ] **Step 2: Run → verify it fails**

Run: `pytest tests/unit/test_template_difpts_n15.py -v`
Expected: FAIL (`HPV_workers_difpts` not in defined_names; N15 == "=M15*0.5"; 8 worker ranges).

- [ ] **Step 3: Back up the template (dated)**

Run:
```bash
cp data/templates/RESUMEN_template_v1.xlsx \
   "data/templates/RESUMEN_template_v1.xlsx.bak-$(date +%Y%m%d-%H%M%S)"
```

- [ ] **Step 4: Apply the edit via openpyxl (one-off script)**

Run this exact Python (from project root):
```python
python - <<'PY'
import openpyxl
from openpyxl.workbook.defined_name import DefinedName

P = "data/templates/RESUMEN_template_v1.xlsx"
wb = openpyxl.load_workbook(P)
ws = wb.active
sheet = ws.title

# 1) Clear the =M15*0.5 fallback → explicit 0 (D2: uncounted HPV shows 0, never the estimate).
ws["N15"] = 0

# 2) Add the named range HPV_workers_difpts → $N$15 (the writer overwrites it with the
#    worker total when HPV dif_pts is counted; otherwise N15 stays at this 0).
name = "HPV_workers_difpts"
if name in wb.defined_names:
    del wb.defined_names[name]
wb.defined_names[name] = DefinedName(name=name, attr_text=f"'{sheet}'!$N$15")

wb.save(P)
print("OK: added", name, "and cleared N15")
PY
```

- [ ] **Step 5: Render-compare backup vs edited (logo/layout intact)**

Render both to PDF in a temp dir (never overwrite Daniel's real outputs) and eyeball them. See memory `reference_libreoffice_xlsx_render` for the soffice path/flags. Example:
```bash
soffice --headless --convert-to pdf --outdir /tmp/3b_after  data/templates/RESUMEN_template_v1.xlsx
soffice --headless --convert-to pdf --outdir /tmp/3b_before data/templates/RESUMEN_template_v1.xlsx.bak-*
```
Then Read both PDFs. Confirm: logo present, header merges, number formats, the table grid, and rows 13/14/15 look unchanged except N15 now blank/0. **If anything regressed, restore the backup and use the surgical XML fallback** (edit `xl/workbook.xml` `<definedNames>` to add the name + the sheet XML to clear N15), then re-render.

- [ ] **Step 6: Run the test → passes**

Run: `pytest tests/unit/test_template_difpts_n15.py -v`
Expected: PASS (all 5).

- [ ] **Step 7: Commit**

```bash
git add data/templates/RESUMEN_template_v1.xlsx tests/unit/test_template_difpts_n15.py
git commit -m "feat(excel): wire HPV dif_pts worker total to N15 (template)

Add named range HPV_workers_difpts -> N15 and clear the =M15*0.5
fallback to 0. The writer overwrites N15 with the counted worker
total; uncounted HPV shows an explicit 0 (Incr 3B, decision D2).
Other hospitals' row-15 HH formulas (H15/J15/L15) untouched.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
> The `.xlsx` backup `.bak-*` is gitignored/uncommitted — leave it on disk until the increment is verified, then it can be removed.

### Task 2: Sync the build recipe + `verify()` + enable-procedure docs

**Files:**
- Modify: `data/templates/build_template_v1.py` (recipe — NOT authoritative; best-effort sync)

- [ ] **Step 1: Update `build()` to clear N15 and add the named range**

In `build()`, after the workforce-named-range loop, add N15 handling. The fila-15 HH formulas are NOT set by the current script (only rows 13/14 are), so N15 currently inherits the sample's `=M15*0.5`. Add:
```python
    # Incr 3B: HPV dif_pts worker total goes to N15 directly (no =M15*0.5 fallback).
    ws["N15"] = 0
    _set_or_replace_name(wb, "HPV_workers_difpts", f"'{sheet_name}'!$N$15")
```
(Place it just before `wb.save(DST)`.)

- [ ] **Step 2: Update `verify()`**

Change the worker-range count assertion from 8 to 9 and add fila-15 assertions:
```python
    if len(worker_names) != 9:
        raise AssertionError(f"Expected 9 worker named ranges, got {len(worker_names)}")
    ...
    # Incr 3B: N15 is HPV dif_pts worker total (cleared formula); others keep docs×0.5.
    if wb.defined_names["HPV_workers_difpts"].attr_text != f"'{ws.title}'!$N$15":
        raise AssertionError("HPV_workers_difpts must point at $N$15")
    if ws["N15"].value == "=M15*0.5":
        raise AssertionError("N15 must NOT keep the =M15*0.5 fallback")
    for col, base in (("H", "G"), ("J", "I"), ("L", "K")):
        if ws[f"{col}15"].value != f"={base}15*0.5":
            raise AssertionError(f"{col}15 must keep ={base}15*0.5 (non-HPV unchanged)")
```

- [ ] **Step 3: Update the module docstring with the "enable another hospital" procedure**

Add to the docstring (the spec §9 / §4.2 procedure), so it is mechanical when Daniel asks:
```
To enable another hospital's dif_pts worker total → Excel (today only HPV):
  1. add the hospital to DIFPTS_WORKER_HOSPITALS in api/routes/output.py,
  2. add a named range {HOSP}_workers_difpts -> {HH_COL[hosp]}15 here,
  3. clear that cell's =col*0.5 formula (ws[f"{HH_COL[hosp]}15"] = 0).
Hospitals NOT enabled keep their docs×0.5 estimate.
```

- [ ] **Step 4: Lint + confirm the recipe is self-consistent (do NOT run with --force)**

Run: `ruff check data/templates/build_template_v1.py`
Expected: 0 violations. (Do NOT run `python build_template_v1.py --force` — it would rebuild from the sample and drop hand-patches; the authoritative `.xlsx` was already edited surgically in Task 1.)

- [ ] **Step 5: Commit**

```bash
git add data/templates/build_template_v1.py
git commit -m "chore(excel): sync build recipe with N15 dif_pts range + enable-hospital docs

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 2: Backend — hospital-scoped dif_pts emission + warning

### Task 3: `DIFPTS_WORKER_HOSPITALS` + emit `HPV_workers_difpts`

**Files:**
- Modify: `api/routes/output.py` (`_build_worker_values`, near the `WORKER_PURPOSE` block ~line 125-143)
- Test: `tests/unit/api/test_routes_output.py`

- [ ] **Step 1: Write failing tests (pure dict, no template needed)**

Append to `tests/unit/api/test_routes_output.py`:
```python
def test_build_worker_values_emits_difpts_for_hpv(tmp_path):
    from api.routes.output import _build_worker_values

    state = {
        "month_root": str(tmp_path / "nope"),  # non-existent → present=None → sum-all marks
        "cells": {
            "HPV": {"dif_pts": {"worker_marks": {
                "d1.pdf": [{"page": 1, "count": 12}, {"page": 2, "count": 8}]}}},
        },
    }
    assert _build_worker_values(state)["HPV_workers_difpts"] == 20


def test_build_worker_values_difpts_zero_when_uncounted(tmp_path):
    from api.routes.output import _build_worker_values

    state = {
        "month_root": str(tmp_path / "nope"),
        "cells": {"HPV": {"dif_pts": {"per_file": {"d1.pdf": 1}}}},  # no worker_marks
    }
    assert _build_worker_values(state)["HPV_workers_difpts"] == 0


def test_build_worker_values_difpts_not_emitted_for_non_hpv(tmp_path):
    from api.routes.output import _build_worker_values

    state = {
        "month_root": str(tmp_path / "nope"),
        "cells": {"HRB": {"dif_pts": {"worker_marks": {
            "d1.pdf": [{"page": 1, "count": 99}]}}}},
    }
    vals = _build_worker_values(state)
    assert "HRB_workers_difpts" not in vals
    assert "HPV_workers_difpts" not in vals  # HPV has no dif_pts cell here
```

- [ ] **Step 2: Run → verify it fails**

Run: `pytest tests/unit/api/test_routes_output.py -k difpts -v`
Expected: FAIL (`KeyError: 'HPV_workers_difpts'`).

- [ ] **Step 3: Implement the constant + emission loop**

In `api/routes/output.py`, add the constant next to `WORKER_PURPOSE` (after line 125):
```python
# dif_pts: el total de trabajadores va a la celda HH de su propia fila (fila 15),
# por hospital. HOY solo HPV (→ N15). Para HABILITAR otra obra "sin más":
#   1. añadirla a este set,
#   2. crear el rango {HOSP}_workers_difpts → {col_HH}15 en el template,
#   3. limpiar la fórmula =col*0.5 de esa celda (ver build_template_v1.py docstring).
# Las obras NO incluidas conservan su estimación docs×0.5 intacta.
DIFPTS_WORKER_HOSPITALS: frozenset[str] = frozenset({"HPV"})
```

In `_build_worker_values`, after the existing `for hosp, sigla_map in ...` loop (before `return out`), add:
```python
    # dif_pts (Incr 3B): worker total → HH cell of its own row, scoped to HPV.
    # Always emits (0 if uncounted) — NO "never counted → skip" guard (D2: explicit
    # 0, never the =M15*0.5 fallback). Do NOT harmonize with the charla/chintegral
    # loop above, which deliberately skips uncounted cells.
    for hosp in DIFPTS_WORKER_HOSPITALS:
        cell = state.get("cells", {}).get(hosp, {}).get("dif_pts")
        if cell is None:
            continue  # no dif_pts cell → N15 stays at the template's 0
        folder = _find_category_folder(month_root / hosp, "dif_pts")
        present = set(cell_page_counts(folder)) if folder.exists() else None
        out[f"{hosp}_workers_difpts"] = compute_worker_count(cell, present)
```

- [ ] **Step 4: Run → passes + lint**

Run: `pytest tests/unit/api/test_routes_output.py -k difpts -v && ruff check api/routes/output.py`
Expected: 3 PASS, 0 lint violations.

- [ ] **Step 5: Commit**

```bash
git add api/routes/output.py tests/unit/api/test_routes_output.py
git commit -m "feat(output): emit HPV dif_pts worker total to N15 (hospital-scoped)

DIFPTS_WORKER_HOSPITALS={HPV} drives a new emission loop: HPV dif_pts
worker total -> HPV_workers_difpts (always, 0 if uncounted). Other
hospitals are not emitted (viewer usable but unmapped). Incr 3B.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 4: Warn when HPV dif_pts worker count is pending

**Files:**
- Modify: `api/routes/output.py` (`_build_worker_warnings` ~line 146-168)
- Test: `tests/unit/api/test_routes_output.py`

- [ ] **Step 1: Write failing tests (pure dict)**

```python
def test_build_worker_warnings_flags_difpts_hpv():
    from api.routes.output import _build_worker_warnings

    state = {"cells": {"HPV": {"dif_pts": {"per_file": {"d1.pdf": 3}}}}}
    warned = {(w["hospital"], w["sigla"]) for w in _build_worker_warnings(state)}
    assert ("HPV", "dif_pts") in warned


def test_build_worker_warnings_difpts_silent_when_terminado():
    from api.routes.output import _build_worker_warnings

    state = {"cells": {"HPV": {"dif_pts": {
        "per_file": {"d1.pdf": 3}, "worker_status": "terminado"}}}}
    warned = {(w["hospital"], w["sigla"]) for w in _build_worker_warnings(state)}
    assert ("HPV", "dif_pts") not in warned


def test_build_worker_warnings_difpts_silent_for_non_hpv():
    from api.routes.output import _build_worker_warnings

    state = {"cells": {"HRB": {"dif_pts": {"per_file": {"d1.pdf": 3}}}}}
    warned = {(w["hospital"], w["sigla"]) for w in _build_worker_warnings(state)}
    assert ("HRB", "dif_pts") not in warned


def test_build_worker_warnings_difpts_silent_when_no_pdfs():
    from api.routes.output import _build_worker_warnings

    state = {"cells": {"HPV": {"dif_pts": {"worker_status": "en_progreso"}}}}
    warned = {(w["hospital"], w["sigla"]) for w in _build_worker_warnings(state)}
    assert ("HPV", "dif_pts") not in warned
```

- [ ] **Step 2: Run → verify it fails**

Run: `pytest tests/unit/api/test_routes_output.py -k "difpts and warnings" -v`
Expected: FAIL (`("HPV", "dif_pts")` not in warnings).

- [ ] **Step 3: Implement the warning loop**

In `_build_worker_warnings`, before `return out`, add:
```python
    # dif_pts (Incr 3B): warn HPV when worker count is pending. Same predicate as
    # charla/chintegral (has PDFs + not terminado), scoped to DIFPTS_WORKER_HOSPITALS.
    # The N15 = 0 / formula-cleared decision (D2) makes this warning load-bearing.
    for hosp in DIFPTS_WORKER_HOSPITALS:
        cell = state.get("cells", {}).get(hosp, {}).get("dif_pts")
        if cell and cell.get("per_file") and cell.get("worker_status") != "terminado":
            out.append({"hospital": hosp, "sigla": "dif_pts"})
```

- [ ] **Step 4: Run → passes + lint**

Run: `pytest tests/unit/api/test_routes_output.py -k difpts -v && ruff check api/routes/output.py`
Expected: 7 PASS (3 from Task 3 + 4 here), 0 lint.

- [ ] **Step 5: Commit**

```bash
git add api/routes/output.py tests/unit/api/test_routes_output.py
git commit -m "feat(output): warn on pending HPV dif_pts worker count

Reuses _build_worker_warnings (has PDFs + not terminado), scoped to
DIFPTS_WORKER_HOSPITALS. N15's 0/no-fallback makes the warning the
signal that HPV capacitación HH is uncounted. Incr 3B.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 5: End-to-end — generated Excel N15 == worker total

**Files:**
- Test: `tests/unit/api/test_routes_output.py` (uses the `client` fixture + real template)

- [ ] **Step 1: Write the failing test**

```python
def test_output_writes_difpts_total_to_n15(client, tmp_path, monkeypatch):
    """End-to-end: HPV dif_pts worker total lands in N15 via HPV_workers_difpts."""
    import openpyxl

    (tmp_path / "ABRIL").mkdir()
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))  # folder absent → sum-all
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    mgr = client.app.dependency_overrides[get_manager]()
    mgr.apply_worker_count(
        "2026-04", "HPV", "dif_pts",
        marks={"d1.pdf": [{"page": 1, "count": 7}, {"page": 2, "count": 5}]},
        status="terminado",
    )
    out = client.post("/api/sessions/2026-04/output", json={}).json()
    wb = openpyxl.load_workbook(out["output_path"])
    sheet, coord = list(wb.defined_names["HPV_workers_difpts"].destinations)[0]
    assert wb[sheet][coord].value == 12
```

- [ ] **Step 2: Run → passes**

Run: `pytest tests/unit/api/test_routes_output.py::test_output_writes_difpts_total_to_n15 -v`
Expected: PASS (the named range exists from Chunk 1; the emission from Task 3 lands 12 in N15).
> If this FAILS with "named range not found" in the output warnings, Chunk 1 was skipped — do Chunk 1 first.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/api/test_routes_output.py
git commit -m "test(output): e2e HPV dif_pts worker total reaches Excel N15

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 3: Frontend — count_type-driven worker-module gate

### Task 6: `showsWorkerCounter(countType)` helper + test

**Files:**
- Modify: `frontend/src/lib/cell-status.js`
- Test: `frontend/src/lib/cell-status.test.js`

> **Why a helper, not a render test:** the frontend has vitest only — no `@testing-library/react`/jsdom — so the gate logic is tested as a pure predicate. `cell-status.js` is the existing home for count_type-driven cell UI predicates (`isCellReady`, `dotVariantFor`).

- [ ] **Step 1: Write failing tests**

Append to `frontend/src/lib/cell-status.test.js`:
```js
import { showsWorkerCounter } from "./cell-status";

describe("showsWorkerCounter", () => {
  it("shows for documents_workers (charla/chintegral/dif_pts)", () => {
    expect(showsWorkerCounter("documents_workers")).toBe(true);
  });
  it("shows for checks (maquinaria)", () => {
    expect(showsWorkerCounter("checks")).toBe(true);
  });
  it("hides for plain documents", () => {
    expect(showsWorkerCounter("documents")).toBe(false);
  });
  it("hides for unknown/undefined count_type", () => {
    expect(showsWorkerCounter(undefined)).toBe(false);
  });
});
```

- [ ] **Step 2: Run → verify it fails**

Run: `cd frontend && npx vitest run src/lib/cell-status.test.js`
Expected: FAIL (`showsWorkerCounter is not a function`).

- [ ] **Step 3: Implement the helper**

Add to `frontend/src/lib/cell-status.js`:
```js
// Incr 3B: which DetailPanel counting module a cell's count_type implies.
// The worker/checks counter shows for documents_workers (charla/chintegral/dif_pts)
// and checks (maquinaria); plain documents siglas show only the document controls.
export const showsWorkerCounter = (countType) =>
  countType === "checks" || countType === "documents_workers";
```

- [ ] **Step 4: Run → passes**

Run: `cd frontend && npx vitest run src/lib/cell-status.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/cell-status.js frontend/src/lib/cell-status.test.js
git commit -m "feat(ui): showsWorkerCounter(countType) predicate for the detail module gate

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 7: Use the predicate in DetailPanel (dif_pts gets the counter)

**Files:**
- Modify: `frontend/src/components/DetailPanel.jsx` (import ~line 10; gate ~line 437-443)

- [ ] **Step 1: Add the import**

At the top imports, add (next to the existing `../lib/...` imports):
```jsx
import { showsWorkerCounter } from "../lib/cell-status";
```

- [ ] **Step 2: Replace the gate + comment**

Replace the block at lines 437-443:
```jsx
      {/* Worker/checks counting module: shown for charla/chintegral (workers) and
          checks (maquinaria). NOT dif_pts — it's documents_workers too but its HH/N15
          Excel wiring is deferred to Incr 3B; showing the counter without a destination
          would be a half-feature. Keep above near-match suspects. */}
      {(countType === "checks" || sigla === "charla" || sigla === "chintegral") && (
        <WorkerCountModule hospital={hospital} sigla={sigla} cell={cell} countType={countType} />
      )}
```
with:
```jsx
      {/* Worker/checks counting module: documents_workers (charla/chintegral/dif_pts)
          and checks (maquinaria). dif_pts wired to N15 in Incr 3B. Keep above
          near-match suspects. */}
      {showsWorkerCounter(countType) && (
        <WorkerCountModule hospital={hospital} sigla={sigla} cell={cell} countType={countType} />
      )}
```

- [ ] **Step 3: Build + full vitest (no component test, so verify build + lib suite)**

Run: `cd frontend && npm run build && npx vitest run`
Expected: build OK; all vitest pass.

- [ ] **Step 4: Manual reasoning check (no render infra)**

Confirm by reading: `countType` is derived at DetailPanel.jsx line 241 via `countTypeFor(sigla)`. For `dif_pts` that is `"documents_workers"` → `showsWorkerCounter` → true → `WorkerCountModule` renders. Document controls remain gated on `!isChecks` (line 385), so dif_pts (not checks) keeps them → both modules show, like charla/chintegral. Voice is handled in `WorkerCountViewer.jsx` (`isWorkersMode = countTypeFor(sigla) === "documents_workers"`) → dif_pts gets voice with no change.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DetailPanel.jsx
git commit -m "feat(ui): show worker counter for dif_pts (count_type-driven gate)

dif_pts is documents_workers, so the gate now keys off count_type
instead of a sigla allowlist. dif_pts shows the document controls AND
the worker counter (voice inherited), like charla/chintegral. Incr 3B.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 4: Final verification

### Task 8: Full suite + regression sweep + smoke handoff

**Files:** none (verification only)

- [ ] **Step 1: No stale assertion on the old N15 formula**

Run: `git grep -nE "M15\*0\.5|N15" -- tests/ | grep -v test_template_difpts_n15`
Expected: no test asserts `N15 == "=M15*0.5"`. If one exists (e.g., an e2e Excel invariant), update it to reflect N15 = worker total / 0 (analogous to the 3A checks-cell exclusion in `tests/e2e/test_smoke.py`).

- [ ] **Step 2: Backend suite**

Run: `pytest -q`
Expected: all pass, 0 failures (prior baseline was 709 passed / 52 skipped — expect +~8 new).

- [ ] **Step 3: Lint**

Run: `ruff check .`
Expected: 0 violations.

- [ ] **Step 4: Frontend**

Run: `cd frontend && npx vitest run && npm run build`
Expected: all vitest pass; build clean.

- [ ] **Step 5: Conducted browser smoke (data-safe) — handoff to controller**

Per memory `feedback_browser_testing_via_devtools` + `project_incremento_3a_shipped` gotchas:
- Back up `data/overseer.db` to `data/_smoke-backup-<ts>/`; operate on a PAST month (ABRIL); restore by **SHA256 hash match** afterward; never touch MAYO. Stop leftover `server.py` processes (by PID; never serena/pyright) before restoring.
- Launch backend + Vite on **:5173** (CORS allows only that origin). If Brave isn't in debug mode, launch it with an isolated temp profile + `--remote-debugging-port=9222`.
- Verify in-browser: open **HPV / dif_pts** → the worker counter module appears (unit "trabajadores", voice/mic visible) **and** the document controls are still present. Count workers, mark "Terminé"; generate the RESUMEN; confirm N15 holds the total. Then with HPV dif_pts uncounted-but-with-PDFs, generate again and confirm the **pending warning** appears and N15 = 0.

- [ ] **Step 6: Push**

```bash
git push origin po_overhaul
git tag incremento-3b && git push origin incremento-3b
```
(Tag after smoke passes; move the tag forward if smoke caught fixes.)

---

## Out of scope (do NOT implement here)
- dif_pts OCR detection (B3) — Track A, separate effort.
- Marks-list current-page highlight (F4) — Incr 3C.
- "Won't reach Excel" hint for non-HPV dif_pts — deferred.
- Any change to HLL/HLU/HRB row-15 HH cells (keep `=col*0.5`).
- Green-dot/settle changes (dif_pts stays document-provenance based, like charla/chintegral).
