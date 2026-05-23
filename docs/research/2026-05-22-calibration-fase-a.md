# Calibración Fase A — ABRIL 2026

Corrida del **2026-05-22**. 8 celdas spot-check para calibrar la confianza en los scanners ocr-per-sigla antes de un diagnóstico amplio (Fase B).

## Cómo leer este reporte

Para cada celda muestro:

1. **Strategy / flavors / carpeta / archivos**: configuración del scanner.
2. **Total portadas/documentos detectados**: lo que el scanner contaría para esa celda hoy.
3. **Detalle por archivo y por página** (estrategia anchors):
   - ✓ `portada f_xxx` — la página fue clasificada como cover; lista las anclas que machearon.
   - 🚫 `anti-anchor` — la página parecía portada pero un anti-anchor la descartó (p.ej. ART en andamios).
   - ⚠ `casi-match` — la página matcheó `min_match - 1` anclas; es candidata a flavor nuevo (A14).
   - — `sin match` — interior del documento.
4. **Detalle por archivo** (estrategia V4): páginas directas / inferidas / falladas + nivel de confianza.

**Tu trabajo:** abre los PDFs marcados con ⚠ o ✓ que parezcan dudosos y confirma o refuta. No tienes que contar todo de cero — solo verificar lo que el scanner dijo.

---

## HRB / bodega

_A7 trivial + anchors mono-flavor — el caso canónico de 1-pág_

- **Strategy:** `anchors`  ·  **top_fraction:** `0.25`  ·  **flavors:** 1 (`f_pets_07_03`)
- **Carpeta:** `HRB/9.-Inspeccion Bodega`
- **Archivos en carpeta:** 2

### → **Total portadas detectadas: 2**

### `2026-05-08_bodega_respel.pdf` (1 pp) — **1** (A7 — locked sin OCR)

### `2026-05-08_bodega_suspel.pdf` (1 pp) — **1** (A7 — locked sin OCR)

_(tiempo de escaneo: 0.0 s)_

---

## HRB / chintegral

_multi-flavor (F-CRS-RCH + JAPA + PREVIENE)_

- **Strategy:** `anchors`  ·  **top_fraction:** `0.3333333333333333`  ·  **flavors:** 3 (`f_rch, f_japa, f_previene`)
- **Carpeta:** `HRB/5.-Charla Integral`
- **Archivos en carpeta:** 3

### → **Total portadas detectadas: 19**

### `2026-04-08_chintegral.pdf` (18 pp) — **10** portada(s)
- p.1: ✓ portada `f_rch` — anclas: ['nombre de la charla', 'relator', 'cargo relator', 'tipologia de charla', 'charla de induccion', 'charla re instruccion', 'reunion de coordinacion', 'difusion de documentos']
- p.2: ✓ portada `f_rch` — anclas: ['nombre de la charla', 'charla de induccion', 'charla re instruccion', 'reunion de coordinacion', 'difusion de documentos']
- p.3: ✓ portada `f_rch` — anclas: ['nombre de la charla', 'tipologia de charla', 'charla de induccion', 'charla re instruccion', 'reunion de coordinacion', 'difusion de documentos']
- p.4: ✓ portada `f_rch` — anclas: ['nombre de la charla', 'relator', 'cargo relator', 'charla de induccion', 'charla re instruccion', 'reunion de coordinacion', 'difusion de documentos']
- p.5: ✓ portada `f_rch` — anclas: ['nombre de la charla', 'relator', 'cargo relator', 'charla de induccion', 'charla re instruccion', 'difusion de documentos']
- p.6: ✓ portada `f_rch` — anclas: ['nombre de la charla', 'charla de induccion', 'charla re instruccion', 'reunion de coordinacion', 'difusion de documentos']
- p.7: ✓ portada `f_rch` — anclas: ['nombre de la charla', 'charla de induccion', 'charla re instruccion', 'reunion de coordinacion', 'difusion de documentos']
- p.8: ✓ portada `f_rch` — anclas: ['nombre de la charla', 'charla de induccion', 'charla re instruccion', 'reunion de coordinacion', 'difusion de documentos']
- p.9: ✓ portada `f_rch` — anclas: ['nombre de la charla', 'charla de induccion', 'charla re instruccion', 'reunion de coordinacion', 'difusion de documentos']
- p.10: ✓ portada `f_rch` — anclas: ['nombre de la charla', 'relator', 'cargo relator', 'charla de induccion', 'charla re instruccion', 'reunion de coordinacion', 'difusion de documentos']
- p.11: — sin match
- p.12: — sin match
- p.13: — sin match
- p.14: — sin match
- p.15: — sin match
- p.16: — sin match
- p.17: — sin match
- p.18: — sin match

