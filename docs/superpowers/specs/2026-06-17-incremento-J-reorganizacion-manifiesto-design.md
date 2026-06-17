# Incremento J — Reorganización vía manifiesto al paso 1

**Fecha:** 2026-06-17
**Estado:** Diseño aprobado (brainstorming), pendiente de plan
**Rama:** `po_overhaul`
**Alcance:** lado PDFoverseer + contrato del manifiesto + documento de handoff para el paso 1. La ejecución física de las operaciones (mover/extraer/rotar PDFs en disco) es trabajo del paso 1 (`A:\informe mensual`) y queda **fuera** de este incremento.

---

## 1. Objetivo

PDFoverseer permite al operador **marcar operaciones de reorganización** sobre los documentos de un mes — mover un archivo completo a otra celda, extraer un rango de páginas que es un documento colado, dividir un archivo en el lugar, o rotar — **llevando el conteo de documentos (y de trabajadores) de una celda a otra**. Esas operaciones:

1. **Corrigen el conteo del mes en el acto** (el Excel y el histórico reflejan la atribución correcta por celda — el total global se preserva).
2. Se **exportan como un manifiesto declarativo versionado** (JSON) que el paso 1 ejecuta físicamente en su 2ª tanda, entre contar (su Step 3) y totalizar a nombres de carpeta (su Step 4).

El manifiesto lleva **intención semántica** (sigla destino, empresa, preservar fecha, rotación), no nombres de archivo de destino: el paso 1 construye el nombre canónico con su propia convención.

### Por qué importa (contexto de Daniel)
Ordenar bien los documentos y contar los que corresponden a cada celda es de los mayores *drivers* de observaciones de la inspección fiscal. Hoy un documento colado en un compilado (p. ej. un ODI dentro de `art_crs.pdf`) se cuenta mal y, peor, queda archivado mal. Este incremento cierra ambas cosas: cuenta bien **ahora** y deja instrucciones para archivar bien **después**.

## 2. No-objetivos (YAGNI)

- **No** ejecutamos operaciones físicas sobre PDFs (ni copia, ni split real). El corpus es de solo lectura (ver `api/CLAUDE.md`). Eso lo hace el paso 1.
- **No** construimos un editor de PDF embebido. El visor solo *marca* rangos.
- **No** sincronizamos de vuelta el estado de aplicación del paso 1 hacia PDFoverseer por ningún canal en vivo (el `status` del manifiesto es informativo; ver §7).
- **No** versionamos `manifest_version` más allá de `1` en este incremento (un solo formato).
- **No** soportamos edición in-situ de una op más allá de borrar + recrear (v1).

## 3. Glosario

- **op (operación):** una instrucción de reorganización, miembro de una lista ordenada por sesión. Cuatro tipos (§4).
- **delta:** el ajuste de conteo que una op induce en una celda (origen `−`, destino `+`). El total global se preserva.
- **manifiesto:** el JSON declarativo versionado que agrupa todas las ops de un mes para entregárselo al paso 1 (§7).
- **celda:** un par `(hospital, sigla)`. 4 hospitales (HPV/HRB/HLU/HLL) × 18 siglas.

## 4. Modelo de operaciones

Cada op vive en `state["reorg_ops"]` (lista ordenada, top-level de la sesión — ver §6). Campos:

| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | `str` | `op_NNN` correlativo dentro de la sesión, estable. |
| `op_type` | `str` | uno de `move_file` / `extract_pages` / `split_in_place` / `rotate`. |
| `source` | `dict` | `{hospital, sigla, file, page_range?}`. `file` = nombre actual del PDF (cómo el paso 1 lo encuentra). `page_range` = `[inicio, fin]` (1-based, inclusivo) o ausente = archivo completo. |
| `dest` | `dict` | `{hospital, sigla}`. Cualquier celda. **Intención**, no filename. |
| `empresa` | `str \| null` | pista para el nombre canónico que arma el paso 1. Opcional. |
| `preserve_date` | `bool` | default `true`: conserva la fecha del documento original al renombrar. |
| `rotation_deg` | `int` | `0` / `90` / `180` / `270`. Default `0`. |
| `doc_count` | `int` | cuántos documentos viajan (ver tabla de conteo). |
| `worker_count` | `int` | cuántos trabajadores/chequeos viajan (0 si la celda no es de trabajadores). |
| `note` | `str \| null` | comentario libre del operador. |
| `status` | `str` | `pending` / `applied`. Informativo + lifecycle interno (§6/§7). Nace `pending`. |

