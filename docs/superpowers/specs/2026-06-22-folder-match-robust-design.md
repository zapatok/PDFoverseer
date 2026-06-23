# Increment A — Robust category-folder matching (renumber-tolerant) — Design

**Date:** 2026-06-22
**Status:** DRAFT for review
**Author:** Claude (Opus 4.8) + Daniel
**Scope:** Backend only. No frontend, no Excel template, no model expansion.

---

## Problem

PDFoverseer maps each of its 18 `SIGLAS` to a canonical category-folder name in
`core/domain.py::CATEGORY_FOLDERS` (e.g. `caliente → "15.-Inspeccion Trabajos en
Caliente"`). Folder resolution (`core/orchestrator/enumeration.py::_find_category_folder`)
matches the **full name including the `NN.-` numeric prefix**, by exact equality or
`canonical + " "` (to tolerate `TOTAL`/` 0`/contractor-count suffixes).

The live corpus has drifted. Both ABRIL and MAYO now contain **20** numbered
category folders — two that PDFoverseer does not model, inserted mid-list:

- `13.-Revision Documentacion Maquinaria`
- `17.-Espacios Confinados`

Those insertions **shift the numbering** of every folder from `Excavaciones`
onward, and the last folder is also spelled differently than the code expects:

| sigla | code expects (`CATEGORY_FOLDERS`) | disk (ABRIL & MAYO) | matches today? |
|---|---|---|---|
| senal | `12.-Senaleticas` | `12.-Senaleticas` | ✓ (folder empty) |
| exc | `13.-Excavaciones y Vanos` | `14.-Excavaciones y Vanos` | ✗ |
| altura | `14.-Trabajos en Altura` | `15.-Trabajos en Altura` | ✗ |
| caliente | `15.-Inspeccion Trabajos en Caliente` | `16.-Inspeccion Trabajos en Caliente` | ✗ |
| herramientas_elec | `16.-Inspeccion Herramientas Electricas` | `18.-Inspeccion Herramientas Electricas` | ✗ |
| andamios | `17.-Andamios` | `19.-Andamios` | ✗ |
| chps | `18.-CHPS` | `20.-CPHS` | ✗ (number **and** spelling) |

Because the match is exact, `_find_category_folder` returns a nominal
non-existent path for those six siglas. Observable effects, confirmed live
against the running backend (MAYO/HRB): the cell-files endpoint returns `[]` for
`exc/altura/caliente/herramientas_elec/andamios/chps` even though
`exc/altura/caliente/herramientas_elec/andamios` have PDFs on disk; the file-list
panel is empty; the category counts shown are **stale/frozen** (the `_cell_has_work`
guard kept them when "Escanear todos" found nothing). The six are silently
un-scannable and un-reviewable.

This is **pre-existing corpus/code drift**, not a regression: `core/domain.py`
has a single commit (its creation), untouched by the structural round. It affects
every month that has the 20-folder structure (ABRIL and MAYO today).

## Goal

Make category-folder resolution **tolerant of numeric-prefix renumbering** (and
of the `CHPS`/`CPHS` spelling), so all 18 modeled siglas resolve to their folder
by the **text after the `NN.-` prefix**. This restores file listing and scanning
for the six broken siglas immediately.

### Success criteria

- `_find_category_folder(hosp_dir, sigla)` resolves the correct on-disk folder for
  all 18 siglas under the current 20-folder corpus (ABRIL & MAYO), regardless of
  the leading number.
- The cell-files endpoint returns the real PDFs for
  `exc/altura/caliente/herramientas_elec/andamios` on MAYO/HRB (and equivalently
  on the other hospitals/months).
- `chps` resolves to `…-CPHS`.
- The two unmodeled corpus folders (`Revision Documentacion Maquinaria`,
  `Espacios Confinados`) remain **unmatched** (uncounted) — they are Increment B.
- **Excel output is unchanged by this increment** (see Excel-neutrality below).

