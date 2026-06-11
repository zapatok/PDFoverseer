# Incremento 1A — Fundación: conteo robusto + sin pisar — Design

**Fecha:** 2026-06-10
**Rama:** `po_overhaul` (trabajo directo; push al cierre de la ronda)
**Predecesores:** conteo-confiable rev-2 (`per_file_method`, `apply_per_file_ocr_result` = merge por archivo), refinements 2026-06-04, guard de clobber `_cell_has_work` (incidente 2026-06-05). Triage 2026-06-09 (`docs/backlog/2026-06-09-ideas-triage.md`).
**Tag previsto:** `incremento-1a` (milestone al cerrar 1A+1B, o por sub-incremento si conviene).

---

## 1. Contexto

El **modelo per-archivo** ya es la fuente de verdad del total de la celda: `compute_cell_count`
(`core/cell_count.py`) suma `per_file` (con `per_file_overrides` por encima), y cada archivo
lleva su método en `per_file_method` (rev-2). El **escaneo de un solo archivo** desde el visor
(`apply_per_file_ocr_result`) ya **fusiona**: escribe solo ese archivo y deja el resto intacto.

Pero el **OCR de celda completa** quedó atrás. Hoy:

- `scan_cells_ocr` (`core/orchestrator.py`) despacha **una celda entera por worker** en un
  `ProcessPoolExecutor`; cada worker corre `count_ocr` sobre todos los PDFs de la celda y
  devuelve **un** `ScanResult`.
- En `cell_done`, la ruta reconstruye ese `ScanResult` y llama a `apply_ocr_result`
  (`api/state.py`), que hace **reemplazo total**:
  ```python
  cell["per_file"] = result.per_file                              # pisa TODO
  cell["per_file_method"] = {f: result.method for f in per_file}  # pisa TODO
  ```

Eso es la raíz de tres problemas del triage, que comparten causa única (la celda se trata como
unidad atómica, no como un conjunto de archivos):

- **A3** — el OCR pisa conteos R1 / manuales / OCR previo.
- **H1** — cancelar a mitad de una celda pierde lo ya escaneado (se persiste recién al `cell_done`).
- **H2** — el OCR no salta archivos ya escaneados individualmente.

**Decisión de arquitectura (Opción B, confirmada por Daniel 2026-06-10):** unificar el OCR de
celda sobre el **modelo por-archivo incremental**, reusando la misma plomería de merge que ya usa
el escaneo de un solo archivo. El batch y el single-file dejan de divergir; el modelo per-archivo
queda como única verdad del OCR.

Este incremento es **solo backend** (la fundación). La honestidad del punto verde, el toggle
`Archivo · Manual` y la validación viven en **1B** (frontend), que cuelga de 1A.

---

## 2. Objetivos / No-objetivos

**Objetivos**

- **O1 — OCR de celda = fusionar-y-saltar + escritura incremental** (cubre A3 / H1 / H2 / S3 del
  triage). El batch escanea **solo los archivos pendientes**, salta los ya confiables
  (R1 / manual / OCR previo), persiste **cada archivo apenas termina** (no al `cell_done`), y
  nunca toca las entradas de los demás archivos.
- **O2 — Etiqueta de tipo de conteo por sigla** (`count_type`), formalizada en `patterns.py` y
  expuesta por la API. Tres valores: `documents` / `documents_workers` / `checks`. Es la
  clasificación que cierra la Decisión 4 y la etiqueta del grupo F.
- **O3 — Procedencia `per_file_method` completa y honesta en todos los caminos de escritura**, de
  modo que el origen de cada archivo refleje cómo se contó **ese** archivo (no el método de la
  celda). En particular, el merge incremental estampa el método por archivo.
- **O4 — Serializar las mutaciones de estado del `SessionManager` con un lock** (prerequisito de
  correctness que el modelo incremental destapa; ver §6).

**No-objetivos (este incremento)**

- **Frontend** — verde por procedencia, toggle `Archivo · Manual` reversible + hint inline,
  validación (negativos, tope ≤páginas en celdas de documento). Todo eso es **1B**. 1A solo
  **provee** los datos (la etiqueta `count_type`, la procedencia honesta) que 1B consume.
