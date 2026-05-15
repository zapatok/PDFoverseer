# FASE 5 — UX slice — Design Spec

**Date:** 2026-05-15
**Branch:** `po_overhaul` (continues from `fase-4-mvp`)
**Predecessor:** FASE 4 UX slice (`docs/superpowers/specs/2026-05-14-fase-4-design.md`)

## Goal

Cerrar tres pendientes del roadmap post-FASE 4, todos construidos sobre la base ya
existente (design system `po-*`, navegación Zustand sin router, primitives en
`frontend/src/ui/`). Una sola fase: el **histórico drill-in** como feature UX eje,
más dos ítems de robustez backend (**cancelación a nivel de página** y **auto-retry
de OCR**) que acompañan.

El refinamiento de motores OCR por tipo de documento queda **explícitamente fuera**
de FASE 5 — diferido a la fase final del roadmap (ver memoria
`project_ocr_refinement_deferred`).

## Scope

### In scope

1. **Histórico drill-in** — click en una celda del SparkGrid (un hospital × una
   sigla) abre un drawer lateral derecho con la serie completa de 12 meses: números
   mes-a-mes, gráfico de línea, stats, y audit del método que generó cada mes.
   Read-only.
2. **Cancelación a nivel de página** — al cancelar un escaneo OCR en curso, el
   worker debe detenerse en ≤3 s en vez de terminar la celda completa.
3. **Auto-retry on OCR failure** — cuando el OCR de una celda falla por una
   excepción transitoria, el orquestador reintenta hasta 2× en silencio antes de
   reportar el error.

### Out of scope

- Refinamiento de motores/parámetros OCR por tipo de documento (fase final).
- Edición de conteos históricos desde el drill-in (se decidió read-only).
- Salto al mes desde el drill-in (descartado en brainstorming).
- Cambios de esquema de base de datos.
- Nuevas dependencias npm o pip.
- `react-router` — la navegación sigue siendo estado Zustand.

---

## Feature 1 — Histórico drill-in

### Mental model

El usuario está en `MonthOverview`, vista "Histórico", mirando el `SparkGrid`
(18 siglas × 4 hospitales de sparklines). Hace click en una celda. Aparece un
**drawer lateral derecho** con la serie de esa celda en detalle. Puede hacer click
en otra celda y el drawer cambia de serie sin cerrarse. Cierra con la X o ESC.

El drill-in es **inspección pura read-only**: no edita nada, no navega a ningún
lado. Su valor es ver los números exactos detrás de la sparkline y auditar de
dónde salió cada mes.

### Component: `ui/Drawer.jsx` (primitive nuevo)

Panel que entra deslizando desde el borde derecho de la ventana.

- **No-modal por diseño.** A diferencia de `ui/Dialog.jsx` (Radix Dialog, modal,
  focus-trap, bloquea el fondo), el `Drawer` NO atrapa el foco ni bloquea clicks en
  el resto de la página. Esto es deliberado: el `SparkGrid` detrás debe permanecer
  interactivo para que el usuario pueda clickear otra celda y cambiar de serie.
- **Sin scrim opaco.** El grid queda visible. A lo sumo un borde/sombra que separe
  el panel del fondo.
- **Props:** `open: boolean`, `onClose: () => void`, `title?: ReactNode`,
  `children`.
- **Cierre:** botón X en el header del panel + tecla ESC (listener mientras
  `open`). Click fuera NO cierra (porque "fuera" incluye el grid, que es
  interactivo).
- **Ancho:** ~420 px fijo. Animación de entrada/salida con transición CSS
  (translateX), sin librería.
- Tokens `po-*` para superficie/borde/texto, consistente con los demás primitives.

Vive en `frontend/src/ui/` junto a los 8 primitives de FASE 3. Un solo consumidor
hoy (`HistoryDrawer`), pero el mecanismo slide-in + ESC + posicionamiento es
genérico y no-trivial; se modela como primitive para mantener el patrón de `ui/`.

### Component: `HistoryDrawer.jsx`

Componente que consume `Drawer` y renderea el contenido del drill-in. Vive en
`frontend/src/components/` (un solo consumidor: `MonthOverview`).

Contenido (validado en mockup durante el brainstorming):

