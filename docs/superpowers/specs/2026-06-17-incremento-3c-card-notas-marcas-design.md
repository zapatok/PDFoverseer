# Incremento 3C — indicador de trabajadores (card) + notas con estado + lista de marcas

**Fecha:** 2026-06-17
**Rama:** `po_overhaul` (rama única; trabajar directo, push al cierre)
**Predecesor:** Incr 3B (`incremento-3b`) — dif_pts workers + N15.
**Corte del Incr 3 (triage 2026-06-09, grupos M/N/F):** cierra la serie 3 con tres remates de UX:
**M2** (indicador en card del hospital), **N1** (notas del detalle con estado), **F4** (lista de MARCAS).
Quedan fuera de la serie: **Incr J** (reorganización/manifiesto) — sesión propia.

---

## 1. Objetivo

Tres componentes independientes, todos pequeños:

- **M2** — un indicador agregado del **estado de conteo de trabajadores** del hospital (pendiente / en
  proceso / listo) en su card del home.
- **N1** — **notas por celda con estado** (`por_resolver` / `resuelto`), **desacopladas** del ajuste manual;
  una nota `por_resolver` **fuerza el punto a ámbar** (no bloquea acciones). Incluye migración de las notas
  viejas (`override_note`).
- **F4** — en la lista de **MARCAS** del visor de conteo, **resaltar la fila de la página actual** y hacer
  **auto-scroll** para que esa fila quede siempre visible.

### En alcance
M2 (agregado tri-estado), N1 (campo nota+estado + gate del punto verde + migración + UI reubicada),
F4 (resaltado + auto-scroll). Todo dentro de PDFoverseer.

### Fuera de alcance (explícito)
- **Bloqueo duro** de la nota (deshabilitar "Terminé"/ignorar acciones) — se eligió "solo ámbar".
- Acoplar M2 a las notas (M2 mira solo `worker_status`).
- Incr J / manifiesto; cualquier cambio de conteo, Excel o histórico.
- Subtotales, badges de presencia (multiplayer), flavor nuevo.

---

## 2. Decisiones (cerradas con Daniel)

| # | Decisión | Valor |
|---|----------|-------|
| D1 | Forma del indicador M2 | **Agregado tri-estado** (un chip por hospital), no mini-dots por celda. |
| D2 | Fuerza del gate de la nota `por_resolver` | **Solo fuerza ámbar** (no deshabilita acciones). Uniforme para todo count_type. |
| D3 | Significado de "mostrar siempre la última página" (F4) | **Auto-scroll a la fila actual** (no fila fija de última página). |
| D4 | Estado de una nota nueva | Nace **`por_resolver`** (flag por defecto). |
| D5 | Notas legacy (`override_note`) | **Migración una sola vez** (override_note → `note`, estado `resuelto`, se elimina `override_note`). Sin shim de lectura. |
| D6 | Ubicación de la sección NOTA en el DetailPanel | **Después de "AJUSTE MANUAL"** (donde vive hoy la nota del override). |
| D7 | M2 vs notas | M2 mira solo `worker_status`. El efecto de la nota se ve en los **dots de documentos** (note-aware vía `dotVariantFor`). |

---

## 3. Contexto del código (estado actual, verbatim)

### 3.1 Punto verde — `frontend/src/lib/cell-status.js`
```js
export function isCellReady(cell, countType = "documents") {
  if (!!cell?.confirmed || hasOverride(cell)) return true;
  if (countType === "checks") return cell?.worker_status === "terminado";
  return cell?.all_reliable ?? allFilesReliable(cell);
}
export function dotVariantFor(cell, { isScanning = false, countType = "documents" } = {}) {
  if (isScanning) return "state-scanning";
  if (cell?.errors?.length > 0) return "state-error";
  if (!cell) return "neutral";
  return isCellReady(cell, countType) ? "confidence-high" : "confidence-low";
}
```
El gate de la nota debe ir **como primera línea** de `isCellReady` (antes de `confirmed`/override).

### 3.2 Punto verde backend — `api/routes/sessions.py::compute_settled`
`compute_settled(cell, folder, pages=None, count_type=None)` — rama checks = `worker_status=="terminado"`;
resto = procedencia (R1/RN/Manual) por archivo. `refresh_all_reliable(...)` persiste `all_reliable` vía
`compute_settled`. El gate de la nota va **como primera condición** (antes de la rama checks).

