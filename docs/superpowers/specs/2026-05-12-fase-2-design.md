# PDFoverseer FASE 2 — OCR para compilaciones + corrección manual + WebSocket progress

**Fecha:** 2026-05-12
**Rama:** `po_overhaul` (continúa después de tag `fase-1-mvp` + `fix(scanners)` commit `1b35597`)
**Spec FASE 1:** `docs/superpowers/specs/2026-05-11-pdfoverseer-overhaul-design.md`

## 1. Goal

Resolver el ~10% de celdas de la matriz 4×18 donde un único PDF contiene N documentos
apilados ("compilaciones"), introducir una UX de corrección manual con preview del PDF,
y emitir eventos de progreso en tiempo real para que la app permanezca usable mientras
corren scanners OCR lentos.

## 2. Scope

**Incluye:**

- 4 scanners especializados (`art_scanner`, `odi_scanner`, `irl_scanner`, `charla_scanner`) con técnicas OCR por sigla
- 4 OCR utils (`header_detect`, `corner_count`, `page_count_pure`, `pdf_render`)
- Modelo de celda enriquecido: 3 campos numéricos independientes (`filename_count`, `ocr_count`, `user_override`) + `override_note`
- UX de corrección manual: lista de archivos en panel detalle + lightbox flotante con preview iframe
- WebSocket protocol con eventos `cell_scanning` / `cell_done` / `cell_error` / `scan_progress` / `scan_complete` / `scan_cancelled`
- API endpoints nuevos: `scan-ocr`, `cancel`, override PATCH, PDF GET, files GET
- Cancelación de batch en curso con target <3s desde click
- Persistencia atómica de overrides y notas
- UPSERT a `historical_counts` al generar Excel (tabla ya existe desde FASE 1)

**Out of scope (deferred to FASE 3):**

- Cross-month report
- Folder rename automation
- JSON export
- ETA basado en histórico de scanners
- Settings UI
- `custom_pdfs_added` / `custom_pdfs_excluded` UI
- Métricas dashboard

## 3. Architecture

### 3.1 Two-pass model

Pase 1 — rápido, automático al abrir un mes:

- `scan_month` corre `filename_glob` sobre las 54 celdas presentes (HPV/HRB/HLU × 18 siglas)
- ~3-7 segundos en ABRIL
- Sin OCR. Sin progress feedback granular.
- Identifica suspects via `page_count_heuristic.flag_compilation_suspect` (ya existe desde FASE 1)

Pase 2 — opt-in, granular:

- Daniel decide qué celdas corren OCR. Tres modos de selección:
  - Individual (botón "OCR" en una fila de CategoryRow)
  - Multi-select (checkboxes + `[OCR N seleccionadas]`)
  - Bulk por hospital (`[OCR todos los suspects de HPV]` en HospitalCard)
- Cada celda usa el scanner de su sigla, que internamente elige técnica OCR primaria + fallback
- Progress por celda emitido vía WS en tiempo real

### 3.2 Scanner techniques per sigla

Cuatro siglas tienen archivo propio. Los otros 14 quedan con `simple_factory` (sin cambios desde FASE 1).

| Sigla | Archivo | Técnica primaria | Fallback |
|---|---|---|---|
| art | `core/scanners/art_scanner.py` | `corner_count` (busca "Página N de M" en esquina superior derecha) | `filename_glob` |
| odi | `core/scanners/odi_scanner.py` | `header_detect` (busca regex `F-CRS-ODI/\d+` en top de cada página) | `filename_glob` |
| irl | `core/scanners/irl_scanner.py` | `header_detect` (`F-CRS-IRL/\d+`) | `filename_glob` |
| charla | `core/scanners/charla_scanner.py` | `page_count_pure` aplicado al único PDF compilado de la carpeta (1 página = 1 charla) | `filename_glob` |

Decision rule uniforme dentro de cada scanner especializado:

1. Si carpeta solo tiene 1 PDF con `page_count` >> esperado (compilación) → técnica primaria OCR aplicada a ese PDF
2. Si carpeta tiene N PDFs con `page_count` normal → `filename_glob` directo (no gasta OCR)
3. Si OCR falla (no matches, timeout, error) → `filename_glob` como fallback, `confidence=LOW`, flag `ocr_failed`