### Tipos y su efecto en el conteo

| Tipo | Qué hace | `source.page_range` | Delta de conteo |
|------|----------|---------------------|-----------------|
| `move_file` | archivo completo F: `(hosp, sigla_orig)` → `(hosp, sigla_dst)`. **Reclasificar = mover a otra sigla.** | ausente | origen `−doc_count`, destino `+doc_count`. `doc_count` default = contribución actual de F a la celda (`per_file_overrides[F] \| per_file[F] \| 1`). |
| `extract_pages` | páginas X–Y de F → `(hosp, sigla_dst)` (el doc colado) | `[X, Y]` | origen `−doc_count`, destino `+doc_count`. `doc_count` default `1`, tope ≤ (Y−X+1). |
| `split_in_place` | partir F en N documentos dentro de la **misma** celda | opcional | sin cambio de conteo (`doc_count = 0`; informa al paso 1 que separe). |
| `rotate` | rotar F o páginas X–Y `rotation_deg°` | opcional | sin cambio de conteo (`doc_count = 0`). |

`worker_count` (celdas `documents_workers` / `checks`): para `move_file` = suma de `count` de las marcas del archivo F; para `extract_pages` = suma de las marcas en páginas X–Y; `0` en celdas `documents`.

### Contrato del request `POST /reorg/ops`
`doc_count` y `worker_count` son **opcionales** en el body. Si el cliente no los envía, el **servidor** resuelve el default leyendo el estado de la celda origen (`doc_count` = `per_file_overrides[F] | per_file[F] | 1` para `move_file`, `1` para `extract_pages`, `0` para split/rotate; `worker_count` = suma de marcas del archivo o del rango). El cliente puede enviarlos para sobrescribir (sujeto a las validaciones de abajo). Así el contrato del body es estable y el cálculo del default vive en un solo lugar (el servidor).

### Validaciones (al crear)
- `dest` ≠ `source` (mismo hospital+sigla) **salvo** `split_in_place` y `rotate` (que pueden quedarse en la celda).
- `extract_pages` requiere `page_range`; `move_file` lo prohíbe.
- `page_range`: `1 ≤ X ≤ Y ≤ páginas(F)` (usando `cell_page_counts(folder)[file]`).
- **No solapar rangos del mismo archivo:** un `extract_pages` cuyo `page_range` se solape con el de otra op `pending` sobre el **mismo** `source.file` se rechaza (400). Evita que el origen reste dos veces las mismas páginas (delta negativo / sub-conteo). La división de un archivo en varios documentos contiguos se modela con rangos **disjuntos**.
- `doc_count ≥ 0`; para `extract_pages`, `doc_count ≤ (Y−X+1)`; para `move_file`, `doc_count ≤ páginas(F)` (mismo tope ≤páginas del Incr 2).
- `rotation_deg ∈ {0, 90, 180, 270}`.
- `source.file` debe existir hoy en la carpeta de la celda origen (si no, 400).
- sigla y hospital de origen y destino válidos (si no, 404).

## 5. Integración con el conteo (capa aditiva)

`state["reorg_ops"]` es la **fuente única**. De ahí se derivan dos cachés por celda, recomputados (nunca editados a mano):

- `cell["reorg_doc_delta"]: int` — suma de deltas de documentos que entran (`+`) y salen (`−`) de la celda por ops `pending`.
- `cell["reorg_worker_delta"]: int` — idem para trabajadores/chequeos.