## Non-goals (explicitly out of scope — these are Increment B)

- Modeling the two new corpus categories as siglas (`SIGLAS` 18→20), their
  `patterns.py` entries, count types, frontend labels, Excel named ranges, or
  template rows.
- Re-counting / re-scanning the restored cells (that is an **operator action**
  after this fix; this increment only restores the ability).
- Any change to the Excel template or to how counts map to named ranges.
- The `chps`-in-Excel question (the template currently has `{hosp}_chps_count`
  ranges; whether `chps` should appear in the report is a B-scope clarification).

## Design

### One matching rule, shared forward and reverse

The fix is a single normalization rule, defined once in `core/domain.py` and used
by both the forward resolver (`_find_category_folder`) and the reverse helper
(`folder_to_sigla`). No duplicated matching logic.

**Normalization:** strip a leading numeric index of the form `^\s*\d+\s*\.\s*-?\s*`
from a folder name, yielding its **text**. Examples:
`"14.-Excavaciones y Vanos" → "Excavaciones y Vanos"`,
`"7.-ART" → "ART"`, `"7.-ART 934" → "ART 934"`.

**Match predicate** (folder text vs canonical text, both stripped): the existing
tolerance is preserved — a folder matches a sigla when its stripped text **equals**
the sigla's stripped canonical text, **or** starts with `canonical_text + " "`
(this keeps `TOTAL`/` 0`/`934` contractor-count suffixes working, e.g.
`"7.-ART 934" → art`).

**`chps`/`CPHS` spelling:** the canonical text for `chps` is corrected to the real
spelling **`CPHS`** (Comité Paritario de Higiene y Seguridad — the code's `CHPS`
was a transposition typo). A small alias set keeps the legacy `CHPS` spelling
accepted too, so a folder named either way resolves to `chps`. The **sigla string
stays `"chps"`** (no change to `SIGLAS`, fixtures, patterns, or the Excel range
name) — only the folder *text* it matches against changes.

### Functions

- `core/domain.py`
  - New private `_folder_text(name: str) -> str` — strips the numeric index.
  - New `_SIGLA_FOLDER_ALIASES: dict[str, tuple[str, ...]]` — `{"chps": ("CHPS",)}`
    (extra accepted spellings beyond the canonical text). Minimal, documented.
  - `CATEGORY_FOLDERS["chps"]` value text corrected from `"18.-CHPS"` to use
    `CPHS` (kept with a nominal number for the absent-folder fallback path; the
    number is irrelevant to matching now).
  - `folder_to_sigla(folder_name)` reimplemented on the rule: compute
    `_folder_text(folder_name)`, compare against each sigla's
    `_folder_text(canonical)` (and its aliases) by the match predicate; return the
    sigla or `None`. Roundtrip and unknown-folder behavior preserved.
  - `sigla_to_folder` unchanged (still returns the canonical, used for nominal
    "folder absent" paths).
- `core/orchestrator/enumeration.py`
  - `_find_category_folder(hosp_dir, sigla)` routed through the rule:
    1. fast path: if `hosp_dir / CATEGORY_FOLDERS[sigla]` exists, return it
       (covers the still-aligned siglas with zero `iterdir`);
    2. else, if `hosp_dir` exists, return the first subdirectory whose
       `folder_to_sigla(sub.name) == sigla`;
    3. else, the nominal `hosp_dir / CATEGORY_FOLDERS[sigla]` (may not exist) —
       unchanged fallback semantics.
  - `enumerate_month` is unchanged structurally; it calls the fixed resolver, so
    `pdf_count_hint`, `folder_exists`, present/missing classification all improve
    automatically for the six.

### Data flow (who benefits, transitively)

