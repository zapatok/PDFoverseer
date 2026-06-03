# Conteo Confiable — Revisión 2 (OCR por-archivo, tooltips de método, fichas por sigla, R1-auto) — Design

**Fecha:** 2026-06-03
**Rama:** `feature/conteo-confiable` (worktree `.worktrees/conteo-confiable`, off `po_overhaul`)
**Predecesores:** MVP `conteo-confiable-mvp` → revisión 1 `conteo-confiable-rev-1` → stream de bugs (per_file plumbing, método vigente, Revisar, Ver portada, override refresh).
**Tag previsto:** `conteo-confiable-rev-2`

---

## 1. Contexto

Tras la revisión 1 y el stream de bugs, Daniel pidió cuatro frentes nuevos sobre
la app de conteo. Tres nacen de su revisión en vivo; uno (R1-auto) es una mejora
de flujo descubierta al aclarar el modelo de meses.

El hilo conductor es el **modelo per-archivo**: `per_file` (conteo por PDF) ya es
la fuente de verdad del total de la celda (`computeCellCount`). Esta ronda extiende
ese modelo para que **cada archivo lleve también su método** (cómo se contó), lo
que destraba el OCR por-archivo del visor y deja los chips honestos sin ambigüedad.

## 2. Objetivos / No-objetivos

**Objetivos**
- **#1** — El botón "Escanear con OCR" del visor escanea **solo el archivo abierto**
  con el motor de su sigla, con una **barra de progreso por página**; el resultado
  se fusiona en la celda sin tocar los demás archivos.
- **#5** — La (i) del método muestra, por sigla, **qué busca** el OCR (derivado de
  las anclas reales de `patterns.py`), lo más breve posible.
- **#6** — En el DetailPanel, entre la cifra grande y "Conteo automático", una
  **ficha por sigla**: 1-2 líneas describiendo el tipo de documento + el **rango de
  páginas típico** (calculado del corpus real).
- **R1-auto** — Al abrir un mes cuya sesión aún no tiene datos, **pase 1 corre solo**.

**No-objetivos (esta ronda)**
- Multiusuario / presencia / bloqueo de celda (su propio spec a futuro — ver §11).
- #7 chip per-archivo en vivo durante el escaneo (necesita streaming de resultado
  parcial por PDF; fuera de alcance, ya descartado en rev-1).
- Reescribir el flujo de "Marcar como nuevo flavor" (sigue siendo el helper de
  portapapeles actual; solo lo documentamos como el camino para subir precisión OCR).

---

## 3. Decisión transversal — método por archivo (`per_file_method`)

**Problema.** Hoy el chip de cada archivo (`_origin_for`) se decide con el método
**de la celda** (`cell.method`). Si OCR-eo un solo archivo de una celda que se contó
por nombre, `cell.method` sigue siendo `filename_glob` → ese archivo mostraría
`R1`/`Pendiente`, no `OCR`. Y si en cambio volteo `cell.method` a OCR, los demás
archivos (no escaneados individualmente) se mostrarían como OCR sin serlo.

**Decisión.** Añadir un mapa **`cell["per_file_method"]`**: `{filename: method}`.
- Lo escriben **todas** las corridas que tocan `per_file`, en sincronía con él:
  - `apply_filename_result` → `per_file_method = {f: result.method for f in result.per_file}`
    (pase 1: `filename_glob` o `page_count_pure`).
  - `apply_ocr_result` → idem con el método OCR (`header_band_anchors`/`v4`/…).
  - `apply_per_file_ocr_result` (single-file, §4.2) → setea solo `per_file_method[filename]`.
  - Las cuatro `setdefault("per_file_method", {})` antes de escribir.
- `_origin_for` usa `per_file_method.get(filename)` si existe; si no, cae a
  `cell.method` (compatibilidad con celdas viejas sin el mapa).
