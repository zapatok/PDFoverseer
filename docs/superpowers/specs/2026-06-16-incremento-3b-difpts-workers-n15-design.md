# Incremento 3B — dif_pts: conteo de trabajadores + mapeo N15

**Fecha:** 2026-06-16
**Rama:** `po_overhaul` (rama única; trabajar directo, push al cierre)
**Predecesor:** Incr 3A (`incremento-3a`) — maquinaria=checks + bug F1.
**Corte del Incr 3 (triage 2026-06-09, grupo F):** 3A = maquinaria + F1; **3B = dif_pts (F2)**;
indicador card (M2) / marks-list (F4) / notas-con-estado (N1) → 3C.

---

## 1. Objetivo

`dif_pts` recibe el contador de trabajadores por teclado (con voz, igual que
charla/chintegral), y el total de trabajadores de **Puerto Varas (HPV)** alimenta la
celda **N15** del RESUMEN (HH-capacitación). Cuando HPV no tiene conteo, N15 queda en
**0** (sin fallback) y el sistema de avisos del Excel marca la celda como **pendiente**.

### En alcance
- El módulo de conteo de trabajadores se muestra para dif_pts (es `documents_workers`).
- N15 (HPV) ← total de trabajadores crudo; **0 si no se contó** (sin fórmula de fallback).
- Aviso "pendiente" para dif_pts/HPV reutilizando el sistema actual (`_build_worker_warnings`).
- Arquitectura hospital-scoped y **extensible** para habilitar otras obras "sin más".
- Refactor del gate de UI a manejado-por-count_type.

### Fuera de alcance (explícito)
- **OCR de dif_pts (B3):** no detecta cantidad en ninguna pasada → es Track A (refinamiento
  OCR data-first), NO este incremento. El conteo de documentos de dif_pts se ajusta manual /
  por filename como hoy.
- **Highlight de la lista de marcas (F4):** → Incr 3C.
- **Hint "no va al Excel" en obras ≠ HPV:** diferido (el visor queda uniforme).
- **Subtotales (F5):** descartado en el triage.
- **Cambios en HLL/HLU/HRB fila 15:** intactas (mantienen su fórmula `col×0.5`).

---

## 2. Decisiones (cerradas con Daniel)

| # | Decisión | Valor |
|---|----------|-------|
| D1 | Valor de N15 cuando HPV tiene conteo | **Total de trabajadores crudo** (headcount), sin factor. |
| D2 | N15 cuando HPV NO tiene conteo | **0** (sin fallback). La fórmula `=M15*0.5` se elimina de N15. |
| D3 | Voz en dif_pts | **Con voz** (heredada de `documents_workers`; cero trabajo extra). |
| D4 | Aviso de pendiente | **Sí**, vía `_build_worker_warnings`, acotado a las obras del set (hoy HPV). |
| D5 | Punto verde de dif_pts | **Sin cambio** — sigue basado en procedencia de documentos (como charla/chintegral). |
| D6 | Obras que reciben el conteo a Excel | **Hoy solo HPV.** Las otras 3 mantienen `col×0.5`. Set extensible. |

**Razón de D2 (sin fallback):** la fórmula `docs×0.5` es un número fabricado que (a) puede estar
lejos del real, (b) hace que la celda *se vea poblada* y le resta fuerza al aviso de D4, y (c) es
la excepción rara — el resto de las celdas de conteo (checks, charla/chintegral) quedan en 0/blanco
si no se contaron. **Costo asumido:** el aviso de D4 pasa a ser *load-bearing* — si se ignora y no
se cuenta, el RESUMEN sale con N15 = 0 en capacitación de HPV (correcto: 0 es honesto).

---

## 3. Contexto del código (estado actual, verbatim)

### 3.1 count_type ya asignado
`dif_pts` ya es `documents_workers` en ambos lados (desde Incr 1A) — **no se toca**:
- Backend: `core/scanners/patterns.py::COUNT_TYPE_BY_SIGLA["dif_pts"] = "documents_workers"`.
- Frontend: `frontend/src/lib/sigla-info.js::SIGLA_COUNT_TYPE.dif_pts = "documents_workers"`.