All live folder resolution goes through `_find_category_folder` (imported from
`core.orchestrator`): the cell-files + cell-pdf routes (`api/routes/sessions/files.py`),
pase-1 filename scan and pase-2 OCR (via `enumerate_month` / the orchestrator),
and the Excel writer's `checks`/`workers` present-files filter (`api/routes/output.py`).
Fixing the one resolver fixes every consumer. `folder_to_sigla` is currently only
referenced by `tests/unit/test_domain.py`; it is fixed for coherence with the
shared rule.

### Excel-neutrality (the hard constraint)

This increment must not move any number in the generated RESUMEN. It does not,
because:

- All six restored siglas are `count_type == "documents"` (verified in
  `patterns.py::COUNT_TYPE_BY_SIGLA`). Document cells get their Excel value from
  `resolve_cell_value(cell)` over **stored state**, with `present_files=None` — no
  folder access. Restoring resolution does not recompute them.
- The only Excel paths that re-resolve the folder live are `checks` (maquinaria)
  and `workers` (charla/chintegral/dif_pts). All four are **pre-senal**, already
  resolve correctly today (their numbers are unshifted), and are untouched by the
  rule change.

Restoring resolution gives the operator back the ability to **review and
re-count** the six (which *will* update their stored counts when the operator
chooses to) — but the fix itself changes nothing in the output. A
generate-before/after regression check guards this.

### Error handling

- A genuinely-absent sigla folder still resolves to a nominal non-existent path →
  files endpoint returns `[]`, scanners report count 0 with `folder_missing` (A8).
  Unchanged.
- An unmodeled corpus folder (`Revision…`, `Espacios…`) matches no sigla →
  ignored. Unchanged for callers; correct for this increment.
- Ambiguity is impossible: stripped canonical texts are pairwise distinct and
  none is a `+" "` prefix of another (e.g. `"Charlas"` vs `"Charla Integral"`,
  `"Inspeccion Trabajos en Caliente"` vs `"Trabajos en Altura"`), so at most one
  sigla matches any folder. A completeness/uniqueness test asserts this.

## Testing

- **`core/domain.py` (unit):** `folder_to_sigla` maps the **current** disk names
  for all 18 siglas (`"14.-Excavaciones y Vanos" → exc`, …, `"20.-CPHS" → chps`)
  **and** the legacy names (`"13.-Excavaciones y Vanos" → exc`, `"18.-CHPS" → chps`)
  — proving renumber tolerance. Suffix tolerance retained
  (`"7.-ART 934" → art`, `+" 0"`). Unmodeled folders → `None`
  (`"13.-Revision Documentacion Maquinaria"`, `"17.-Espacios Confinados"`,
  `"99.-Unknown"`). Roundtrip `sigla_to_folder`→`folder_to_sigla` preserved.
  Pairwise-distinctness assertion over the 18 stripped canonicals.
- **`_find_category_folder` (unit, tmp dirs):** build a fake hospital dir with the
  **20-folder** layout; assert each of the 18 siglas resolves to the right folder,
  the two extras are never returned, and the fast path still works for an aligned
  layout. Cancel/absent-dir paths unchanged.
- **Excel regression (integration):** generate the RESUMEN for a fixture/real
  session before and after the change; assert the written named-range values are
  identical (Excel-neutrality).
- Full suite green (`-m "not slow"`), ruff 0.

## Risks

- **Over-broad match** (a non-category folder matching a sigla): mitigated by
  exact-text / `+" "` predicate + the distinctness test; the two known extras are
  asserted to resolve to `None`.
- **A month with a *different* text** (not just a different number) would still
  miss — acceptable; this fix targets renumbering + the known `CPHS` spelling, the
  observed drift. A genuinely renamed category is a domain change (Increment B
  territory).

## Verification plan (live, read-only, on a copy DB)

After implementation: restart the backend on a copy DB, hit the cell-files
endpoint for MAYO/HRB `exc/altura/caliente/herramientas_elec/andamios` → expect the
real PDF counts (1/4/9/9/6); `chps`/`senal` → 0 (empty on disk, correct). Confirm
the real `overseer.db` is byte-identical afterward (the read path is read-only).