- **RN / tratamientos en bloque** (Incremento 2). 1A deja el merge **preparado para respetar** una
  procedencia operador-afirmada (R1/RN) que aún no existe, pero no agrega la acción RN.
- **Contador por teclado generalizado / maquinaria = chequeos en la UI** (Incremento 3). 1A sí
  marca `maquinaria` como `count_type: "checks"` en los datos; la UI/lógica de chequeos es 3.
- **Bug F1** (conteo de trabajadores que no propaga al Excel) — Incremento 3.
- **Refinamiento OCR data-first** (Track A). 1A no toca anclas ni motores; solo la orquestación.
- **Reescritura del flujo "flavor nuevo"** (Incremento 4).

---

## 3. Decisión transversal A — el OCR de celda migra al modelo por-archivo incremental

El cambio central. Tres reglas: **qué se escanea** (skip), **cómo se persiste** (incremental), y
**qué queda a nivel celda** (finalización).

### 3.1 Predicado de "pendiente" — qué se escanea y qué se salta

Un archivo es **pendiente** (lo escanea el OCR de celda) si y solo si su procedencia actual es
"sin contar de forma confiable": método `filename_glob` (o ausente) **y** sin override manual. Es
exactamente el archivo que `_origin_for` hoy etiqueta **"Pendiente"** (multipágina, contado solo
por nombre).

Se **salta** (no se re-escanea, no se toca) todo lo demás, que es justo el conjunto confiable:

| Estado del archivo | `per_file_method[f]` | ¿Se escanea? | Razón |
|---|---|:--:|---|
| Override manual (`per_file_overrides`) | — (irrelevante) | **No** | Juicio humano manda (A3). |
| OCR previo | `header_band_anchors` / `v4` / `header_detect` / `corner_count` | **No** | No pisar OCR previo (A3 / H2). |
| R1 página-fija | `page_count_pure` | **No** | Certeza estructural (A3). |
| (futuro) R1/RN operador | método ratio (Incr. 2) | **No** | El invariante ya queda listo. |
| Pendiente | `filename_glob` / ausente | **Sí** | Multipágina sin contar → el objetivo del OCR. |

**Cómputo del conjunto a saltar** (en la ruta, desde el estado de la celda — no requiere abrir
PDFs):

```python
skip = {f for f, m in per_file_method.items() if m and m != "filename_glob"} | set(per_file_overrides)
```

Esto cubre **H2** (saltar ya-escaneados) de forma natural: una vez que un archivo se OCR-eó, su
método deja de ser `filename_glob` → entra en `skip` → no se vuelve a escanear en una corrida de
celda. El **re-escaneo puntual** sigue disponible por el botón "Escanear con OCR" del visor
(camino single-file, que **no** consulta `skip`).

> **Archivos de 1 página (A7):** no necesitan tratamiento especial en el skip. Un PDF de 1 página
> contado por nombre tiene `per_file_method = "filename_glob"` → técnicamente "pendiente", pero al
> entrar a `count_ocr` el lock A7 lo resuelve trivialmente (1 página = 1 documento, sin OCR) y se
> reporta con método que `_origin_for` mapea a **R1** (ver §3.4). Costo: una lectura de
> `page_count`, sin OCR. No se pisa nada (sigue siendo 1 = R1).

### 3.2 Contrato del callback por-archivo (enriquecido)

Hoy `count_ocr(...)` reporta progreso con `on_pdf(name)` (solo el nombre, en el `finally` tras
procesar cada PDF). En ese punto del código `per_file[name]` y los near-matches del archivo **ya
están calculados**. Se **enriquece** el callback para que cargue el resultado del archivo:

```python
on_pdf(filename: str, count: int | None, method: str, near_matches: list[NearMatchEntry]) -> None
```

- `count`: documentos hallados en ese PDF (`per_file.get(name)`); `None` si fue ilegible
  (`page_count_failed`) → el merge no escribe ese archivo (queda Error/pendiente).
- `method`: método **por archivo** (no el de la celda). En `AnchorsScanner.count_ocr`:
  - A7 (1 página) → método que rinde **R1** (ver §3.4).
  - contado por anclas / fallback-1-doc → `"header_band_anchors"`.
