# Revisión post-MVP de Conteo Confiable — visor, chips honestos, OCR desde el visor y fixes

**Fecha:** 2026-06-03
**Rama:** `feature/conteo-confiable` (worktree, sobre `po_overhaul` consolidado)
**Predecesor:** `docs/superpowers/specs/2026-06-02-conteo-confiable-y-revision-design.md`
(MVP enviado, tag `conteo-confiable-mvp`).

## Contexto

La revisión en vivo del MVP de Conteo Confiable (ABRIL, chrome-devtools) dejó 14
observaciones de Daniel. Esta obra las agrupa en 5 frentes. Es **refinamiento de
UX + un par de features** sobre el flujo de revisión por archivo; no toca el
modelo de "listo" honesto de la celda (eso ya está enviado) salvo donde se indica
(se elimina el chip "Estructura" a nivel de archivo, decisión D4).

### Mapa de las 14 observaciones → frentes

| # | Observación | Frente |
|---|-------------|--------|
| 3, 10 | "R1" en archivos multipágina donde 1 página ≠ 1 documento (charla/chintegral/odi) | **G1 Chips** |
| 4 | Botón para escanear con OCR el documento que se está viendo | **G3 OCR-visor** |
| 5, 6 | Tras OCR, el chip y el conteo por archivo no se refrescan (FileList ni visor) | **G3 OCR-visor** |
| 7 | Que el chip cambie *en vivo* mientras escanea el OCR | **Fuera de alcance (D6)** |
| 1, 9 | Visor sin miniaturas, sin ajuste-a-ventana; PgUp/PgDn no andan; nav lenta | **G2 Visor** |
| 2 | Input/número de ajuste manual en el visor en negro, se pierde | **G4 Fixes** |
| 8 | (i) junto al "Método" que explique brevemente qué busca | **G4 Fixes** |
| 11 | ETA del escaneo en segundos, debería ser minutos | **G4 Fixes** |
| 12 | Header del hospital "Total: XXX detectados" — ¿XXX qué? | **G4 Fixes** |
| 13 | Al generar Excel, los toasts de advertencia se solapan | **G4 Fixes** |
| 14 | Listar y abrir el último Excel del mes desde el home | **G5 Excel-home** |

## Decisiones transversales