`page_count_pure` opera sobre **un único PDF** (el PDF compilado de la
carpeta charla). El scanner llama `page_count_pure(pdf_path)` solo cuando
la carpeta cumple regla 1. Para carpetas con N PDFs individualizados,
charla cae a `filename_glob` por regla 2 — no se suma `page_count` de N
PDFs (eso contaría páginas, no documentos).

### 3.3 OCR utils

```
core/scanners/utils/
├── filename_glob.py       (existente, fixed en commit 1b35597)
├── page_count_heuristic.py (existente)
├── per_empresa_breakdown.py (existente, vía filename_glob.py)
├── header_detect.py       NUEVO  — busca códigos F-CRS-*/NN
├── corner_count.py        NUEVO  — busca "Página N de M"
├── page_count_pure.py     NUEVO  — 1pp = 1doc (trivial)
└── pdf_render.py          NUEVO  — wrapper PyMuPDF para extraer pages/regiones
```

Cada util ≤250 LOC. Stateless (sin singletons), reciben `Path` y devuelven valores primitivos.

`pdf_render.py` expone:

```python
def render_page_image(pdf_path: Path, page_idx: int, *, dpi: int = 150) -> PIL.Image
def render_page_region(pdf_path: Path, page_idx: int, bbox: tuple[float, float, float, float], *, dpi: int = 200) -> PIL.Image
def get_page_count(pdf_path: Path) -> int
```

`header_detect.py` expone:

```python
def count_form_codes(pdf_path: Path, *, sigla_code: str, dpi: int = 200) -> HeaderDetectResult
# Renderea top-third de cada página, OCR, busca regex F-CRS-<sigla_code>/\d+, devuelve set único de matches.
# HeaderDetectResult: count, matches: list[str], pages_with_match: list[int]
```

`corner_count.py` expone:

```python
def count_paginations(pdf_path: Path, *, dpi: int = 200) -> CornerCountResult
# Renderea esquina superior derecha (per-spec original §266), OCR, parsea "Página N de M".
# Cuenta transiciones M en cada total único, suma. Una serie [1/3, 2/3, 3/3, 1/2, 2/2] → 2 docs.
```

Reuso del motor 5-fases: el regex y digit-normalization de `core/utils.py`
(`_PAGE_PATTERNS`, OCR digit map) ya están probados y resuelven los falsos
positivos. `corner_count.py` los importa directamente — qué exactamente
queda como decisión durante implementación (ver §11.2).

### 3.4 Cell state model

Estado por celda en `sessions.state_json["cells"][hospital][sigla]`:

```json
{
  "filename_count": 1,
  "ocr_count": 17,
  "user_override": null,
  "override_note": null,
  "method": "header_detect",
  "confidence": "high",
  "breakdown": {"AGUASAN": 0, ...},
  "flags": ["compilation_suspect"],
  "errors": [],
  "files_scanned": 1,
  "duration_ms_filename": 12,
  "duration_ms_ocr": 23410
}
```

**Prioridad para el Excel writer** (evalúa de arriba a abajo, primer no-null gana):

1. `user_override`
2. `ocr_count`
3. `filename_count`
4. `0` (celda no escaneada, sin override)

**Migración FASE 1 → FASE 2:**

Al abrir una sesión existente (state_json con campo `count` legacy), el primer
`get_session_state` aplica la migración in-place y persiste de vuelta via
`update_session_state` en la misma transacción:

```python
def _migrate_cell_v1_to_v2(cell: dict) -> dict:
    if "count" in cell:
        cell["filename_count"] = cell.pop("count", None)  # default-safe por si futuro refactor mueve la guarda
    cell.setdefault("ocr_count", None)
    cell.setdefault("override_note", None)
    # `excluded` (bool, FASE 1) se mantiene; sin uso UI nuevo en FASE 2.
    return cell
```

Idempotente: las celdas sin `count` (nunca escaneadas) o ya migradas pasan sin
cambios. La persistencia inmediata garantiza que consumers no-API (orchestrator
en re-scan, generador de Excel) leen siempre el schema FASE 2. No requiere
migración SQL — el cambio vive en el JSON state.

**Excluded cells:** el flag `cell.excluded: bool` heredado de FASE 1 sigue
existiendo en el JSON state. FASE 2 no introduce UI nueva para togglearlo
(queda para FASE 3); el writer del Excel respeta `excluded` ignorando esas
celdas como hoy.

### 3.5 Cancellation