- `near_matches`: los del archivo (`[nm for nm in near_matches if nm.pdf_name == name]`).

Ambos scanners con OCR (`AnchorsScanner`, `PaginationScanner`) implementan la firma nueva. La
revisión confirmó que `PaginationScanner` (`count_documents_v4`) **también** tiene el conteo
por-PDF disponible al `finally` → **Q4 resuelto, sin fallback** para insgral/altura.

**Patrón de captura en el `finally`** (la revisión lo marcó como trampa de implementación): en
`AnchorsScanner.count_ocr` el `count`/`method` del archivo se fijan en ramas distintas del loop
(A7, anclas, fallback, error) **antes** del `continue`, mientras que `on_pdf` se llama en el
`finally` — donde esas variables no están en scope. Hay que capturarlas en locales **reseteados
por PDF, antes de cada `continue`**:

```python
for pdf in pdfs:
    cancel.check()
    emit = True
    _count: int | None = None       # reset por PDF; None = ilegible → no se fusiona
    _method = "filename_glob"        # A7 / por defecto
    try:
        ...
        if page_count == 1:          # A7: 1 pág = 1 doc
            per_file[pdf.name] = 1; _count = 1; _method = "filename_glob"; continue
        ...                          # anclas
        per_file[pdf.name] = ocr.count; _count = ocr.count; _method = "header_band_anchors"
    except CancelledError:
        emit = False; raise
    finally:
        if emit and on_pdf is not None:
            on_pdf(pdf.name, _count, _method, _file_near_matches(pdf.name))
```

El camino "sin flavors" y `scan_strategy: "none"` emiten el tick con `method="filename_glob"` (y el
conteo real de pase 1, no vacío) → la ruta lo trata como **solo-progreso** (no fusiona; §3.3), así
nunca pisan el conteo de pase 1.

### 3.3 Orquestación — persistencia incremental por-PDF

El merge por-archivo se hace con la función **ya existente y testeada** `apply_per_file_ocr_result`
(que escribe solo `per_file[f]`, `per_file_method[f]` y los near-matches de ese archivo, dejando
todo lo demás intacto). El batch deja de llamar a `apply_ocr_result` para el `per_file`.

**Camino sincrónico** (`max_workers==1`, tests): `on_pdf` (enriquecido) emite directamente un
evento de resultado por-archivo a `on_progress`; la ruta lo fusiona.

**Camino multi-worker** (`ProcessPoolExecutor`): el worker corre en un subproceso, así que reporta
por la cola IPC existente. El evento `pdf_done` se enriquece:

```python
# worker (subproceso) → cola IPC
{"type": "pdf_done", "hospital": h, "sigla": s, "pdf_name": name,
 "count": count, "method": method, "near_matches": [...]}
```

El **hilo de drain** (proceso principal) lo recibe y, además del tick de progreso (`pdf_progress`,
sin cambios), **reenvía un evento `file_result` a `on_progress`** por cada `pdf_done`. La ruta, en
`on_progress`, agrega una rama que mapea `file_result` → `mgr.apply_per_file_ocr_result(...)`.

**near-matches por la cola IPC = `list[dict]`** (la revisión, I4): `apply_per_file_ocr_result`
espera `near_matches: list[dict]`, y `NearMatchEntry` es un dataclass. El worker **serializa a
dict** (mismo shape que el WS: `pdf_name`/`page_index`/`flavor_name`/`matched_anchors`/
`missing_anchors`) **antes** de encolar — los `NearMatchEntry` nunca cruzan la frontera de proceso
como objetos (aunque sean picklables, el contrato del mutador es `dict`).

**Regla de fusión en la ruta** (subsume I5): el handler de `file_result` fusiona vía
`apply_per_file_ocr_result` **solo si `method` es un método OCR** (∉ `{filename_glob}`) **y
`count is not None`**. Un tick con `method="filename_glob"` (A7, sin-flavors, `none`) o `count=None`
(ilegible) es **solo-progreso** → no toca `per_file`. Así el batch nunca reescribe lo de pase 1 ni
los archivos R1 de 1 página; la fusión queda exclusivamente para resultados OCR reales.