### `2026-04-15_chintegral.pdf` (7 pp) — **1** portada(s)
- p.1: — sin match
- p.2: — sin match
- p.3: — sin match
- p.4: — sin match
- p.5: — sin match
- p.6: — sin match
- p.7: ✓ portada `f_rch` — anclas: ['nombre de la charla', 'relator', 'cargo relator']

### `2026-04-22_chintegral.pdf` (13 pp) — **8** portada(s)
- p.1: — sin match
- p.2: ✓ portada `f_rch` — anclas: ['nombre de la charla', 'relator', 'cargo relator']
- p.3: ✓ portada `f_rch` — anclas: ['nombre de la charla', 'relator', 'cargo relator']
- p.4: ✓ portada `f_rch` — anclas: ['nombre de la charla', 'relator', 'cargo relator']
- p.5: ✓ portada `f_rch` — anclas: ['nombre de la charla', 'relator', 'cargo relator']
- p.6: ✓ portada `f_rch` — anclas: ['nombre de la charla', 'relator', 'cargo relator']
- p.7: — sin match
- p.8: ✓ portada `f_rch` — anclas: ['nombre de la charla', 'relator', 'cargo relator']
- p.9: ✓ portada `f_rch` — anclas: ['nombre de la charla', 'relator', 'cargo relator']
- p.10: ✓ portada `f_rch` — anclas: ['nombre de la charla', 'relator', 'cargo relator']
- p.11: — sin match
- p.12: — sin match
- p.13: — sin match

_(tiempo de escaneo: 30.0 s)_

---

## HLU / odi

_1 PDF marcado como compilación-sospechosa (flag automático)_

- **Strategy:** `anchors`  ·  **top_fraction:** `0.25`  ·  **flavors:** 1 (`f_crs_odi_03`)
- **Carpeta:** `HLU/3.-ODI Visitas`
- **Archivos en carpeta:** 1

### → **Total portadas detectadas: 21**

