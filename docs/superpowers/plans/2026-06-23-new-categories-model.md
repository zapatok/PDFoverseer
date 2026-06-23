# Increment B — Model 2 new corpus categories — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Model `revdocmaq` and `espacios` as siglas (18→20) so PDFoverseer's category set matches the 20 MAYO folders; write them to the RESUMEN's existing orphan rows (B22/B26); make `chps` the only sigla excluded from the Excel; and reconcile existing sessions so all 20 appear on open.

**Architecture:** Add the two siglas across the backend registries (domain, patterns, count_type) + frontend label maps; wire the Excel via a **direct, additive `.xlsx` edit** (the template is hand-patched — never regenerate); a reconcile-on-load seeds missing cells; `_build_cell_values` skips `chps`. Intentionally **not** Excel-neutral (B22/B26 fill, B31 blanks); the other 17 siglas don't move.

**Tech Stack:** Python 3.10+, pytest, ruff, openpyxl; React/Vite + vitest.

**Spec:** `docs/superpowers/specs/2026-06-23-new-categories-model-design.md`

**Co-Author trailer (every commit):** `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Stage explicit paths only (never `git add -A`).

---

## Chunk 1: Backend model + registries + Excel + frontend + reconcile

### Task 1: Domain + scanner registries + count_type (one atomic commit — the completeness gates make this all-or-nothing)

**Why atomic:** adding to `SIGLAS` makes `set(PATTERNS)==set(SIGLAS)` and `set(COUNT_TYPE_BY_SIGLA)==set(SIGLAS)` fail until the entries exist; do them together so the suite stays green.

**Files:**
- Modify: `core/domain.py` (`SIGLAS`, `CATEGORY_FOLDERS`)
- Modify: `core/scanners/patterns.py` (`PATTERNS`, `COUNT_TYPE_BY_SIGLA`)
- Modify: `core/utils.py` (`SCANNER_PATTERNS_VERSION`)
- Modify: `core/orchestrator/enumeration.py` (docstrings 18→20 only)
- Test: `tests/unit/test_domain.py`, `tests/unit/test_orchestrator.py`,
  `tests/unit/test_orchestrator_scan.py`, `tests/e2e/test_smoke.py`,
  `tests/unit/scanners/test_patterns_registry.py`,
  `tests/unit/scanners/test_count_type.py` (auto), `tests/integration/test_abril_full_corpus.py` (slow)

- [ ] **Step 1: Update the count-assertion tests to expect 20/80 (TDD red)**

`tests/unit/test_domain.py`:
- `test_siglas_are_the_18_canonical` → rename to `…_20_canonical`; in the expected tuple insert `"revdocmaq"` right after `"senal"` and `"espacios"` right after `"caliente"`; `assert len(SIGLAS) == 20`.
- `test_category_folders_map_to_numbered_names`: `assert len(CATEGORY_FOLDERS) == 20`; add `assert CATEGORY_FOLDERS["revdocmaq"] == "13.-Revision Documentacion Maquinaria"` and `assert CATEGORY_FOLDERS["espacios"] == "17.-Espacios Confinados"` (keep the existing `chps == "18.-CHPS"` line).
- `test_folder_to_sigla_unmodeled_corpus_folders_return_none` → rename to `…_new_corpus_folders_resolve`; change both asserts to `assert folder_to_sigla("13.-Revision Documentacion Maquinaria") == "revdocmaq"` and `… "17.-Espacios Confinados" == "espacios"`.

`tests/unit/test_orchestrator.py`:
- `test_enumerate_month_populates_18_categories_per_hospital` + `test_enumerate_month_returns_zero_for_missing_category`: `18 → 20`.
- `test_find_category_folder_resolves_renumbered_corpus`: invert the two `… not in returned` asserts (lines ~74-75) to `assert "13.-Revision Documentacion Maquinaria" in returned` / `… "17.-Espacios Confinados" in returned`; add `assert _find_category_folder(hosp, "revdocmaq").name == "13.-Revision Documentacion Maquinaria"` and `… "espacios" … == "17.-Espacios Confinados"`; fix the now-stale "never returned" comment.

`tests/unit/test_orchestrator_scan.py`: `assert len(results) == 72` → `== 80` (+ comment "4 × 20 = 80").
`tests/e2e/test_smoke.py`: `assert scan_result["scanned"] == 72` → `== 80`.
`tests/integration/test_abril_full_corpus.py`: `assert len(results) == 72` → `== 80`.
`tests/unit/scanners/test_patterns_registry.py::test_v4_pagination_migration_state`: add `"espacios"` to `pagination_expected`; add a `none_expected = {"reunion", "revdocmaq"}` set with `for sigla in none_expected: assert PATTERNS[sigla]["scan_strategy"] == "none"` (and drop the standalone `reunion` assert, now covered). Rename the function/docstring off "v4" if desired (optional).

- [ ] **Step 2: Run the updated tests → expect FAIL**

Run: `.venv-cuda/Scripts/python.exe -m pytest tests/unit/test_domain.py tests/unit/test_orchestrator.py tests/unit/scanners/test_count_type.py tests/unit/scanners/test_patterns_registry.py -q -p no:faulthandler`
Expected: FAIL (siglas not yet added; completeness gates red; tuple mismatch).

- [ ] **Step 3: Add the two siglas to `core/domain.py`**

In `SIGLAS`, insert in folder order: `"revdocmaq"` after `"senal"`, `"espacios"` after `"caliente"` →
```python
SIGLAS: tuple[str, ...] = (
    "reunion", "irl", "odi", "charla", "chintegral", "dif_pts", "art",
    "insgral", "bodega", "maquinaria", "ext", "senal", "revdocmaq",
    "exc", "altura", "caliente", "espacios", "herramientas_elec",
    "andamios", "chps",
)
```
In `CATEGORY_FOLDERS` add:
```python
    "revdocmaq": "13.-Revision Documentacion Maquinaria",
    "espacios": "17.-Espacios Confinados",