**`cell_done` ya NO escribe `per_file` / `per_file_method`** (eso se hizo incrementalmente). Solo
**finaliza metadata de celda** (ver §3.5).

Diagrama del flujo nuevo (multi-worker):

```
worker.count_ocr  ──(por cada PDF)──>  IPC: pdf_done{count,method,near_matches}
                                             │
                          drain thread ──────┤──> on_progress: pdf_progress     (tick barra)
                                             └──> on_progress: file_result ──> apply_per_file_ocr_result  (merge + persist)
worker return ScanResult ──(as_completed)──> on_progress: cell_done ──> finaliza metadata de celda (NO per_file)
```

### 3.4 Método por-archivo y el chip R1

`apply_per_file_ocr_result` ya estampa `per_file_method[filename] = method`. Para que el chip sea
honesto (`_origin_for`):

- A7 (1 página): `count_ocr` reporta `method = "filename_glob"` para ese archivo → como
  `page_count == 1`, `_origin_for` da **R1**. (No se introduce un método nuevo; se reusa la regla
  existente `filename_glob + page_count==1 → R1`.)
- Multipágina por anclas: `method = "header_band_anchors"` → **OCR** (o **Revisar** si `count == 0`).
- `PaginationScanner`: su método propio (`v4` / `page_count_pure`) → chip correspondiente.

Sin cambios en `_origin_for` salvo que ahora **siempre** habrá `per_file_method[f]` para los
archivos escaneados (la procedencia deja de depender del fallback a `cell.method`).

### 3.5 Campos a nivel celda — qué se mantiene en `cell_done`

Con el merge incremental, `per_file` / `per_file_method` / `near_matches` quedan al día por
archivo. `cell_done` finaliza **solo metadata de celda**, sin tocar el conteo por-archivo:

- `cell["method"]` ← método OCR de la corrida (compat / display; el chip ya es per-archivo).
- `cell["confidence"]`, `cell["flags"]`, `cell["errors"]`, `cell["duration_ms_ocr"]` ← de la corrida.
- **`cell["ocr_count"]`**: se mantiene su semántica actual de **fallback** (lo usa
  `compute_cell_count` solo cuando `per_file` está vacío). Decisión: en `cell_done` se setea
  `ocr_count = sum(per_file_de_los_archivos_escaneados_en_esta_corrida)` **solo para compat** y
  para que `_cell_has_work` siga viendo trabajo (belt-and-suspenders; de todos modos
  `per_file_method` con métodos no-`filename_glob` ya marca trabajo). El total **real** de la celda
  lo sigue dando `compute_cell_count` desde `per_file`. *(Punto de revisión — ver §10 Q1.)*
- **No** se tocan: `user_override`, `per_file_overrides`, `manual_entry`, `confirmed`,
  `worker_marks`, `filename_count`.

> Una **celda sin archivos pendientes** (todo confiable) se salta entera: emite un `cell_done` (o
> un `cell_skipped`) para que la UI cierre el estado "escaneando", sin mutar conteos.

---

## 4. Decisión B — etiqueta de tipo de conteo por sigla (`count_type`)

**Problema.** Hoy `scan_info_for` (`core/scanners/scan_info.py`) solo expone el `kind` de
*escaneo* (`anchors` / `pagination` / `none`). El frontend **hardcodea** `charla`/`chintegral`
para mostrar el módulo de trabajadores, y `maquinaria` usa el scanner de anclas aunque en realidad
cuenta **chequeos** (columnas de fecha marcadas), no documentos. El "qué cuenta esta celda" es un
eje **ortogonal** al "cómo se escanea".

**Decisión (triage F-label, verbatim en Apéndice).** Un campo simple de **3 valores**, no
jerarquía de clases, en `patterns.py` (fuente única por sigla):

| `count_type` | Siglas | Qué es el número de la celda |
|---|---|---|
| `documents` | las 14 restantes | documentos (mayoría). |
| `documents_workers` | `charla`, `chintegral`, `dif_pts` | documentos a una columna del Excel **+** trabajadores (contador por teclado) a otra (HH). |
| `checks` | `maquinaria` | el único número son **chequeos** = columnas de fecha marcadas. |

**Implementación.**