1. **Header** — `{hospital} · {sigla}` en grande; subtítulo con la etiqueta de la
   sigla (`SIGLA_LABELS`) y el rango temporal ("12 meses · jun 2025 → may 2026").
2. **Stats strip** — tres stats calculadas client-side desde los 12 puntos:
   - Último (conteo del mes más reciente)
   - Promedio 12m
   - Rango (mín–máx)
3. **Gráfico de línea** — los 12 puntos como polyline en un `<svg>`, último punto
   resaltado. Consistente con el estilo de `Sparkline` pero a mayor tamaño. Si la
   serie es anómala (ver tono más abajo) la línea usa el tono ámbar.
4. **Tabla mes-a-mes** — una fila por mes, **más reciente arriba**. Columnas:
   - Mes (`MM/YYYY`)
   - Conteo (tabular-nums)
   - Método — chip con la familia visual de `OriginChip`: `filename_glob` → "R1",
     técnicas OCR (`header_detect` / `corner_count` / `page_count_pure`) → "OCR",
     `manual` → "manual".
   - La fila del mes anómalo se resalta en ámbar (`po-suspect`).

No hay columna de Confianza (decidido en brainstorming — el dato `confidence`
viene en el payload pero no se muestra).

### SparkGrid integration

`frontend/src/components/SparkGrid.jsx`:

- Cada celda (hoy un `<div>` con `Sparkline` + valor + `Tooltip`) pasa a ser
  clickeable — un `<button>` que invoca la acción de abrir el drill-in para ese
  `(hospital, sigla)`.
- La celda cuya serie está abierta en el drawer lleva un anillo de resaltado
  (`ring` con token `po-accent`).
- La función `anomalyTone(series)` ya existente se reutiliza tanto para el tono de
  la celda como para el del drawer — el `HistoryDrawer` la importa o se extrae a un
  helper compartido si conviene (decisión del plan).

### State (Zustand)

`frontend/src/store/session.js` — un campo nuevo y dos acciones, siguiendo el patrón
de `historyView` (FASE 4):

```js
historyDrawer: null,   // { hospital, sigla } | null

openHistoryDrawer: (hospital, sigla) => set({ historyDrawer: { hospital, sigla } }),
closeHistoryDrawer: () => set({ historyDrawer: null }),
```

Click en celda → `openHistoryDrawer`. Click en otra celda → `openHistoryDrawer`
otra vez (reemplaza). X/ESC → `closeHistoryDrawer`. `setView` / `setHistoryView`
deben limpiar `historyDrawer` al salir de la vista Histórico (igual que ya
resetean `hospitalMode`/`focusSigla`/`historyView`).

### Data flow — sin cambio de backend

El endpoint `GET /sessions/{id}/history?n=12` ya devuelve, por cada
`"{hospital}|{sigla}"`, la serie completa de 12 puntos con
`{year, month, count, confidence, method}`. El hook `useHistory` de
`frontend/src/lib/useHistoryStore.js` ya cachea ese objeto a nivel de módulo.

El `HistoryDrawer` **no hace fetch propio**: lee la serie de la misma data ya
cacheada que alimenta el `SparkGrid` (`history[`${hospital}|${sigla}`]`). Cero
endpoints nuevos, cero requests nuevos. Si la celda no tiene serie (sin datos
históricos), el drawer muestra un estado vacío ("Sin datos para esta serie").

---

## Feature 2 — Cancelación a nivel de página (<3 s)

### Estado actual

La cancelación es cooperativa vía `CancellationToken`
(`core/scanners/cancellation.py`), respaldada por un `multiprocessing.Event`. El
orquestador `scan_cells_ocr` (`core/orchestrator.py`) ya hace "cancel-fast":
descarta futures encolados y deja de procesar resultados apenas detecta el cancel
(`pool.shutdown(wait=False, cancel_futures=True)`).

El problema está **dentro del worker**: las tres funciones OCR por tipo de
documento —

- `count_paginations` (`core/scanners/utils/corner_count.py`) — usada por `art_scanner`
- `count_form_codes` (`core/scanners/utils/header_detect.py`) — usada por `_header_detect_base`
- `count_documents_in_pdf` (`core/scanners/utils/page_count_pure.py`) — usada por `charla_scanner`