- **Por qué todas y no solo el single-file:** si solo el single-file lo escribiera,
  un re-pase-1 dejaría `cell.method = filename_glob` y los archivos no presentes en
  el mapa saltarían de "OCR" a "R1/Pendiente" (inconsistencia silenciosa). Con el mapa
  escrito por cada corrida, el método por archivo siempre refleja cómo se contó ese
  archivo, sin depender de `cell.method`.
- El total de la celda sigue siendo `computeCellCount` (suma de `per_file` con
  overrides) — sin cambios.

**Regla `_origin_for` (final), por archivo:**
```
override is not None                      → "Manual"
page_count == 0                           → "Error"
method ∈ {header_detect, corner_count,
         header_band_anchors, v4}         → "Revisar" si per_file_count == 0, si no "OCR"
method == "page_count_pure"               → "R1"
method == "filename_glob"                 → "R1" si page_count == 1, si no "Pendiente"
else                                      → "R1"
```
donde `method = per_file_method.get(filename) or cell.method`.

> Esto absorbe el fix de Bug A (Revisar) y lo hace per-archivo correcto: un único
> archivo OCR-eado a 0 muestra Revisar aunque la celda se haya contado por nombre.

### 3.1 Call site (`get_cell_files`, `api/routes/sessions.py`)

`get_cell_files` ya extrae `per_file`/`per_file_overrides`/`cell_method` antes de
definir el closure `_origin_for`. Añadir, en el mismo bloque:
```python
per_file_method = cell.get("per_file_method") or {}
```
y dentro de `_origin_for` resolver el método como
`method = per_file_method.get(filename) or cell_method`, usando ese `method` en
todas las ramas (en vez de `cell_method` directo). La firma del closure puede leer
`per_file_method` por cierre (igual que ya lee `cell_method`/`per_file`), sin
parámetro nuevo. El resto del call site (`_origin_for(pdf.name, override,
page_count, inferred)`) no cambia.

---

## 4. #1 — OCR por-archivo desde el visor

### 4.1 Comportamiento
- En el visor (PDFLightbox, modo inspect) el botón **"Escanear con OCR"** escanea
  **solo el PDF abierto** con el scanner de su sigla (anchors o pagination).
- Aparece una **barra de progreso por página** (`página X de N`) dentro del visor
  mientras corre. Al terminar, el `filesTick` (ya cableado) refresca chip + conteo.
- El botón de afuera ("Escanear pendientes (N)" / escaneo de celda) **no cambia**:
  sigue escaneando la celda entera.
- Sin cost-guard (un archivo es barato).
- Si la sigla no tiene estrategia OCR (`scan_strategy == "none"`, p.ej. reunion),
  el botón se deshabilita con tooltip "Esta categoría no usa OCR".

### 4.2 Backend
- **Scanner — scope de un PDF + progreso por página.**
  - `AnchorsScanner.count_ocr` y `PaginationScanner.count_ocr` ganan un parámetro
    opcional `only: str | None` (nombre de archivo). Cuando se pasa, filtran
    `enumerate_cell_pdfs(folder)` a ese único PDF.
  - `count_covers_by_anchors` (header_band_anchors.py:128, loop
    `for page_idx in range(pages_total)`) gana un callback opcional
    `on_page: Callable[[int, int], None]` invocado por página `(page_idx, pages_total)`.
    `count_ocr` lo propaga. **PaginationScanner/V4 (insgral, altura): decisión del
    plan.** El path V4 (`core/scanners/utils/v4_count.py` → `pipeline.analyze_pdf`)
    itera páginas internamente pero **no** acepta hoy un `on_page`; el plan decide
    entre (a) cablearlo por `count_documents_v4`/`analyze_pdf` (esfuerzo medio) o
    (b) dejar la barra del visor **indeterminada** solo para esas 2 siglas (progreso
    por PDF como hoy). Recomendación: (b) — esas 2 siglas son raras en el visor y el
    costo de (a) no se justifica en esta ronda.