```

- [ ] **Step 4: Add the `PATTERNS` + `COUNT_TYPE_BY_SIGLA` entries (`core/scanners/patterns.py`)**

In `PATTERNS` (anywhere in the dict; place logically):
```python
    "revdocmaq": {
        "filename_glob": r"^.*(revision|documentacion).*\.pdf$",
        "scan_strategy": "none",
        "recursive_glob": True,
    },
    "espacios": {
        "filename_glob": r"^.*espacios.*\.pdf$",
        "scan_strategy": "pagination",
        "cover_code": "F-PETS-CRS-08-01",
        "recursive_glob": True,
    },
```
(Pagination needs no `cover_flavors` — confirmed: `insgral`/`altura` are pagination without it, and `PaginationScanner` only `.get("cover_code")`.)

In `COUNT_TYPE_BY_SIGLA` add `"revdocmaq": "documents",` and `"espacios": "documents",`.

- [ ] **Step 5: Bump `SCANNER_PATTERNS_VERSION` (`core/utils.py`)**

Append a `v5` comment line + change the value to `"v5-new-categories"`:
```python
    # v5: + revdocmaq (none) + espacios (pagination, F-PETS-CRS-08-01) → 20 siglas.
    "v5-new-categories"
```

- [ ] **Step 6: Update `core/orchestrator/enumeration.py` docstrings** — replace "18 category cells"/"18" wording with 20 (≥5 spots; no logic change — it iterates `SIGLAS`).

- [ ] **Step 7: Run the backend suite → expect PASS**

Run: `.venv-cuda/Scripts/python.exe -m pytest -m "not slow" -q -p no:faulthandler` (full, since many files touched)
Expected: all pass. Then `.venv-cuda/Scripts/python.exe -m ruff check core/ tests/` → clean.

- [ ] **Step 8: New scanner test — espacios pagination counts a compilation**

Add to `tests/unit/scanners/test_pagination_scanner.py` (or a new `test_espacios.py`) a test that a 2-inspection "Página N de 2" synthetic PDF (4 pages) yields count 2 via `PaginationScanner` — mirror an existing pagination scanner test's monkeypatch style (patch `core.scanners.pagination_scanner.get_page_count` + `count_documents_by_pagination`), no personal-data fixture. Run it → PASS.

- [ ] **Step 9: Commit**

```bash
git add core/domain.py core/scanners/patterns.py core/utils.py core/orchestrator/enumeration.py tests/unit/test_domain.py tests/unit/test_orchestrator.py tests/unit/test_orchestrator_scan.py tests/e2e/test_smoke.py tests/unit/scanners/test_patterns_registry.py tests/integration/test_abril_full_corpus.py tests/unit/scanners/test_pagination_scanner.py
git commit -m "feat(domain): model revdocmaq + espacios siglas (18->20)"
```

---

### Task 2: Reconcile-on-load (existing sessions surface all 20)

**Files:**
- Modify: wherever `migrate_state_v2_to_v3` is defined (grep; likely `api/state.py` or `core/db/migrations.py`) + `api/state.py::_load_and_migrate`
- Test: the test file covering `migrate_state_*` / `_load_and_migrate`

- [ ] **Step 1: Failing test** — a v3 session whose `cells["HRB"]` lacks `revdocmaq`/`espacios`, after `get_session_state`, has `cells["HRB"]["revdocmaq"] == {}` and `["espacios"] == {}`, while an existing populated cell (e.g. `cells["HRB"]["odi"]`) is **unchanged**. Run → FAIL.

- [ ] **Step 2: Implement `migrate_state_v3_to_v4`** (next to `migrate_state_v2_to_v3`):
```python
def migrate_state_v3_to_v4(state: dict) -> tuple[dict, bool]:
    """Seed an empty {} cell for every (present hospital, sigla) pair missing
    from the session, so categories added after the session was scanned still
    appear. Idempotent; never overwrites an existing cell."""
    from core.domain import SIGLAS

    changed = False
    for hosp_cells in state.get("cells", {}).values():
        for sigla in SIGLAS:
            if sigla not in hosp_cells:
                hosp_cells[sigla] = {}
                changed = True
    return state, changed