### `compute_cell_count` (capa aditiva, dentro de la fuente única)
`core/cell_count.py::compute_cell_count` se reestructura así: el cuerpo actual (las **tres** rutas de retorno — `user_override`, `checks`→`_sum_marks`, `per_file`/fallback) se extrae **verbatim** a un helper privado nuevo `_base_count(cell, count_type, present_files)`. `compute_cell_count` queda como un único punto de retorno que hornea el delta **después** de la cascada:

```python
def compute_cell_count(cell, count_type="documents", present_files=None):
    base = _base_count(cell, count_type, present_files)   # cuerpo actual, sin cambios
    return base + (cell.get("reorg_doc_delta") or 0)
```

El delta `reorg_doc_delta` es **aditivo uniforme sobre todos los `count_type`, incluido `checks`** (no hay rama especial): respeta `user_override` como base y, como `split_in_place`/`rotate` llevan `doc_count=0`, en la práctica solo `move_file`/`extract_pages` mueven el número. El espejo JS `frontend/src/lib/cellCount.js::computeCellCount` se reestructura igual (helper interno + `+ (cell.reorg_doc_delta ?? 0)` al final). La paridad cross-language se valida con casos nuevos en `tests/fixtures/cell_count_cases.json` (+ `tests/test_cell_count_cross_language.py`).

**Cómo fluye a cada consumidor (verificado contra el código):**
- **UI:** lee `computeCellCount` (JS) → delta incluido.
- **Excel (documentos):** `core/excel/output.py::_build_cell_values` → `core/excel/writer.py::resolve_cell_value` → `compute_cell_count`. El delta fluye **transitivamente** vía `resolve_cell_value`; ese llamador no se toca.
- **Excel (trabajadores):** `_build_worker_values` → `compute_worker_count` (ver "Trabajadores" abajo). Fluye en cuanto se parchea `compute_worker_count`; `_build_worker_values` no se toca.
- **Histórico:** el UPSERT deriva de `compute_cell_count` → delta incluido.

### Trabajadores
`compute_worker_count` (en `api/state.py` — ubicación no obvia: es cómputo puro pero vive en `api/`; el total de trabajadores alimenta el visor y N15 vía Incr 3B) se parchea para sumar `+ (cell.get("reorg_worker_delta") or 0)`. Es el único cambio del path de trabajadores; su llamador indirecto en Excel (`_build_worker_values`) queda correcto sin tocarse. El delta de trabajadores es un **número**, no marcas reubicadas: las marcas reales se quedan con el archivo físico hasta que el paso 1 lo mueva.

## 6. Persistencia y ciclo de vida

### Persistencia
- `state["reorg_ops"]`: lista top-level, leída con `state.get("reorg_ops", [])`. **Sin migración de esquema SQL** (el estado es JSON en `sessions.state_json`; clave nueva con default vacío, igual que `count_type` en su día).
- Incluida en el `GET /api/sessions/{id}` → el frontend la lee del estado (no hace falta endpoint GET aparte).
- `reorg_doc_delta` / `reorg_worker_delta`: cachés por celda, recomputados desde `reorg_ops`.

### `refresh_reorg_deltas` (patrón de caché recomputado, como `refresh_all_reliable`)
Función nueva en `api/routes/sessions.py`. **Diferencia de alcance:** `refresh_all_reliable` es **por-celda** (recibe `hospital`/`sigla`/`folder`); `refresh_reorg_deltas` es **a nivel de sesión** — barre todas las celdas, pone los deltas en 0 y los recomputa desde `reorg_ops`. Comparte el patrón (caché derivado de la fuente, recomputado tras mutaciones), no la firma.