- Agregar `"count_type": "<valor>"` a las 18 entradas de `PATTERNS` (explícito por sigla; lo
  exige la simetría con el resto de campos data-driven y el gate de completitud).
- Extender el **test de completitud** de `patterns.py` para exigir `count_type ∈ {documents,
  documents_workers, checks}` en las 18.
- Exponer `count_type` en `scan_info_for(...)` (un campo más en el dict que ya devuelve
  `/api/siglas/{sigla}/scan-info`). El frontend (1B/Incr. 3) lo lee en vez de hardcodear.
- **`maquinaria`** en 1A solo cambia el **dato** (`count_type: "checks"`). El resultado del scanner
  de anclas para `maquinaria` pasa a ser irrelevante para el conteo (lo formaliza Incr. 3); 1A no
  cambia su `scan_strategy` todavía para no romper su pase actual sin el reemplazo manual listo.
  *(Punto de revisión — ver §10 Q2.)*

---

## 5. Decisión C — procedencia `per_file_method` completa

rev-2 ya hizo que **todas** las corridas que tocan `per_file` escriban `per_file_method` en
sincronía. 1A **cierra los bordes** que el modelo incremental destapa:

- El merge incremental (`apply_per_file_ocr_result`) estampa `per_file_method[f]` por archivo
  escaneado (ya lo hace). ✔
- `apply_ocr_result` deja de escribir `per_file`/`per_file_method` en masa (su rol pasa a ser
  finalización de metadata de celda, §3.5), evitando el reemplazo destructivo.
- Verificar que `apply_per_file_override` (override manual por archivo) **no** necesita estampar
  `per_file_method` (la procedencia "Manual" se deriva de la presencia en `per_file_overrides`, y
  `_origin_for` la antepone a todo). Se documenta la invariante en el spec/tests; sin cambio de
  código.
- Migración: las celdas viejas sin `per_file_method` siguen cayendo al fallback `cell.method` en
  `_origin_for` (compat ya existente). Sin migración de datos nueva.

---

## 6. Decisión D — serializar las mutaciones de estado (lock)

**Hazard (confirmado trazando el write-path).** `SessionManager` hace **read-modify-write del blob
`state_json` completo sin lock**: `_load_and_migrate` (lee todo el estado) → muta una celda →
`json.dumps` → `update_session_state` (UPDATE en autocommit, `isolation_level=None`). La conexión
es **única y compartida** con `check_same_thread=False`. Hoy es seguro **por accidente**: el batch
solo escribe desde el hilo de dispatch (una celda a la vez en `as_completed`) y el drain solo
reporta progreso.

El modelo incremental escribe **por-PDF desde el hilo de drain** y finaliza metadata en el hilo de
dispatch (`cell_done`) → dos hilos haciendo read-modify-write del mismo blob → **lost updates**.
Además ya existe una **carrera latente**: editar una celda por HTTP (override/confirm) mientras
corre un scan.

**Fix.** Un **`threading.RLock`** por `SessionManager` que envuelva la secuencia
**load → mutate → write** de **cada** método mutador (`apply_filename_result`, `apply_ocr_result`,
`apply_per_file_ocr_result`, `apply_user_override`, `apply_per_file_override`, `apply_worker_count`,
`apply_confirmed`, `clear_near_matches`, `finalize`). App de un usuario → contención nula. Cierra
el hazard del incremental **y** la carrera latente HTTP-durante-scan.

> **RLock, no Lock** (la revisión, C1 — el riesgo #1): `apply_cell_result` (deprecado pero **vivo**,
> `api/state.py:468`) delega 100% en `apply_filename_result`. Con un `Lock` **no reentrante**, ese
> camino adquiere el lock y la llamada interna intenta re-adquirirlo → **deadlock silencioso**
> (cuelga el scan sin excepción ni log). `RLock` lo evita y cubre cualquier futuro
> mutador-que-llama-a-mutador. Auditar callers de `apply_cell_result` al implementar; si está
> muerto, eliminarlo (y de paso simplifica).

> **Lecturas crudas (la revisión, M2):** `_load_and_migrate` es una lectura sin lock del blob
> completo; algunos handlers HTTP la llaman directo tras un mutador para armar la respuesta (p. ej.
> `patch_per_file_override`), un TOCTOU de bajo impacto (solo el payload de respuesta, no el estado
> persistido). Documentar `_load_and_migrate` como **lectura cruda no protegida**; donde importe la
> coherencia de la respuesta, leer vía un getter que tome el lock.