### 3.2 Layout del Excel (de `data/templates/build_template_v1.py`)
- `dif_pts` = **fila 15**.
- Columna *cantidad* por hospital: `HLL=G, HLU=I, HRB=K, HPV=M`.
- Columna *HH* por hospital: `HLL=H, HLU=J, HRB=L, HPV=N`.
- ⇒ **N15 = celda HH de HPV en la fila de dif_pts.** `M15 = HPV_dif_pts_count` (cantidad de documentos).

Estado **actual** de las celdas HH de la fila 15 en el template (fórmulas):
```
H15 = =G15*0.5    J15 = =I15*0.5    L15 = =K15*0.5    N15 = =M15*0.5
```
(HH-capacitación estimada como documentos × 0.5.)

Rangos con nombre existentes de la fila 15 (cantidad de documentos, **se conservan**):
```
HLL_dif_pts_count → $G$15   HLU_dif_pts_count → $I$15
HRB_dif_pts_count → $K$15   HPV_dif_pts_count → $M$15
```

### 3.3 Camino actual de los valores de trabajadores al Excel (`api/routes/output.py`)
```python
WORKER_PURPOSE: dict[str, str] = {"charla": "chgen", "chintegral": "chintegral"}
```
`_build_worker_values` emite `{HOSP}_workers_{purpose} = compute_worker_count(cell, present)`
para **todas** las obras de charla/chintegral; el rango con nombre del template decide en qué celda
cae (filas 29/30, con fórmula `×0.25`/`×0.5` en la fila de la sigla). `_build_worker_warnings`
marca incompleto cuando la celda tiene `per_file` y `worker_status != "terminado"`.

> **Insight clave:** la emisión en Python es *uniforme* (`compute_worker_count` = total crudo). El
> factor `×0.25/×0.5` y la fila de destino son detalles del **template** (los define el rango con
> nombre), no de Python. Para dif_pts el rango apunta a N15 **sin** fórmula multiplicadora → N15 = total crudo.

### 3.4 Gate actual del módulo en el detalle (`frontend/src/components/DetailPanel.jsx:441`)
```jsx
{(countType === "checks" || sigla === "charla" || sigla === "chintegral") && (
  <WorkerCountModule hospital={hospital} sigla={sigla} cell={cell} countType={countType} />
```
`WorkerCountModule` (inline en `DetailPanel.jsx:146`) ya acepta `countType` y deriva solo la **etiqueta
de unidad** ("trabajadores"). La **voz** se decide más abajo, en `WorkerCountViewer.jsx` (~líneas 115-122:
`isWorkersMode = countTypeFor(sigla) === "documents_workers"`, `enabled: !micPaused && isWorkersMode`) →
como dif_pts ya es `documents_workers`, el visor lo trata como modo-trabajadores con voz activa y el toggle
de micrófono visible, **sin cambio en `WorkerCountViewer`**. Los endpoints de conteo de trabajadores
(`patch_worker_count`, `scan_one_file`) son **genéricos por sigla** (ya funcionaron para maquinaria) →
dif_pts pasa por el mismo camino sin allowlist.

---

## 4. Arquitectura

### 4.1 Backend — `api/routes/output.py`

Constante hospital-scoped (fuente única, con el procedimiento de habilitación documentado):

```python
# dif_pts: el total de trabajadores va a la celda HH de su propia fila (fila 15),
# por hospital. HOY solo HPV (→ N15). Para HABILITAR otra obra "sin más":
#   1. añadirla a este set,
#   2. crear el rango con nombre {HOSP}_workers_difpts → {col_HH}15 en el template,
#   3. limpiar la fórmula =col*0.5 de esa celda HH.
# Las obras NO incluidas conservan su estimación docs×0.5 intacta.
DIFPTS_WORKER_HOSPITALS: frozenset[str] = frozenset({"HPV"})
```

