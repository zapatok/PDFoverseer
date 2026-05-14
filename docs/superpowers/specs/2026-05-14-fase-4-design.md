# PDFoverseer FASE 4 — Slice UX: HLL manual, docs por archivo, multi-mes

**Fecha:** 2026-05-14
**Rama:** `po_overhaul` (continúa después de tag `fase-3-polish` + commit `911084f` `a11y(pdf-lightbox)`)
**Specs predecesoras:**
- `docs/superpowers/specs/2026-05-13-fase-3-polish-design.md` (FASE 3)
- `docs/superpowers/specs/2026-05-12-fase-2-design.md` (FASE 2)

---

## 1. Goal

Cerrar tres pendientes UX del roadmap post-FASE 3 que comparten una capa de diseño (po-* tokens + 8 primitives de FASE 3) y se construyen sobre la columna vertebral existente (MonthOverview → HospitalDetail → FileList). Tres features independientes a nivel de scope pero coherentes a nivel de experiencia: el usuario gana visibilidad sobre datos que hoy quedan implícitos o invisibles.

1. **HLL manual-entry** — Habilitar el flujo para meses en los que un hospital (típicamente HLL) no se normalizó vía el pipeline `informe mensual`. El usuario puede capturar los 18 conteos a mano sin romper el resto de la app.
2. **Docs por archivo en FileList** — Exponer, para cada PDF dentro de un cell, cuántos documentos aporta. Hoy ese dato existe a nivel cell-total pero nunca se desglosa.
3. **Multi-mes overview (tendencia histórica)** — Toggle "Histórico" en MonthOverview que reemplaza la grilla de hospitales por una vista 18 siglas × 4 hospitales con sparklines de los últimos 12 meses.

## 2. Scope

**Incluye:**

- HLL manual flow: HospitalCard CTA "Llenar manualmente →" en estado empty; HospitalDetail con `mode="manual"`; reusa CategoryRow + InlineEditCount existentes; autoshift de focus al siguiente input al presionar Enter; reusa el literal de `method` `"manual"` que ya existe en FASE 2 (no se inventan valores nuevos).
- Per-file: extiende `ScanResult` con `per_file: dict[str, int] | None`; cada scanner (simple_factory + OCR scanners) lo propaga; persiste en cell state; expone en `/files`; nuevo endpoint `PATCH /cells/{h}/{s}/files/{filename}/override`; cell-count derivado de `sum(per_file_overrides | per_file)` cuando hay datos; el cell `method` se mantiene como el del scanner subyacente (per-file override es un refinamiento, no un método nuevo); cuando hay overrides el cell también recibe `method="manual"` solo si la suma derivada se vuelve la fuente principal del count (ver §6.3).
- Frontend per-file: FileList row muestra `Npp + Ndocs + OriginChip (OCR/R1/manual)` con InlineEditCount sobre el badge de docs; chip uniforme tipo Badge primitive de FASE 3 con tres variantes (iris/jade/amber).
- Multi-mes: toggle `[Mes actual] [Histórico]` en header de MonthOverview con URL state (`?view=history`); nuevo componente `Sparkline` (~50 LoC SVG inline, sin libs externas); nuevo `SparkGrid` 18×4 reusando layout del MonthOverview; tooltip al hover muestra los valores mes-a-mes; anomalías (caída >30% vs promedio 6m, baseline efectivo ≥6 meses) en tone "warn"; nuevo endpoint `GET /sessions/{id}/history?n=12`.
- Sin schema migrations: todos los nuevos campos en cell state son aditivos vía `setdefault`. `historical_counts` se reusa tal cual.
- Verificar/garantizar que `core/excel/writer.py` genera HLL con 0 (o vacío) cuando no hay datos. Si no lo hace, fix antes que el flow manual.

**Out of scope (deferred a FASE 4.5 o posterior):**

- Drill-in al click en una celda del SparkGrid (la sparkline expone los valores vía tooltip; la vista de "detalle histórico con todos los meses" queda fuera).
- Refinamiento per-sigla de los motores OCR (header_detect semántico, ART corner_count gap, charla compilation vs N-PDFs). Roadmap motor.
- Page-level cancellation (<3s).
- Auto-retry on OCR failure.
- Configurabilidad del N de meses del SparkGrid (fijo en 12).
- Light mode, responsive mobile, keyboard shortcuts globales (Enter-Tab dentro del manual flow sí entra).
- Edición / borrado / merge de `historical_counts` entries antiguos.

