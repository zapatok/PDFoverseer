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
  (provisional token; `none` → `SimpleFilenameScanner`). Must NOT collide with
  `maquinaria` in `extract_sigla` — verify the filename-glob precedence so a
  revdocmaq file is not absorbed by `maquinaria` and vice versa (a real risk since
  both names contain "maquinaria"; resolved here by requiring "revision"/
  "documentacion" tokens). Moot while 0 files, but build it right.
- `espacios`: `{filename_glob: r"^.*espacios.*\.pdf$", scan_strategy: "pagination",
  cover_code: "F-PETS-CRS-08-01"}` (a brand-new pagination sigla; no `cover_flavors`
  — that field is required only for `anchors`).

Add both to `COUNT_TYPE_BY_SIGLA` as `"documents"`.

**Bump `SCANNER_PATTERNS_VERSION`** in `core/utils.py` (new scan strategies added).
*(Note: the hookify `bump-version-tags` BLOCK rule covers `core/{pipeline,ocr,inference,image}.py` + `vlm/*` — patterns.py is not in it; this bump is by the patterns convention, not that gate.)*

### 3. Excel template (`data/templates/build_template_v1.py` → regenerate)

The template is **generated** by this script (idempotent, from the production
sample), and rows 22 & 26 are **orphan rows already present** for layout fidelity.
So:
- **Wire the orphan rows:** add `{HOSP}_revdocmaq_count` → row 22 and
  `{HOSP}_espacios_count` → row 26 (G/I/K/M columns, 4 hospitals × 2 = 8 new named
  ranges) to the builder's sigla→row map.
- **Drop `chps` from the Excel:** remove the `{HOSP}_chps_count` named ranges from
  the builder; leave the B31 "CHPS" label/row intact (Carla can fill it by hand if
  ever needed). Net count-ranges: 72 − 4 (chps) + 8 (new) = **76**.
- Regenerate `RESUMEN_template_v1.xlsx` (it is reproducible). Keep `v1` (no layout
  break: rows already exist, only named ranges change). Update the builder docstring
  + `data/templates/README.md` (the two rows are no longer "orphan"; chps is now
  unwired-by-design, not just empty).

**Safety:** back up the current `.xlsx` (dated copy) before regenerating; diff
`defined_names` before/after to confirm exactly +8 (revdocmaq/espacios) and −4
(chps), nothing else moved.

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

### 6. Existing-session reconciliation (load-bearing)

Existing MAYO/ABRIL sessions in `overseer.db` were created with 18 siglas/hospital.
For the 2 new categories to **appear** (the whole point), opening such a session
must surface them as cells. The plan MUST verify the session-open path adds missing
siglas (reconciles `state.cells[hosp]` against `SIGLAS`) — and add that
reconciliation if absent. Without it, the new rows would show only after a fresh
scan / new month. This is the one place B could silently fail its goal.

## What changes in the output (NOT Excel-neutral — intended)

- B22 (revdocmaq) and B26 (espacios) now receive counts (mostly 0; espacios HLL =
  its inspection count once scanned).
- B31 (chps) is no longer written by PDFoverseer (stays blank/manual).
- The category list (UI) shows 20 rows per hospital; history gains revdocmaq/
  espacios rows.
- All other 17 siglas' values are unchanged.

## Test fan-out (enumerate; the plan turns each into a step)

- `tests/unit/test_domain.py`: `SIGLAS` tuple (→20), `len(SIGLAS)==20`,
  `len(CATEGORY_FOLDERS)==20`; add `revdocmaq`/`espacios` to the expected tuple
  in order; roundtrip still covers all (now 20).
- `tests/unit/test_orchestrator.py`: `len(inv.cells[hosp])==18` → `==20`.
- `tests/integration/test_abril_full_corpus.py` (slow): `len(results)==72` → `==80`.
- Completeness gates: `tests/unit/scanners/test_count_type.py` and
  `test_patterns_registry.py` will now require entries for the 2 new siglas (the
  gates are the enforcement — they fail until patterns + count_type are added).
- New Excel test: revdocmaq→B22 and espacios→B26 receive values; **no
  `chps` value is written** (B31 stays blank); a builder/defined-names test for the
  76 count ranges + the absence of `{HOSP}_chps_count`.
- New scanner test: espacios pagination counts a 2-inspection compilation as 2 (a
  synthetic 4-page "Página N de 2" fixture, or assert via the existing pagination
  engine unit harness — no personal-data fixture).
- Frontend: update the sigla-set assertion in `sigla-info.test.js`/labels test.
- Grep `18`/`72` for any other count assertion and update.

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