```python
@dataclass
class CancellationToken:
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True

    def check(self) -> None:
        if self.cancelled:
            raise CancelledError()
```

Cada scanner OCR debe chequear el token en cada checkpoint natural (entre páginas del PDF, entre archivos de la carpeta). Target: `cancel()` a notificación de `scan_cancelled` debe ocurrir en <3 segundos.

El backend mantiene 1 token por sesión activa. Re-lanzar un batch antes que el anterior termine retorna 409 Conflict.

**Edge cases:**

| Caso | Comportamiento |
|---|---|
| `POST /cancel` sin batch activo | 200 OK idempotente (no-op). No emite WS event. |
| `cancel()` antes de iterar primera celda | Orchestrator detecta token al primer check → emite `scan_cancelled` con `scanned=0, total=N` y retorna. |
| `cancel()` justo después de `scan_complete` emitido | Token se ignora — el batch ya terminó. POST cancel sigue devolviendo 200. |
| `cancel()` durante render de página | Worker termina la página actual, próximo checkpoint detecta token y abandona el PDF. La celda queda con `errors=["cancelled"]` (no en `ocr_count`). |

## 4. Backend changes

### 4.1 SessionManager extensions (`api/state.py`)

Reemplaza el método único por tres más finos:

```python
def apply_filename_result(self, session_id, hospital, sigla, result: ScanResult) -> None
def apply_ocr_result(self, session_id, hospital, sigla, result: ScanResult) -> None
def apply_user_override(self, session_id, hospital, sigla, value: int | None, note: str | None) -> None
```

Cada uno toca exactamente sus campos (no pisa otros). `apply_ocr_result` además guarda `method` y `duration_ms_ocr`. El valor de `method` refleja la técnica que efectivamente produjo el `ocr_count`: si la primaria del scanner ganó, `method ∈ {"header_detect", "corner_count", "page_count_pure"}`; si la primaria falló (no_matches, timeout, error) y el scanner cayó a `filename_glob` como fallback interno, `method = "filename_glob"` (es decir, el origen real del número guardado). `value=None` en override borra el campo.

Migración legacy se ejecuta en `get_session_state` antes de devolver al cliente (lazy, idempotente).

### 4.2 Orchestrator `scan_cells_ocr` (`core/orchestrator.py`)

```python
def scan_cells_ocr(
    cells: list[tuple[str, str, Path]],     # (hospital, sigla, folder_path)
    *,
    on_progress: Callable[[ProgressEvent], None],
    cancel: CancellationToken,
    max_workers: int = 2,
) -> dict[tuple[str, str], ScanResult]:
    ...
```

`ProcessPoolExecutor(max_workers=2)` — OCR es CPU+RAM heavy, 2 workers es seguro en máquinas modernas. El callback `on_progress` se invoca desde el thread principal (no desde el worker) para evitar issues de cross-thread. El bridge worker→main se hace vía `concurrent.futures.as_completed`.

### 4.3 API endpoints

| Método | Path | Body | Resultado |
|---|---|---|---|
| POST | `/api/sessions/{id}/scan-ocr` | `{cells: [["HPV","odi"], ...]}` | 202 Accepted, batch lanzado en thread; progreso via WS. 409 si hay otro batch en curso. |
| POST | `/api/sessions/{id}/cancel` | — | 200 OK siempre (idempotente). Si hay batch activo, setea `cancel_token.cancelled`. Si no hay batch, no-op (sin error, sin WS event). Ver §3.5 edge-cases. |
| PATCH | `/api/sessions/{id}/cells/{hospital}/{sigla}/override` | `{value: int \| null, note: str \| null}` | 200 OK + cell state actualizado. Validación: `value` debe estar en `[0, MAX_REASONABLE_COUNT]` (default 10000, carry-over de FASE 1) o ser `null` para borrar. |
| GET | `/api/sessions/{id}/cells/{hospital}/{sigla}/files` | — | `[{name: "x.pdf", subfolder: "TITAN", page_count: 28, suspect: true}, ...]`. Lista vacía `[]` si la carpeta no tiene PDFs. |
| GET | `/api/sessions/{id}/cells/{hospital}/{sigla}/pdf` | `?index=N` (opcional) | application/pdf streaming. Default index=0 (mayor `page_count`). Validación de path traversal obligatoria. 404 con `{detail: "no_pdfs_in_cell"}` si la carpeta no tiene PDFs; 400 si `index` está fuera de rango. |

