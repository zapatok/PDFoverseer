# Auditoría del sistema OCR per-sigla — backend + frontend

**Fecha:** 2026-05-23
**Branch:** `feature/ocr-per-sigla`
**Alcance:** flujo completo de scan (pase 1 filename + pase 2 OCR), API, WebSocket,
store frontend, lógica de conteo, Excel writer, alineación con el propósito.
**Método:** lectura directa del worktree (Serena indexa `po_overhaul`, no esta rama).

---

## Resumen ejecutivo

El sistema está **conceptualmente bien alineado** con su propósito (distingue
régimen 1 trivial de régimen 2 compilación vía el badge "Compilación", cascada de
conteo correcta, Excel writer atómico). El problema operativo central —"la barra
de progreso se queda ahí y no sé si está vivo"— es **real y de diseño**: el
progreso se mide por celda, no por PDF. Los demás hallazgos son higiene o mejoras
de aprovechamiento.

| # | Severidad | Hallazgo | Archivos |
|---|-----------|----------|----------|
| 1 | 🔴 Alto | Progreso por celda → barra congelada en celdas grandes (3 defectos apilados) | `orchestrator.py`, `ScanProgress.jsx`, `session.js` |
| 2 | 🟠 Alto (alineación) | OCR corre sobre régimen 1 sin guard de costo ni de necesidad | `sessions.py`, `CategoryRow.jsx` |
| 3 | 🟡 Medio | `count_ocr` ignora `recursive_glob` (siempre `rglob`) | `anchors_scanner.py` |
| 4 | 🟡 Medio | Heurística de compilación con umbral fijo ×5 → falsos negativos | `page_count_heuristic.py` |
| 5 | ⚪ Bajo | `page_count_pure.py` es código muerto (solo su test lo importa) | `utils/page_count_pure.py` |
| 6 | ⚪ Bajo | Documentación desactualizada (api/CLAUDE.md, core/CLAUDE.md, Serena) | docs |
| 7 | ⚪ Bajo | Asimetría de default `effective_count=1` vs `compute_cell_count=0` | `sessions.py`, `state.py` |

---

## 🔴 1. El progreso se mide por celda, no por PDF

Tres capas apiladas, todas en el camino de scan real (multi-worker):

### 1a. Granularidad equivocada

[`scan_cells_ocr`](../../core/orchestrator.py) emite `scan_progress {done, total}`
con la **celda** como unidad. Seleccionar HPV/art (767 PDFs, ~70 min) ⇒ `total=1`,
la barra muestra `0/1` durante 70 minutos y salta a `1/1` al final. La iteración
real (PDF-por-PDF, página-por-página) vive en
[`AnchorsScanner.count_ocr`](../../core/scanners/anchors_scanner.py) dentro de un
**subproceso** que solo devuelve el resultado agregado de la celda — el avance
interno nunca cruza al proceso principal.

### 1b. `cell_scanning` se emite tarde (post-result)

En el camino multi-worker (producción):

```python
for fut in as_completed(future_to_cell):
    ...
    h, s, result, err = fut.result()              # bloquea hasta que la celda TERMINA
    on_progress({"type": "cell_scanning", ...})   # recién acá marca "escaneando"
    ...
    on_progress({"type": "cell_done", ...})
```

`cell_scanning` llega cuando la celda **ya terminó**. La celda entra y sale de
`scanningCells` (el spinner individual de `CategoryRow`) en el mismo instante, al
final. Durante el scan real, ninguna señal a nivel celda. En el camino
`max_workers==1` (síncrono, solo tests) sí se emite antes — por eso los tests no
lo detectan.

### 1c. El ETA es código muerto

[`ScanProgress.jsx`](../../frontend/src/components/ScanProgress.jsx) lee
`event.eta_ms`, pero el backend **nunca emite ese campo** en `scan_progress`
(verificado en `orchestrator.py`: `on_progress({"type": "scan_progress", "done":
scanned, "total": total})`). La rama `etaMs && !terminal` jamás se cumple; el
"~Xs" no aparece nunca. El store lo mapea a `event.eta_ms` igualmente
([`session.js`](../../frontend/src/store/session.js)).

**Resultado neto:** spinner girando + `0/1` inmóvil + sin ETA ⇒ indistinguible de
un cuelgue.

### Dirección de arreglo (decisión tomada en el plan)

Progreso **por PDF** vía un canal IPC (`multiprocessing.Queue`): el worker invoca
un callback por cada PDF terminado, que escribe a la queue; un thread drenador en
el orquestador la reenvía como evento `pdf_progress`. El total de PDFs se
pre-calcula enumerando las celdas seleccionadas. No toca la lógica de agregación
ya validada en Fase A/B (riesgo acotado). El paralelismo intra-celda queda como
nota futura (no es el problema percibido).

---

## 🟠 2. OCR corre sobre régimen 1 sin guard de costo ni de necesidad

