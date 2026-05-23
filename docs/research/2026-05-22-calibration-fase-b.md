# Calibración Fase B (sample) — ABRIL 2026

Corrida del **2026-05-23 00:09**.

## Metodología

Muestreo de máximo **2 PDFs por celda × 20 páginas por PDF**. No es un conteo definitivo; es un smoke test para detectar problemas estructurales: carpetas vacías, anchors que no firan, anti_anchors disparándose, errores OCR.

## Resumen ejecutivo

- **Celdas totales:** 72
- **Celdas con flags:** 24
- **Tiempo total OCR:** 834.1 s (13.9 min)

## Tabla resumen (todas las celdas)

| Hosp | sigla | strat | total | smpl-files | smpl-pgs | covers | near | anti | errs | dur (s) | flags |
|------|-------|-------|-------|------------|----------|--------|------|------|------|---------|-------|
| HPV | reunion | none | 2 | 2 | 0 | 2 | 0 | 0 | 0 | 0.0 | — |
| HPV | art | anchors | 767 | 2 | 8 | 0 | 0 | 0 | 0 | 6.2 | no_covers_no_signal |
| HPV | irl | anchors | 141 | 2 | 40 | 2 | 0 | 0 | 0 | 44.3 | — |
| HPV | odi | anchors | 90 | 2 | 4 | 2 | 0 | 0 | 0 | 3.2 | — |
| HPV | charla | anchors | 338 | 2 | 12 | 0 | 2 | 0 | 0 | 13.9 | near_matches_no_covers |
| HPV | insgral | pagination | 206 | 2 | 8 | 0 | 0 | 0 | 2 | 0.0 | no_documents_detected, errors_2 |
| HPV | bodega | anchors | 1 | 1 | 4 | 4 | 0 | 0 | 0 | 3.0 | — |
| HPV | caliente | anchors | 46 | 2 | 20 | 20 | 0 | 0 | 0 | 11.8 | — |
| HPV | exc | anchors | 1 | 1 | 20 | 20 | 0 | 0 | 0 | 18.3 | — |
| HPV | senal | anchors | 3 | 2 | 7 | 1 | 0 | 0 | 0 | 1.7 | — |
| HPV | ext | anchors | 6 | 2 | 16 | 16 | 0 | 0 | 0 | 11.6 | — |
| HPV | maquinaria | anchors | 14 | 2 | 12 | 0 | 0 | 0 | 0 | 10.1 | no_covers_no_signal |
| HPV | altura | pagination | 160 | 2 | 20 | 0 | 0 | 0 | 2 | 0.0 | no_documents_detected, errors_2 |
| HPV | chps | anchors | 1 | 1 | 3 | 1 | 2 | 0 | 0 | 1.9 | — |
| HPV | chintegral | anchors | 6 | 2 | 12 | 0 | 2 | 0 | 0 | 12.3 | near_matches_no_covers |
| HPV | dif_pts | anchors | 19 | 2 | 28 | 24 | 0 | 0 | 0 | 29.4 | — |
| HPV | herramientas_elec | anchors | 215 | 2 | 40 | 38 | 2 | 0 | 0 | 31.3 | — |
| HPV | andamios | anchors | 67 | 2 | 3 | 1 | 1 | 0 | 0 | 2.1 | — |
| HRB | reunion | none | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | folder_missing |
| HRB | art | anchors | 96 | 2 | 38 | 0 | 0 | 0 | 0 | 35.4 | no_covers_no_signal |
| HRB | irl | anchors | 92 | 2 | 40 | 2 | 0 | 0 | 0 | 47.5 | — |
| HRB | odi | anchors | 1 | 1 | 20 | 10 | 0 | 0 | 0 | 19.3 | — |
| HRB | charla | anchors | 46 | 2 | 26 | 17 | 1 | 0 | 0 | 28.6 | — |
| HRB | insgral | pagination | 19 | 2 | 2 | 2 | 0 | 0 | 0 | 0.0 | — |
| HRB | bodega | anchors | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 0.0 | — |
| HRB | caliente | anchors | 4 | 2 | 22 | 2 | 16 | 0 | 0 | 18.6 | — |
| HRB | exc | anchors | 1 | 1 | 2 | 2 | 0 | 0 | 0 | 2.9 | — |
| HRB | senal | anchors | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | folder_missing |
| HRB | ext | anchors | 5 | 2 | 2 | 2 | 0 | 0 | 0 | 0.0 | — |
| HRB | maquinaria | anchors | 8 | 2 | 23 | 1 | 6 | 0 | 0 | 38.4 | — |
| HRB | altura | pagination | 9 | 2 | 2 | 2 | 0 | 0 | 0 | 0.0 | — |
| HRB | chps | anchors | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | folder_missing |
| HRB | chintegral | anchors | 3 | 2 | 25 | 11 | 0 | 0 | 0 | 18.7 | — |
| HRB | dif_pts | anchors | 92 | 2 | 20 | 14 | 2 | 0 | 0 | 20.9 | — |
| HRB | herramientas_elec | anchors | 9 | 2 | 8 | 0 | 1 | 0 | 0 | 7.7 | near_matches_no_covers |
| HRB | andamios | anchors | 7 | 2 | 3 | 1 | 1 | 0 | 0 | 1.9 | — |
| HLU | reunion | none | 1 | 1 | 0 | 1 | 0 | 0 | 0 | 0.0 | — |
| HLU | art | anchors | 7 | 2 | 40 | 1 | 3 | 0 | 0 | 38.0 | — |
| HLU | irl | anchors | 25 | 2 | 40 | 2 | 0 | 0 | 0 | 45.3 | — |
| HLU | odi | anchors | 1 | 1 | 20 | 9 | 1 | 0 | 0 | 13.8 | — |
| HLU | charla | anchors | 7 | 2 | 40 | 3 | 0 | 0 | 0 | 31.0 | — |
| HLU | insgral | pagination | 4 | 2 | 7 | 1 | 0 | 0 | 1 | 0.0 | errors_1 |
| HLU | bodega | anchors | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | folder_missing |
| HLU | caliente | anchors | 1 | 1 | 2 | 2 | 0 | 0 | 0 | 1.3 | — |
| HLU | exc | anchors | 1 | 1 | 5 | 5 | 0 | 0 | 0 | 4.6 | — |
| HLU | senal | anchors | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | folder_missing |
| HLU | ext | anchors | 1 | 1 | 2 | 2 | 0 | 0 | 0 | 1.1 | — |
| HLU | maquinaria | anchors | 2 | 2 | 10 | 4 | 4 | 0 | 0 | 10.1 | — |
| HLU | altura | pagination | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | folder_missing |
| HLU | chps | anchors | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | folder_missing |
| HLU | chintegral | anchors | 3 | 2 | 9 | 1 | 1 | 0 | 0 | 8.6 | — |
| HLU | dif_pts | anchors | 5 | 2 | 22 | 22 | 0 | 0 | 0 | 25.3 | — |
| HLU | herramientas_elec | anchors | 3 | 2 | 10 | 10 | 0 | 0 | 0 | 7.4 | — |
| HLU | andamios | anchors | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | folder_missing |
| HLL | reunion | none | 1 | 1 | 0 | 1 | 0 | 0 | 0 | 0.0 | — |
| HLL | art | anchors | 1 | 1 | 20 | 0 | 0 | 0 | 0 | 17.9 | no_covers_no_signal |
| HLL | irl | anchors | 89 | 2 | 40 | 2 | 0 | 0 | 0 | 40.7 | — |
| HLL | odi | anchors | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | folder_missing |
| HLL | charla | anchors | 1 | 1 | 20 | 15 | 0 | 0 | 0 | 20.2 | — |
| HLL | insgral | pagination | 1 | 1 | 6 | 0 | 0 | 0 | 1 | 0.0 | no_documents_detected, errors_1 |
| HLL | bodega | anchors | 1 | 1 | 2 | 2 | 0 | 0 | 0 | 1.5 | — |
| HLL | caliente | anchors | 1 | 1 | 20 | 20 | 0 | 0 | 0 | 14.5 | — |
| HLL | exc | anchors | 1 | 1 | 20 | 20 | 0 | 0 | 0 | 17.7 | — |
| HLL | senal | anchors | 1 | 1 | 20 | 0 | 6 | 0 | 0 | 10.2 | near_matches_no_covers |
| HLL | ext | anchors | 1 | 1 | 20 | 17 | 3 | 0 | 0 | 14.5 | — |
| HLL | maquinaria | anchors | 1 | 1 | 14 | 2 | 6 | 0 | 0 | 11.7 | — |
| HLL | altura | pagination | 1 | 1 | 770 | 0 | 0 | 0 | 1 | 0.0 | no_documents_detected, errors_1 |
| HLL | chps | anchors | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | folder_missing |
| HLL | chintegral | anchors | 1 | 1 | 10 | 1 | 4 | 0 | 0 | 7.0 | — |
| HLL | dif_pts | anchors | 1 | 1 | 20 | 9 | 1 | 10 | 0 | 17.5 | anti_anchored_10 |
| HLL | herramientas_elec | anchors | 1 | 1 | 20 | 19 | 1 | 0 | 0 | 15.2 | — |
| HLL | andamios | anchors | 1 | 1 | 20 | 3 | 10 | 0 | 0 | 18.0 | — |