Endpoint existente sin cambios: `POST /api/sessions/{id}/scan` (pase 1 filename_glob).

### 4.4 WebSocket protocol

Endpoint `/ws/sessions/{session_id}` (ya existe desde FASE 1 como keepalive). FASE 2 emite eventos JSON line-delimited:

```jsonl
{"type":"cell_scanning","hospital":"HPV","sigla":"odi","timestamp":1234567890}
{"type":"cell_done","hospital":"HPV","sigla":"odi","result":{"ocr_count":17,"method":"header_detect","confidence":"high","duration_ms_ocr":23410}}
{"type":"cell_error","hospital":"HPV","sigla":"odi","error":"pdf_corrupted: ..."}
{"type":"scan_progress","done":3,"total":10,"eta_ms":120000}
{"type":"scan_complete","scanned":10,"errors":0,"cancelled":0}
{"type":"scan_cancelled","scanned":3,"total":10}
```

`cell_done` siempre corresponde al pase OCR (el pase 1 no emite progreso
granular), por eso el campo se llama `duration_ms_ocr` consistente con el
schema en §3.4.

**Threading model concreto.** La ruta `POST /scan-ocr` lanza
`scan_cells_ocr` en un thread vía `BackgroundTasks` o
`asyncio.run_in_executor`. Dentro, `ProcessPoolExecutor(2)` ejecuta workers
en subprocesses. El thread orchestrator itera `as_completed(futures)` y
para cada resultado invoca el `on_progress(event)` callback —
**ese callback corre en el thread orchestrator**, no en el subprocess.
El callback construye el evento WS y lo encola al asyncio loop principal
con `app.state.loop.call_soon_threadsafe(broadcast, event)`. La función
`broadcast` recorre conexiones WS activas para esa sesión y manda el JSON.
Captura del loop principal: en `app.main:lifespan` se guarda
`app.state.loop = asyncio.get_running_loop()`.

**Reconexión.** Cliente reintenta cada 3s tras drop. Al reconectar:

1. Frontend hace `GET /sessions/{id}` → resync del cell state persistido.
2. Frontend **limpia** `scanningCells` y `scanProgress` en el store.
3. Si un batch sigue activo en el backend, los próximos `cell_scanning`/
   `cell_done`/`scan_progress` eventos repueblan el store. Visualmente hay
   un gap de 0-3s donde el progress bar muestra estado "vacío".

Aceptamos ese gap visual en FASE 2 — la alternativa (endpoint
`/scan-status` para query del estado in-flight) suma superficie API sin
beneficio práctico (Daniel raramente cierra el browser mid-batch).

### 4.5 DB additions

`historical_counts` table ya existe desde FASE 1 (migration en `core/db/migrations.py`). El schema:

```sql
historical_counts(year, month, hospital, sigla, count, confidence, method, finalized_at)
PRIMARY KEY (year, month, hospital, sigla)
```

FASE 2 agrega la **escritura** sin migración de schema: al final de
`POST /sessions/{id}/output`, después de generar el Excel exitosamente,
UPSERT una fila por celda no excluida:

```sql
INSERT INTO historical_counts (year, month, hospital, sigla, count, confidence, method, finalized_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(year, month, hospital, sigla) DO UPDATE SET
  count = excluded.count,
  confidence = excluded.confidence,
  method = excluded.method,
  finalized_at = excluded.finalized_at
```

El campo `method` codifica el origen efectivo del count:

| Origen del count efectivo | `method` value |
|---|---|
| `user_override != null` | `"override"` |
| `ocr_count` ganó (no override, hubo OCR) | técnica concreta: `"header_detect"`, `"corner_count"`, `"page_count_pure"` |
| `filename_count` ganó (no override ni OCR) | `"filename_glob"` |

Auditoría implícita: `method = "override"` en histórico marca celdas donde
hubo intervención humana. Idempotente: regenerar Excel del mismo mes 2 veces
no rompe (UPSERT sobreescribe con valores iguales).

### 4.6 PDF serving

`GET /api/sessions/{id}/cells/{hospital}/{sigla}/pdf?index=N` sirve el PDF embebido en el lightbox.

Seguridad:

1. Resolve `cell.folder_path` desde el session state (no acepta path del cliente).
2. `index` es entero, 0 ≤ index < len(pdfs_in_folder).
3. La carpeta debe estar dentro de `INFORME_MENSUAL_ROOT` (Python `Path.is_relative_to`).
4. Si esas validaciones fallan → 400 / 404.