### 3.3 Notas hoy — acopladas al override
- `frontend/src/components/OverridePanel.jsx`: una `<textarea>` (estado `note`) que se guarda **junto** al
  override vía `saveOverride(session, hospital, sigla, value, note)`; la textarea está **disabled** fuera de
  modo Manual → hoy **no existe una nota sin override**.
- Persistencia: el campo de la celda es `override_note` (string|null). `apply_filename_result` "never touches
  override_note".

### 3.4 Migración lazy ya existente — `api/state.py` + `core/state/migrations.py`
`SessionManager._load_and_migrate(session_id)` carga el `state_json`, corre `migrate_state_v1_to_v2(state)` →
`(state, changed)`, y **persiste de vuelta solo si cambió** (idempotente, por sesión, en cada load/setter).
`core/state/migrations.py` ya tiene `migrate_cell_v1_to_v2` + `migrate_state_v1_to_v2`. La migración de N1
**reusa esta misma costura** (paso v2→v3), sin hook de arranque ni script.

### 3.5 Almacenamiento
Las celdas viven como **JSON** en `sessions.state_json` (TEXT). Agregar `note`/`note_status` = llaves nuevas
del dict, **sin migración de esquema**. (Verificado: 4 sesiones en `overseer.db`; **2 celdas** con
`override_note` real, ambas en MAYO finalizado — HLL/dif_pts y HPV/art.)

### 3.6 Card del hospital — `frontend/src/components/HospitalCard.jsx`
Muestra una fila de `Dot`s por sigla (estado de documentos vía `dotVariantFor`). M2 agrega un **Badge**
agregado de trabajadores, separado de esa fila.

### 3.7 Lista de marcas — `frontend/src/components/WorkerHud.jsx` (líneas ~59-75)
Renderiza `pageMarks` (las marcas del archivo actual, ordenadas por página) como `<li>`. F4 resalta la fila
`m.page === pageInFile` y hace scroll a ella. `pageInFile` ya es una prop del HUD.

---

## 4. Arquitectura

### 4.1 N1 — nota por celda con estado

**Modelo de datos (cell JSON):** dos campos nuevos
- `note: string | null` — texto de la nota.
- `note_status: "por_resolver" | "resuelto" | null` — `null` cuando no hay nota.
Invariante: `note_status` no-nulo ⟺ `note` con texto. Una nota nueva nace `por_resolver` (D4).

**Migración (D5) — `core/state/migrations.py`, paso v2→v3:**
```python
def migrate_cell_v2_to_v3(cell: dict) -> dict:
    """override_note (acoplado al override) → note/note_status desacoplados. Idempotente."""
    if "note" not in cell:
        legacy = cell.get("override_note")
        cell["note"] = legacy or None
        cell["note_status"] = "resuelto" if legacy else None  # legacy = no-bloqueante
    cell.pop("override_note", None)
    return cell
```
+ `migrate_state_v2_to_v3(state) -> (state, changed)` (changed si algún cell tenía `override_note` o le faltaba
`note`). `_load_and_migrate` **encadena** v1→v2 y v2→v3 (corre ambas; persiste si cualquiera cambió). Las 2 notas
de MAYO se migran solas en el próximo load, como `resuelto` (no vuelven ámbar a MAYO).

**Gate del punto verde (D2 — solo ámbar):**
- Frontend `isCellReady` (primera línea): `if (cell?.note_status === "por_resolver") return false;`
  → vía `dotVariantFor`, el dot queda `confidence-low` (ámbar) aunque la celda esté confirmed/override/
  terminado/all_reliable.
- Backend `compute_settled` (primera condición): `if cell.get("note_status") == "por_resolver": return False`
  → `all_reliable` queda consistente.
- **No deshabilita acciones**: contar, marcar "Terminé", override siguen funcionando; el ámbar es el recordatorio.

**Persistencia + endpoint:**
- `SessionManager.set_note(session_id, hospital, sigla, text, status)` (api/state.py) — escribe `note`/
  `note_status` en la celda (vía `_load_and_migrate` + `update_session_state`). Normaliza: texto vacío →
  `note=None, note_status=None`.
- `PATCH /api/sessions/{id}/cells/{hospital}/{sigla}/note` body `{text: str|null, status: "por_resolver"|"resuelto"}`
  → `set_note` + `refresh_all_reliable(...)` → devuelve la celda. Valida `status` ∈ los dos valores.