> Nota: el getter `get_session_state` también lee el blob; basta con que las **escrituras** sean
> mutuamente exclusivas (un lector concurrente ve un estado consistente porque cada escritura es un
> UPDATE atómico del blob entero). Se protege la sección crítica de escritura; el getter puede
> tomar el lock también para lecturas coherentes si resulta barato.

---

## 7. Cambios por archivo

**Backend — orquestación / estado**

- `core/scanners/base.py` — actualizar el tipo del callback `on_pdf` (firma enriquecida §3.2) en
  el contrato/Protocol del scanner si está tipado ahí.
- `core/scanners/anchors_scanner.py` — `count_ocr`: (a) aceptar `skip: set[str] | None` y saltar
  esos archivos; (b) emitir `on_pdf(name, count, method, near_matches)`; (c) método por-archivo A7.
- `core/scanners/pagination_scanner.py` — mismas tres cosas (verificar paridad de firma; ya acepta
  `cancel`/`on_pdf`/`only`/`on_page` porque `scan_one_file_ocr` lo invoca genérico).
- `core/scanners/simple_factory.py` — el camino "sin OCR"/`none`: emitir el tick enriquecido (count
  desde `per_file`, near_matches vacío). Verificar `page_count_pure` reporta método por-archivo.
- `core/orchestrator.py`:
  - `_ocr_worker` / `pdf_cb` — propagar `count`/`method`/`near_matches` por la cola IPC.
  - `scan_cells_ocr` — pasar `skip` por celda a los workers (extender el `cell_tuple`); `_drain`
    reenvía el evento de resultado por-archivo; `_emit_pdf` (sync) idem; `cell_done` ya no carga
    `per_file` en el evento (o la ruta lo ignora para el merge).
  - `scan_one_file_ocr` — adaptar a la firma enriquecida de `on_pdf` si la comparte (sigue usando
    `on_page` para la barra por-página; sin cambio funcional).
- `api/routes/sessions.py`:
  - `scan_ocr` — calcular `skip` por celda desde el estado (§3.1) y pasarlo al orquestador; en
    `on_progress`, **agregar rama `file_result`** → `apply_per_file_ocr_result` (fusiona solo si
    `method` es OCR y `count is not None`, §3.3); ajustar el manejo de `cell_done` para que finalice
    metadata (no `per_file`).
  - (sin cambio en `scan_file_ocr`; ya hace el merge correcto.)
- `api/state.py`:
  - `SessionManager.__init__` — agregar `self._lock = threading.RLock()` (RLock por C1).
  - `apply_cell_result` — auditar callers; eliminar si está muerto (evita el camino de re-entrada).
  - Envolver con `self._lock` la sección crítica de cada método mutador (§6).
  - `apply_ocr_result` — re-scopear a **finalización de metadata** (no escribir
    `per_file`/`per_file_method`); o introducir `finalize_cell_ocr(...)` y dejar `apply_ocr_result`
    como deprecated/compat. *(Decisión de naming — §10 Q3.)*

**Backend — tipo de conteo**

- `core/scanners/patterns.py` — `count_type` en las 18 entradas **+ extender el TypedDict
  `SiglaPattern`** con `count_type: Literal["documents", "documents_workers", "checks"]` (M1; si
  alguna fixture arma patterns parciales, usar `NotRequired`, si no, requerido).
- `core/scanners/scan_info.py` — incluir `count_type` en el dict de `scan_info_for`.
- (constante de valores válidos: en `core/utils.py` si se quiere un `COUNT_TYPES = frozenset(...)`
  para el gate, por la regla "constantes en utils.py".)

**Tests** (ver §8) — orquestación, estado, scan_info, completitud de patterns, cross-language del
conteo (sin cambio esperado en el resultado de `compute_cell_count`).

---

## 8. Plan de pruebas

**Unit / integración (pytest)**