**`_build_worker_values`** — tras el bucle charla/chintegral, agregar:
```python
for hosp in DIFPTS_WORKER_HOSPITALS:
    cell = state.get("cells", {}).get(hosp, {}).get("dif_pts")
    if cell is None:
        continue  # no hay celda dif_pts para esa obra → N15 queda en 0 del template
    folder = _find_category_folder(month_root / hosp, "dif_pts")
    present = set(cell_page_counts(folder)) if folder.exists() else None
    out[f"{hosp}_workers_difpts"] = compute_worker_count(cell, present)
```
- **Siempre emite** (0 si no hay marcas) — D2: sin fallback, sin condicional "solo si hay marcas".
- ⚠️ **Divergencia deliberada vs charla/chintegral:** el bucle existente de `_build_worker_values`
  *salta* una celda cuando no tiene `worker_marks` ni `worker_status` ("nunca se contó → no emitir;
  el template queda en blanco", líneas 138-139). El bucle de dif_pts **omite ese guard a propósito**
  (D2 exige escribir un 0 explícito). NO armonizar los dos bucles — el de charla/chintegral se deja
  intacto con su skip; el de dif_pts siempre emite.
- `present` = archivos presentes en la carpeta (mismo filtro canónico del fix F1; `None` si la
  carpeta no existe → `compute_worker_count` cae a su filtro legacy por `per_file`).

**`_build_worker_warnings`** — agregar dif_pts acotado al set:
```python
for hosp in DIFPTS_WORKER_HOSPITALS:
    cell = state.get("cells", {}).get(hosp, {}).get("dif_pts")
    if cell and cell.get("per_file") and cell.get("worker_status") != "terminado":
        out.append({"hospital": hosp, "sigla": "dif_pts"})
```
(charla/chintegral siguen iterando sobre `WORKER_PURPOSE` sin cambio.)

> El historial (`historical_counts`) y `_build_cell_values` NO cambian: el número **de celda** de
> dif_pts es su conteo de documentos (`count_type="documents_workers"` cae a la cascada de documentos
> en `compute_cell_count`). El total de trabajadores es un valor *aparte* que solo alimenta N15.

### 4.2 Template — `data/templates/RESUMEN_template_v1.xlsx`

Artefacto **autoritativo** (hand-patched). Editar vía openpyxl preservando todo lo demás:
1. **Limpiar la fórmula de N15** (`=M15*0.5` → `0`). La celda pasa a ser un valor que el writer
   sobrescribe vía el rango con nombre cada generación.
2. **Añadir** rango con nombre `HPV_workers_difpts → 'Cump. Programa Prevención'!$N$15`.
3. **NO tocar** H15/J15/L15 (conservan `=col*0.5`) ni los 4 `*_dif_pts_count` ni los 8
   `*_workers_{chgen,chintegral}`.

Protocolo: respaldo fechado del `.xlsx` antes de editar; verificación por render LibreOffice→PDF a
ruta temporal (nunca sobre el output real de Daniel).

**`build_template_v1.py` (recipe, no autoritativo)** — sincronizar como best-effort:
- Quitar N15 del bucle que setea `=col*0.5` para la fila 15 (o limpiarla explícitamente a 0).
- Añadir el rango `HPV_workers_difpts → $N$15`.
- `verify()`: ahora **9** rangos de trabajadores (8 + `HPV_workers_difpts`); aserción de que N15 NO
  es la fórmula `=M15*0.5` y que H15/J15/L15 SÍ la conservan.
- Documentar en el docstring/recipe los 3 pasos de "habilitar otra obra".

### 4.3 Frontend — `frontend/src/components/DetailPanel.jsx`

Refactor del gate (línea ~441) a manejado-por-count_type:
```jsx
{(countType === "checks" || countType === "documents_workers") && (
  <WorkerCountModule hospital={hospital} sigla={sigla} cell={cell} countType={countType} />
```
- Incluye dif_pts de forma natural (es `documents_workers`); elimina el comentario "NO dif_pts" de 3A.
- Los **controles de documento** ya se muestran para `documents_workers` (solo se ocultan en `checks`),
  así que dif_pts queda con **ambos**: controles de documento + módulo de trabajadores — igual que
  charla/chintegral.
- **Voz:** heredada (`documents_workers` → `isWorkersMode` → voz activa). Sin cambio en `WorkerCountViewer`.

Sin cambios en el resto de consumidores de count_type (CategoryRow/MonthOverview/HospitalDetail/
scanCost/CategoryBulkActions/session.js): dif_pts ya fluía como `documents_workers` desde 1A.

---

## 5. Flujo de datos (N15)

```
Visor de teclado (dif_pts, HPV) → worker_marks
        │  PATCH /cells/HPV/dif_pts/worker-count
        ▼
compute_worker_count(cell, present_files)   ← total crudo, filtrado por archivos presentes (F1)
        │  al generar el RESUMEN
        ▼
_build_worker_values → out["HPV_workers_difpts"] = total   (0 si no hay marcas)
        │
        ▼
generate_resumen escribe el rango con nombre → N15 = total   (sobrescribe el 0 del template)
```
- Contado + `terminado` → N15 = total, sin aviso.
- Con PDFs y sin `terminado` → N15 = 0 (o total parcial) **+ aviso** en `worker_warnings`.
- Sin celda/sin PDFs → N15 = 0, sin aviso.

---

## 6. Casos borde / manejo de errores

- **HPV sin carpeta dif_pts:** `folder.exists()` falso → `present=None` → `compute_worker_count` usa
  filtro legacy; si no hay marcas → 0. N15 = 0.
- **Marcas en un PDF presente pero no en `per_file`:** cubierto por el filtro F1 (archivos presentes),
  igual que charla/chintegral/maquinaria en 3A.
- **Alguien marca `terminado` sin contar:** `worker_marks` vacío → total 0 → N15 = 0, sin aviso
  (aserción del usuario respetada; 0 honesto).
- **Otra obra (≠ HPV) con conteo de trabajadores en dif_pts:** se guarda (visor habilitado) pero
  **no** se emite a Excel; su H/J/L15 conserva `col×0.5`. Sin aviso.
- **Regeneración idempotente:** N15 se sobrescribe con el mismo valor; sin deriva.

---

## 7. Plan de pruebas

### Backend (pytest, fixtures reales — sin mock de DB)
- `_build_worker_values` emite `HPV_workers_difpts` = total crudo cuando HPV/dif_pts tiene marcas.
- Emite **0** cuando HPV/dif_pts existe pero no tiene marcas (sin fallback).
- **No** emite `{HLL,HLU,HRB}_workers_difpts` aunque esas obras tengan marcas en dif_pts.
- `_build_worker_warnings` incluye `{hospital: "HPV", sigla: "dif_pts"}` con PDFs y sin `terminado`;
  **no** lo incluye cuando `terminado`; **no** incluye otras obras.
- Filtro F1: marcas en un PDF presente-pero-no-en-`per_file` cuentan (paridad con 3A).
- Historial/`_build_cell_values` de dif_pts = conteo de documentos (no regresa).

### Template (pytest)
- Tras el build/parche: existe `HPV_workers_difpts → $N$15`; total de rangos `_workers_` = 9.
- N15 **no** es `=M15*0.5`; H15/J15/L15 **sí** conservan `=col*0.5`.
- Los 4 `*_dif_pts_count` y los 8 `*_workers_{chgen,chintegral}` intactos.
- Verificación por render (LibreOffice headless → PDF temporal).

### Frontend (vitest)
- DetailPanel: módulo de conteo se renderiza para dif_pts (`documents_workers`).
- dif_pts conserva los controles de documento (no se ocultan como en `checks`).
- maquinaria (`checks`) sigue ocultando los controles de documento.
- Una sigla `documents` pura no muestra el módulo.
- (Regresión) dif_pts se comporta como charla/chintegral en `computeCellCount`/`isCellReady`.

### Smoke conducido (chrome-devtools, data-safe)
Respaldar `data/overseer.db`; operar sobre un mes **pasado** (ABRIL); restaurar por hash. Verificar:
abrir HPV/dif_pts → aparece el módulo de trabajadores (con voz) + controles de documento; contar y
marcar terminado; generar RESUMEN y comprobar N15 = total; sin contar → N15 = 0 + aviso "pendiente".

---

## 8. Versión / hooks / convenciones

- **Sin bump de versión:** no se tocan `core/{pipeline,ocr,inference,image}.py` ni `vlm/*`.
- Archivos tocados: `api/routes/output.py`, `data/templates/RESUMEN_template_v1.xlsx`,
  `data/templates/build_template_v1.py`, `frontend/src/components/DetailPanel.jsx`, tests.
- Guard de deliverables: el `.xlsx` dispara el hook de respaldo (ask) — confirmar la sobrescritura
  tras dejar el `.bak` fechado.
- `ruff check .` = 0; vitest verde; commits `type(scope): message`; trailer Co-Authored-By verbatim.

---

## 9. Futuro (anotado, fuera de 3B)

- **Habilitar otra obra:** los 3 pasos de §4.1/§4.2 (set + rango + limpiar fórmula). Documentados en
  el código para que sea mecánico cuando Daniel lo pida.
- **OCR de dif_pts (B3):** Track A (refinamiento data-first por sigla).
- **Hint en obras ≠ HPV** ("este conteo no va al Excel"): revisitar si genera confusión.