**Desacople del override (barrido COMPLETO de consumidores):** la nota deja de viajar por el path del override.
- **`saveOverride` pierde el parámetro `note`** (store `session.js`); el endpoint de override + `apply_user_override`
  dejan de aceptar/escribir cualquier nota. La nota vive **solo** por `saveNote`/`NotePanel`.
- **Todos los callers de `saveOverride` se actualizan a NO pasar nota** (hoy varios pasan `cell?.override_note ?? null`):
  `OverridePanel.jsx` (pierde la textarea y su estado `note`; queda el input numérico + nota de validación),
  **`CategoryRow.jsx`** (~línea 36, commit de inline-edit), **`FileList.jsx`** (~línea 101), `DetailPanel.jsx`
  (~línea 259, ya pasa `null`). **Verificación de plan:** `git grep saveOverride` para no dejar ningún caller con nota.
- **Limpiar/editar el override NO toca la nota** (son independientes): borrar el override deja la nota tal cual.
- Nuevo `frontend/src/components/NotePanel.jsx`: textarea (autosave debounced vía `saveNote`) + control de estado:
  - `por_resolver`: editable; chip/indicador "Por resolver" (ámbar); botón **"Marcar resuelta"**.
  - `resuelto`: textarea **read-only**; chip "Resuelta" (jade); botón **"Reabrir"** (→ `por_resolver`, reabre
    edición, re-bloquea). Reversible (D-N1).
  - sin texto: placeholder; al escribir, nace `por_resolver`.
- `DetailPanel.jsx` renderiza `<NotePanel>` en una sección **"NOTA"** justo **después de "AJUSTE MANUAL"** (D6),
  siempre visible (no gateada por modo ni count_type). Store: acción `saveNote(session, hosp, sigla, text, status)`
  que pega al endpoint y mergea la celda devuelta.

### 4.2 M2 — indicador de trabajadores en la card

**Helper puro — `frontend/src/lib/cell-status.js`:**
```js
// Estado agregado de conteo de trabajadores de un hospital sobre sus celdas worker
// (count_type ∈ {documents_workers, checks} = charla/chintegral/dif_pts/maquinaria).
// "relevante" = la celda tiene archivos. Devuelve null si no hay relevantes (sin chip).
export function hospitalWorkerStatus(cells) { /* "listo" | "en_proceso" | "pendiente" | null */ }
```
Reglas (D1): **listo** = todas las relevantes en `worker_status==="terminado"`; **pendiente** = ninguna
empezada (sin `worker_status` ni marcas); **en_proceso** = el resto; **null** = ninguna relevante.
- "relevante" = la celda tiene archivos. Señal de presencia en la card: `per_file` no vacío (fallback: conteo
  de documentos > 0). La card recibe `cells` del `session` (GET de estado completo → incluye `worker_status`/
  `worker_marks`/`per_file`; los handlers WS hacen spread del cell existente, así que esos campos sobreviven).
  **Verificación de plan:** confirmar que ningún handler del store reemplaza el cell entero perdiendo esos campos.
- "empezada" = `worker_status` presente (en_progreso/terminado) **o** `worker_marks` no vacío.

**UI — `HospitalCard.jsx`:** un `Badge` (primitive) junto al nombre del hospital, tono por estado
(jade=listo, amber=en proceso, neutral=pendiente), texto corto ("Trabajadores: listos/en proceso/pendientes").
No se renderiza si `hospitalWorkerStatus` es `null`. Reusa el primitive (feedback_chip_consistency).

### 4.3 F4 — lista de MARCAS: resaltado + auto-scroll

`WorkerHud.jsx`: en el `.map` de `pageMarks`, marcar la `<li>` con `m.page === pageInFile` con un fondo/borde
token `po-*` (variante "actual"). `ref` en esa fila + `useEffect([pageInFile])` que hace `scrollIntoView({block:
"nearest"})` para mantenerla visible al avanzar. Si la página actual **no tiene marca**, no se fabrica fila (no
hay resaltado; el scroll cae en la última fila existente o no actúa). Sin fila fija de última página (D3).

---

## 5. Flujo de datos (gate de la nota)

```
NotePanel (texto/estado) ──PATCH …/note──> set_note → cell.note/note_status
        │                                      │
        │                                      └─ refresh_all_reliable → compute_settled
        │                                            (note_status=="por_resolver" → False)
        ▼ (respuesta: celda mergeada en el store)
dotVariantFor(cell) → isCellReady (1ª línea: note_status por_resolver → false) → ámbar
```
- Nota `por_resolver` → dot ámbar (front en vivo + back consistente). Acciones siguen habilitadas.
- "Marcar resuelta" → `resuelto` → read-only; el dot vuelve a su estado por procedencia/terminado.
- "Reabrir" → `por_resolver` → editable + ámbar de nuevo.

