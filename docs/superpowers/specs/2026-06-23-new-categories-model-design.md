# Increment B — Model the 2 new corpus categories (revdocmaq, espacios) — Design

**Date:** 2026-06-23
**Status:** DRAFT for review
**Author:** Claude (Opus 4.8) + Daniel
**Scope:** Backend + Excel template + frontend labels. Builds on Increment A.

---

## Problem & goal

The live corpus has **20** prevention categories per hospital, but PDFoverseer
models only **18** `SIGLAS`. Two real categories are unmodeled:

- `13.-Revision Documentacion Maquinaria` (→ report row **B22**)
- `17.-Espacios Confinados` (→ report row **B26**)

Increment A made folder resolution renumber-tolerant but deliberately left these
two **unmatched** (uncounted). Daniel's directive: *"que estén las mismas
categorías que en las carpetas de los hospitales como existen ahora para mayo, y
que solo cphs no vaya al excel."*

**Goal:** model both as first-class siglas so PDFoverseer's category set matches
the 20 corpus folders, count them, and write them to the RESUMEN — wiring the two
**orphan rows** the template already has (B22, B26). And make **`chps` the only
sigla not written to the Excel** (it stays counted/visible in the UI).

## Vision finding (the count-type determination Daniel delegated)

Only one sample exists in the entire corpus: `revdocmaq` has **0 PDFs anywhere**;
`espacios` has exactly one (`MAYO/HLL/2026-05_espacios_confinados.pdf`, 935 KB).