```
Wire into `_load_and_migrate`: add `state, changed3 = migrate_state_v3_to_v4(state)` after the v2→v3 call, and `if changed1 or changed2 or changed3:` for the persist. Import it alongside the others.

- [ ] **Step 3: Run → PASS** (the new test + the existing state tests). Then full `-m "not slow"` suite green + ruff clean.

- [ ] **Step 4: Commit**
```bash
git add <state/migrations file> tests/<state test>
git commit -m "fix(state): reconcile-on-load seeds missing siglas so all 20 categories appear"
```

---

### Task 3: Excel writer — exclude `chps` from the report

**Files:**
- Modify: `api/routes/output.py` (`_build_cell_values`)
- Test: `tests/unit/api/test_routes_output.py`

- [ ] **Step 1: Failing/updated test** — the `chps` exclusion drops **4** cells
  (one per hospital), so BOTH count assertions in `tests/unit/api/test_routes_output.py`
  must change (read the file to confirm exact line numbers/setup):
  - the **no-excluded** grid test (~line 167, `== len(HOSPITALS) * len(SIGLAS)`) →
    `== len(HOSPITALS) * (len(SIGLAS) - len(EXCEL_EXCLUDED_SIGLAS))` (= 4×19 = **76**).
  - the **excluded-art** test (~line 177, currently `… - 1`) → keep the `- 1` for the
    `excluded=True` art cell but also account for chps:
    `== len(HOSPITALS) * (len(SIGLAS) - len(EXCEL_EXCLUDED_SIGLAS)) - 1` (= 76 − 1 = **75**).
  - Add an explicit `assert "HRB_chps_count" not in values`.
  Run → FAIL. (NB: `- len(EXCEL_EXCLUDED_SIGLAS)` alone is wrong — exclusion is
  per-hospital, hence the `len(HOSPITALS) * (…)` factoring.)

- [ ] **Step 2: Implement** — in `api/routes/output.py`, module level:
```python
# chps (CPHS — Comité Paritario) is modeled + counted but is NOT written to the
# RESUMEN (Daniel, 2026-06-23: "solo cphs no va al excel"). History keeps it.
EXCEL_EXCLUDED_SIGLAS: frozenset[str] = frozenset({"chps"})
```
In `_build_cell_values`, at the top of the `for sigla in SIGLAS:` body: `if sigla in EXCEL_EXCLUDED_SIGLAS: continue`. **Do NOT touch** the history-upsert loop in `generate()` — chps + the 2 new siglas still persist to `historical_counts`.

- [ ] **Step 3: Run → PASS** + ruff.

- [ ] **Step 4: Commit**
```bash
git add api/routes/output.py tests/unit/api/test_routes_output.py
git commit -m "feat(output): exclude chps from the RESUMEN (counted + in history, not in Excel)"
```

---

### Task 4: Excel template — direct `.xlsx` edit (wire B22/B26, drop chps ranges)

**CRITICAL:** do NOT run `build_template_v1.py` (non-idempotent; would wipe hand-patches). Edit the `.xlsx` in place via openpyxl, additive (named ranges only).

**Files:**
- Modify: `data/templates/RESUMEN_template_v1.xlsx` (named ranges only)
- Modify: `data/templates/build_template_v1.py` (`SIGLA_ROW`/`ORPHAN_ROWS`/`verify`) + `data/templates/README.md` (docs/sync only — not run)
- Test: `tests/unit/excel/test_template.py`

- [ ] **Step 1: Back up the `.xlsx`** (the openpyxl-via-script edit does NOT trigger the Write/Edit guard hook):
```bash
cp "data/templates/RESUMEN_template_v1.xlsx" "data/templates/RESUMEN_template_v1.xlsx.bak-$(date +%Y%m%d-%H%M%S)"
```

- [ ] **Step 2: Edit the named ranges via openpyxl + diff** (a throwaway script; column map per README: G=HLL, I=HLU, K=HRB, M=HPV):
```python
import openpyxl
from openpyxl.workbook.defined_name import DefinedName
p = "data/templates/RESUMEN_template_v1.xlsx"
wb = openpyxl.load_workbook(p)
before = set(wb.defined_names.keys())
sheet = wb.active.title
cols = {"HLL": "G", "HLU": "I", "HRB": "K", "HPV": "M"}
for hosp, col in cols.items():
    for sigla, row in (("revdocmaq", 22), ("espacios", 26)):
        name = f"{hosp}_{sigla}_count"
        wb.defined_names[name] = DefinedName(name, attr_text=f"'{sheet}'!${col}${row}")
    del wb.defined_names[f"{hosp}_chps_count"]