Implementación: `FileResponse(path, media_type="application/pdf")` — FastAPI streamea con range requests soportados (necesario para PDFs grandes que el iframe paginará).

Performance: <1s para PDFs <100MB. Sin cache HTTP (los PDFs no cambian entre revisiones, pero tampoco son grandes).

## 5. Frontend changes

### 5.1 Componentes nuevos

| Archivo | Responsabilidad |
|---|---|
| `frontend/src/components/FileList.jsx` | 3a columna del HospitalDetail. Lista los PDFs de la celda seleccionada con filtro/orden/badges. Click abre el lightbox. |
| `frontend/src/components/PDFLightbox.jsx` | Modal flotante. Preview en `<iframe>` + cabecera con counts/override/nota. Cierra con X / backdrop / Esc. |
| `frontend/src/components/OverridePanel.jsx` | Input numérico + textarea nota. Reutilizado en panel detalle y lightbox (mismo state via store). |
| `frontend/src/components/ScanControls.jsx` | Header de HospitalDetail con `[OCR seleccionadas]` y `[OCR suspects de este hospital]`. |
| `frontend/src/components/ScanProgress.jsx` | Footer global pegado abajo. Barra de progreso + texto + `[Cancel]`. Auto-dismiss 5s después de `scan_complete`. |
| `frontend/src/lib/ws.js` | Cliente WebSocket. Conecta al abrir sesión, reintenta cada 3s, despacha eventos al store. |

### 5.2 Componentes modificados

| Archivo | Cambio |
|---|---|
| `CategoryRow.jsx` | + checkbox multi-select · + spinner cuando `scanningCells.has(sigla)` · + ✕ rojo si `errors.length > 0` |
| `HospitalDetail.jsx` | Layout 3 columnas (categorías \| detalle+override \| FileList). Responsive: <1400px = FileList stacked abajo. |
| `HospitalCard.jsx` | + botón "OCR suspects" (oculto si no hay suspects en el hospital). |
| `MonthOverview.jsx` | + botón global "OCR todos los suspects del mes". |
| `App.jsx` | Mounta `<ScanProgress/>` global. Inicializa WS en `useEffect` al abrir sesión. |

### 5.3 Store extensions (`store/session.js`)

Campos nuevos:

```js
{
  selectedCells: new Set(),         // "HPV_odi", "HRB_odi"
  scanningCells: new Set(),
  scanProgress: null,               // {done, total, eta_ms} | null
  lightbox: null,                   // {hospital, sigla, pdfIndex} | null
  wsConnected: false,
}
```

Acciones:

```js
toggleCell(hospital, sigla)
selectAllSuspects(hospital?)        // hospital=undefined => mes completo
clearSelection()
startOcr(cells?)                    // cells=undefined => usa selectedCells
cancelOcr()
setOverride(hosp, sigla, value, note)
openLightbox(hosp, sigla, pdfIndex)
closeLightbox()
handleWsEvent(event)                // dispatcher central
```

### 5.4 API client (`lib/api.js`)

Funciones nuevas:

```js
api.scanOcr(sessionId, cells)
api.cancelScan(sessionId)
api.setOverride(sessionId, hospital, sigla, value, note)
api.listFiles(sessionId, hospital, sigla)
api.pdfUrl(sessionId, hospital, sigla, index = 0)   // devuelve URL para iframe, no fetch
```

### 5.5 WS client (`lib/ws.js`)

```js
class SessionWS {
  constructor(sessionId, onEvent)
  connect()         // reintenta cada 3s si cae
  close()
}
```

Singleton instanciado en `App.jsx` al abrir sesión, cerrado al cambiar sesión / desmontar.

### 5.6 Layout responsive

Breakpoints: ≥1400px = 3 columnas lado a lado · 1024-1399px = archivos stacked debajo del detalle · <1024px fuera de scope (Daniel trabaja en desktop).

```
≥1400px:                          1024-1399px:
┌────┬────────┬────────┐          ┌────┬─────────────┐
│cat │detalle │archivos│          │cat │ detalle     │
│    │        │        │          │    ├─────────────┤
│    │        │        │          │    │ archivos    │
└────┴────────┴────────┘          └────┴─────────────┘
```

## 6. UX flows