— **no reciben el `CancellationToken`** y por lo tanto no tienen checkpoint de
cancelación dentro de su loop de páginas. Los scanners (`art_scanner`,
`charla_scanner`, `_header_detect_base`) solo chequean `cancel.check()` *antes* de
empezar el OCR, no durante. Resultado: al cancelar a mitad del OCR de una
compilación grande, esa función corre todas las páginas del PDF antes de devolver
el control — decenas de segundos para un PDF de 40+ páginas.

(`core/pipeline.py`, el V4 pipeline pesado, sí chequea cancelación por lote de
`BATCH_SIZE=12` páginas — su granularidad es aceptable y queda fuera de este
cambio; el gap real son las utils OCR de FASE 4 sin checkpoint.)

### Cambio

- Threadear el `CancellationToken` (o un predicado de cancelación equivalente)
  hacia las funciones OCR por tipo de doc que tienen loop de páginas
  (`count_paginations`, `count_form_codes`; `count_documents_in_pdf` es un conteo
  de páginas puro sin loop de OCR — si no itera páginas, no requiere checkpoint, lo
  confirma el plan).
- Dentro de esos loops, chequear el token cada página (o cada 1–2 páginas) y
  abortar limpiamente — levantando `CancelledError` o devolviendo un resultado
  centinela que el scanner traduzca a `err="cancelled"`.
- Los scanners (`art_scanner`, `charla_scanner`, `_header_detect_base`) pasan su
  `cancel` recibido hacia estas utils.

### Comportamiento al cancelar a mitad de celda

- La celda interrumpida **descarta el OCR parcial** y conserva su conteo
  `filename_glob` (R1). No se guarda ningún número parcial.
- Las celdas que ya terminaron su OCR antes del cancel **conservan su resultado
  OCR** — sin cambio respecto del comportamiento actual.
- El evento `scan_cancelled` que emite el orquestador no cambia.

### Objetivo medible

Desde que el usuario presiona Cancelar hasta que el escaneo se detiene: **≤3
segundos**, incluso con una compilación grande en curso.

---

## Feature 3 — Auto-retry on OCR failure

### Estado actual

En `scan_cells_ocr` (`core/orchestrator.py`), cada celda se procesa vía
`_ocr_worker(ct)`, que devuelve `(hospital, sigla, result, err)`. `_ocr_worker`
atrapa cualquier excepción y la devuelve como string en `err`. Hoy, si `err` es no
nulo (y distinto de `"cancelled"`), la celda se reporta directamente como
`cell_error` — sin reintento.

### Cambio

- En el orquestador, envolver la llamada de OCR de cada celda con lógica de
  reintento: ante un `err` no nulo y distinto de `"cancelled"`, reintentar
  `_ocr_worker` para esa celda hasta **2 veces** con un backoff corto entre
  intentos.
- **Silencioso:** el reintento no emite eventos de progreso adicionales. El usuario
  solo ve la celda completarse normalmente (si un reintento tuvo éxito) o el
  `cell_error` habitual (si los reintentos se agotaron).
- Solo tras agotar los reintentos se reporta el error por el camino existente
  (`cell_error` / lista de errores).
- **Granularidad:** celda completa — la unidad del orquestador. No hay reintento
  por página.
- **Sin clasificador transitorio/determinístico** (YAGNI): se reintenta cualquier
  `err` no-`"cancelled"`. Reintentar 2× un fallo determinístico (PDF corrupto) es
  barato e inocuo; agregar un clasificador no se justifica.
- **Interacción con cancelación:** si el token de cancelación está activo, no se
  reintenta — un `err="cancelled"` nunca dispara retry, y un cancel que llega
  durante la ventana de reintentos corta el ciclo.

Aplica a ambos caminos de `scan_cells_ocr`: el sincrónico (`max_workers==1`, usado
en tests) y el multi-worker (`ProcessPoolExecutor`). En el camino multi-worker, el
reintento implica re-submitir la celda fallida al pool; el plan define el mecanismo
exacto.

---

## Data model

Sin cambios de esquema de base de datos. Sin cambios de payload de API.

