# ABRIL 2026 corpus audit — what PDFoverseer actually faces

> Audit date: 2026-05-11. Snapshot of `A:\informe mensual\ABRIL\` for HPV/HRB/HLU only (HLL not normalized yet this month).
>
> Purpose: ground PDFoverseer's design in the real corpus instead of the per-family research lens. Read before any UI/UX overhaul or scope discussion.

## TL;DR

PDFoverseer's job is **NOT "scan a PDF and count entries"** generically. The corpus has **two distinct regimes** with very different needs:

| Regime | What it looks like | What PDFoverseer needs to do |
|---|---|---|
| **Trivial** | 1 PDF = 1 scanned document, named `YYYY-MM-DD_sigla_descriptor_empresa.pdf` | Walk folder, group by sigla in filename, return count. **No OCR needed.** |
| **Compilation** | 1 PDF contains N stacked documents (e.g. HRB ODI: 1 file = 34 pages = ~17 ODIs) | Detect document boundaries inside the PDF (page splits, form headers) and count |

Most categories × hospitals fall in the trivial regime in ABRIL. The compilation regime is concentrated in:

- **HRB ODI Visitas** (1 PDF, 34 pages)
- **HLU ODI Visitas** (1 PDF, 48 pages)
- **HRB IRL** (92 PDFs, but ≥1 sample is 37 pages — needs deeper audit)
- Likely older months (FEBRERO, MARZO) where files weren't yet individualized by `informe mensual/.scripts/renombrar_archivos.py`

## The shared environment

The `informe mensual` sibling project already enforces strong conventions that PDFoverseer should leverage:

1. **Filename format**: `YYYY-MM-DD_sigla_descriptor_empresa.pdf` (snake_case, no accents, no ñ)
2. **18 canonical siglas** (matches 18 prevention categories): `reunion, irl, odi, charla, chintegral, dif_pts, art, insgral, bodega, maquinaria, ext, senal, exc, altura, caliente, herramientas_elec, andamios, chps`
3. **Folder naming**: `N.-Nombre Canónico` for empty, `N.-Nombre TOTAL` once counted (e.g. `7.-ART 934`). `0` suffix = zero activity that month.
4. **Per-empresa subfolders** (HPV only mostly): inside a category folder, subfolders by empresa name with format `EMPRESA COUNT` (e.g. `CRS 483`)

These conventions mean **classification by sigla is filename-trivial** — no model required. The hard part is the count itself when files are compilations.

## Per-category × hospital audit (ABRIL 2026)

| # | Categoría | HPV | HRB | HLU | Compilation suspects |
|---|---|---|---|---|---|
| 1 | reunion | 2 PDFs, flat | 0 | 1 PDF, flat | none |
| 2 | irl | 141 PDFs, flat (1/worker) | 92 PDFs (sample 37 pp ⚠) | 25 PDFs, flat | **HRB IRL** — confirm |
| 3 | odi | 90 PDFs, flat | **1 PDF, 34 pp** ⚠ | **1 PDF, 48 pp** ⚠ | **HRB ODI, HLU ODI** |
| 4 | charla | 338 PDFs, 16 empresa subs | 46 PDFs, 16 empresa subs | 7 PDFs, flat | likely none |
| 5 | chintegral | 6 PDFs (4-6 pp each) | 3 PDFs | 3 PDFs (sample 8 pp) | none — multi-page is normal |
| 6 | dif_pts | 19 PDFs (14 pp/sample) | 92 PDFs (10 pp/sample) | 5 PDFs | possibly — page count high vs file count |
| 7 | art | **767 PDFs**, 13 empresa subs | 96 PDFs, 16 empresa subs | 7 PDFs, flat | trivial |
| 8 | insgral | 206 PDFs, 10 empresa subs | 19 PDFs, flat | 4 PDFs, flat | trivial |
| 9 | bodega | 1 PDF, flat | 2 PDFs, flat | 0 | trivial |
| 10 | maquinaria | 14 PDFs, 3 subs | 8 PDFs, flat | 2 PDFs, flat | trivial |
| 11 | ext | 6 PDFs, 4 subs | 5 PDFs, flat | 1 PDF, flat | trivial |
| 12 | senal | 3 PDFs, 2 subs | 0 | 0 | trivial |
| 13 | exc | 1 PDF, flat | 1 PDF, flat | 1 PDF, flat | trivial |
| 14 | altura | 160 PDFs, 6 subs | 9 PDFs, 1 sub | 0 | trivial |
| 15 | caliente | 46 PDFs, 5 subs | 4 PDFs, flat | 1 PDF, flat | trivial |
| 16 | herramientas_elec | 215 PDFs, 9 subs | 9 PDFs, flat | 3 PDFs, flat | trivial |
| 17 | andamios | 67 PDFs, 4 subs | 7 PDFs, flat | 0 | trivial |
| 18 | chps | 1 PDF, flat | 0 | 0 | trivial |

Empty cells (0 PDFs, " 0" suffix on folder) are a normal monthly state and a routine output value.

### Compilation rate estimate

Of 54 (hospital × category) cells:
- **0 explicit compilados** (no `compilacion_para_contar_*.pdf` exists)
- **3 confirmed implicit compilations** (HRB ODI, HLU ODI, HRB IRL — need verification)
- **~51 trivial** = filename glob suffices

If this holds, **>90% of PDFoverseer's work is filename-based**. The OCR/inference engine is needed for the remaining ~10%.

## What documents actually look like

PDF content varies. From 10-sample inspection:

- **Most pages are pure scans** — no text layer, OCR required to read content
- **Some PDFs have a text layer** (digitally generated forms) — readable directly with PyMuPDF `get_text()`
- **Documents follow standardized templates** with header codes:
  - `F-CRS-ODI/03` — ODI form (Obligación de Informar / Visita)
  - `F-CRS-RCH-01` — Registro de Charla (chintegral, charlas)
  - Likely a code per sigla
- **Individual document length** typically 2-5 pages (one ODI = 2 pages, one chintegral = 5-8 pages)

This means a **header-template detection approach** could count documents inside a compilation by counting form-header occurrences — potentially more robust than pixel-density alone.

## Inputs (the path PDFoverseer should consume)

```
A:\informe mensual\<MES>\<HOSPITAL>\
├── 1.-Reunion Prevencion[ TOTAL | 0]
├── 2.-Induccion IRL[ TOTAL | 0]
├── ...                                          ← 18 numbered subfolders
└── 18.-CHPS[ TOTAL | 0]
```

The current PDFoverseer flow ("open one PDF at a time") fights this layout. Natural input unit is **a category folder**, not a single PDF.

## Output (the one target)

Single Excel file: `A:\informe mensual\<MES>\RESUMEN_<MES>_<YYYY>.xlsx`, sheet "Cump. Programa Prevención":

- 18 rows × 4 hospitals × (Cantidad Realizada + HH) + TOTALS = 72 cantidad cells to fill
- HH columns are Excel formulas (workforce count × coefficient); PDFoverseer does **not** touch them
- The folder name suffix (`7.-ART 934`) is the same number that goes into the Excel cell — they should match

Future evolution: a parallel JSON output for downstream tools is plausible, but not implemented yet.

## What PDFoverseer probably does WRONG right now

Looking at the audit through the lens of the current app:

1. **Single-PDF input unit** — wrong for ~95% of category cells. Should be folder-level.
2. **Heavy OCR/inference on every PDF** — wasteful when filename + page count would suffice for trivial cases.
3. **Per-PDF UI flow** — the user has 54 cells to populate per month; per-PDF UX is 100× more clicks than needed.
4. **Pixel-density experiments target the hard 10% case only** — solving that is valuable but not the headline goal. The headline is the full 72-cell Excel output.
5. **Probably nothing currently writes the Excel** — the existing UI shows counts in browser, but the bridge to `RESUMEN_<MES>_2026.xlsx` is missing. Verify before redesigning.

## Suggested redesign anchors (for discussion, not yet decided)

- **Input**: pick a month folder (e.g. `A:\informe mensual\ABRIL\`). App enumerates the 4 hospitals × 18 categories automatically.
- **Per cell**: app shows count from filename glob; flags cells where compilation is likely (heuristic: 1 PDF + >10 pages + sigla matches IRL/ODI patterns).
- **Compilation cells**: user clicks → OCR/inference engine runs only there → app shows detected count + confidence + ability to override.
- **Output**: button "Generar RESUMEN" writes the Excel directly to the month folder (or anywhere user picks).
- **Confidence per cell**: surface accuracy badges (green = filename count, yellow = OCR estimate, red = low confidence) — matches user statement "me ayuda a contar algunos tipos y otros no".

## Open questions for the user

- Does the workflow ever need to handle older months (FEBRERO, MARZO) where compilation prevalence might be much higher? Or is ABRIL forward the only target?
- Is the per-empresa breakdown (`CRS 483` inside `7.-ART 934`) part of what PDFoverseer should report, or only the rolled-up category total?
- When PDFoverseer disagrees with the user's manual count, who wins by default? (Currently the human; do we want that explicit in UI?)
- Should the app *write* the folder rename (`7.-ART` → `7.-ART 934`) as part of its output, or only the Excel cell?