## 3. Mental model

FASE 4 no cambia el modelo central de PDFoverseer (memoria `project_pdfoverseer_purpose`: contar documentos por (hospital × sigla) sobre 72 celdas mensuales, régimen 1 trivial vs régimen 2 compilación). Lo que agrega son **tres dimensiones de visibilidad** sobre el mismo modelo:

- **Granularidad por archivo** (per-file): hasta ahora el motor era una caja negra a nivel cell; FASE 4 expone la atribución por archivo individual cuando existe.
- **Override sin scan** (manual): asume que el motor nunca corrió porque no hay archivos físicos, pero el dato existe (alguien lo contó fuera del sistema).
- **Eje temporal** (multi-mes): hasta ahora la app era mes-céntrica; FASE 4 permite ver continuidad o quiebres en una sigla a lo largo del tiempo.

Las 3 dimensiones son ortogonales y no se entrelazan en runtime — un cell tiene per-file XOR manual-entry (no ambos), y el SparkGrid lee de `historical_counts` que ya consolida cualquiera de las precedencias.

## 4. Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      FRONTEND (React + Vite)                    │
│  MonthOverview                                                  │
│   ├─ [Mes actual]  [Histórico] ◀ toggle NEW                     │
│   ├─ HospitalCardGrid (mes actual)                              │
│   │   └─ HospitalCard×4                                         │
│   │       └─ "Llenar manualmente →" CTA ◀ NEW (cuando state=empty)│
│   └─ SparkGrid (histórico) ◀ NEW                                │
│       └─ Sparkline×72                                           │
│  HospitalDetail                                                 │
│   ├─ mode="scanned" (default, comportamiento FASE 3)            │
│   └─ mode="manual" ◀ NEW (placeholder distinto, focus first)    │
│       └─ CategoryRow×18                                         │
│           ├─ InlineEditCount (reusado)                          │
│           └─ FileList                                           │
│               └─ Row: Npp + Ndocs + OriginChip ◀ NEW            │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      BACKEND (FastAPI)                          │
│  POST /sessions/{id}/cells/{h}/{s}/override   ya existe FASE 2  │
│  PATCH /sessions/{id}/cells/{h}/{s}/files/{filename}/override   │
│         ◀ NUEVO                                                 │
│  GET /sessions/{id}/cells/{h}/{s}/files       extiende per_file │
│  GET /sessions/{id}/history?n=12              ◀ NUEVO           │
│                                                                 │
│  core/scanners/*.py        ScanResult.per_file (extendido)      │
│  api/state.py              persiste per_file + per_file_ovrd    │
│  core/excel/writer.py      tolera HLL vacío (verificar)         │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                       SQLite (data/overseer.db)
                       ── session_state.cells (+ per_file, +overrides)
                       ── historical_counts (sin cambios)
```

Lo que NO cambia: `/sessions` (CRUD), `/output` (Excel), websocket, `core/orchestrator`, `core/inference`, modelos SR, módulo `vlm/`.

## 5. Componentes

### 5.1 Frontend

| Componente | Acción | Detalle |
|------------|--------|---------|
| `HospitalCard` | extiende | Cuando `state==="empty"` (sin folder), reemplaza el placeholder estático por un CTA accionable "Llenar manualmente →" que navega a `/hospital/{code}?mode=manual&focus=reunion`. (CTA copy idéntico en card y detail header — single string en `frontend/src/lib/constants.js`.) |
| `HospitalDetail` | extiende | Acepta `mode: "scanned" \| "manual"`. En modo manual: (a) header muestra "N/18 ingresadas" en lugar de "N/18 procesadas"; (b) cada CategoryRow muestra "—" como placeholder del count; (c) focus inicial en el InlineEditCount de la primera sigla; (d) Enter avanza al siguiente input. |
| `CategoryRow` | extiende | (a) Acepta `mode="manual"` que cambia placeholder y oculta chip de método cuando count es null. (b) Cuando hay `per_file_overrides`, recalcula su display count como `sum(overrides | per_file)`. |
| `FileList` | extiende | Cada row pasa de `[icono][name][page_count]` a `[icono][name][page_count][badge N docs editable][OriginChip]`. Búsqueda existente sin cambio. Footer muestra "N archivos · M docs total" (M = cell-count). |
| `OriginChip` | nuevo, interno | ~15 LoC. 3 variantes: `OCR` (po-iris), `R1` (po-jade), `manual` (po-amber). Padding/radius/altura idénticos. No es primitive top-level; vive en `frontend/src/components/`. |
| `Sparkline` | nuevo | ~50 LoC SVG inline. Props: `data: number[]`, `tone?: "neutral"\|"warn"\|"muted"`. **Tonto** — no calcula anomalías; solo dibuja según el tone que recibe. Si `data.length === 0` renderiza dashed line; si `data.length === 1` renderiza solo el punto. Hereda po-* tokens. |
| `SparkGrid` | nuevo | Vista que reemplaza HospitalCardGrid cuando `?view=history`. Layout: 18 filas (siglas) × 5 columnas (label + 4 hospitales). **Computa** `anomalyTone(series)` y lo pasa como prop a `<Sparkline>`. Cada celda: `<Sparkline data={series} tone={anomalyTone(series)} />` + valor del último mes a la derecha. Hover en celda → Tooltip con la lista de (month, count). |
| `MonthOverview` | extiende | Header agrega switch `[Mes actual] [Histórico]` que escribe a `?view=`. URL state, no Zustand. Recarga preservante. |
| `useSessionStore` | extiende | Nueva acción `savePerFileOverride(hospital, sigla, filename, count)` siguiendo el patrón AbortController-safe de FASE 3 (`saveOverride`). Key del AbortController: `${hospital}|${sigla}|${filename}`. |
| `useHistoryStore` | nuevo | Hook con **cache módulo-level** (objeto singleton fuera del componente, similar al patrón de `frontend/src/lib/api.js`). Fetchea `/history?n=12` la primera vez que cualquier consumer monta; cachea por `session_id`; expone `invalidate()` que SparkGrid llama cuando recibe el toast post-Excel. Cero deps nuevas (ni Zustand, ni React Query). |
| `InlineEditCount` | reusa tal cual | Mismo signature: `(value: number, onSave: (v: number) => void)`. Sirve para cell-count (FASE 3) y per-file-count (FASE 4). |

### 5.2 Backend

| Archivo | Cambio |
|---------|--------|
| `core/scanners/base.py` | Agrega `per_file: dict[str, int] \| None = None` al dataclass `ScanResult`. |
| `core/scanners/simple_factory.py` | Construye `per_file = {filename: 1 for filename in glob}` paralelo al `breakdown` por empresa existente. No remover breakdown. |
| `core/scanners/art_scanner.py`, `charla_scanner.py`, `_header_detect_base.py` | Modifican el loop interno (que ya itera por archivo) para acumular `per_file: dict[str, int]` y exponerlo en ScanResult. Fallback `per_file=None` solo si el OCR falla (error path). |
| `api/state.py` | (a) `apply_filename_result`, `apply_ocr_result` y el dispatcher legacy `apply_cell_result` (líneas 169–177, deprecated wrapper sobre filename_result) persisten `cell["per_file"] = result.per_file`. (b) Nuevo método `apply_per_file_override(session_id, hospital, sigla, filename, count)`. (c) Función pura `compute_cell_count(cell)` con la jerarquía de precedencia. |
| `api/routes/sessions.py` | (a) `/files` endpoint joinea `cell.per_file` y `cell.per_file_overrides` con la lista enumerada del disco. (b) Nuevo endpoint `PATCH /sessions/{id}/cells/{h}/{s}/files/{filename}/override`. |
| `api/routes/history.py` | **NUEVO**. `GET /sessions/{id}/history?n=12` returna `{(hospital, sigla): [(year, month, count, method), ...]}`. Implementación reusa `core/db/historical_repo.query_range(from_year, from_month, to_year, to_month)` que ya existe (~línea 99) — query usa el patrón canónico `(year * 12 + month) BETWEEN ?` para cubrir cross-year ranges. **No** se modifica el schema de `historical_counts` (columnas reales: `year INTEGER, month INTEGER, hospital, sigla, count, confidence, method, finalized_at`, PK `(year, month, hospital, sigla)`). |
| `frontend/src/lib/cellCount.js` | **NUEVO**. Función pura `computeCellCount(cell)` espejando 1:1 la lógica de `api/state.py.compute_cell_count`. Sin TypeScript (el repo es 100% `.jsx` + `.js`; no hay TS toolchain). |
| `core/excel/writer.py` | Verificar con `pytest tests/test_writer.py -k missing_hospital` (test a crear si no existe): cuando un hospital no tiene datos en cell state, las 18 celdas correspondientes salen como 0 o vacías sin error. Tarea PRE-FLIGHT (ver §9.4). |
| `api/main.py` | Registrar el nuevo router `history`. |

### 5.3 Sin nuevos primitives top-level

Memoria `project_fase3_shipped` regla: "Nuevos primitivos solo si hay un shape genuinamente nuevo." `OriginChip` se construye sobre `Badge` (no es nuevo primitive). `Sparkline` es una visualización (no input), vive en `components/` no en `ui/`.

## 6. Modelo de datos

### 6.1 Cell shape (session_state JSON)

Campos marcados ◀ son nuevos en FASE 4. Todos opcionales con `cell.setdefault(...)` al leer → backward-compatible con sesiones existentes.

```python
cell = {
    "hospital": "HRB",
    "sigla": "odi",
    "filename_count": 5,
    "ocr_count": 24,
    "user_override": None,
    "override_note": None,
    "breakdown": None,                # per-empresa, ya existía
    "per_file": {                     # ◀ NEW
        "compilacion_odi_abril.pdf": 24,
        "odi_visita_juan-perez.pdf": 1,
    },
    "per_file_overrides": {           # ◀ NEW
        "odi_misc.pdf": 5,
    },
    "manual_entry": False,            # ◀ NEW (true cuando es HLL flow; usado por
                                       # frontend para distinguir UI; backend persiste
                                       # method="manual" en historical_counts)
    "flags": [...],
    "errors": [...],
    "files_scanned": 6,
    "duration_ms_filename": 12,
    "duration_ms_ocr": 8345,
    "excluded": False,
}
```

### 6.2 Cell-count derivado (orden de precedencia)

```python
def compute_cell_count(cell: dict) -> int:
    # 1. Escape hatch FASE 2: override total del cell gana siempre.
    if cell.get("user_override") is not None:
        return cell["user_override"]

    # 2. FASE 4: si hay datos per-file (de OCR o override), suma derivada.
    per_file = cell.get("per_file") or {}
    per_file_overrides = cell.get("per_file_overrides") or {}
    if per_file or per_file_overrides:
        all_files = set(per_file) | set(per_file_overrides)
        return sum(
            per_file_overrides.get(f, per_file.get(f, 0))
            for f in all_files
        )

    # 3. Fallback existente: OCR count o filename count.
    return cell.get("ocr_count") or cell.get("filename_count") or 0
```

### 6.3 historical_counts.method registry (audit trail)

Contrato establecido en FASE 2 §4.5 y frozen en `frontend/src/lib/method-labels.js` (comentario: "never invent new tokens here"). FASE 4 **no agrega valores nuevos** — reusa los existentes.

| Literal | Significado | Origen |
|---------|-------------|--------|
| `"filename_glob"` | Régimen 1, conteo derivado del nombre de archivo. | FASE 1 |
| `"header_detect"` | OCR detectó cabeceras de formulario (header_detect scanners). | FASE 2 |
| `"corner_count"` | OCR detectó "Pagina N de M" en esquina (ART). | FASE 2 |
| `"page_count_pure"` | Heurística page_count / typical (charla, fallback). | FASE 2 |
| `"manual"` | Usuario proveyó el valor — cubre **3 casos en FASE 4**: (a) `user_override` post-scan (FASE 2 escape hatch), (b) HLL manual-entry sin scan (FASE 4 nuevo flow), (c) cell donde la suma derivada de `per_file_overrides` es lo que define el count final. |

**Por qué reusar `"manual"` en lugar de inventar `"manual_entry"` o `"per_file_override"`:** mantiene el contrato del frontend (`METHOD_LABEL["manual"] = "Manual"`) intacto; el caso "intervino el usuario" es semánticamente uno solo a nivel del audit trail; el detalle granular (cell-level vs HLL flow vs per-file override mix) ya está representado en otros campos del cell (`user_override`, `manual_entry`, `per_file_overrides`).

### 6.4 Query histórica

Schema real (`core/db/migrations.py:21-31`): columnas separadas `year INTEGER` y `month INTEGER`, PK `(year, month, hospital, sigla)`. Query canónica con el patrón ya usado en `core/db/historical_repo.py:108`:

```sql
SELECT year, month, hospital, sigla, count, confidence, method, finalized_at
FROM historical_counts
WHERE (year * 12 + month) BETWEEN ? AND ?
ORDER BY year, month, hospital, sigla
```

Cálculo del rango (Python): `from_key = from_year * 12 + from_month`; para 12 meses atrás desde mayo 2026, `from = (2025, 6)` → `from_key = 24306`; `to = (2026, 5)` → `to_key = 24317`.

La función `core/db/historical_repo.query_range(from_year, from_month, to_year, to_month)` ya implementa exactamente este patrón — el endpoint `/history` la llama directamente sin SQL nuevo.

Volumen máximo: 12 × 4 × 18 = 864 rows. Query + agrupamiento Python <100ms en local.

## 7. Data flow

### 7.1 HLL manual-entry

```
[user] click "Llenar manualmente →" en HospitalCard(HLL, empty)
   → router.push("/hospital/HLL?mode=manual&focus=reunion")
   → HospitalDetail renderea CategoryRow×18 modo manual
   → focus en InlineEditCount de "reunion"
[user] tipea "12" + Enter
   → useSessionStore.saveOverride("HLL", "reunion", 12, manual=True)
   → POST /sessions/{id}/cells/HLL/reunion/override
       {count: 12, method: "manual"}     # ver registry §6.3 — reusa literal FASE 2
   → api/state.py: cell.user_override=12, cell.manual_entry=True
   → WebSocket broadcast cell_updated
   → focus auto al InlineEditCount de "irl"
[user] cierra app, F5 → state persiste (BD)
[user] genera Excel
   → historical_counts UPSERT vía core/db/historical_repo.upsert_count(...)
       (year=2026, month=4, hospital="HLL", sigla="reunion",
        count=12, confidence="manual", method="manual",
        finalized_at=NOW)
   → Excel sale con HLL=12 en row "reunion"
```

### 7.2 Per-file override en FileList

```
[user] click en badge "24 docs" de file "compilacion_odi.pdf" en FileList
   → InlineEditCount inline (mismo de FASE 3)
[user] cambia a "20" + Enter
   → useSessionStore.savePerFileOverride("HRB", "odi", "compilacion_odi.pdf", 20)
   → PATCH /sessions/{id}/cells/HRB/odi/files/compilacion_odi.pdf/override
       {count: 20}
   → api/state.py.apply_per_file_override
       cell.per_file_overrides["compilacion_odi.pdf"] = 20
       new_count = compute_cell_count(cell)
   → WebSocket broadcast cell_updated con per_file + overrides + new count
   → FileList row: chip OCR → manual (ámbar)
   → CategoryRow: count actualizado (suma derivada)
   → Sonner toast: "Override guardado para compilacion_odi.pdf"
```

### 7.3 Multi-mes tendencia

```
[user] click toggle "Histórico" en header MonthOverview
   → router.replace("?view=history")
   → MonthOverview detecta view, renderea <SparkGrid>
[useHistoryStore] (si no cacheado) GET /sessions/{id}/history?n=12
   → api/routes/history.py: llama historical_repo.query_range(...), group by (hospital, sigla)
   → returns {"HPV|reunion": [{year: 2025, month: 5, count: 8, method: "filename_glob"}, ...], ...}
[SparkGrid] renderea 18×5 grid
   → cada celda: <Sparkline data={series.map(s => s.count)} tone={anomalyTone(series)} />
   → valor del último mes a la derecha
   → Tooltip al hover muestra lista de (month, count)
[user] click toggle "Mes actual"
   → router.replace("?view=current" o sin query)
   → MonthOverview vuelve a HospitalCardGrid
```

## 8. Edge cases y risks

### 8.1 Edge cases — HLL manual

| Caso | Comportamiento |
|------|----------------|
| Usuario ingresa N valores, en mes futuro aparece la carpeta HLL normalizada. | El re-scan respeta `user_override` (FASE 2). El manual_entry=true se mantiene en el cell del mes original. |
| Usuario genera Excel sin ingresar nada. | Excel sale con HLL=0 (o vacío). Pre-flight: garantizar en `core/excel/writer.py`. |
| F5 a mitad del flow. | Persistencia ya es por-Enter (POST /override). State recargado de BD. Sin data loss. |
| Spam de toasts si ingresa 18 valores rápido. | sonner dedupe por content; usar id estable "manual_saved" para overwrite consecutivo. |

### 8.2 Edge cases — Per-file

| Caso | Comportamiento |
|------|----------------|
| Scanner reporta `per_file` pero el FS tiene un PDF nuevo no escaneado. | `/files` enumera del FS; filenames sin entry en `per_file` muestran "—" con OriginChip "sin escanear" (gris). |
| Override > page_count del archivo. | Permitir. Mostrar warning sutil (chip "?" adicional). No validar — confiar en el usuario. |
| Override = 0. | Válido. El archivo cuenta como 0 docs aunque exista. Útil para descartar PDFs erróneos. |
| Race entre saveOverride (cell-level FASE 2) y savePerFileOverride. | AbortController keys diferentes: `${h}\|${s}` vs `${h}\|${s}\|${file}`. Persistencia atómica vía JSON blob completo en `update_session_state`. |
| Scanner no devuelve `per_file` (legacy/error path). | `cell.per_file = None` → frontend fallback a régimen 1 (1 doc per file) con chip "R1". |
| `simple_factory` ya cuenta por empresa (breakdown). | Agregar `per_file` paralelo, no remover breakdown (FASE 5 puede reutilizarlo). |

### 8.3 Edge cases — Multi-mes

| Caso | Comportamiento |
|------|----------------|
| historical_counts vacío (primera ejecución). | SparkGrid renderiza todos los rows con tone="muted" + "—". EmptyState si literally cero rows. |
| Mes con re-generations múltiples del Excel. | UPSERT toma el último valor. Sparkline usa el último. |
| HLL agregado a partir de MAYO 2026 (sin datos previos). | Sparkline arranca con dashed gris para meses sin datos, transiciona a sólido azul al haber datos. |
| Anomalía sobre baseline corto (<6 meses). | No marcar anomalías si N efectivo < 6 → evita falsos positivos en arranque. |
| F5 con `?view=history`. | URL state gana. SparkGrid renderiza. |

### 8.4 Risks arquitectónicos

| Risk | Severidad | Plan |
|------|-----------|------|
| Scanner OCR rompe al agregar `per_file` (tipo wrong, tests existentes fallan). | Alta | TDD estricto: extender ScanResult con tests primero. Cada scanner se modifica con test rojo→verde. |
| historical_counts no se popula como esperaba (bug latente FASE 2). | Media | Pre-flight: smoke ABRIL, BD inspect, verificar 54 rows (3 hospitales × 18). Fix antes de FASE 4 si falla. |
| Sparkline con 1 punto se ve raro. | Baja | Component renderiza solo el punto si N==1. Test dedicado. |
| Bundle delta significativo. | Baja (single-user, memoria `feedback_bundle_size_irrelevant_single_user`) | Reportar en commit body para audit. No bloquea. |
| HLL "Llenar manualmente" con 100ms de delay por POST. | Baja | Optimistic update + rollback on error (mismo patrón FASE 3). |
| Cell-count derivado diverge entre frontend y backend. | Media | `compute_cell_count(cell)` función pura en Python (`api/state.py`) espejada como `computeCellCount(cell)` en JS (`frontend/src/lib/cellCount.js` — siguiendo la convención `lib/` del repo, no TS). Test cross-language vía fixtures JSON compartidos en `tests/fixtures/cell_count_cases.json`. |

## 9. Testing strategy

### 9.1 Layers

FASE 3 §8 (`docs/superpowers/specs/2026-05-13-fase-3-polish-design.md`) estableció: **no nuevos tests automatizados de UI** (no vitest, no jest, no testing-library). PDFoverseer es single-user / LAN / batch; el ROI de la toolchain frontend no justifica la setup. FASE 4 mantiene la línea: tests Python automatizados, smoke manual frontend.

| Layer | Tool | Cobertura FASE 4 |
|-------|------|-------------------|
| Unit Python | pytest + fixtures reales | (a) ScanResult.per_file serializa OK; (b) cada scanner devuelve per_file con keys = filenames; (c) compute_cell_count cubre las ramas (override, per_file mix, fallback); (d) apply_per_file_override flow; (e) apply_override / apply_filename_result / apply_ocr_result preservan `user_override` y `manual_entry` cuando ya existen; (f) writer.py tolera HLL ausente. |
| Integration Python | pytest + fixtures fase 1 (`data/samples/abril/`) | (a) `scan_month` propaga per_file end-to-end para una cell de 2 archivos; (b) endpoint `/history?n=12` shape correcto con BD pre-poblada SQL; (c) `PATCH /files/{f}/override` actualiza state + emite WebSocket; (d) `historical_repo.query_range` integrado con la nueva ruta. |
| Cross-language | pytest + fixtures JSON | `tests/fixtures/cell_count_cases.json` contiene N casos `{cell, expected_count}`. Un test Python valida `compute_cell_count(cell) == expected`. La paridad JS se verifica en el smoke manual cuando el frontend muestra el mismo número que el backend para los mismos cells. |
| E2E smoke manual | chrome-devtools MCP (Claude maneja) | Recorrer las 3 features, capturar screenshots, encontrar bugs reales, commitearlos. Memoria `feedback_browser_testing_via_devtools`. Cobertura: HLL flow completo (entry + persist + Excel), per-file override (chip change + total recalc + persist), multi-mes toggle (URL state + sparkline tones + tooltip). |

### 9.2 Fixtures

- `tests/fixtures/per_file_scanresult.json` — ScanResult serializado con per_file lleno (uno por tipo de scanner).
- `tests/fixtures/historical_counts_12m.sql` — INSERTs para 12 meses × 4 hospitales × 18 siglas, con HLL solo en últimos 6 meses para testear "—" inicial y anomalías de baseline corto.
- Reusar `data/samples/abril/` para integration tests de scanner.
- Reusar `frontend/src/__fixtures__/` para mocks de API.

### 9.3 Orden TDD (rigid)

Cada commit debe ser red→green→refactor con verificación visible:

1. Extender `ScanResult.per_file` — test: serializa/deserializa OK.
2. `simple_factory` devuelve `per_file = {f: 1 for f in glob}`.
3. `art_scanner` retorna per_file (un solo scanner OCR primero).
4. `charla_scanner` retorna per_file.
5. `_header_detect_base` retorna per_file (afecta todos los header-detect scanners).
6. `compute_cell_count(cell)` función pura + tests de las 3 ramas.
7. `apply_per_file_override` en `state.py`.
8. Endpoint `PATCH /files/{f}/override`.
9. Endpoint `GET /history?n=12` (reusa `historical_repo.query_range`).
10. Frontend: `frontend/src/lib/cellCount.js` (función pura, tests Python cross-language).
11. Frontend: `Sparkline` component (smoke manual; no test unit por convención FASE 3).
12. Frontend: `OriginChip` component.
13. Frontend: extender `FileList` row con per_file UI.
14. Frontend: extender `HospitalCard` + `HospitalDetail` para HLL manual flow.
15. Frontend: `SparkGrid` + toggle en `MonthOverview` + `useHistoryStore` (cache módulo-level).
16. Smoke E2E manual con chrome-devtools MCP. Bugs caught → commits adicionales antes de cerrar.

### 9.4 Pre-flight (antes de cualquier código)

- [ ] Verificar que `historical_counts` se popula al generar Excel hoy (smoke ABRIL → BD inspect → 54 rows esperados con method ∈ los 5 literales del registry §6.3).
- [ ] Verificar que `core/excel/writer.py` tolera un hospital sin datos: ejecutar `pytest tests/test_writer.py -k missing_hospital` (crear test si no existe; debe pasar). Si el writer falla, fix mínimo antes de tareas FASE 4.
- [ ] Verificar que AbortController-safe `saveOverride` de FASE 3 sigue intacto en `useSessionStore` (grep el patrón).
- [ ] Confirmar que `core/db/historical_repo.query_range` tiene la signature esperada `(from_year, from_month, to_year, to_month)` — si difiere, ajustar §5.2 antes de implementar.

## 10. Acceptance criteria

**AC1 — HLL manual flow:**
- Desde MonthOverview de ABRIL, el card HLL muestra "Llenar manualmente →" en lugar de un estado opaco no-clickeable.
- Click en el CTA navega a HospitalDetail con mode=manual, focus en input de la primera categoría.
- Tipear N + Enter guarda (toast confirma), focus pasa al siguiente input. ESC sale del modo edit sin cambios.
- F5 después de ingresar 5 categorías mantiene los 5 valores.
- Generar Excel con HLL=valores ingresados; las 18 celdas del Excel reflejan los valores; las no-ingresadas salen como 0.
- Generar Excel sin ingresar nada genera HLL en 0 sin error.
- `historical_counts` registra entries con `method="manual"` (literal FASE 2 reusado, ver registry §6.3).

**AC2 — Per-file docs:**
- FileList row para un cell con OCR muestra `Npp + N docs + chip OCR` (azul outlined badge + chip iris).
- FileList row para un cell régimen 1 muestra `Npp + N docs + chip R1` (mismo badge, chip jade).
- Click en el badge de N docs abre inline-edit; Enter guarda, Escape cancela.
- Tras override: badge cambia a fondo ámbar, chip cambia a "manual", cell-total recalcula como suma derivada y CategoryRow refleja el nuevo total inmediatamente.
- Toast Sonner confirma cada override.
- BD persiste `per_file_overrides`; F5 mantiene los overrides.
- `historical_counts` registra entries con `method="manual"` cuando el cell-count final viene de overrides per-file (registry §6.3 caso (c)). Si todos los archivos del cell mantienen el valor inferido por OCR (sin override), el `method` queda como el del scanner (`header_detect`/`corner_count`/`page_count_pure`).

**AC3 — Multi-mes:**
- MonthOverview header tiene toggle `[Mes actual] [Histórico]` que cambia `?view=`.
- Vista Histórico renderiza 18 siglas × 4 hospitales con sparkline (12 meses) + valor del último mes.
- Sparkline en tone="warn" (ámbar) cuando hay caída >30% vs promedio 6m, solo si baseline efectivo ≥6 meses.
- Hover en celda muestra Tooltip con la lista de (mes, valor).
- F5 con `?view=history` mantiene la vista.
- Sin datos: dashed gris + "—". EmptyState si la BD está literalmente vacía.

**AC4 — Cross-cutting:**
- 0 violations en `ruff check .` antes de commit.
- 0 tests fallidos en `pytest` y `npm test`.
- Smoke E2E con chrome-devtools MCP recorre los 3 flows sin regressions en FASE 3.
- Bundle delta reportado en commit body (memoria: no bloquea).
- Atomic conventional commits con descriptive bodies (memoria `feedback_first_attempt_quality_bar`).

## 11. Open questions

Ninguna pendiente al cierre del brainstorming. Todas las decisiones tomadas con confirmación explícita del PO en sesión 2026-05-14.

## 12. References

- Memoria `project_pdfoverseer_purpose` — modelo central de 2 regímenes.
- Memoria `project_fase3_shipped` — baseline de diseño y reglas (po-* tokens, 8 primitives, no raw palette classes).
- Memoria `feedback_first_attempt_quality_bar` — proceso completo SDD obligatorio.
- Memoria `feedback_chip_consistency` — chips de misma familia comparten forma (Badge primitive).
- Memoria `feedback_browser_testing_via_devtools` — smoke E2E lo maneja Claude vía chrome-devtools MCP.
- Memoria `feedback_no_db_mocking` — tests usan fixtures reales, no mocks de BD.
- Spec FASE 3 — `docs/superpowers/specs/2026-05-13-fase-3-polish-design.md`.
- Spec FASE 2 — `docs/superpowers/specs/2026-05-12-fase-2-design.md`.
- Audit ABRIL corpus — `docs/research/2026-05-11-abril-corpus-audit.md`.