### `2026-05-06_odi.pdf` (48 pp) — **21** portada(s)
- p.1: ✓ portada `f_crs_odi_03` — anclas: ['nombre completo', 'actividad', 'medidas de control', 'pagina 1 de']
- p.2: — sin match
- p.3: ✓ portada `f_crs_odi_03` — anclas: ['nombre completo', 'actividad', 'medidas de control', 'pagina 1 de']
- p.4: — sin match
- p.5: ✓ portada `f_crs_odi_03` — anclas: ['nombre completo', 'actividad', 'medidas de control', 'pagina 1 de']
- p.6: — sin match
- p.7: ✓ portada `f_crs_odi_03` — anclas: ['empresa', 'actividad', 'medidas de control', 'pagina 1 de']
- p.8: — sin match
- p.9: ✓ portada `f_crs_odi_03` — anclas: ['nombre completo', 'actividad', 'medidas de control', 'pagina 1 de']
- p.10: — sin match
- p.11: ✓ portada `f_crs_odi_03` — anclas: ['nombre completo', 'empresa', 'actividad', 'medidas de control', 'pagina 1 de']
- p.12: — sin match
- p.13: ✓ portada `f_crs_odi_03` — anclas: ['nombre completo', 'actividad', 'medidas de control', 'pagina 1 de']
- p.14: — sin match
- p.15: ✓ portada `f_crs_odi_03` — anclas: ['nombre completo', 'empresa', 'pagina 1 de']
- p.16: — sin match
- p.17: ⚠ casi-match `f_crs_odi_03` — machearon: ['nombre completo', 'pagina 1 de']; faltó: ['n telefonico', 'c identidad', 'empresa', 'actividad', 'peligro incidente potencial', 'medidas de control']
- p.18: — sin match
- p.19: ✓ portada `f_crs_odi_03` — anclas: ['nombre completo', 'actividad', 'medidas de control', 'pagina 1 de']
- p.20: — sin match
- p.21: ✓ portada `f_crs_odi_03` — anclas: ['nombre completo', 'empresa', 'pagina 1 de']
- p.22: — sin match
- p.23: ✓ portada `f_crs_odi_03` — anclas: ['nombre completo', 'empresa', 'actividad', 'medidas de control', 'pagina 1 de']
- p.24: — sin match
- p.25: ⚠ casi-match `f_crs_odi_03` — machearon: ['nombre completo', 'pagina 1 de']; faltó: ['n telefonico', 'c identidad', 'empresa', 'actividad', 'peligro incidente potencial', 'medidas de control']
- p.26: — sin match
- p.27: ⚠ casi-match `f_crs_odi_03` — machearon: ['nombre completo', 'pagina 1 de']; faltó: ['n telefonico', 'c identidad', 'empresa', 'actividad', 'peligro incidente potencial', 'medidas de control']
- p.28: — sin match
- p.29: ✓ portada `f_crs_odi_03` — anclas: ['nombre completo', 'actividad', 'medidas de control', 'pagina 1 de']
- p.30: — sin match
- p.31: ✓ portada `f_crs_odi_03` — anclas: ['nombre completo', 'empresa', 'actividad', 'medidas de control', 'pagina 1 de']
- p.32: — sin match
- p.33: ✓ portada `f_crs_odi_03` — anclas: ['nombre completo', 'empresa', 'actividad', 'pagina 1 de']
- p.34: — sin match
- p.35: ✓ portada `f_crs_odi_03` — anclas: ['nombre completo', 'empresa', 'actividad', 'medidas de control', 'pagina 1 de']
- p.36: — sin match
- p.37: ✓ portada `f_crs_odi_03` — anclas: ['nombre completo', 'medidas de control', 'pagina 1 de']
- p.38: — sin match
- p.39: ✓ portada `f_crs_odi_03` — anclas: ['nombre completo', 'empresa', 'actividad', 'medidas de control', 'pagina 1 de']
- p.40: — sin match
- p.41: ✓ portada `f_crs_odi_03` — anclas: ['nombre completo', 'empresa', 'medidas de control', 'pagina 1 de']
- p.42: — sin match
- p.43: ✓ portada `f_crs_odi_03` — anclas: ['nombre completo', 'empresa', 'actividad', 'medidas de control', 'pagina 1 de']
- p.44: — sin match
- p.45: ✓ portada `f_crs_odi_03` — anclas: ['nombre completo', 'empresa', 'pagina 1 de']
- p.46: — sin match
- p.47: ✓ portada `f_crs_odi_03` — anclas: ['nombre completo', 'empresa', 'actividad', 'medidas de control', 'pagina 1 de']
- p.48: — sin match

_(tiempo de escaneo: 35.0 s)_

---

## HRB / andamios

_multi-flavor (F-CRS-LCH-05 + RIBEIRO) + anti-anchor ART_

- **Strategy:** `anchors`  ·  **top_fraction:** `0.25`  ·  **flavors:** 2 (`f_lch_05, f_ribeiro`)
- **Carpeta:** `HRB/17.-Andamios`
- **Archivos en carpeta:** 7

### → **Total portadas detectadas: 5**

### `2026-04-02_andamios_check_list.pdf` (1 pp) — **1** (A7 — locked sin OCR)

### `2026-05-08_andamios_check_list.pdf` (2 pp) — **0** portada(s)
- p.1: ⚠ casi-match `f_lch_05` — machearon: ['lista de chequeo de andamios', 'pagina 1 de']; faltó: ['constructora region sur', 'f crs lch 05', 'tipo andamio', 'datos del andamio', 'superficie de apoyo', 'estructura del andamio', 'plataformas de trabajo']
- p.2: — sin match

### `2026-05-08_andamios_check_list_a.pdf` (6 pp) — **0** portada(s)
- p.1: — sin match
- p.2: — sin match
- p.3: — sin match
- p.4: — sin match
- p.5: — sin match
- p.6: — sin match

### `2026-05-08_andamios_check_list_b.pdf` (6 pp) — **0** portada(s)
- p.1: — sin match
- p.2: — sin match
- p.3: — sin match
- p.4: — sin match
- p.5: — sin match
- p.6: — sin match

### `2026-05-08_andamios_check_list_c.pdf` (4 pp) — **1** portada(s)
- p.1: — sin match
- p.2: — sin match
- p.3: ✓ portada `f_lch_05` — anclas: ['lista de chequeo de andamios', 'datos del andamio', 'pagina 1 de']
- p.4: ⚠ casi-match `f_lch_05` — machearon: ['lista de chequeo de andamios', 'datos del andamio']; faltó: ['constructora region sur', 'f crs lch 05', 'tipo andamio', 'superficie de apoyo', 'estructura del andamio', 'plataformas de trabajo', 'pagina 1 de']