- **Orquestador — corrida de un archivo.** Nuevo helper
  `scan_one_file_ocr(hospital, sigla, folder, filename, *, on_progress, cancel)`
  que corre el scanner con `only=filename` + `on_page`, emitiendo eventos:
  `file_scan_started {hospital, sigla, filename, pages_total}`,
  `file_page_progress {filename, page, pages_total}`,
  `file_scan_done {hospital, sigla, filename, result:{count, method, per_file, near_matches}}`,
  `file_scan_error`. (Eventos nuevos, namespaced `file_*`, para no chocar con el
  batch de celda.)
- **Endpoint.** `POST /api/sessions/{id}/cells/{h}/{s}/files/{filename}/scan-ocr`
  (filename URL-encoded). **Resolución de carpeta — igual que `get_cell_files`:**
  `folder = _find_category_folder(Path(state["month_root"]) / hospital, sigla)`;
  validar que `filename` esté en `{p.name for p in folder.rglob("*.pdf")}` → 404 si
  no (mismo guard de `_SESSION_ID_RE` para `session_id`). Lanza la corrida en el
  executor y transmite los eventos `file_*` por el WS de la sesión.
- **Merge de estado.** Nuevo método `SessionManager.apply_per_file_ocr_result(
  session_id, hospital, sigla, filename, *, count, method, near_matches)`:
  - `cell.setdefault("per_file", {})[filename] = count`
  - `cell.setdefault("per_file_method", {})[filename] = method`
  - Reemplaza en `cell["near_matches"]` las entradas de **ese** `pdf_name` por las
    nuevas (deja las de otros archivos intactas).
  - **No** toca `per_file` de otros archivos, ni `user_override`, ni `confirmed`.
  - No re-deriva `ocr_count` de la celda (el total se calcula con `compute_cell_count`).
- **`per_file_method` en las corridas de celda.** Además del merge single-file,
  `apply_ocr_result` **y** `apply_filename_result` setean
  `cell["per_file_method"] = {f: result.method for f in (result.per_file or {})}`
  (ver §3 — sin esto, un re-pase-1 desincronizaría los chips). Es el único cambio
  que esas dos funciones suman a lo ya existente.

### 4.3 Frontend
- `src/lib/api.js`: `scanFileOcr(sessionId, hospital, sigla, filename)` →
  POST al endpoint nuevo.
- `store/session.js`: estado `fileScan` `{ hospital, sigla, filename, page, pagesTotal,
  terminal }`; handlers WS para `file_scan_started` / `file_page_progress` /
  `file_scan_done` / `file_scan_error`. En `file_scan_done` bumpea `filesTick`
  (refresca FileList + lightbox) — igual que `cell_done`.
- `PDFLightbox.jsx`: el botón "Escanear con OCR" llama `scanFileOcr(...)` con el
  archivo actual; mientras `fileScan` apunte a este archivo, muestra la barra
  `página X de N` (componente chico, reusa el patrón de `ScanProgress`). Deshabilita
  el botón para siglas sin OCR.

### 4.4 Edge cases
- Archivo de 1 página → A7 (cuenta 1, sin OCR); la barra salta 0→1. **Decisión:** el
  `per_file_method` del archivo hereda el método de la corrida (`header_band_anchors`/
  su sigla), así su chip es `OCR` con 1 doc — trivialmente correcto (1 página = 1
  documento) y vive en una celda de estrategia OCR. No distinguimos A7 a nivel de
  método per-archivo en esta ronda (sería un matiz extra; si más adelante se quiere
  que los 1-página lean `R1` aun en celdas OCR, es un ajuste aparte).
- Cancelación: el WS de la sesión ya tiene `cancel`; un `file_scan` cancelado emite
  `file_scan_error`/terminal y no fusiona nada.
- Mientras corre un `file_scan`, deshabilitar el botón de escaneo de celda para esa
  celda (y viceversa) para no pisar resultados.