---

## 6. Casos borde / manejo de errores

- **Nota vacía:** `note=None, note_status=None` → sin gate, sin chip.
- **`resuelto` con texto borrado a vacío:** se normaliza a `None/None` (deja de existir la nota).
- **Migración idempotente:** corre solo si el cell tiene `override_note` o le falta `note`; segura en sesión
  finalizada (solo reubica el campo; no toca conteos/Excel/histórico). Las 2 notas MAYO → `resuelto`.
- **M2 sin celdas worker con archivos:** `hospitalWorkerStatus` = `null` → sin chip (no "pendiente" falso).
- **M2 con dif_pts en obra ≠ HPV:** cuenta igual para el agregado (M2 es estado de conteo, no del mapeo a Excel).
- **F4 página actual sin marca:** no hay fila que resaltar; no se fabrica.
- **Override sin nota (tras desacople):** el override funciona igual; la nota es independiente.

---

## 7. Plan de pruebas

### Backend (pytest, fixtures reales — sin mock de DB)
- `migrate_cell_v2_to_v3` / `migrate_state_v2_to_v3`: `override_note` con texto → `note` + `note_status="resuelto"`,
  `override_note` eliminado; **cell con `override_note=None` (o sin él) → `note=None` y `note_status=None`** (NO
  "resuelto"); idempotente (2ª pasada `changed=False`). Encadenado en `_load_and_migrate` (correr v1→v2 y v2→v3;
  persistir si cualquiera cambió).
- `compute_settled`: `note_status="por_resolver"` → `False` aunque procedencia/terminado serían `True`;
  `resuelto`/`None` → no afecta.
- Endpoint `PATCH …/note`: persiste texto+estado, normaliza vacío, valida `status`, refresca `all_reliable`,
  devuelve la celda; 404 sigla/sesión desconocida.

### Frontend (vitest)
- `isCellReady`/`dotVariantFor`: `note_status="por_resolver"` → no-listo/ámbar aun con `confirmed`/override/
  `all_reliable`/`worker_status=terminado`; `resuelto`/`null` → comportamiento previo intacto.
- `hospitalWorkerStatus`: listo / en_proceso / pendiente / null (todos los casos, incl. dif_pts y maquinaria;
  obra sin celdas worker → null).
- (F4) predicado de "fila actual" si se extrae; el auto-scroll se verifica en smoke (sin jsdom).

### Smoke conducido (chrome-devtools, data-safe)
Respaldar `overseer.db`; operar en un mes **pasado** (ABRIL); restaurar por hash; nunca MAYO. Verificar:
nota `por_resolver` en una celda verde → pasa a ámbar; "Marcar resuelta" → vuelve a verde; "Reabrir" → ámbar;
la nota vive en su sección tras AJUSTE MANUAL y es editable sin override. M2: chip del hospital refleja el
estado de conteo de trabajadores. F4: al avanzar páginas en el visor, la fila actual se resalta y queda visible.

---

## 8. Versión / hooks / convenciones

- **Sin bump de versión:** no se tocan `core/{pipeline,ocr,inference,image}.py` ni `vlm/*`.
- Archivos: `core/state/migrations.py` (v2→v3), `api/state.py` (`set_note` + encadenar migración),
  `api/routes/sessions.py` (endpoint nota + gate en `compute_settled`), `frontend/src/lib/cell-status.js`
  (gate nota en `isCellReady` + `hospitalWorkerStatus`), `frontend/src/components/{NotePanel(new),DetailPanel,
  OverridePanel,HospitalCard,WorkerHud}.jsx`, `frontend/src/store/session.js` (`saveNote`, limpiar `note` de
  `saveOverride`), tests.
- `ruff check .` = 0; vitest verde; commits `type(scope): message`; trailer Co-Authored-By verbatim;
  tokens `po-*` (nunca el modificador `/opacity` sobre tokens po-* CSS-var).

---

## 9. Futuro (anotado, fuera de 3C)
- El gate de la nota es la **primera pieza** del "ciclo de vida / gate de celda" (grupo L del triage).
- **Incr J** (reorganización/manifiesto) — sesión propia.