### `2026-05-08_andamios_check_list_d.pdf` (6 pp) — **0** portada(s)
- p.1: — sin match
- p.2: — sin match
- p.3: — sin match
- p.4: — sin match
- p.5: — sin match
- p.6: — sin match

### `2026-05-08_andamios_chequeo.pdf` (9 pp) — **3** portada(s)
- p.1: ✓ portada `f_lch_05` — anclas: ['lista de chequeo de andamios', 'tipo andamio', 'pagina 1 de']
- p.2: ✓ portada `f_lch_05` — anclas: ['lista de chequeo de andamios', 'datos del andamio', 'pagina 1 de']
- p.3: — sin match
- p.4: ⚠ casi-match `f_lch_05` — machearon: ['lista de chequeo de andamios', 'pagina 1 de']; faltó: ['constructora region sur', 'f crs lch 05', 'tipo andamio', 'datos del andamio', 'superficie de apoyo', 'estructura del andamio', 'plataformas de trabajo']
- p.5: — sin match
- p.6: ✓ portada `f_lch_05` — anclas: ['lista de chequeo de andamios', 'datos del andamio', 'pagina 1 de']
- p.7: ⚠ casi-match `f_lch_05` — machearon: ['lista de chequeo de andamios', 'pagina 1 de']; faltó: ['constructora region sur', 'f crs lch 05', 'tipo andamio', 'datos del andamio', 'superficie de apoyo', 'estructura del andamio', 'plataformas de trabajo']
- p.8: ⚠ casi-match `f_lch_05` — machearon: ['superficie de apoyo', 'pagina 1 de']; faltó: ['lista de chequeo de andamios', 'constructora region sur', 'f crs lch 05', 'tipo andamio', 'datos del andamio', 'estructura del andamio', 'plataformas de trabajo']
- p.9: — sin match

_(tiempo de escaneo: 31.2 s)_

---

## HRB / altura

_V4 paginación (estrategia distinta a anchors)_

- **Strategy:** `pagination` (motor V4 — autocorrelación + Dempster-Shafer)
- **Carpeta:** `HRB/14.-Trabajos en Altura`
- **Archivos en carpeta:** 9

### → **Total documentos detectados: 14**

### `2026-04-01_altura_check_list.pdf` (1 pp) — **1** (A7 — locked sin OCR)

### `2026-04-02_altura_check_list.pdf` (1 pp) — **1** (A7 — locked sin OCR)

### `2026-04-07_altura_check_list.pdf` (1 pp) — **1** (A7 — locked sin OCR)

### `2026-04-08_altura_check_list.pdf` (1 pp) — **1** (A7 — locked sin OCR)

### `2026-04-02_altura_check_list_liena_de_vida_chequeo_linea_de_vida.pdf` (3 pp) — **2** documento(s) — confianza: baja (LOW)
- páginas con paginación directa: 0; inferidas: 3; falladas: 0

### `2026-04-12_altura_check_list_linea_de_vida_chequeo_linea_de_vida.pdf` (3 pp) — **2** documento(s) — confianza: baja (LOW)
- páginas con paginación directa: 0; inferidas: 3; falladas: 0

### `2026-04-19_altura_check_list_liena_de_vida_chequeo_linea_de_vida.pdf` (3 pp) — **2** documento(s) — confianza: baja (LOW)
- páginas con paginación directa: 0; inferidas: 3; falladas: 0

### `2026-04-26_altura_check_list_linea_de_vida_chequeo_linea_de_vida.pdf` (3 pp) — **2** documento(s) — confianza: baja (LOW)
- páginas con paginación directa: 0; inferidas: 3; falladas: 0

### `2026-04-30_altura_check_list_linea_de_vida_chequeo_linea_de_vida.pdf` (3 pp) — **2** documento(s) — confianza: baja (LOW)
- páginas con paginación directa: 0; inferidas: 3; falladas: 0

_(tiempo de escaneo: 11.3 s)_

---

## HPV / chps

_mono-flavor, template compartido con cat 1 reunion, 1 PDF_

- **Strategy:** `anchors`  ·  **top_fraction:** `0.25`  ·  **flavors:** 1 (`f_ar_01`)
- **Carpeta:** `HPV/18.-CHPS`
- **Archivos en carpeta:** 1