(Resumen — flujos completos detallados en sección de brainstorm. El plan de implementación los expande con código JSX/Python.)

1. **Bulk OCR hospital:** click `[OCR suspects]` en HospitalCard → POST scan-ocr → WS events → CategoryRows actualizan en vivo → ScanProgress visible → auto-dismiss al completar.
2. **Batch OCR selección:** checkbox 3 celdas → `[OCR 3]` → flujo idéntico.
3. **OCR celda única:** botón "OCR" en una fila → flujo idéntico con N=1.
4. **Cancel:** botón en ScanProgress → POST cancel → token.cancel() → workers actuales terminan página y abandonan → WS `scan_cancelled` → footer dice "Cancelado · 3/10".
5. **Override sin scan:** abrir lightbox (con o sin counts) → escribir número → cerrar (X/backdrop/Esc) → autosave → PATCH override.
6. **Override después de OCR:** misma UX, ahora con pase 1 y pase 2 visibles para comparar.
7. **Borrar override:** input vacío + cerrar → PATCH `value=null` → Excel revierte a pase 2 o 1.
8. **Editar nota:** textarea blur → PATCH (debounce 1s).
9. **Error en OCR:** WS `cell_error` → CategoryRow ✕ rojo → panel detalle muestra error → Daniel puede override igual o reintentar.
10. **WS disconnect:** banner "Reconectando..." → cada 3s reintenta → al volver, GET /sessions resync.
11. **Cerrar el frontend a mitad de batch (sin matar el backend):** el proceso uvicorn sigue corriendo, el batch sigue ejecutándose en su thread, DB persiste cada `cell_done` atómicamente. Al reabrir el browser: WS reconecta, GET resync, el batch completa normalmente. Si Daniel mata el proceso backend (Ctrl+C en la terminal), el batch se pierde — sin recovery automático en FASE 2; Daniel re-lanza el batch al volver.

## 7. Error handling

| Caso | Comportamiento |
|---|---|
| OCR Tesseract crashea por PDF corrupto | scanner devuelve `errors=["pdf_corrupted: {path}"]`, celda en ✕, batch sigue |
| OCR timeout (>60s/celda) | scanner aborta, fallback automático a filename_glob, `flags=["ocr_timeout"]`, `confidence=LOW` |
| `header_detect` sin matches | count=0 + `flags=["no_header_matches"]`, fallback filename_glob |
| `corner_count` sin "Página N de M" | count=page_count + `flags=["no_pagination"]`, assume 1pp=1doc, `confidence=LOW` |
| PDF muy grande para render @200 DPI | reintenta con DPI 100 → 75 → 50 → si todo falla, error |
| Cancel mientras se renderiza una página | worker termina la página, próximo checkpoint abandona |
| Backend muere a mitad de batch | scan se pierde (no recovery automático FASE 2). DB no se corrompe — cada `cell_done` es atómico. Daniel re-lanza |
| PDF >500MB | rechaza `GET /pdf` con 413, mensaje sugiere compresión aguas arriba |
| Override negativo | API rechaza 400 con `value must be >= 0` |
| Concurrencia: 2 batches en curso | POST scan-ocr devuelve 409 Conflict si ya hay batch activo |
| WS disconnect | banner UI, reintenta cada 3s, REST resync al volver |

## 8. Testing strategy

| Capa | Qué se testea | Fixtures |
|---|---|---|
| Unit OCR utils | `header_detect`, `corner_count`, `page_count_pure` aislados | PDFs reales de ABRIL en `tests/fixtures/fase2/` |
| Unit scanners | `art_scanner`, `odi_scanner`, `irl_scanner`, `charla_scanner` con fixtures + fallback path | Mismo set + scanners mockeados para timing |
| Unit orchestrator | `scan_cells_ocr` + `CancellationToken` + callback dispatch | Scanners mockeados con sleeps controlados |
| Unit state | `apply_filename_result`, `apply_ocr_result`, `apply_user_override`, migración legacy `count` → `filename_count` | tmp_path SQLite |
| API integration | endpoints nuevos (scan-ocr, cancel, override, pdf, files) con FastAPI TestClient | tmp_path DB + corpus real ABRIL |
| WS integration | conexión, eventos en orden correcto, override survival entre re-scans, reconnect | TestClient WS helper |
| E2E slow | flujo completo end-to-end: scan → suspects → OCR batch → override → generate → verificar Excel | corpus real, marked `@pytest.mark.slow` |