---

## 5. #5 — Tooltip de método derivado de las anclas

### 5.1 Fuente
`core/scanners/patterns.py` ya tiene, por sigla, los `cover_flavors` con sus
`anchors` (texto estructural que el OCR busca en la banda superior). Ejemplo odi:
`antecedentes generales`, `identificación del trabajador`, `tipo de inducción`, …

### 5.2 Exposición
- Backend: helper `scan_info_for(sigla) -> dict` en un módulo nuevo
  `core/scanners/scan_info.py` (o función en `patterns.py`):
  - `scan_strategy == "anchors"` → `{kind:"anchors", looks_for:[<top N anclas
    distintivas>]}`. "Top N" = las primeras `min(3, len)` anclas de la unión de
    flavors, saltando las genéricas de paginación (`"pagina 1 de"`). Determinista,
    sin redacción a mano.
  - `scan_strategy == "pagination"` → `{kind:"pagination"}`.
  - `scan_strategy == "none"` → `{kind:"none"}`.
- Endpoint: `GET /api/siglas/{sigla}/scan-info` → el dict. (Estático por sigla;
  el front lo cachea.) Alternativa más simple: incluir `scan_info` en el payload
  de cada celda de `GET /api/sessions/{id}` — **decisión: endpoint dedicado**, para
  no inflar el estado de sesión y porque es invariante por sigla.

### 5.3 Frontend
- `src/lib/method-info.js` pasa a componer el texto del tooltip a partir de
  `scan-info` + el método:
  - anchors → `"OCR de encabezado. Busca: <a1> · <a2> · <a3>."`
  - pagination → `"Cuenta documentos por la numeración 'Página N de M'."`
  - page_count_pure → `"Un documento por página."`
  - filename_glob → `"Un documento por archivo PDF."`
  - manual → `"Valor ingresado a mano."`