El propósito (`project_pdfoverseer_purpose`) es explícito: *"Don't OCR what
filenames already classify — regime 1 is glob+aggregate, no model"*. ~90% de las
celdas son régimen 1 (1 PDF = 1 doc; el filename ya cuenta).

Hoy la app deja correr OCR completo sobre cualquier celda seleccionada, sin avisar
que (a) en régimen 1 el conteo por filename ya es correcto, ni (b) que sobre 767
PDFs tardará decenas de minutos. La señal conceptual existe a medias: el badge
**"Compilación"** ([`CategoryRow.jsx`](../../frontend/src/components/CategoryRow.jsx))
marca régimen 2, pero **no frena ni advierte** antes de un OCR caro.

### Dirección de arreglo

Guard de confirmación previo: estimar PDFs/páginas de las celdas seleccionadas y,
si supera un umbral, pedir confirmación con estimación de tiempo y recordatorio de
que en régimen 1 el filename basta. Apoyado en el progreso fino de #1 (sin él, la
confirmación no alcanza).

---

## 🟡 3. `count_ocr` ignora `recursive_glob`

[`AnchorsScanner.count_ocr`](../../core/scanners/anchors_scanner.py) usa
`folder.rglob("*.pdf")` incondicional, mientras el pase 1
(`SimpleFilenameScanner`) respeta `recursive_glob` de `patterns.py`. Hoy no hay
bug observable (las siglas no-recursivas no tienen subcarpetas en ABRIL —
verificado en Fase B: `diff=0`), pero es **inconsistencia latente**: si una sigla
no-recursiva gana subcarpetas, pase 1 y pase 2 cuentan distinto. Mismo patrón que
mordió a `charla` (que requirió añadir `recursive_glob`).

---

## 🟡 4. Heurística de compilación con umbral fijo ×5

[`flag_compilation_suspect`](../../core/scanners/utils/page_count_heuristic.py)
marca sospecha si algún PDF supera `EXPECTED_PAGES_PER_DOC[sigla] × 5`. Para
andamios: `expected=2 × 5 = 10`. Los `check_list_*.pdf` de HRB/andamios tienen 6-9
páginas → **no disparan**, pese a ser compilaciones reales (34 docs). El `×5` es
craso. Encaja con la preferencia registrada de no asumir umbrales/densidades
fijas.

### Dirección de arreglo

Bajar el factor (×3) **y** añadir señal agregada (ratio total-páginas /
total-PDFs >> expected) que capta compilaciones repartidas en varios PDFs medianos
sin disparar falsos positivos en régimen 1. Calibrar contra los conteos Fase A/B
ya disponibles.

---

## ⚪ 5. `page_count_pure.py` es código muerto

Solo lo importa `tests/unit/scanners/utils/test_page_count_pure.py`. Ningún código
de producción lo usa (`corner_count` ya se borró; éste quedó). Era parte de la
limpieza Chunk 7 pendiente.

---

## ⚪ 6. Documentación desactualizada

- [`api/CLAUDE.md`](../../api/CLAUDE.md) describe `routes/files.py`,
  `routes/pipeline.py`, `/api/browse`, `SESSION_TTL` — **borrados en FASE 1**.
- `core/CLAUDE.md` arranca con la arquitectura V4 vieja (single-PDF); la nueva
  (scanner triad) recién al final. Orden confuso sobre qué está activo.
- Memoria Serena `codebase_structure` afirma que `pipeline.py` fue borrado, cuando
  vive y lo usa `PaginationScanner`.

---

## ⚪ 7. Asimetría de default en conteo per-file

[`get_cell_files`](../../api/routes/sessions.py) muestra `effective_count = 1`
para un archivo sin dato; [`compute_cell_count`](../../api/state.py) usa default
`0`. Tras un scan completo `per_file` cubre todos los PDFs y no hay divergencia; el
desajuste solo aparece pre-scan (presentación). Riesgo bajo, fix opcional.

---

## Lo que está bien (no perder en el ruido)

- **Excel writer atómico** (`tmp → bak → rename`; named ranges faltantes → warning,
  no crash).
- **Cascada de conteo** (`override > per-file > ocr > filename`) clara y correcta.
- **Matcher de anchors** sin doble conteo (first-passing-flavor wins); near-match
  telemetry aislada.
- **Cancelación** cooperativa real (`cancel_futures=True`, checkpoint por página,
  honrada en <3 s).
- **WebSocket** con keepalive y pruning de conexiones muertas.
- La separación régimen 1/2 **existe** — el #2 es de aprovechamiento, no de
  ausencia.

---

## Orden recomendado de ataque

1. **#1** — desbloquea el testing manual (sin progreso fino no se valida nada sobre
   celdas grandes).
2. **#4** — barato; mejora la guía de qué OCRear.
3. **#2** — guard de costo, se apoya en #1 resuelto.
4. **#3, #5, #6, #7** — higiene, una pasada de limpieza.
