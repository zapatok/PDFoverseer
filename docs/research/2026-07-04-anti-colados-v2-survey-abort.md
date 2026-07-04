# Anti-colados vertiente-2 (form-code) — survey findings & ABORT decision

**Date:** 2026-07-04
**Gate:** §7 of `docs/superpowers/specs/2026-07-03-anti-colados-guard-design.md`
**Tool:** `tools/survey_form_codes.py` (ABRIL+MAYO × 4 hospitals, multi-page
PDFs only, HRB over-sampled, production corner-OCR extractor).
**Decision (Daniel, 2026-07-04):** **ABORT vertiente 2.** Vertiente 1 (filename,
shipped, tag `anti-colados-v1`) stands as the anti-colados guard.

## Why the premise failed

Vertiente 2 assumed a page's form code is a reliable **foreign-sigla
discriminator** ("positive foreign evidence only", §1/§2.1). The deep survey
disproved that on the real corpus:

1. **The `F-CRS-LCH-NN` ("Lista de Chequeo") family is SHARED across ~7
   inspection siglas.** Observed cross-sigla code collisions (normalized):
   - `FCR5LCH034` — **exc AND insgral**
   - `FCR5LCH` — **altura, andamios, insgral**
   - `FCR5LCH10` / `FCR5LCH14` — **caliente AND herramientas_elec**
   - `FPET5CR50101` (altura's own PETS-01-01) — also in **andamios**
   - `FCR5ART01` (art) — also read in **andamios**

   A generic checklist code in cell X therefore matches *other* inspection
   siglas' expected sets, so a cell's OWN checklist page would be flagged as a
   foreign colado → systematic false positives. Including any LCH code in a
   sigla's `expected_codes` poisons the guard.

2. **Corner OCR is too noisy for the code to be trusted.** irl read its real
   codes 161× but mixed with non-code word captures (`F0RMADA5`×11,
   `F0RMALA5`×4 = "FORMADAS/…", and `FECHA…` date-field text), and digit/letter
   confusion blurred the few distinct codes (leading zeros `LCH31`/`LCH031`,
   S/5, O/0). The "seen ≥2×" noise filter fails because the misreads repeat
   systematically.

The tool's mechanical verdict ("12 viable siglas") is **misleading** — its
naive `propose()` swept in shared LCH codes and noise. The genuinely
distinct, clean, non-colliding codes belong to only **~3-4 siglas**: bodega
(`F-PETS-CRS-07-03`), espacios (`F-PETS-CRS-08-*`), odi (`F-CRS-ODI-03`), and
irl (`F-CRS-IRL-01`, noise-heavy). ext has **no corner code at all** (already
known). The compilation-heavy inspection siglas — where Daniel says most
*interior* colados live — are exactly the undetectable LCH family.

## Decision rationale

- The reliable slice (interior colados into bodega/espacios/odi only) is too
  thin to justify the `expected_codes` maintenance + the false-positive risk of
  any LCH leakage.
- Vertiente 1 already covers the "whole file in the wrong folder" half of
  colados (Daniel's estimate: ~half), with zero false-positive risk.
- Interior colados remain findable by hand via the existing Incr-J reorg ops
  (extract_pages) — the operator marks them in the viewer; no automation lost
  that existed before.
- This is precisely the §7 abort trigger ("unresolved cross-sigla/cross-hospital
  contradictions") — the gate did its job before Chunk 3 was built.

## What was kept

- `tools/survey_form_codes.py` — committed, reusable if the corpus's form-code
  discipline ever changes (e.g. sigla-specific codes replace the shared LCH
  family).
- The spec's vertiente-2 design is retained as a record of what was evaluated;
  the plan's Chunk 3 is **not executed**.
