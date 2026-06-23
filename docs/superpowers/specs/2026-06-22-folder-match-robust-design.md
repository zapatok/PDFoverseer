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

**`chps`/`CPHS` spelling:** the disk spells it `CPHS` (Comité Paritario de Higiene
y Seguridad — the code's `CHPS` is a transposition typo). Rather than edit the
constant (which would break existing assertions), `CATEGORY_FOLDERS["chps"]` is
left **unchanged** (`"18.-CHPS"`, still used as the nominal absent-folder path) and
the `CPHS` spelling is accepted via a small **alias** set, so a folder named either
way resolves to `chps`. The sigla string stays `"chps"`; nothing in `SIGLAS`,
fixtures, patterns, the Excel range name, or `test_domain.py` changes.

### Functions

- `core/domain.py`
  - New private `_folder_text(name: str) -> str` — strips the numeric index.
  - New `_SIGLA_FOLDER_ALIASES: dict[str, tuple[str, ...]]` — `{"chps": ("CPHS",)}`
    (extra folder-text spellings a sigla also matches, beyond its canonical text).
  - `CATEGORY_FOLDERS` is **unchanged** — `chps` stays `"18.-CHPS"` (the nominal
    absent-folder path); the disk `CPHS` spelling is handled purely by the alias,
    so every existing `test_domain.py` assertion stays green.
  - `folder_to_sigla(folder_name)` reimplemented on the rule: compute
    `_folder_text(folder_name)`, compare against each sigla's
    `_folder_text(canonical)` **and its aliases** by the match predicate; return
    the sigla or `None`. Roundtrip and unknown-folder behavior preserved.
  - Remove the now-dead `_FOLDER_TO_SIGLA` module dict — the reimplemented
    `folder_to_sigla` iterates `CATEGORY_FOLDERS` + aliases directly (avoids a stale
    unused constant / ruff warning).
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

All live folder resolution goes through the single `_find_category_folder`
(imported from `core.orchestrator`); fixing it fixes every consumer transitively.
The full consumer set (verified by search, all benefit with no per-site change):
`api/routes/sessions/files.py` (cell-files + cell-pdf), `api/routes/output.py`
(Excel cell-values, worker-values, **and the history-upsert loop**),
`api/routes/sessions/_common.py` (apply_ratio + per-file override),
`api/routes/sessions/writes.py` (apply_confirmed / set_note / apply_worker_count),
`api/routes/sessions/reorg.py` (op source/dest validation),
`api/routes/sessions/scan.py` (pase-1 + pase-2), and `enumerate_month` itself.
No other code matches folder names by `sub.name ==`/`startswith` — `filename_glob.py`
and `simple_factory.py` receive an **already-resolved** folder and only `rglob`
inside it. `folder_to_sigla` is currently referenced only by
`tests/unit/test_domain.py`; it is fixed for coherence with the shared rule.

### Excel-neutrality (the hard constraint)

This increment must not move any number in the generated RESUMEN. It does not,
because:

- All six restored siglas are `count_type == "documents"` (verified in
  `patterns.py::COUNT_TYPE_BY_SIGLA`). Document cells get their Excel value from
  `resolve_cell_value(cell)` over **stored state**, with `present_files=None` — no
  folder access. Restoring resolution does not recompute them.
- The only Excel paths that re-resolve the folder live are `checks` (maquinaria —
  folder 10, in both `_build_cell_values` and the history-upsert loop) and
  `workers` (charla 4 / chintegral 5 / dif_pts 6, in `_build_worker_values`). All
  are **pre-senal** (numbers ≤ 10, below the 12-boundary where the shift starts),
  already resolve correctly today, and are untouched by the rule change. The
  renumbering only affects folders 13+ (exc onward), none of which feed a live
  folder-resolve on the Excel path.

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

- **`core/domain.py` (unit):** the **existing** `test_domain.py` assertions stay
  green unchanged (CATEGORY_FOLDERS is untouched; roundtrip + `+" 0"`/`+" 934"`
  suffix + unknown→None all still hold). New cases: `folder_to_sigla` maps the
  **current** disk names for all 18 siglas (`"14.-Excavaciones y Vanos" → exc`, …,
  `"20.-CPHS" → chps`) **and** the legacy names (`"13.-Excavaciones y Vanos" → exc`,
  `"18.-CHPS" → chps`) — proving renumber + spelling tolerance; a `charla` suffix
  case (`"4.-Charlas 0" → charla`); the two unmodeled folders → `None`
  (`"13.-Revision Documentacion Maquinaria"`, `"17.-Espacios Confinados"`).
  **Pairwise-distinctness test:** over the set of all stripped match texts (18
  canonicals + the `CPHS` alias), assert for every distinct pair `(a, b)`:
  `a != b and not a.startswith(b + " ") and not b.startswith(a + " ")` — the
  load-bearing no-collision guarantee for the predicate.
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