```python
def refresh_reorg_deltas(mgr, session_id, *, check_applied=False):
    # 1. (solo si check_applied) marca status="applied" toda op pending cuyo
    #    source.file YA NO esté presente en su carpeta origen → su delta deja de contar.
    # 2. pone reorg_doc_delta = reorg_worker_delta = 0 en TODAS las celdas.
    # 3. por cada op pending: origen -= doc_count/worker_count; destino += ...
    # 4. persiste.
```

Se llama:
- tras **crear/borrar** una op → `check_applied=False` (los archivos no se movieron; solo recomputa).
- al **terminar un escaneo pase 1** (`POST /scan`) → `check_applied=True` (es el único momento — y el único endpoint — en que un archivo pudo haberse movido físicamente entre sesiones). **Call site concreto:** justo después del bucle `for (hosp, sigla), r in results.items(): mgr.apply_cell_result(...)` en el handler de `POST /scan`, antes del `return`. La verificación de presencia usa el sistema de archivos (no el estado), así que el orden relativo al bucle no afecta el resultado; se coloca después por claridad.

### Ciclo de vida — Opción 1 (descarte por evidencia)
El manifiesto se exporta **una vez al cierre del mes**. Los deltas corrigen el conteo del mes **antes** de que el paso 1 mueva físicamente.

**Footgun (doble conteo):** si se re-escanea el mes *después* de que el paso 1 movió los archivos, el archivo ya estaría físicamente en su celda nueva (cuenta `+1` por `per_file`) **y** el delta seguiría sumando `+1`.

**Regla (decidida — opción 1, evidencia sobre afirmación):** en un re-escaneo (`check_applied=True`), si el `source.file` de una op `pending` **ya no está presente** en su carpeta origen, la op pasa a `status="applied"` y **deja de aportar delta** (el `−` del origen y el `+` del destino ya son realidad física). Cero limpieza manual, sin doble conteo, robusto a aplicación parcial (es por-op) y converge a la verdad física aun si el archivo se borró en vez de moverse (el destino solo gana `+1` si el archivo realmente llegó, vía su propio `per_file`). Descartada la opción 2 (congelar al exportar) por depender de la afirmación del paso 1 en vez de la evidencia.

El campo `status` del manifiesto es **informativo** (visibilidad para Daniel + log del paso 1); **no** es la base del conteo de PDFoverseer (que usa la evidencia de presencia del archivo).

## 7. Manifiesto

JSON declarativo versionado. La **fuente** identifica el archivo por su **nombre actual** (única forma de que el paso 1 lo encuentre); el **destino** expresa intención y el paso 1 construye el nombre canónico (`fecha_sigla_descriptor_empresa.pdf`, snake_case, sin acentos, con su `COMPANY_CORRECTIONS`).

```json
{
  "manifest_version": 1,
  "generated_at": "2026-06-17T14:30:00",
  "source_project": "PDFoverseer",
  "month": "2026-06",
  "operations": [
    {
      "id": "op_001",
      "op_type": "extract_pages",
      "source": { "hospital": "HRB", "sigla": "art", "file": "art_crs.pdf", "page_range": [45, 47] },
      "dest":   { "hospital": "HRB", "sigla": "odi" },
      "empresa": null,
      "preserve_date": true,
      "rotation_deg": 0,
      "doc_count": 1,
      "worker_count": 0,
      "note": "ODI colado en el compilado de ART",
      "status": "pending"
    }
  ]
}
```

### Destino de exportación
`<OVERSEER_OUTPUT_DIR>/reorganizacion_<YYYY-MM>.json` (junto al RESUMEN; **nunca** dentro de `INFORME_MENSUAL_ROOT`, que es solo lectura). Escritura atómica (tmp→rename), igual patrón que el Excel.

### Endpoint de exportación
`POST /api/sessions/{id}/reorg/export` → escribe el manifiesto, devuelve `{path, operation_count}`. Incluye solo ops `pending` (las `applied` ya se ejecutaron). Si no hay ops `pending`, 400 con mensaje claro.

## 8. UI