Único cambio de estado: el campo `historyDrawer` en el store Zustand
(`frontend/src/store/session.js`), descrito en Feature 1.

---

## Edge cases

- **Celda sin serie histórica** — el `HistoryDrawer` recibe `undefined`/`[]` para
  `history[key]`: muestra un estado vacío, no crashea.
- **Serie con menos de 12 meses** — stats y gráfico se calculan sobre los puntos
  disponibles; la tabla muestra solo los meses que hay.
- **Click en otra celda con el drawer abierto** — `openHistoryDrawer` reemplaza la
  serie; el drawer no se cierra ni re-anima la entrada.
- **Salir de la vista Histórico con el drawer abierto** — `historyDrawer` se
  resetea a `null` junto con `historyView`.
- **Cancelar antes de que arranque el OCR** — ya cubierto: el pre-flight de
  `scan_cells_ocr` emite `scan_cancelled(scanned=0)`.
- **Cancelar durante la ventana de reintentos** — el ciclo de retry chequea
  cancelación y corta; la celda queda en R1.
- **Fallo OCR persistente** — tras 2 reintentos fallidos, se reporta `cell_error`
  como hoy; la celda conserva su conteo R1.
- **`count_documents_in_pdf` sin loop de páginas** — si efectivamente es un conteo
  puro, no necesita checkpoint; el plan lo verifica antes de threadear `cancel`.

## Testing strategy

- **Drill-in** — frontend; verificación por smoke E2E vía chrome-devtools MCP
  (abrir drawer, cambiar de serie, cerrar con ESC/X, estado vacío). Sin runner de
  tests JS (el proyecto no tiene uno; fuera de alcance agregarlo).
- **Cancelación** — pytest: iniciar un escaneo OCR sobre una compilación, cancelar
  a mitad, assert que (a) el escaneo se detiene dentro del presupuesto de 3 s y
  (b) la celda interrumpida revierte a su conteo R1. Test del checkpoint de
  cancelación en las utils OCR con un token que se activa tras N páginas.
- **Auto-retry** — pytest: un scanner inyectado que falla N veces y luego tiene
  éxito → el retry lo recupera y la celda termina OK; un scanner que falla siempre
  → el `cell_error` se expone tras exactamente 2 reintentos. Sin mocking de base de
  datos (regla del proyecto); usar fakes de scanner/worker.
- **Regresión** — `pytest -q` completo verde y `ruff check .` sin violaciones
  antes de cerrar. Verificar que las features de FASE 4 no regresionaron (HLL
  manual flow, per-file overrides, toggle Histórico/SparkGrid).

## Acceptance criteria

**AC1 — Drill-in**
- Click en una celda del SparkGrid abre el drawer lateral derecho con esa serie.
- El drawer muestra header, stats strip, gráfico de línea y tabla mes-a-mes con
  chips de método; la fila anómala resaltada en ámbar.
- Click en otra celda cambia la serie sin cerrar el drawer; la celda activa lleva
  resaltado.
- ESC y la X cierran el drawer; el grid detrás permanece interactivo en todo
  momento.
- Una celda sin datos muestra estado vacío sin crashear.
- Cero requests de red nuevos: el drawer lee de la data ya cacheada por
  `useHistoryStore`.

**AC2 — Cancelación**
- Al cancelar un escaneo OCR en curso, el escaneo se detiene en ≤3 s, incluso con
  una compilación grande siendo procesada.
- La celda interrumpida conserva su conteo R1; las celdas ya completadas conservan
  su OCR.

**AC3 — Auto-retry**
- Un fallo OCR transitorio se recupera automáticamente con hasta 2 reintentos
  silenciosos; el usuario no ve ruido adicional.
- Un fallo persistente se reporta como `cell_error` tras agotar los 2 reintentos.
- Un `err="cancelled"` nunca dispara reintentos.

**AC4 — Cross-cutting**
- `ruff check .` sin violaciones; `pytest -q` completo verde.
- Sin dependencias nuevas; delta de bundle marginal.
- Las tres features de FASE 4 siguen funcionando (sin regresión).
- Branch `po_overhaul`; tag `fase-5-mvp` al cierre, esperando aprobación de push.