### → **Total portadas detectadas: 1**

### `2026-04-30_chps_acta_reunion.pdf` (3 pp) — **1** portada(s)
- p.1: ✓ portada `f_ar_01` — anclas: ['acta de reunion', 'f crs ar 01', 'lista de convocados', 'hospital de', 'lugar de la reunion']
- p.2: ⚠ casi-match `f_ar_01` — machearon: ['acta de reunion', 'f crs ar 01']; faltó: ['lista de convocados', 'desarrollo de la reunion', 'hospital de', 'lugar de la reunion', 'pagina 1 de']
- p.3: ⚠ casi-match `f_ar_01` — machearon: ['acta de reunion', 'f crs ar 01']; faltó: ['lista de convocados', 'desarrollo de la reunion', 'hospital de', 'lugar de la reunion', 'pagina 1 de']

_(tiempo de escaneo: 2.0 s)_

---

## HRB / exc

_intersection anchors (cat 13)_

- **Strategy:** `anchors`  ·  **top_fraction:** `0.25`  ·  **flavors:** 1 (`f_lch_xx`)
- **Carpeta:** `HRB/13.-Excavaciones y Vanos`
- **Archivos en carpeta:** 1

### → **Total portadas detectadas: 2**

### `2026-05-08_exc_chequeo.pdf` (2 pp) — **2** portada(s)
- p.1: ✓ portada `f_lch_xx` — anclas: ['excavaciones', 'fecha', 'constructora region sur spa', 'pagina 1 de']
- p.2: ✓ portada `f_lch_xx` — anclas: ['excavaciones', 'fecha', 'constructora region sur spa', 'pagina 1 de']

_(tiempo de escaneo: 2.9 s)_

---

## HRB / ext

_intersection anchors (cat 11)_

- **Strategy:** `anchors`  ·  **top_fraction:** `0.25`  ·  **flavors:** 1 (`f_lch_xx`)
- **Carpeta:** `HRB/11.-Extintores`
- **Archivos en carpeta:** 5

### → **Total portadas detectadas: 50**

### `2026-04-01_ext_check_list.pdf` (1 pp) — **1** (A7 — locked sin OCR)

### `2026-04-09_ext_check_list.pdf` (1 pp) — **1** (A7 — locked sin OCR)

### `2026-04-23_ext_check_list.pdf` (1 pp) — **1** (A7 — locked sin OCR)

### `2026-05-08_ext_chequeo.pdf` (47 pp) — **47** portada(s)
- p.1: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'tipo de extintor', 'pagina 1 de']
- p.2: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'tipo de extintor', 'pagina 1 de']
- p.3: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'tipo de extintor', 'pagina 1 de']
- p.4: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'tipo de extintor', 'pagina 1 de']
- p.5: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'tipo de extintor', 'pagina 1 de']
- p.6: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'tipo de extintor', 'pagina 1 de']
- p.7: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'tipo de extintor', 'pagina 1 de']
- p.8: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.9: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'tipo de extintor', 'pagina 1 de']
- p.10: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'tipo de extintor', 'pagina 1 de']
- p.11: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'tipo de extintor', 'pagina 1 de']
- p.12: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'tipo de extintor', 'pagina 1 de']
- p.13: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'tipo de extintor', 'pagina 1 de']
- p.14: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.15: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.16: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.17: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.18: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.19: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.20: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.21: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.22: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.23: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.24: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.25: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.26: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.27: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.28: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.29: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.30: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.31: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.32: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'fecha de vencimiento del extintor', 'pagina 1 de']
- p.33: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.34: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.35: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.36: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.37: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.38: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.39: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.40: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.41: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'tipo de extintor', 'pagina 1 de']
- p.42: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.43: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.44: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.45: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'tipo de extintor', 'pagina 1 de']
- p.46: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'fecha de vencimiento del extintor', 'tipo de extintor', 'pagina 1 de']
- p.47: ✓ portada `f_lch_xx` — anclas: ['chequeo extintores', 'ubicacion del extintor', 'numero de serie del extintor', 'tipo de extintor', 'pagina 1 de']

### `2026-05-08_ext_ubicacion.pdf` (2 pp) — **0** portada(s)
- p.1: — sin match
- p.2: — sin match

_(tiempo de escaneo: 36.4 s)_

---