- El DetailPanel ya tiene la (i) con Tooltip (del fix #8); solo cambia la fuente del
  texto a este compositor sigla-aware.

---

## 6. #6 — Ficha por sigla (descripción + rango de páginas)

### 6.1 Ubicación
En el DetailPanel, **entre** la cifra grande (`N documentos`) y el título
"Conteo automático": un bloque chico de 2-3 líneas:
- Línea 1-2: **qué es** este tipo de documento (conciso).
- Línea 3: **"Suele tener X-Y páginas por documento."**

### 6.2 Contenido — descripciones (borrador; Daniel corrige)
Tabla nueva `frontend/src/lib/sigla-info.js` (`SIGLA_DESCRIPTION`). **Borrador**
desde labels + anclas; respeta la regla de `sigla-labels.js` (no inventar, no
expandir siglas; lo dudoso va marcado para que Daniel lo ajuste):

| sigla | label | descripción (borrador) |
|-------|-------|------------------------|
| reunion | Reunión de prevención | Acta de reunión del equipo/comité de prevención. |
| irl | Inducción IRL | Información de Riesgos Laborales entregada al trabajador (DS 44). |
| odi | ODI Visitas | Obligación de Informar a visitas: riesgos de la obra para quien la visita. |
| charla | Charlas | Charla de seguridad con su lista de asistencia. |
| chintegral | Charla integral | Charla integral con lista de asistencia ampliada. |
| dif_pts | Difusión PTS | Difusión de un Procedimiento de Trabajo Seguro. |
| art | ART | Análisis de Riesgo del Trabajo, por tarea. |
| insgral | Inspecciones generales | Inspección general de las condiciones de la obra. |
| bodega | Inspección bodega | Inspección de la bodega (orden, almacenamiento). |
| maquinaria | Inspección de maquinaria | Inspección del estado de maquinaria. |
| ext | Extintores | Registro/inspección de extintores. |
| senal | Señaléticas | Inspección de señaléticas de la obra. |
| exc | Excavaciones y vanos | Chequeo de excavaciones y vanos. |
| altura | Trabajos en altura | Chequeo/permiso de trabajos en altura. |
| caliente | Inspección trabajos en caliente | Chequeo/permiso de trabajos en caliente. |
| herramientas_elec | Inspección herramientas eléctricas | Inspección de herramientas eléctricas. |
| andamios | Andamios | Lista de chequeo de andamios. |
| chps | CHPS | Acta del Comité Paritario de Higiene y Seguridad. |

> **chps** = Comité Paritario de Higiene y Seguridad (confirmado por Daniel/Carla).
> El *token* de sigla `chps` viene mal de la fuente (debería ser CPHS); se mantiene
> como está en esta ronda — corregirlo cruza varios proyectos del pipeline y se
> difiere a futuro. El resto de las descripciones quedaron OK en la revisión de Daniel.

### 6.3 Contenido — rangos de páginas (del corpus)
- Script de auditoría one-off `tools/audit_sigla_page_ranges.py`: recorre
  `INFORME_MENSUAL_ROOT` (todos los meses × hospitales), por sigla junta el conteo
  de páginas de cada PDF y emite `{sigla: {p25, median, p75, min, max, n}}`.
- El **rango típico mostrado** = `p25–p75` (robusto a outliers como el `charla_crs`
  de 399pp). Se hornea en `SIGLA_PAGE_RANGE` dentro de `sigla-info.js` (valores
  fijos revisables; no se calcula en vivo en cada render).
- Microcopy: `"Suele tener 4–6 páginas por documento."` Si `p25==p75` →
  `"Suele tener N páginas."`. Siglas de 1 página (las fijas de 1pp) →
  `"Normalmente 1 página."`.

---

## 7. R1-auto al abrir un mes

### 7.1 Comportamiento (decidido: solo en la primera apertura)
- Al abrir un mes (`openMonth`), si la sesión **no tiene datos escaneados**
  (todas las celdas vacías / `cells == {}`), dispara pase 1 automáticamente.
- Si ya hay datos (se escaneó antes, o hay OCR/overrides), **no** re-escanea: usa lo
  guardado. Re-escanear queda en el botón manual.
- Motivo: pase 1 sobrescribe `per_file`/`method` y limpia `near_matches`, así que
  correrlo en cada apertura **borraría resultados OCR** previos.

### 7.2 Implementación
- Frontend `store/session.js` `openMonth`: tras `getSession`, si
  `Object.keys(session.cells||{}).length === 0`, llamar `runScan(sessionId)`.
- Indicador: el `loading` existente cubre el spinner de "Escaneando…".
- (Sin cambios de backend: reusa `POST /scan`.)

---

## 8. Mapa de archivos

**Backend**
- `core/scanners/utils/header_band_anchors.py` — `count_covers_by_anchors` gana `on_page`.
- `core/scanners/anchors_scanner.py`, `pagination_scanner.py` — `count_ocr` gana `only` + propaga `on_page`.
- `core/scanners/utils/cell_enumeration.py` — (si hace falta) helper para filtrar a 1 archivo.
- `core/orchestrator.py` — `scan_one_file_ocr` + eventos `file_*`.
- `core/scanners/scan_info.py` (nuevo) — `scan_info_for(sigla)`.
- `api/state.py` — `apply_per_file_ocr_result`; `per_file_method` en apply_filename/ocr.
- `api/routes/sessions.py` — endpoint single-file scan; `_origin_for` usa `per_file_method`.
- `api/routes/siglas.py` (nuevo) o en `months.py` — `GET /api/siglas/{sigla}/scan-info`.
- `tools/audit_sigla_page_ranges.py` (nuevo, one-off).

**Frontend**
- `src/lib/api.js` — `scanFileOcr`, `getScanInfo`.
- `src/store/session.js` — `fileScan` + handlers WS `file_*`; `openMonth` R1-auto.
- `src/components/PDFLightbox.jsx` — botón single-file + barra por página.
- `src/components/FileViewerProgress.jsx` (nuevo, chico) — barra `página X de N`.
- `src/lib/method-info.js` — compositor sigla-aware (usa scan-info).
- `src/lib/sigla-info.js` (nuevo) — `SIGLA_DESCRIPTION` + `SIGLA_PAGE_RANGE`.
- `src/components/DetailPanel.jsx` — ficha (#6) + tooltip (#5) desde scan-info.

---

## 9. Contratos / tipos

- `per_file_method`: `dict[str, str]` en el cell state. Métodos: los tokens
  existentes (`filename_glob`, `page_count_pure`, `header_detect`, `corner_count`,
  `header_band_anchors`, `v4`).
- Evento `file_page_progress`: `{type, hospital, sigla, filename, page:int, pages_total:int}`.
- Evento `file_scan_done`: `{type, hospital, sigla, filename, result:{ocr_count:int,
  method:str, per_file:{<filename>:int}, near_matches:[...]}}`.
- `scan-info`: `{sigla, kind:"anchors"|"pagination"|"none", looks_for?:[str]}`.

---

## 10. Testing (cadence: tests al final, "todo junto" — preferencia de Daniel)

Por tarea se escribe el test + código + commit; la corrida completa
(`pytest`+`vitest`+`build`) + smoke se hace junta al final.

- **#1 backend:** `apply_per_file_ocr_result` fusiona sin tocar otros archivos
  (per_file de B intacto al escanear A); `per_file_method[A]` queda en el método OCR;
  near_matches de A reemplazados, de B intactos. Orquestador emite `file_page_progress`
  con `page` 1..N (path A7 + path OCR, monkeypatching `get_page_count`). Endpoint 404
  si el archivo no está en la celda.
- **#1 `_origin_for` per-archivo:** con `per_file_method` mixto, A→OCR, B→R1 (mismo cell).
- **#5:** `scan_info_for("odi")` devuelve `kind=anchors` + las anclas esperadas (no la
  de paginación); `scan_info_for("insgral")` → pagination; `reunion` → none. Endpoint OK.
- **#6:** `SIGLA_DESCRIPTION`/`SIGLA_PAGE_RANGE` cubren las 18 siglas (test de
  completitud). El script de auditoría no entra a la suite (one-off).