## Celdas con flags (detalle)

### HPV / art — no_covers_no_signal

- **Files (total):** 767 · **sampled:** 2 files / 8 pages
- **Detected:** 0 covers · **near:** 0 · **anti:** 0 · **errs:** 0
- **Notes:** sample of 2/767 files

### HPV / charla — near_matches_no_covers

- **Files (total):** 338 · **sampled:** 2 files / 12 pages
- **Detected:** 0 covers · **near:** 2 · **anti:** 0 · **errs:** 0
- **Notes:** sample of 2/338 files

### HPV / insgral — no_documents_detected, errors_2

- **Files (total):** 206 · **sampled:** 2 files / 8 pages
- **Detected:** 0 covers · **near:** 0 · **anti:** 0 · **errs:** 2
- **Notes:** V4 inferred=0 failed=0; sample of 2/206 files

### HPV / maquinaria — no_covers_no_signal

- **Files (total):** 14 · **sampled:** 2 files / 12 pages
- **Detected:** 0 covers · **near:** 0 · **anti:** 0 · **errs:** 0
- **Notes:** sample of 2/14 files

### HPV / altura — no_documents_detected, errors_2

- **Files (total):** 160 · **sampled:** 2 files / 20 pages
- **Detected:** 0 covers · **near:** 0 · **anti:** 0 · **errs:** 2
- **Notes:** V4 inferred=0 failed=0; sample of 2/160 files