- **Merge incremental:** una celda con 3 archivos (1 con override manual, 1 ya OCR-eado, 1
  pendiente multipágina) + un OCR de celda → solo el pendiente se escanea; los otros dos quedan
  **byte-idénticos**; el total por `compute_cell_count` no regresiona. (Reproduce A3.)
- **Skip / H2:** correr OCR de celda dos veces → la segunda no re-escanea nada (todo quedó con
  método no-`filename_glob`); los conteos no cambian.
- **Cancelar conserva (H1):** simular cancelación tras N PDFs en una celda → los N primeros quedan
  persistidos con su método OCR; el resto, pendiente. (Camino sync `max_workers=1`.)
- **A7 en celda OCR:** un PDF de 1 página dentro de una celda escaneada → chip **R1**, count 1,
  método que rinde R1 (no "OCR").
- **Lock / concurrencia:** dos mutaciones concurrentes al mismo session (p. ej. `apply_confirmed`
  desde un hilo + `apply_per_file_ocr_result` desde otro) → ambas persisten, sin lost update.
  (Test determinístico con barreras, sin mockear el DB — regla del proyecto.)
- **`count_type`:** gate de completitud (18/18 con valor válido); `scan_info_for` devuelve
  `count_type` correcto para `charla` (`documents_workers`), `maquinaria` (`checks`), `odi`
  (`documents`).
- **No-regresión:** `odi` HRB (baseline B5) y la corrida full ABRIL (`test_abril_full_corpus`,
  `test_scan_ocr_full`) dan los mismos totales que hoy.
- **Cross-language:** `test_cell_count_cross_language` verde sin tocar fixtures (1A no cambia la
  cascada de conteo).

**Smoke conducido (chrome-devtools, post-merge)** — Brave en debug; conducido por mí:

1. Abrir un mes; OCR-ear una celda multipágina; verificar que la barra avanza por PDF y que el
   detalle/lista refleja conteos por archivo a medida (no de golpe al final).
2. Ajustar un archivo a mano; re-OCR-ear la celda → el ajuste manual **sobrevive**.
3. OCR-ear una celda; OCR-ear de nuevo → no re-escanea (rápido / sin cambios).
4. Cancelar a mitad → lo escaneado queda; lo no escaneado, pendiente.

---

## 9. Riesgos y mitigaciones

- **Refactor de orquestación toca el `ProcessPoolExecutor` + IPC.** Mitigación: el camino sync
  (`max_workers=1`) cubre la lógica de merge sin subprocesos y es el que más usan los tests;
  validar primero ahí, luego el multi-worker. Mantener los eventos de progreso existentes intactos.
- **Paridad de firma `PaginationScanner.count_ocr`.** Ya acepta `cancel`/`on_pdf`/`only`/`on_page`
  (lo invoca `scan_one_file_ocr` genérico). Verificar al implementar que honra `skip` + callback
  enriquecido; si su forma de contar (V4/paginación) no expone `count` por-PDF fácilmente, evaluar
  fallback (persistir esa celda al `cell_done` como hoy, marcándola como excepción documentada).
  *(Punto de revisión — §10 Q4.)*
- **Frecuencia de escritura ↑ (una por PDF).** Cada merge re-serializa el blob de sesión completo.
  El blob es chico (decenas de KB) y `apply_per_file_ocr_result` ya hace esto por single-file; con
  WAL + autocommit + lock es aceptable para el volumen (decenas/cientos de PDFs por scan).
- **Semántica de `ocr_count` ambigua** tras el cambio (deja de ser "el conteo"). Mitigación:
  documentar que es fallback; `compute_cell_count` ya prioriza `per_file`. Revisar si conviene
  dejar de escribirlo (§10 Q1).

---

## 10. Decisiones cerradas tras la revisión