wb.save(p)
after = set(openpyxl.load_workbook(p).defined_names.keys())
print("ADDED:", sorted(after - before))
print("REMOVED:", sorted(before - after))
```
Expected: ADDED = the 8 revdocmaq/espacios ranges; REMOVED = the 4 chps ranges; nothing else. **If the diff shows anything else, restore from the backup and stop.** (The installed openpyxl exposes `defined_names` as a dict — `.keys()` and `wb.defined_names[name] = DefinedName(name, attr_text=ref)` both work; confirmed by the earlier template dump. `del wb.defined_names[name]` removes one.)

- [ ] **Step 3: Update `test_template.py`** — `assert len(cantidad_names) == 72` → `== 76`; add `assert "HRB_revdocmaq_count" in names`, `assert "HLL_espacios_count" in names`, `assert "HRB_chps_count" not in names`.

- [ ] **Step 4: Add an end-to-end Excel test** (extend `tests/unit/api/test_routes_output.py`): generate the RESUMEN for a session with a stored count on `revdocmaq`/`espacios`; assert B22 (revdocmaq) and B26 (espacios) receive the values via their named ranges, and that the cphs cell (B31) is **not written** (stays the template default / blank). Mirror the existing `HPV_workers_difpts` destination-read pattern.

- [ ] **Step 5: Sync the builder (docs only, do not run)** — in `build_template_v1.py`: remove 22 & 26 from `ORPHAN_ROWS`, add `"revdocmaq": 22`/`"espacios": 26` to `SIGLA_ROW`, remove `"chps"` from `SIGLA_ROW`; update `verify()` to expect 76 count ranges + assert no `{HOSP}_chps_count`. Update `README.md` (rows 22/26 no longer orphan; chps unwired by design). Do **not** execute the script.

- [ ] **Step 6: Run → PASS** (`tests/unit/excel/` + `tests/unit/api/test_routes_output.py`) + ruff.

- [ ] **Step 7: Commit** (include the `.xlsx`; the `.bak` is gitignored or remove it after — do NOT commit the backup):
```bash
git add data/templates/RESUMEN_template_v1.xlsx data/templates/build_template_v1.py data/templates/README.md tests/unit/excel/test_template.py tests/unit/api/test_routes_output.py
git commit -m "feat(excel): wire revdocmaq->B22 + espacios->B26, drop chps ranges (direct .xlsx edit)"
```

---

### Task 5: Frontend labels

**Files:**
- Modify: `frontend/src/lib/sigla-labels.js` (`SIGLA_LABELS`, `SIGLAS`)
- Modify: `frontend/src/lib/sigla-info.js` (`SIGLA_DESCRIPTION`, `SIGLA_PAGE_RANGE`, `SIGLA_COUNT_TYPE`)
- Test: `frontend/src/lib/sigla-info.test.js` auto-covers via `SIGLAS` (no edit needed unless it hardcodes 18)

- [ ] **Step 1: Add to `sigla-labels.js`** — `SIGLA_LABELS`: `revdocmaq: "Revisión doc. maquinaria"`, `espacios: "Espacios confinados"`. Insert both into the `SIGLAS` array in the SAME folder order as the backend (revdocmaq after senal, espacios after caliente).

- [ ] **Step 2: Add to `sigla-info.js`** — for each of revdocmaq/espacios add one entry to all three maps: `SIGLA_DESCRIPTION` ("Revisión de documentación de maquinaria." / "Inspección de medidas de seguridad para trabajos en espacios confinados."), `SIGLA_PAGE_RANGE` (`{ p25: 1, p75: 2 }` — both are short forms; espacios is 2pp/inspection), `SIGLA_COUNT_TYPE` (`"documents"` both).

- [ ] **Step 3: Check `sigla-info.test.js`** — if it hardcodes "18", update the `it("covers all … siglas")` titles to 20; the loops iterate `SIGLAS` so they auto-cover. Run vitest:
Run: `cd frontend && npm run test -- --run src/lib/sigla-info.test.js`
Expected: PASS.

- [ ] **Step 4: Full vitest + build**
Run: `cd frontend && npm run test -- --run` then `npm run build`
Expected: all pass, build OK.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/lib/sigla-labels.js frontend/src/lib/sigla-info.js frontend/src/lib/sigla-info.test.js
git commit -m "feat(web): labels + info for revdocmaq + espacios"
```