Reading the espacios sample: it is a **"LISTA DE CHEQUEO PARA TRABAJOS EN ESPACIOS
CONFINADOS"** (form code `F-PETS-CRS-08-01`), a **2-page form per inspection**
("Página 1 de 2" / "Página 2 de 2", paginated in the top-right corner), and the
single PDF is a **compilation of multiple inspections** (inspection #1 on pp1-2,
inspection #2 starting p3). The report row counts **inspections = documents**.

Conclusions:
- **`espacios`: `count_type="documents"`, `scan_strategy="pagination"`** — it is a
  compilation; pagination counts each inspection's "Página 1 de 2" cover correctly
  (this file → 2), where `none` would undercount to 1. `cover_code="F-PETS-CRS-08-01"`.
- **`revdocmaq`: `count_type="documents"`, `scan_strategy="none"` — PROVISIONAL.**
  No samples exist to verify, so this is the natural default (a count of reviews,
  1 PDF = 1). It is always 0 today, so the choice is currently moot; revisit the
  strategy/filename token when real files appear.

## Design

### 1. Domain (`core/domain.py`)

Insert the two siglas into `SIGLAS` in **folder/report order** (so the UI list and
the Excel loop match the corpus):

```
…, "senal", "revdocmaq", "exc", "altura", "caliente", "espacios",
"herramientas_elec", "andamios", "chps"   # → 20 siglas
```

Add to `CATEGORY_FOLDERS`:
```
"revdocmaq": "13.-Revision Documentacion Maquinaria",
"espacios":  "17.-Espacios Confinados",
```
(Increment A's matcher is renumber-tolerant, so these resolve by text regardless
of the on-disk number.) No alias needed.

### 2. Scanner registry (`core/scanners/patterns.py`)

Add one `SiglaPattern` per new sigla (mirroring existing entries):
- `revdocmaq`: `{filename_glob: r"^.*(revision|documentacion).*\.pdf$", scan_strategy: "none"}`
  (provisional token; `none` → `SimpleFilenameScanner`). On the collision concern:
  `extract_sigla` keys off the **sigla name** as a token (`"revdocmaq"` vs
  `"maquinaria"` — neither is a substring-token of the other), so it is safe **by
  construction**; the `filename_glob` here only governs the **OCR scanner's file
  discovery** and is where the "revision/documentacion" tokens earn their keep.
  Moot while 0 files, but build it right.
- `espacios`: `{filename_glob: r"^.*espacios.*\.pdf$", scan_strategy: "pagination",
  cover_code: "F-PETS-CRS-08-01"}` (a brand-new pagination sigla; no `cover_flavors`
  — that field is required only for `anchors`).

Add both to `COUNT_TYPE_BY_SIGLA` as `"documents"`.

**Bump `SCANNER_PATTERNS_VERSION`** in `core/utils.py` (new scan strategies added).
*(Note: the hookify `bump-version-tags` BLOCK rule covers `core/{pipeline,ocr,inference,image}.py` + `vlm/*` — patterns.py is not in it; this bump is by the patterns convention, not that gate.)*

### 3. Excel template — edit the `.xlsx` directly (do NOT regenerate)

**Critical:** `build_template_v1.py` is **NOT idempotent** — its own docstring
declares the shipped `RESUMEN_template_v1.xlsx` the *authoritative artifact* and
warns it carries **hand-patches the script does not reproduce** (the 2026-06-04
O11/O12 `#REF!` fix, the 2026-06-06 logo/font/borders/number-format work).
Running `build()` would **rebuild from the MARZO sample and wipe those patches**
— a violation of the "editable deliverables are user property" rule. So the
template change is made by **editing the `.xlsx` in place** (named ranges only),
never by regenerating.

Rows 22 & 26 are **orphan rows already present** in the sheet (labels intact).
The edit (via `openpyxl`, additive — touches only `defined_names`, never content
or formatting):
- **Wire the orphan rows:** add `{HOSP}_revdocmaq_count` → `$G/$I/$K/$M$22` and
  `{HOSP}_espacios_count` → `…$26` (4 hospitals × 2 = **8 new** named ranges).
- **Drop `chps` from the Excel:** delete the 4 `{HOSP}_chps_count` named ranges;
  leave the B31 "CHPS" label/row intact (manual fill if ever needed). Net
  count-ranges: 72 − 4 + 8 = **76**.

**Safety (load-bearing, since an openpyxl edit via a script does NOT trigger the
Write/Edit guard hook):** make a **dated backup** of the `.xlsx` first; after the
edit, **diff `defined_names` before/after** to prove exactly +8 / −4 and that no
other range, cell, or format changed; surface that diff to Daniel at the smoke
gate before committing the `.xlsx`.

**Keep the builder in sync (no regeneration):** update `build_template_v1.py`'s
`SIGLA_ROW`/`ORPHAN_ROWS` maps (remove 22/26 from orphans, add
`revdocmaq:22`/`espacios:26`; remove `chps`) and its `verify()` assertion
(`count_names == 76`, and no `{HOSP}_chps_count`) so the script stays consistent
with the `.xlsx` for any future `v2` — but it is documentation only here, not run.
Update `data/templates/README.md` (rows 22/26 no longer "orphan"; chps unwired by
design).

### 4. Excel writer value map (`api/routes/output.py`)

`_build_cell_values` iterates `HOSPITALS × SIGLAS` and emits `{hosp}_{sigla}_count`.
- The two new siglas flow automatically (documents → `present_files=None`, value
  from stored state) → written to B22/B26.
- **Exclude `chps`:** add a module-level `EXCEL_EXCLUDED_SIGLAS = frozenset({"chps"})`
  and `continue` for those siglas, so no `{hosp}_chps_count` is emitted (the
  template has no such range anymore either — both sides agree). The **history
  upsert loop is unchanged** — `chps` (and the 2 new siglas) still persist to
  `historical_counts` (internal DB, not the Excel). Daniel's "no va al excel" is
  scoped to the report, not history.

### 5. Frontend labels

Add Spanish-neutro entries for `revdocmaq` and `espacios` to the sigla label/info
maps (`frontend/src/lib/sigla-labels.js`, `sigla-info.js`) — short label + a
one-line description matching the report row wording ("Revisión de documentación
de maquinaria", "Inspección de espacios confinados"). Update any frontend test that
asserts the sigla set/count.

### 6. Existing-session reconciliation (load-bearing) — RESOLVED: reconcile on load

The frontend builds the category list as `SIGLAS.filter((s) => cells[s])`
([`HospitalDetail.jsx:34`](../../frontend/src/views/HospitalDetail.jsx)) — a sigla
appears **only once its cell exists** in the session blob. Existing MAYO/ABRIL
sessions were scanned with 18 siglas, so they have no cell for `revdocmaq`/`espacios`
→ the new rows would stay hidden until a fresh pase-1 (which the user may not know
to run). That silently fails B's goal.

**Resolution — reconcile on load (no version bump):** in the session-load path
(`api/state.py`, after the existing `migrate_state_*` calls in `_load_and_migrate`/
`get_session_state`), seed a `{}` cell for every `(hosp, sigla)` in
`HOSPITALS × SIGLAS` that is missing — `state["cells"].setdefault(hosp, {}).setdefault(sigla, {})`.
Idempotent; **never overwrites** an existing cell (so no count changes); an empty
`{}` cell resolves to count 0 (`compute_cell_count({}, …) == 0`) exactly as an
absent cell did in the Excel path (`hosp_cells.get(sigla, {})`), so **output is
unchanged** for everything already counted — it only makes the full 20-category set
**appear** immediately on open, no re-scan. (A `{}` is truthy in JS, so the
frontend filter includes it.) Add a unit test: loading a v3 session missing a sigla
yields a `{}` cell for it without touching the others.

## What changes in the output (NOT Excel-neutral — intended)

- B22 (revdocmaq) and B26 (espacios) now receive counts (mostly 0; espacios HLL =
  its inspection count once scanned).
- B31 (chps) is no longer written by PDFoverseer (stays blank/manual).
- The category list (UI) shows 20 rows per hospital; history gains revdocmaq/
  espacios rows.
- All other 17 siglas' values are unchanged.

## Test fan-out (enumerate; the plan turns each into a step)

Adding 2 siglas inverts several existing assertions. The plan MUST handle each:

- `tests/unit/test_domain.py`:
  - `test_siglas_are_the_18_canonical` — rename + update the verbatim tuple
    (insert `"revdocmaq"` after `"senal"`, `"espacios"` after `"caliente"`),
    `len(SIGLAS)==20`, `len(CATEGORY_FOLDERS)==20`.
  - `test_folder_to_sigla_unmodeled_corpus_folders_return_none` — **invert**:
    `"13.-Revision Documentacion Maquinaria" → "revdocmaq"` and
    `"17.-Espacios Confinados" → "espacios"` (no longer `None`). Rename it.
  - `test_folder_match_texts_pairwise_distinct` — must still pass (verified:
    "Revision Documentacion Maquinaria"/"Espacios Confinados" collide with no
    existing canonical); run it as a gate.
- `tests/unit/test_orchestrator.py`:
  - `test_enumerate_month_populates_18_categories_per_hospital` and
    `test_enumerate_month_returns_zero_for_missing_category`: `18 → 20`.
  - `test_find_category_folder_resolves_renumbered_corpus` (added in Increment A) —
    **invert** the two `… not in returned` assertions (lines ~72-75) to `… in
    returned`, and add positive resolution checks for `revdocmaq → "13.-…"`,
    `espacios → "17.-…"`. Update the stale "never returned" comment.
- `tests/unit/test_orchestrator_scan.py`: `len(results)==72` → `==80`.
- `tests/e2e/test_smoke.py`: `scanned == 72` → `== 80`.
- `tests/integration/test_abril_full_corpus.py` (slow): `len(results)==72` → `==80`.
- `core/orchestrator/enumeration.py`: docstrings say "18 category cells" — update
  to 20 (≥5 spots).
- Completeness gates: `tests/unit/scanners/test_count_type.py` and
  `test_patterns_registry.py` require entries for both new siglas (they fail until
  added). In particular `test_patterns_registry.py::test_v4_pagination_migration_state`
  hardcodes the 18-sigla strategy split — add `"espacios"` to the pagination set and
  account for `"revdocmaq"` (strategy `none`; add a `none`/`reunion`-style bucket).
- `tests/unit/excel/test_template.py`: `len(cantidad_names) == 72` → `== 76`
  (existing assertion; will fail the moment the `.xlsx` is patched).
- `tests/unit/test_domain.py::test_category_folders_map_to_numbered_names`:
  `len(CATEGORY_FOLDERS) == 18` → `== 20` (the `chps == "18.-CHPS"` line stays —
  CATEGORY_FOLDERS keeps chps; add `revdocmaq`/`espacios` spot-checks).
- `tests/unit/api/test_routes_output.py`: any assertion derived from `len(SIGLAS)`
  (e.g. `len(vals) == len(HOSPITALS) * len(SIGLAS) - 1`) must become
  `… - len(EXCEL_EXCLUDED_SIGLAS)` (= 80 − 4 = 76) so the chps exclusion is counted
  correctly, not a bare `-1`.
- New Excel test: revdocmaq→B22 and espacios→B26 receive values; **no `chps` value
  is written**; assert the `.xlsx` `defined_names` have the 8 new ranges and no
  `{HOSP}_chps_count` (76 count ranges total).
- New scanner test: espacios pagination counts a 2-inspection "Página N de 2"
  compilation as 2 (synthetic fixture; no personal-data corpus slice).
- Frontend: update the sigla-set assertion in `sigla-info.test.js` / the labels
  test; add label+description entries.
- Final grep `18`/`72` across backend + frontend to catch any remaining count
  assertion.

## Risks

- **revdocmaq filename token unverified** (no samples) → its filename-glob is a
  guess; could mis-match or collide with `maquinaria`. Mitigated: always 0 files
  today; the pattern requires distinct tokens; flagged for refinement.
- **espacios pagination on a single real file** — low blast radius; if pagination
  mis-reads the corner, the cell drops to LOW confidence (existing behavior) and the
  operator counts by keyboard.
- **Template regeneration** — reproducible from the script, but back-up + diff
  guards against an unintended layout change.
- **Session reconciliation** (§6) — if missed, new cells don't appear on existing
  sessions; explicitly verified in the plan.

## Out of scope

- OCR/anchor tuning for either category; refining revdocmaq once files exist.
- Any change to the 17 unaffected siglas or to worker/checks logic.
- A template `v2` reorder (the README's cosmetic idea) — not needed.

## Verification plan (live, on a COPY DB)

1. Copy `overseer.db`; record real sha256.
2. Start backend on the copy; open MAYO. Confirm the category list shows 20 incl.
   `revdocmaq` + `espacios`; `espacios` for HLL resolves its file (and, scanned via
   pagination, counts the inspections).
3. Generate the RESUMEN; confirm B22/B26 are populated and **B31 (chps) is blank**;
   spot-check a few unchanged siglas equal their prior values.
4. Stop, delete the copy, confirm real `overseer.db` byte-identical.