- **`ocr_count` en `cell_done`: SE MANTIENE.** La revisión confirmó que el write
  belt-and-suspenders (`sum(per_file` de la corrida)`) es seguro y nunca compite con el conteo real
  (`compute_cell_count` prioriza `per_file`). Se mantiene por compat + para que `_cell_has_work` vea
  trabajo (aunque también lo detecta vía `per_file_method`).
- **`maquinaria` en 1A: solo el dato `count_type: "checks"`.** No se toca `scan_strategy` (su pase
  de anclas sigue corriendo; su número se vuelve irrelevante aguas arriba en Incr. 3, junto con el
  contador por teclado que aún no existe). 1A no puede arreglar el conteo de chequeos del todo, solo
  marcar el tipo.
- **Naming: función nueva `finalize_cell_ocr(...)` + deprecación de `apply_ocr_result`.** La
  finalización de metadata (no-`per_file`) vive en `finalize_cell_ocr`; `apply_ocr_result` queda
  como shim deprecado mientras migran tests/llamadores, luego se borra (junto con `apply_cell_result`).
- **`PaginationScanner`: RESUELTO, sin fallback.** La revisión verificó que `count_documents_v4`
  tiene el conteo por-PDF disponible al `finally` → insgral/altura fusionan incrementalmente como
  las demás siglas.

---

## 11. Trazabilidad — decisiones del triage (verbatim)

Copiadas textualmente de `docs/backlog/2026-06-09-ideas-triage.md` (regla anchors-verbatim: no
destilar entre capas; el triage es la autoridad).

> **Decisión 2 — OCR no pisa + saltar ya-escaneados (A3 / H2 / S3): ✅ RESUELTA.**
> El OCR de celda pasa de "reemplazar todo el mapa `per_file`" a **"fusionar y saltar"**: salta los
> archivos ya confiables (R1 / manual / OCR previo), solo escanea los pendientes, y escribe SOLO
> esas entradas (no toca las demás). Cubre A3 + H2 + S3 de una. Re-escaneo puntual queda disponible
> vía el botón OCR por-archivo existente.

> **Decisión 4 — validación del número (A4): ✅ RESUELTA (categorización corregida por Daniel).**
> Bloquear negativos siempre; 0 explícito válido. El tope **`conteo ≤ páginas` aplica SOLO al
> conteo de documentos**. Tres tipos de celda [...]: Doc-counting (tope ≤ páginas); Worker-counting
> SEPARADO (`charla`, `chintegral`, `dif_pts`) con conteo de trabajadores en campo aparte
> (`worker_marks`), sin tope; Check-counting como conteo PRINCIPAL (`maquinaria`), chequeos =
> columnas de fecha marcadas, sin tope. Requiere marcar formalmente el tipo de cada celda.

> **H1 — cancelar pierde lo ya escaneado: ✅ RESUELTA (cae de la Decisión 2).** Hoy el OCR de celda
> escribe los resultados todo junto al final → cancelar a mitad descarta lo procesado. Con la
> Decisión 2 (fusionar por archivo) + escritura **incremental** (persistir cada archivo apenas
> termina, como ya hace el OCR de un solo archivo), cancelar = parar sin perder lo hecho;
> no-empezados quedan pendientes, el en-curso se descarta. H2/H3 ya estaban dentro de la Decisión 2.

> **F — etiqueta de "tipo de conteo" por sigla: ✅ RESUELTA.** [...] Mantener **mínimo**: un campo
> simple de 3 valores, no jerarquía de clases. [...] cuenta-documentos (mayoría);
> cuenta-documentos-y-trabajadores (`charla`, `chintegral`, `dif_pts`); cuenta-chequeos
> (`maquinaria`). La etiqueta le dice al contador qué tallar y al Excel de dónde sacar cada número.

> **Decisión B-b (invariante RN, para diseñar la fundación):** [...] **No pisa lo ya resuelto**: la
> acción RN cae **solo sobre archivos pendientes** — nunca toca R1 (1 pág = 1 doc), ni manual, ni
> OCR previo. Es el MISMO invariante de la Decisión 2 ("tratamientos en bloque saltan lo resuelto").

---

## 12. Definición de hecho (1A)

- `ruff check .` 0 violaciones; `pytest` verde (incl. los tests nuevos de §8); `vitest`/build sin
  tocar (1A es backend) salvo que `scan_info` rompa algún consumidor FE (verificar).
- Smoke conducido (§8) OK.
- Commits atómicos conventional-commit; bump de version-tag donde aplique (hookify
  `bump-version-tags` para `core/orchestrator.py` / scanners; `SCANNER_PATTERNS_VERSION` por el
  `count_type`).
- Memoria de milestone al cerrar 1A (o 1A+1B juntos).