---

### Task 6: Full verification + live smoke

- [ ] **Step 1: Full backend suite + ruff + slow ABRIL**
```
.venv-cuda/Scripts/python.exe -m pytest -m "not slow" -q -p no:faulthandler   # all green
.venv-cuda/Scripts/python.exe -m ruff check core/ api/ tests/                  # clean
.venv-cuda/Scripts/python.exe -m pytest tests/integration/test_abril_full_corpus.py -q -p no:faulthandler  # 80 cells
```

- [ ] **Step 2: Live smoke on a COPY DB (Brave debug)** — copy `data/overseer.db` → `data/_smoke_B_overseer.db` (record real sha256 while the dev backend is stopped); start the backend on the copy (`OVERSEER_DB_PATH=…_smoke_B… PORT=8010`), drive Brave (isolated context, fetch/WS :8000→:8010 rewrite) to MAYO → HRB: confirm the category list shows **20** rows incl. `revdocmaq` + `espacios`; HLL `espacios` resolves its 1 file; generate the RESUMEN and confirm **B22/B26 populated, B31 (chps) blank**, a couple of unchanged siglas equal their prior values. Stop, delete the copy, confirm real `overseer.db` byte-identical.

- [ ] **Step 3: Push**
```bash
git push origin po_overhaul
```

---

## Notes
- DRY/YAGNI: reuse `PaginationScanner` for espacios (no new engine); revdocmaq stays `none` (no samples). TDD: red→green per task; Task 1 is atomic by necessity (completeness gates).
- The `.xlsx` edit is the one irreversible-ish artifact touch — backup + diff + restore-on-surprise is mandatory; surface the diff before committing.
- Out of scope: revdocmaq filename-token refinement (no samples), any OCR tuning.