**Fixtures a extraer del corpus real** (per memoria `feedback_art670_fixture_disaster` — no fabricar):

- `HRB_odi_compilation.pdf` (34pp, esperado ~17 ODIs vía header_detect)
- `HLU_odi_compilation.pdf` (48pp, esperado ~24 ODIs)
- `HPV_art_multidoc_sample.pdf` (28pp con paginación)
- `HPV_charla_single.pdf` (multi-página normal, 1 doc)
- 1 PDF sintético `corrupted.pdf` (0-byte) **deliberadamente fabricado** para test de error handling. Justificación: no es substituto de datos reales para inferencia (que es lo que `feedback_art670_fixture_disaster` prohibe) sino un input degenerado controlado para verificar que el scanner falla gracefully. No alimenta ningún test de count.

## 9. Performance budgets

| Métrica | Target | Cómo medir |
|---|---|---|
| Pase 1 filename_glob 54 cells | <10s | Test integración existente |
| OCR 1 celda HRB/ODI (34pp) | <45s | Benchmark único en `tests/benchmark/`. Cálculo back-of-envelope: 34 páginas × ~0.8s Tesseract sobre crop top-third @ 200 DPI ≈ 27s. Margen 45s para overhead de PyMuPDF + IO. |
| OCR batch 10 celdas | <5 min con `max_workers=2` | E2E test |
| Cancel response | <3s desde click hasta `scan_cancelled` | Test de timing dedicado |
| PDF serve | <1s para PDFs <100MB | FastAPI FileResponse benchmark |
| WS event latency backend→UI | <100ms | Implícito en E2E |
| Workflow mensual completo (Daniel) | <15 min | Tracking manual + auto en E2E |

## 10. Definition of done

- [ ] `pytest -m "not slow"` 100% verde
- [ ] `pytest -m slow` 100% verde, incluyendo E2E del flujo completo
- [ ] `ruff check .` → 0 violaciones
- [ ] `npm --prefix frontend run build` → 0 warnings
- [ ] Los 11 flujos UX de sección 6 verificados manualmente en Brave debug
- [ ] HRB/ODI ABRIL: count cambia de 1 (filename) a ~17 (OCR) en el Excel generado
- [ ] HPV/ART ABRIL: count confirmado contra filename_glob (corner_count debe matchear ya que ART está individualizado)
- [ ] Workflow real de un mes completable en <15 min
- [ ] WS reconnect validado (matar Vite o backend mid-batch, debe recuperar y resincronizar)
- [ ] Cancel <3s validado
- [ ] Lightbox abre PDFs de 100+ páginas sin congelar
- [ ] Override survival entre re-scans validado
- [ ] **Regression guard:** los counts de FASE 1 (celdas sin OCR aplicado) permanecen sin cambios después de la migración legacy `count` → `filename_count`. Test E2E lo verifica corriendo un scan FASE 1, migrando, y comparando antes/después de las 54 celdas
- [ ] CLAUDE.md, README, memorias actualizadas con FASE 2
- [ ] Tag `fase-2-mvp`

## 11. Open decisions

Quedan algunos puntos a refinar durante el plan de implementación:

1. **`page_count_heuristic` thresholds por sigla:** los umbrales actuales son conservadores. FASE 2 puede ajustarlos basándose en distribución real de ABRIL/MARZO/FEBRERO una vez tengamos ese data.
2. **`corner_count` — qué símbolos exactos importa del motor 5-fases:** el spec §3.2 ya commit a reusar `core/utils._PAGE_PATTERNS` + digit-normalization. Queda decidir durante implementación qué wrapper/helper público exponer (si se mueve a un módulo neutro vs import directo desde `core/utils`).
3. **PDF viewer:** `<iframe>` es el plan por simplicidad. Si la UX queda pobre (no annotations, no thumbnail navigation), evaluar pdf.js en FASE 3.
4. **Thread vs process pool para OCR:** `ProcessPoolExecutor(2)` es el plan. Si Tesseract muestra ser thread-safe en práctica, podría bajarse a threads (menos overhead). A medir.
5. **Idempotencia del UPSERT a `historical_counts`:** re-generar el Excel del mismo mes 2 veces debe ser idempotente. Hoy lo es por design del `ON CONFLICT DO UPDATE`. Test E2E lo cubre.