### 8.1 Acciones de archivo completo — `FileList`
Cada archivo gana un menú "Reorganizar →": tipo (`move_file` / `rotate` / reclasificar = `move_file` a otra sigla), destino `(hospital, sigla)` (selector), empresa opcional, rotación. No requiere abrir el visor.

### 8.2 Rango de páginas — visor (`WorkerCountViewer`)
Modo reorg que reusa la infra existente (PdfPage / usePdfDocument / thumbnails / nav / zoom): el operador marca **página inicio** y **página fin** (clic en dos miniaturas o botones "marcar inicio / marcar fin" sobre la página activa), ve el rango resaltado, elige destino y tipo (`extract_pages` / `split_in_place` / `rotate` de páginas) → crea la op. Validación de rango en el cliente (inicio ≤ fin, dentro de límites) y en el backend (§4).

**Interfaz (para que el plan no la invente):** el modo se activa con una prop nueva `mode` (`"worker"` por defecto = comportamiento actual, `"reorg"` = selección de rango); el HUD de conteo de trabajadores no se renderiza en `"reorg"`. Estado nuevo local: `reorgStartPage: number|null` y `reorgEndPage: number|null` (1-based; `null` = sin marcar). El callback de creación de op sube por una prop `onCreateOp(opDraft)` al contenedor (`DetailPanel`/vista), que llama al endpoint `POST /reorg/ops`. La lógica de validación de rango (inicio ≤ fin, 1..páginas) es una función pura testeable con vitest, separada del render.

### 8.3 Sección "REORGANIZACIÓN" — `DetailPanel`
Sección siempre visible (mismo patrón que la sección NOTA de Incr 3C), tras AJUSTE MANUAL. Muestra:
- **Delta neto** de la celda (`+2 / −1`) arriba.
- **Ops salientes** (origen = esta celda): chip de tipo, rango/archivo, `−doc_count → HOSP/sigla`, botón eliminar.
- **Ops entrantes** (destino = esta celda): `+doc_count ← HOSP/sigla`.
- Ops `applied` se muestran atenuadas (informativo).
- Botón global "Exportar manifiesto".

### Endpoints de ops
- `POST /api/sessions/{id}/reorg/ops` — crea (valida §4, append, `refresh_reorg_deltas`, devuelve la op + celdas afectadas).
- `DELETE /api/sessions/{id}/reorg/ops/{op_id}` — borra, `refresh_reorg_deltas`. Editar = borrar + recrear (v1).

### Tokens / primitivas
Solo tokens `po-*` y las 8 primitivas compartidas (`Badge`, etc.). Chips de tipo de op = familia `Badge` (forma compartida, varía color/texto). Sin `bg-slate-*` crudos, sin `/opacity` sobre vars `po-*`.

## 9. Manejo de errores y casos borde

- **Op a archivo ya ausente antes de exportar** (re-escaneo previo lo marcó `applied`): se muestra atenuada, no exporta.
- **Rango fuera de límites / `doc_count` sobre el tope:** 400 con mensaje.
- **Destino == origen** salvo split/rotate: 400.
- **Múltiples `extract_pages` del mismo archivo:** se permiten **solo con rangos disjuntos** (el solape se rechaza al crear, §4 — así el origen nunca resta dos veces las mismas páginas). Todos los rangos apuntan a la numeración del **original**; el contrato instruye al paso 1 a aplicarlos en orden de página **descendente** (o contra una copia intacta) para no correr los índices (§10).
- **Carpeta de celda inexistente:** 404 (`A8` / patrón existente).
- **Sesión desconocida / sigla desconocida:** 404 (no 500).

## 10. Contrato cross-proyecto y documento de handoff

**Entregable:** un `.md` estático (autoría única, no generado por la app) que Daniel lleva al proyecto del paso 1 (`A:\informe mensual`). Vive en `docs/handoff/paso1-manifiesto-reorganizacion.md` (repo PDFoverseer) y se versiona con `manifest_version`. Contenido:

1. **Qué es y por qué existe:** PDFoverseer cuenta y detecta documentos mal clasificados/colados; el manifiesto le dice al paso 1 cómo dejar el archivo físico coherente con los libros.
2. **Dónde leerlo:** `<carpeta de outputs de PDFoverseer>/reorganizacion_<YYYY-MM>.json`. **No** está dentro de `A:\informe mensual`.
3. **Cuándo ejecutarlo:** entre el Step 3 (contar) y el Step 4 (totalizar a nombres de carpeta) del workflow del paso 1.
4. **Contrato campo por campo** (tabla de §4, verbatim).
5. **En qué fijarse:**
   - El destino es **intención** — el paso 1 construye el nombre con su convención (`fecha_sigla_descriptor_empresa.pdf`, `COMPANY_CORRECTIONS`), no usa un filename literal.
   - `preserve_date` = conserva la fecha del documento original.
   - **Orden de extracciones:** múltiples `extract_pages` del mismo archivo se numeran contra el **original**; aplicar en página descendente o contra copia intacta.
   - **Idempotencia:** re-correr el manifiesto no debe duplicar (verificar destino antes de mover).
   - Reportar remanentes como ya hace el paso 1.
   - Patrón `--ejecutar` dry-run-first del paso 1 aplica.

## 11. Pruebas

### Backend (pytest)
- `refresh_reorg_deltas`: recompute correcto de `reorg_doc_delta`/`reorg_worker_delta` desde `reorg_ops` (entrantes `+`, salientes `−`); idempotente.
- `compute_cell_count`: capa aditiva (base + delta), respeta `user_override` como base, checks y documents_workers.
- Paridad cross-language (`cell_count_cases.json`): casos con `reorg_doc_delta`.
- Lifecycle opción 1: op cuyo `source.file` desaparece tras escaneo → `applied`, delta 0; sin doble conteo (escaneo cuenta el archivo en destino vía `per_file`).
- Validaciones §4: rango, tope `doc_count`, dest==origen, tipos sin `page_range`.
- Manifiesto: shape (round-trip), solo ops `pending`, escritura atómica, destino en `OVERSEER_OUTPUT_DIR`.
- Endpoints: crear (200 + delta), borrar (200 + delta recomputado), export (200 / 400 sin pending), 404s.

### Frontend (vitest)
- Render de la sección REORGANIZACIÓN: lista entrantes/salientes, delta neto, ops `applied` atenuadas.
- Lógica de selección de rango (inicio ≤ fin, dentro de límites) en el modo reorg del visor.
- Estado de exportación (deshabilitar sin ops pending).

## 12. Fuera de alcance / futuro

- Ejecución física en el paso 1 (su trabajo).
- Sincronización en vivo del estado de aplicación del paso 1.
- `manifest_version > 1`.
- Edición in-situ de ops (hoy: borrar + recrear).
- Reorg de celdas `checks` (maquinaria) más allá de la capa aditiva uniforme (raro; no se construye UI especial).
- Persistir `per_file_pages` (sigue lazy vía `cell_page_counts`; deuda heredada).

## 13. Resumen de decisiones

- **Modelo de conteo:** ajuste de conteo (delta origen `−` / destino `+`, total preservado) + lista de ops. El doc extraído vive como op del manifiesto, **no** como archivo abrible.
- **Selección de rango:** visual, desde el visor.
- **Ciclo de vida:** opción 1 (descarte por evidencia de archivo-origen-ausente) + campo `status` informativo no-decisivo en el manifiesto.
- **Fuente única:** `state["reorg_ops"]`; deltas son cachés recomputados a nivel de sesión (mismo patrón que `all_reliable`, pero el recompute barre todas las celdas).
- **Capa aditiva** en `compute_cell_count` (+ espejo JS) → fluye a UI/Excel/histórico sin tocar llamadores.
- **Export a `OVERSEER_OUTPUT_DIR`** (corpus es solo lectura).
- **Entregable handoff** `.md` estático para el paso 1.