- **R1-auto:** test de store: `openMonth` con `cells:{}` llama `runScan`; con datos, no.
- **Smoke (chrome-devtools, ABRIL, DB aislada):** escanear un archivo desde el visor
  (barra por página → chip OCR/Revisar + conteo refrescado); (i) de método muestra las
  anclas; ficha de sigla con descripción + rango; abrir un mes "fresco" dispara R1.

**Worktree caveat:** ~12 fallos `FileNotFoundError` por `data/samples/*.pdf` gitignored
ausentes — no son regresión.

---

## 11. Fuera de alcance — multiusuario (nota para futuro)

Compartir la app en LAN con Carla + presencia + bloqueo de celda es **su propio
spec+plan**. Resumen de lo que implicaría (para cuando se retome):
- LAN: `HOST=0.0.0.0` + URL/cloudflared; ambas contra el mismo FastAPI + SQLite (WAL ya activo, suficiente para 2 usuarios).
- Presencia: extender el WS por sesión para registrar/difundir clientes conectados.
- Bloqueo de celda: reclamar/soltar celda, difundir por WS, rechazar edición concurrente; candado con heartbeat/timeout para no quedar colgado.
- Riesgos: concurrencia de escritura en SQLite (baja con 2 usuarios, ok), candados zombi, y los flujos de autosave/override necesitando chequeo de candado.

---

## 12. Orden sugerido (para el plan)

`per_file_method` (transversal §3) → #5 (scan-info, chico, independiente) →
#6 (ficha, depende de scan-info para nada; independiente) → R1-auto (chico) →
#1 (el grande: backend single-file + barra + merge) → verificación.