- **D1 — Vocabulario único de chip per-archivo: `R1 · OCR · Manual · Pendiente · Error`.**
  Reemplaza el set actual (`trivial · Estructura · R1 · OCR · manual`). Un solo eje:
  *"¿este archivo ya está contado y es confiable, o hay que hacer algo?"*. El
  *mecanismo* (nombre / páginas / OCR) vive en el "Método" del panel DETALLE (con
  la (i) de D-G4/#8), no en el chip.
- **D2 — Navegación del visor: `scroll = página`, `Shift+scroll = zoom`** (estilo
  Figma), con **ajuste-a-ventana por defecto** y **columna de miniaturas**. Teclado
  secundario: `PgDn/PgUp` (o `↓/↑`) página, `+/−` zoom.
- **D3 — Refresco post-OCR (al terminar) entra; el cambio en vivo (#7) no.**
- **D4 — Archivo de sigla de páginas fijas (exc/bodega/ext/…) → chip `R1`.** Se
  **elimina el chip "Estructura"** (y su tono `blue` en `OriginChip`). El método de
  celda sigue siendo `page_count_pure` con label "Conteo de páginas" en DETALLE.
  *(Aprobado por Daniel.)*
- **D5 — Archivo de 1 página → chip `R1`** (reemplaza "trivial"). 1 página = 1
  documento, confiable. *(Aprobado por Daniel.)*
- **D6 — Siglas fijas inferidas (caliente, herramientas_elec, exc) → también `R1`**
  a nivel de archivo (igual que las sólidas bodega/ext). El matiz "verificar"
  sigue como el flag de celda `fixed_pages_inferred` ya existente; no se duplica en
  el chip. *(Default alineado a la dirección de Daniel; confirmable en revisión.)*

---

## G1 — Chips honestos per-archivo

**Objetivo (#3, #10):** que el chip de cada archivo diga la verdad. Hoy un archivo
multipágina de charla/chintegral/odi muestra "R1" (verde, sugiere fiable) cuando
su conteo por nombre es un supuesto.

### Regla del chip (autoridad: backend `_origin_for`)

`_origin_for` vive en `api/routes/sessions.py:408-425` (anidado en `get_cell_files`),
que ya conoce `page_count` por archivo, `cell_method` y `override`. Pasa a recibir
`page_count` y devolver uno de los 5 valores, en este orden de prioridad:

1. `override is not None` → **`Manual`**
2. `page_count == 0` (PDF ilegible / error de lectura) → **`Error`**
3. `cell_method` en `{header_detect, corner_count, header_band_anchors, v4}` → **`OCR`**
4. `cell_method == "page_count_pure"` (sigla fija) → **`R1`** *(D4)*
5. `cell_method == "filename_glob"`:
   - `page_count == 1` → **`R1`** *(D5)*
   - `page_count > 1` → **`Pendiente`** *(el fix #3/#10)*
6. fallback → `R1`

> El orden importa: `Manual` y `Error` ganan sobre el método; `OCR` (celda
> escaneada) gana sobre la heurística de páginas.

### Frontend

- **`OriginChip.jsx`**: `ORIGIN_VARIANT` pasa a `{ R1: "jade", OCR: "iris",
  Manual: "blue", Pendiente: "amber", Error: "state-error" }`. Se elimina la
  entrada `Estructura`. (`blue` queda libre al borrar Estructura → se reusa para
  `Manual`; `Error` usa el tono `state-error` ya existente.)
- **`FileList.jsx:114-116`**: se quita la rama `page_count === 1 ? trivial :
  OriginChip`. Siempre `<OriginChip origin={f.origin} />` (el backend ya decide).
- **`PDFLightbox.jsx` `FileSummary`**: idem — quita la rama `trivial`/Estructura,
  usa `<OriginChip origin={file.origin} />`.
- **`HistoryDrawer.jsx` `methodToOrigin`**: el TODO sigue (history fuera de
  alcance); `page_count_pure` ahí mapeará a "R1" (no "OCR") para coherencia visual
  mínima — ajuste de 1 línea ya que Estructura desaparece.

### Comportamiento intencional a documentar

Una celda **confirmada** (verde por `confirmed`, p. ej. odi marcada a mano) puede
mostrar archivos con chip **`Pendiente`**: el punto verde dice "el operador dio el
total por listo", el chip del archivo dice "el split por archivo no está
verificado por máquina". Responden preguntas distintas; es honesto y deseado.
(Esto reemplaza el "R1 verde" que confundía en #3.)

### Tests
- **vitest** `OriginChip.test.js`: las 5 etiquetas → su tono; desconocido → neutral.
- **pytest** `tests/test_cell_files_endpoint.py` (extender): para una celda sembrada
  con `cell_method` y archivos de distinto `page_count`/override, `origin` por
  archivo cae en R1/OCR/Manual/Pendiente/Error según la regla. Fixtures reales.

---

## G2 — Visor de archivos: miniaturas + ajuste-a-ventana + nav scroll/zoom

**Objetivo (#1, #9):** el visor de archivos (`PDFLightbox` modo inspección) debe
abrir **ajustado a la ventana**, con **columna de miniaturas** a la izquierda, y
navegar con **scroll = página / Shift+scroll = zoom** (PgUp/PgDn hoy no hacen nada
porque el visor usa pan/zoom de `react-zoom-pan-pinch`).

### Enfoque: reemplazar `InspectView` por el patrón paginado del visor de trabajadores

Hoy `InspectView` (`PDFLightbox.jsx:42-71`) envuelve **todas** las páginas en un
`TransformWrapper` (pan/zoom) a `scale=1.5` fijo. `TransformWrapper` intercepta la
rueda → bloquea `scroll = página`. **Se elimina `TransformWrapper`** y se
reconstruye `InspectView` con el patrón ya probado de `WorkerCountViewer`
(página única + `useFitScale` + zoom explícito + miniaturas + teclado).

Piezas reutilizables (sin cambios):
- `WorkerThumbnails({ doc, pageCount, currentPage, marks, onSelect })` —
  `marks=[]` (el visor de archivos no marca trabajadores). Lazy + WeakMap cache.
- `useFitScale(doc, pageNumber) → { panelRef, fitScale }` — `panelRef` al panel
  scrolleable.
- `PdfPage({ doc, pageNumber, scale })` — render canvas; `scale = effectiveScale`.
- Patrón de zoom: `const [zoom, setZoom] = useState(1)`,
  `effectiveScale = Math.max(0.1, fitScale * zoom)`, **reset `zoom=1` al cambiar de
  página** (`useEffect(..., [pageNumber])`).

`page_count` viene de `files[lightbox.fileIndex].page_count`
(`PDFLightbox.jsx:104`, ya en scope) — fuente más fiable que `numPages` del hook
(sin flash del conteo).

### Navegación (componente local del visor de archivos)

- **Rueda** sobre el panel (`onWheel`):
  - `e.shiftKey` → zoom (`e.preventDefault()`; `deltaY<0` zoom-in, `>0` zoom-out por `ZOOM_STEP`).
  - sin shift → página (`e.preventDefault()`; `deltaY>0` siguiente, `<0` anterior;
    con un pequeño *throttle*/acumulador para que un golpe de trackpad no salte 5
    páginas).
- **Teclado** (listener `window` mientras el visor está montado, como
  `WorkerCountViewer`): `PgDn`/`↓` siguiente, `PgUp`/`↑` anterior, `+/=` zoom-in,
  `-/_` zoom-out.
- **Miniaturas:** click salta a la página (`onSelect`).
- **Barra de zoom** mínima (label `Math.round(zoom*100)%` + botón ajustar) como en
  el visor de trabajadores; "ajustar" resetea `zoom=1`.

### Layout del visor (modo inspección)

```
┌ Dialog ─────────────────────────────────────────────┐
│ header: HOSP · sigla · label · archivo · Npp         │
├──────────┬───────────────────────────────┬──────────┤
│ miniat.  │   página única (fit*zoom)      │ aside    │
│ (w-28)   │   scroll=pág, shift+scroll=zoom│ per-file │
└──────────┴───────────────────────────────┴──────────┘
```

El `aside` per-archivo (FileSummary + editor, ya existente) se mantiene a la
derecha; la columna de miniaturas se agrega a la izquierda del panel de página.

### Riesgos
- El `Dialog` (Radix) atrapa el foco pero reenvía `keydown` al `window` igual que
  hoy hace `WorkerCountViewer` dentro del mismo `Dialog` (modo `count_workers`), así
  que el patrón ya funciona en este contenedor.
- El modo `count_workers` (`WorkerCountViewer`) **no se toca**; solo se reescribe la
  rama de inspección.

### Tests
- **vitest** `fit-scale.test.js` ya cubre `computeFitScale`. Agregar un test puro
  del throttle/acumulador de la rueda → página (extraer `wheelToPageStep(deltaY,
  acc)` a `lib/`), y del paso de zoom.
- Smoke en vivo (Daniel): abrir, ver fit, scrollear páginas, shift-zoom, miniaturas.

---

## G3 — Escanear con OCR desde el visor + refresco al terminar

**Objetivo (#4, #5, #6):** botón "Escanear con OCR" en el visor de la celda; y que
al terminar el OCR, **FileList y el visor reflejen** los nuevos conteos por archivo
y el chip `OCR`.

### Diagnóstico
El backend **ya** llena `per_file` con los conteos del OCR
(`AnchorsScanner.count_ocr` → `per_file[pdf.name] = ocr.count`, A7 lock = 1 para
1-página; `anchors_scanner.py:98,116,133,137,173`), y `apply_ocr_result` persiste
`cell["per_file"]`. El bug es de **frescura en el frontend**: `FileList` y
`PDFLightbox` consultan `getCellFiles` solo cuando cambia `[session, hospital,
sigla]`, no cuando termina el OCR.

### Cambios

- **Botón en el visor** (`PDFLightbox`, rama inspección): "Escanear con OCR" que
  llama `scanOcr(session_id, [[hospital, sigla]])` (acción de store ya existente,
  con su cost-guard). Visible solo si la sigla tiene `scan_strategy` OCR
  (anchors/pagination); para `none`/sin OCR, deshabilitado con tooltip. El estado de
  escaneo (spinner) se refleja con `scanningCells`/`scanProgress` ya existentes.
- **Refresco al terminar:** ambos componentes se re-consultan `getCellFiles` cuando
  el WS emite el evento terminal de la celda. Mecanismo: un contador/versión en el
  store (`filesRefreshTick[`${h}|${s}`]` o un `lastScanCompletedCell`) que se
  incrementa en el handler de `cell_done`/`scan_complete`; `FileList` y el visor lo
  incluyen en las deps de su `useEffect` de fetch. (Alternativa equivalente: que el
  store guarde el `per_file` por celda y los componentes deriven de ahí; se elige el
  re-fetch por simplicidad y porque `origin`/`page_count` se calculan server-side.)
- **Visor "1 documento" tras OCR (#5):** se resuelve con el mismo re-fetch —
  `FileSummary` lee `files[fileIndex].effective_count`, que tras el re-fetch toma el
  `per_file` del OCR.

### Fuera de alcance (D6 → #7)
El cambio del chip **en vivo, página a página, mientras escanea**, requiere eventos
por-PDF con resultado parcial (hoy `count_ocr` solo expone `on_pdf(name)` = "estoy
en este PDF", sin el conteo). Se deja como fast-follow; se anota como deuda.

### Tests
- **pytest**: ya hay cobertura de `count_ocr` → `per_file`. Agregar (o verificar) que
  tras `apply_ocr_result`, `get_cell_files` devuelve `origin="OCR"` y
  `effective_count` = conteo OCR por archivo.
- Smoke: escanear una celda compilación (p. ej. odi HRB) desde el visor; verificar
  chip OCR + conteo correcto en FileList y visor sin recargar.

---

## G4 — Fixes puntuales

- **#2 — Input de ajuste manual en negro.** En el `aside` del visor, el
  `InlineEditCount`/spinbutton hereda un color oscuro. Forzar `text-po-text` (y el
  borde/placeholder a tokens `po-*`) en el input del editor per-archivo.
- **#8 — (i) en "Método".** Junto al label "Método" del DetailPanel, un ícono
  `Info` (lucide) con `Tooltip` que explica brevemente el método. Mapa nuevo
  `frontend/src/lib/method-info.js` (token → frase corta), p. ej.:
  - `filename_glob` ("Nombre"): "Un documento por archivo PDF. Fiable cuando cada
    PDF es un solo documento."
  - `page_count_pure` ("Conteo de páginas"): "Un documento por página. Para siglas
    donde cada página es un chequeo (bodega, extintores, excavaciones…)."
  - `header_band_anchors` ("OCR encabezados"): "Lee el encabezado de cada página y
    cuenta una portada por documento."
  - `v4` ("Paginación"): "Cuenta documentos por la numeración 'Página N de M'
    detectada por OCR."
  - `manual`: "Valor ingresado a mano."
  (Copy ajustable por Daniel; vive en un solo lugar.)
- **#11 — ETA en minutos.** `ScanProgress.jsx:42-43` muestra `~${Math.round(etaMs/
  1000)}s`. Pasar a minutos: `~${Math.max(1, Math.round(etaMs/60000))} min` (o
  `Xm Ys` si <1 min se siente raro; se elige "≥1 min" por simplicidad y porque los
  escaneos OCR reales son de minutos). Extraer `formatEta(ms)` a `lib/scanCost.js`
  con test vitest.
- **#12 — Header del hospital.** `HospitalDetail.jsx:61-64`: "Total: XXX detectados"
  → "Total: XXX documentos" (espeja "documentos detectados" del HospitalCard). Es
  la suma de conteos de celda (documentos), no archivos ni PDFs.
- **#13 — Toasts solapados.** `MonthOverview.jsx:42-55` dispara `toast.success` +
  `toast.warning` síncronos → colisión de entrada. **Fix: un solo toast** —
  `toast.success(titulo, { description: <advertencias> })` cuando hay
  `worker_warnings`; sin segundo toast. (Elimina la carrera de timing.)

### Tests
- **vitest**: `formatEta` (minutos), `method-info` (todos los tokens presentes).
- Smoke: generar Excel con celdas charla/chintegral incompletas → un solo toast con
  descripción de advertencias.

---

## G5 — Home: listar y abrir el último Excel del mes (#14)

**Objetivo:** en el home (MonthOverview) listar el/los Excel generados y poder
abrirlos desde el navegador.

### Backend (nuevo)
- **`GET /api/sessions/{session_id}/output`** — sirve `RESUMEN_{session_id}.xlsx`
  desde `OVERSEER_OUTPUT_DIR` con `FileResponse` (igual patrón de contención que
  `get_cell_pdf`: validar `session_id` regex, 404 si no existe), `media_type`
  `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`,
  `Content-Disposition: attachment; filename="RESUMEN_{id}.xlsx"`. Incluir `mtime`
  vía un `GET …/output/meta` o devolver 404/exists en un HEAD; ver abajo.
- **`GET /api/outputs`** — lista los `RESUMEN_*.xlsx` presentes en
  `OVERSEER_OUTPUT_DIR` con `{session_id, filename, mtime_iso, size}`, ordenados por
  `mtime` desc. (Para "el último".)

> El `.xlsx` no se renderiza inline en el navegador: al hacer click se **descarga**
> y el SO lo abre con Excel. Es el comportamiento web correcto para un binario
> Office; se documenta así en el microcopy ("Descargar / abrir").

### Frontend
- `MonthOverview`: bajo el selector de mes / junto a "Generar Excel del mes", una
  sección "Último Excel" que consulta `GET /api/outputs` (o el `…/output/meta` del
  mes activo) y muestra `RESUMEN_YYYY-MM.xlsx` con su fecha, como link al endpoint de
  serve (`<a href={api.outputUrl(session_id)}>`). Si no hay, no se muestra (o "aún
  no generado").
- `api.js`: `outputUrl(sessionId)` + `listOutputs()`.

### Tests
- **pytest** `tests/test_output_serve_endpoint.py`: genera un Excel (o siembra un
  archivo en un `OVERSEER_OUTPUT_DIR` temporal), `GET …/output` → 200 +
  content-type correcto; 404 si no existe; `GET /api/outputs` lista el archivo.
  Sin mock de DB/FS (tmp dir real).

---

## Estructura de archivos (resumen)

**Backend**
- `api/routes/sessions.py` — `_origin_for` (regla de 5 chips + `page_count`); nuevo
  `GET …/output` (serve).
- `api/routes/output.py` (o `outputs.py` nuevo) — `GET /api/outputs` (list).
- `tests/test_cell_files_endpoint.py`, `tests/test_output_serve_endpoint.py`.

**Frontend**
- `components/OriginChip.jsx` (5 variantes, sin Estructura), `ui/Badge.jsx` (quitar/
  reasignar `blue`).
- `components/FileList.jsx`, `components/PDFLightbox.jsx` (chip; reescritura de
  `InspectView` con miniaturas/fit/nav; botón OCR; refresco post-OCR; input blanco).
- `components/ScanProgress.jsx` (#11), `views/HospitalDetail.jsx` (#12),
  `views/MonthOverview.jsx` (#13 toast, #14 sección Excel),
  `components/DetailPanel.jsx` (#8 (i)).
- `store/session.js` (tick de refresco post-OCR), `lib/api.js` (output endpoints),
  `lib/method-info.js` (nuevo), `lib/scanCost.js` (`formatEta`),
  `hooks/useFitScale.js` + `components/WorkerThumbnails.jsx` + `PdfPage.jsx`
  (reuso, sin cambios).
- Tests vitest: `OriginChip.test.js`, `scanCost.test.js` (formatEta), nuevo test del
  paso de rueda/zoom.

## Fuera de alcance (YAGNI)
- #7 chip en vivo durante el OCR (necesita streaming por-PDF con resultado parcial).
- Rehacer el visor de trabajadores (solo se reusan sus piezas).
- Cambios al historial (`HistoryDrawer`) más allá del mapeo mínimo de `methodToOrigin`.
- Render inline del `.xlsx` en el navegador (no soportado; se descarga).

## Orden sugerido de implementación
G1 (chips) → G4 (fixes puntuales, rápidos) → G3 (OCR-visor + refresco) → G2 (visor
rework, el más grande) → G5 (Excel home). Smoke al cierre. Tag al final.

## Notas de verificación
- Pase final de tests al final (preferencia de Daniel): no gatear por chunk.
- Recordar: el worktree no trae los PDFs gitignored de `data/samples` → ~12 fallos
  ambientales esperados de VLM/pdf_render/eval; verdes en main. No son regresión.