### HPV / chintegral — near_matches_no_covers

- **Files (total):** 6 · **sampled:** 2 files / 12 pages
- **Detected:** 0 covers · **near:** 2 · **anti:** 0 · **errs:** 0
- **Notes:** sample of 2/6 files

### HRB / reunion — folder_missing

- **Files (total):** 0 · **sampled:** 0 files / 0 pages
- **Detected:** 0 covers · **near:** 0 · **anti:** 0 · **errs:** 0

### HRB / art — no_covers_no_signal

- **Files (total):** 96 · **sampled:** 2 files / 38 pages
- **Detected:** 0 covers · **near:** 0 · **anti:** 0 · **errs:** 0
- **Notes:** sample of 2/96 files

### HRB / senal — folder_missing

- **Files (total):** 0 · **sampled:** 0 files / 0 pages
- **Detected:** 0 covers · **near:** 0 · **anti:** 0 · **errs:** 0

### HRB / chps — folder_missing

- **Files (total):** 0 · **sampled:** 0 files / 0 pages
- **Detected:** 0 covers · **near:** 0 · **anti:** 0 · **errs:** 0

### HRB / herramientas_elec — near_matches_no_covers

- **Files (total):** 9 · **sampled:** 2 files / 8 pages
- **Detected:** 0 covers · **near:** 1 · **anti:** 0 · **errs:** 0
- **Notes:** sample of 2/9 files

### HLU / insgral — errors_1

- **Files (total):** 4 · **sampled:** 2 files / 7 pages
- **Detected:** 1 covers · **near:** 0 · **anti:** 0 · **errs:** 1
- **Notes:** V4 inferred=0 failed=0; sample of 2/4 files

### HLU / bodega — folder_missing

- **Files (total):** 0 · **sampled:** 0 files / 0 pages
- **Detected:** 0 covers · **near:** 0 · **anti:** 0 · **errs:** 0

### HLU / senal — folder_missing

- **Files (total):** 0 · **sampled:** 0 files / 0 pages
- **Detected:** 0 covers · **near:** 0 · **anti:** 0 · **errs:** 0

### HLU / altura — folder_missing

- **Files (total):** 0 · **sampled:** 0 files / 0 pages
- **Detected:** 0 covers · **near:** 0 · **anti:** 0 · **errs:** 0

### HLU / chps — folder_missing

- **Files (total):** 0 · **sampled:** 0 files / 0 pages
- **Detected:** 0 covers · **near:** 0 · **anti:** 0 · **errs:** 0

### HLU / andamios — folder_missing

- **Files (total):** 0 · **sampled:** 0 files / 0 pages
- **Detected:** 0 covers · **near:** 0 · **anti:** 0 · **errs:** 0

### HLL / art — no_covers_no_signal

- **Files (total):** 1 · **sampled:** 1 files / 20 pages
- **Detected:** 0 covers · **near:** 0 · **anti:** 0 · **errs:** 0

### HLL / odi — folder_missing

- **Files (total):** 0 · **sampled:** 0 files / 0 pages
- **Detected:** 0 covers · **near:** 0 · **anti:** 0 · **errs:** 0

### HLL / insgral — no_documents_detected, errors_1

- **Files (total):** 1 · **sampled:** 1 files / 6 pages
- **Detected:** 0 covers · **near:** 0 · **anti:** 0 · **errs:** 1
- **Notes:** V4 inferred=0 failed=0

### HLL / senal — near_matches_no_covers

- **Files (total):** 1 · **sampled:** 1 files / 20 pages
- **Detected:** 0 covers · **near:** 6 · **anti:** 0 · **errs:** 0

### HLL / altura — no_documents_detected, errors_1

- **Files (total):** 1 · **sampled:** 1 files / 770 pages
- **Detected:** 0 covers · **near:** 0 · **anti:** 0 · **errs:** 1
- **Notes:** V4 inferred=0 failed=0

### HLL / chps — folder_missing

- **Files (total):** 0 · **sampled:** 0 files / 0 pages
- **Detected:** 0 covers · **near:** 0 · **anti:** 0 · **errs:** 0

### HLL / dif_pts — anti_anchored_10

- **Files (total):** 1 · **sampled:** 1 files / 20 pages
- **Detected:** 9 covers · **near:** 1 · **anti:** 10 · **errs:** 0
