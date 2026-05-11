# RESUMEN Excel Templates

## RESUMEN_template_v1.xlsx

Source for the monthly **Cumplimiento Programa Prevención** workbook.

The Excel writer (`core/excel/writer.py`) loads this template, fills cells by *named range*, and writes to `data/outputs/RESUMEN_<MES>_<AÑO>.xlsx` or a user-chosen path. Named ranges decouple the writer from cell positions — the template can evolve without breaking code as long as the same names exist.

### Structure

Single sheet (the sheet title contains `Cump. Programa Prevención` with accents).

| Section | Rows | Notes |
|---|---|---|
| Header / branding | 1-8 | Logo cell, title row, antecedentes |
| Column headers | 9 | "Cantidad Realizada \| HH Capacitación" per hospital + TOTAL |
| Sigla rows (canonical 18) | 10-21, 23-25, 27-28, 31 | One row per sigla — see mapping below |
| Orphan rows | 22, 26 | Inherited from the production sample, NOT mapped to any sigla. Left in place for layout fidelity; the writer never touches them. |
| Workforce inputs | 29-30 | Values live in the HH columns (H/J/L/N), not the cantidad columns |

### Named range conventions

**Cantidad cells (72 ranges)** — `<HOSPITAL>_<SIGLA>_count`:

- `<HOSPITAL>` ∈ `HLL`, `HLU`, `HRB`, `HPV`
- `<SIGLA>` ∈ the 18 siglas defined in `core/domain.py:SIGLAS`
- Each range resolves to a single cell in column G (HLL), I (HLU), K (HRB), or M (HPV)

Examples: `HPV_art_count` → `M16` · `HLL_reunion_count` → `G10` · `HRB_chps_count` → `K31`

**Workforce cells (8 ranges)** — `<HOSPITAL>_workers_<PURPOSE>`:

- `<PURPOSE>` ∈ `chgen` (charlas generales diarias) or `chintegral` (charla integral semanal)
- Each range resolves to a single cell in column H (HLL), J (HLU), L (HRB), or N (HPV) — note these are **HH columns**, not cantidad columns
- Used by the HH Capacitación formulas in rows 13-14

Examples: `HPV_workers_chgen` → `N29` · `HLL_workers_chintegral` → `H30`

### Sigla → row mapping

| Sigla | Row | Sample header (column B) |
|---|---|---|
| reunion | 10 | "Nº de Reuniones de Prevención de Riesgos" |
| irl | 11 | "Nº de Charlas de Inducción (ODI)" *(label mislabeled in original sample — formula confirms IRL)* |
| odi | 12 | "Nº de Charlas de Inducción Visita" |
| charla | 13 | "Nº de Charlas Generales (Diarias)" |
| chintegral | 14 | "Nº de Charlas Integrales" |
| dif_pts | 15 | "Difusión de PTS" |
| art | 16 | "ART realizadas" |
| insgral | 17 | "Nº de Inspecciones Generales a las áreas de trabajo" |
| bodega | 18 | "Nº de Inspecciones a bodegas SUSPEL/RESPEL" |
| maquinaria | 19 | "Nº de Inspecciones a maquinarias y equipo" |
| ext | 20 | "Nº de Inspecciones a equipamiento de emergencia (extintores)" |
| senal | 21 | "Nº de Inspecciones a señalética de obra" |
| *(orphan)* | *22* | *"Revisión de Documentación de maquinaria" — not in canonical 18* |
| exc | 23 | "Inspección de medidas de seguridad en excavaciones" |
| altura | 24 | "Inspección a medidas de seguridad en trabajo en altura" |
| caliente | 25 | "Inspección de Medidas de Seguridad para trabajo en caliente" |
| *(orphan)* | *26* | *"Inspección de Medidas de Seguridad para trabajos en espacios confinados" — not in canonical 18* |
| herramientas_elec | 27 | "Inspección de Herramientas Eléctricas" |
| andamios | 28 | "Inspección de Andamios" |
| chps | **31** | "CHPS — Comité Paritario de Higiene y Seguridad" *(added by builder — sample has no CHPS row)* |

### Rebuilding

Run from project root:

```bash
python data/templates/build_template_v1.py
```

Idempotent. Overwrites the existing `RESUMEN_template_v1.xlsx`. Source is the production sample at `data/output_sample/RESUMEN_ABRIL_2026.xlsx`.

### Versioning

When the layout changes in a breaking way (cells move, new sigla added, etc.):

1. Bump the suffix: `RESUMEN_template_v2.xlsx`
2. Add `build_template_v2.py`
3. Update `core/excel/template.py:DEFAULT_TEMPLATE`
4. Keep `v1` in the repo for backward compat

### Known limitations of v1

- Orphan rows (22, 26) inherited from sample — could be removed in v2 if Daniel confirms they're not needed
- CHPS row at 31 is below the workforce rows (29-30) — visually unusual. v2 could reorder so all 18 siglas come before workforce
- Header labels still in cp1252 with accent encoding artifacts from the original — purely cosmetic, opening in Excel renders correctly
