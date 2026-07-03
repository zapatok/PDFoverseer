# Pagination-count benchmark — results & migration decision

**Date:** 2026-06-21
**Spec:** `docs/superpowers/specs/2026-06-20-ocr-pagination-refinement-design.md`
**Plan:** `docs/superpowers/plans/2026-06-20-ocr-pagination-refinement.md` (Task 9)
**Harness:** `eval/pagination_count/` (`benchmark.py` + `report.py`); GT = `samples.py`.

Pagination-first engine vs the current production scanner (AnchorsScanner / V4) on light
slices of the real merged MAYO corpus. GT = Daniel's MAYO counts (DB `filename_glob` for whole
merged files = the true divided-state count) / `1-de-1 deterministic` / `eye` (slices + RCH
controls). Δ = count − GT. "recovered" = pages whose corner OCR failed and were filled by lite
sequence-recovery. Data read at runtime; no corpus bytes committed.

## Per-sample results

| sigla | pages | GT | current (Δ) | pagination (Δ) | recovered | source |
|-------|------:|---:|------------:|---------------:|----------:|--------|
| odi | 42 | 21 | 19 (-2) | **21 (0)** | 0 | DB filename_glob |
| art | 20 | 5 | 0 (-5) | **5 (0)** | 8 | eye (clean ARTs) |
| art | 120 | 30 | 19 (-11) | **31 (+1)** | 40 | eye (degraded merged slice) |
| altura | 41 | 20 | 20 (0) | **20 (0)** | 0 | DB filename_glob |
| ext | 38 | 38 | 38 (0) | **38 (0)** | 0 | DB filename_glob |
| bodega | 2 | 2 | 2 (0) | **2 (0)** | 0 | DB filename_glob |
| caliente | 60 | 60 | 60 (0) | **60 (0)** | 3 | 1-de-1 deterministic |
| insgral | 6 | 1 | 1 (0) | **1 (0)** | 1 | DB filename_glob |
| insgral | 48 | 48 | 48 (0) | **48 (0)** | 1 | 1-de-1 deterministic |
| irl | 54 | 1 | 0 (-1) | **1 (0)** | 4 | eye (1 packet, cover_code) |
| exc | 24 | 24 | 24 (0) | **24 (0)** | 0 | DB filename_glob |
| andamios | 39 | 39 | 13 (-26) | **33 (-6)** | 17 | DB filename_glob |
| herramientas_elec | 60 | 60 | 43 (-17) | **60 (0)** | 34 | 1-de-1 deterministic |
| chintegral | 37 | ~25 | 36 (+11) | 35 (+10) | 2 | eye (RCH control) |
| charla | 36 | 36 | 17 (-19) | 36 (0) | 0 | 1-de-1 (RCH control, all 1pp) |
| senal | 24 | 18 | 0 (-18) | 0 (-18) | 0 | DB filename_glob (LANDSCAPE) |

## Decision (controller judgment — overrides the mechanical ≤ verdict on 3 siglas)

**MIGRATE to `pagination`** (pagination wins or ties + is robust/maintainable):
`odi, ext, bodega, caliente, exc, herramientas_elec, art, andamios`, and **`irl`** (with
`cover_code="F-CRS-ODI-01"`). `altura` and `insgral` are already `pagination` → they
auto-upgrade from the heavy V4 to the lite engine (validated: exact, no regression).

- The wins are large where anchors are brittle: clean ART (anchors **0/5** → pagination 5/5),
  degraded merged ART (anchors **-11** → pagination **+1** via recovery), herramientas_elec
  (anchors **-17** → 60/60), IRL (anchors **0** → 1/1 via cover_code).
- **andamios** migrates with the caveat it is **honestly LOW-confidence** (17/39 = 44% recovery
  → above the 0.30 threshold → flagged for the keyboard counter). Still far better than anchors
  (-6 vs -26), and the imperfection is surfaced, not hidden.

**KEEP `anchors`** (mechanical verdict said MIGRATE, but domain judgment overrides):
- **`charla`, `chintegral`, `dif_pts`** (RCH family, spec D6): chintegral is bad for *both*
  methods (+10 / +11 — the confirmed "Página 1 de 2" template bug). charla's sample looked
  perfect only because it had **no 2-page charlas** (where the bug overcounts) — unrepresentative.
  RCH stays anchors + manual confirmation. (dif_pts wasn't sampled but is the same template/bug.)
- **`senal`**: **both** methods got **0/18** — its landscape corner is unreadable by the
  pagination crop AND its body anchors failed on this merged file. Migrating to an equally-broken
  method buys nothing. Stays anchors. **Open follow-up:** landscape-orientation OCR for senal
  (neither path handles it today; in the normal *divided* workflow senal is filename-trivial, so
  this only bites the merged-MAYO artifact).
- **`chps`** (acta, not sampled, low volume), **`maquinaria`** (`checks`, separate), **`reunion`**
  (`none`).

## Notes
- Every migrated sigla is **one-line reversible** (`scan_strategy` back to `"anchors"`).
- Honest-confidence model carries the imperfect cases (andamios, degraded ART): high recovery
  ratio → LOW → the operator confirms with the keyboard counter (the shipped `conteo-confiable`
  + Feature-1 path).
- The merged monsters exaggerate difficulty; in Daniel's future *divided* workflow most of these
  cells are filename-trivial again, and the persistent regime-2 cases (insgral, altura, per-empresa
  ART/odi/irl bundles) are exactly the ones pagination now handles.

## Addendum 2026-07-03 — F7/F8 honest-confidence gate (audit remediation, Fase 4)

Re-ran the 16 real-corpus samples through the production scanners (`_build_scanner_for_sigla`
→ `count_ocr`, same path as `benchmark.py` part (a), plus confidence/flags capture) **before**
(`709bb2b`) and **after** the F7 (`3f87f30`) + F8 (`7768161`) commits.

**Gate result: PASSED.** All 16 counts and `per_file` maps are **identical**. Exactly 3
confidence flips, all `high → low`, all on the intended shapes — no LOW→HIGH, no method change:

| # | sigla | count | flip | new flag | cause |
|---|-------|-------|------|----------|-------|
| 7 | caliente | 60 | high → low | `pagination_low_confidence` | recovered document-starts (F7) |
| 9 | insgral (merged compilation) | 48 | high → low | `pagination_low_confidence` | recovered document-starts (F7) |
| 16 | senal (merged, landscape) | 0 | high → low | `anchors_low_confidence` | 0 covers on a multi-page PDF (F8) |

senal 0/18 finally stops reading as a confident "listo" — it now routes to the keyboard
counter, which was the point of F8. caliente/insgral keep their exact counts; the recovery
that produced them is now surfaced instead of silently trusted (F7's mixed-totals overcount
edge cannot hide behind HIGH anymore).
