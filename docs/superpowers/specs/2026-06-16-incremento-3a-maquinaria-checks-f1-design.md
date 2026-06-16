# Incremento 3A — maquinaria = conteo de chequeos + bug F1 (divergencia de filtro)

**Fecha:** 2026-06-16
**Rama:** `po_overhaul` (trabajo directo; push al cierre de la ronda)
**Estado:** DISEÑO aprobado por Daniel (2026-06-16) — pendiente de spec-review + revisión del usuario.
**Predecesores:** Incr 1A (`incremento-1a`, fundación backend: `count_type` por sigla,
`per_file_method`, merge incremental), 1B (`incremento-1b`, frontend honesto), 2
(`incremento-2`, RN + tope ≤páginas + señal `all_reliable`).
**Origen del alcance:** `docs/backlog/2026-06-09-ideas-triage.md` — Incremento 3 (líneas 564-567),
decisiones B-a/B7 (maquinaria=chequeos), F (contador parametrizado por unidad), F1 (bug), A2/Decisión 1
(verde honesto). Este corte (3A) toma **maquinaria=chequeos + F1**; dif_pts/N15, indicador en card (M2),
marks-list (F4) y notas-con-estado (N1) quedan para 3B/3C.

---

## 1. Objetivo

Habilitar el conteo de **chequeos** de `maquinaria` (sigla de conteo manual: el número del Excel son
columnas de fecha marcadas, no documentos) reusando el visor de teclado existente, y **arreglar el bug
F1**: el total de trabajadores que el visor muestra no coincide con el que ven el detalle y el Excel.
Ambas piezas comparten el mismo subsistema (marcas → total → filtro → propagación), por eso van juntas:
si no se arregla el filtro de F1, maquinaria hereda el mismo bug.

## 2. Contexto verificado (código actual)

- **El visor ya es genérico.** `WorkerCountViewer` recibe `hospital`/`sigla`, marca
  `{archivo: [{page, count}]}`, y deriva el total con `computeWorkerCount` (nunca se almacena).
  Atajos: PageDown (fijar+avanzar), PageUp (retroceder), Delete (borrar marca), 0-9 (dígitos),
  Backspace, E (editar), M (mic), +/− (zoom). Voz vía `useSpeechNumber`.
- **`count_type` ya existe (Incr 1A):** `core/scanners/patterns.py::count_type_for(sigla)` → uno de
  `documents` (14 siglas) / `documents_workers` (charla, chintegral, dif_pts) / `checks` (maquinaria).
  Expuesto al frontend por `GET /api/siglas/{sigla}/scan-info` (lo consume `DetailPanel`/`FileList`).
- **Cuenta de celda:** `core/cell_count.py::compute_cell_count(cell)` (módulo puro). Precedencia:
  `user_override` > suma `per_file`/`per_file_overrides` > `ocr_count`/`filename_count` > 0. Tiene
  **espejo JS** en `frontend/src/lib/cellCount.js`, sincronizado por
  `tests/test_cell_count_cross_language.py` contra `tests/fixtures/cell_count_cases.json`.
- **Total de trabajadores backend:** `api/state.py::compute_worker_count(cell)` (línea 53) — suma los
  `count`, **filtrando por las claves de `per_file`** (línea 70: `if per_file and filename not in per_file: continue`).
- **Total de trabajadores frontend:** `frontend/src/lib/worker-count.js::computeWorkerCount(marks, fileNames)`
  — filtra por `fileNames` cuando `fileNames.length > 0`; si viene vacío/nulo, NO filtra.
- **Sitios de cómputo del total (la divergencia de F1):**
  - Visor (`WorkerCountViewer.jsx:137-138`): `computeWorkerCount(marks, files.map(f => f.name))` →
    filtra por **todos los PDF del disco** de la celda (`api.getCellFiles`).
  - Detalle (`DetailPanel.jsx:149`, dentro de `WorkerCountModule`):
    `computeWorkerCount(cell.worker_marks, Object.keys(cell.per_file || {}))` → filtra por `per_file`.
  - Excel (`api/routes/output.py::_build_worker_values`, línea 115-127): `compute_worker_count(cell)` →
    filtra por `per_file`.
- **Render del contador hoy:** gateado por `sigla === "charla" || sigla === "chintegral"`
  (`DetailPanel.jsx:416`). El módulo dice "Conteo de trabajadores" / "Contar trabajadores" /
  "Continuar conteo" / "Revisar", sufijo "trabajadores".
- **Carpeta de una celda (backend):** `_find_category_folder(month_root / hospital, sigla)` (importado de
  `core.orchestrator`) + `cell_page_counts(folder)` (lazy, `api/routes/sessions.py:96`); listar nombres
  de PDF es barato (glob), abrir cada PDF para páginas es caro — F1 solo necesita los **nombres**.
- **PATCH del conteo:** `PATCH /api/sessions/{id}/cells/{h}/{s}/worker-count` (`sessions.py:721`) persiste
  `worker_marks/status/cursor` (`apply_worker_count`, `state.py:493`, sobrescribe `worker_marks` entero
  cuando `marks` no es None) y **devuelve** `{worker_marks, worker_status, worker_cursor, worker_count}`.
- **Sin cambios de pipeline/scanner:** `maquinaria` ya es `count_type=checks`. NO se toca
  `core/{pipeline,ocr,inference,image}.py` ni `vlm/*` ni los anchor sets → **no aplica** el hook
  `bump-version-tags` ni `SCANNER_PATTERNS_VERSION`. `maquinaria` conserva su `scan_strategy` actual;
  su resultado de scanner simplemente se ignora para la cuenta (ver §3.3).

## 3. Parte 1 — maquinaria como celda de conteo de chequeos

### 3.1 Semántica del conteo

`maquinaria` no cuenta documentos ni usa el OCR de anclas para su número (Decisión B-a). El operador abre
el visor y **talla los chequeos por página** (columnas de fecha marcadas con SI/NO/NA, ~5 por formulario).
El total = suma de las marcas = **la cuenta principal de la celda** (puede superar las páginas, por diseño).

### 3.2 Modelo de datos — reusar `worker_marks` (decisión aprobada)

maquinaria almacena su tally en el **mismo campo `worker_marks`** y el mismo `worker_status`/`worker_cursor`.
No se introduce campo nuevo ni se renombra (evita migrar datos de Feature 1 + el path del Excel + MAYO en
vivo). La deuda de nombre ("worker_marks" guardando chequeos) es aceptable (app de un usuario, campo
interno) y se documenta con un comentario en `compute_worker_count` y `apply_worker_count`.

### 3.3 La cuenta de la celda viene del tally (cambio en `compute_cell_count` + espejo JS)

`compute_cell_count` gana un parámetro `count_type`:

```python
def compute_cell_count(cell: dict, count_type: str = "documents",
                       present_files: set[str] | None = None) -> int:
    # 1. user_override sigue siendo el escape hatch absoluto.
    if cell.get("user_override") is not None:
        return cell["user_override"]
    # 2. checks: la cuenta es el tally manual; per_file/OCR se ignoran.
    if count_type == "checks":
        return compute_worker_count(cell, present_files)
    # 3. resto: cascada per_file actual (sin cambios).
    ...
```

- **Precedencia para `checks`:** `user_override` > tally de chequeos > 0. Se ignora
  `per_file`/`per_file_overrides`/`ocr_count` (irrelevantes para maquinaria, aunque un escaneo previo los
  haya poblado — así un "OCR la celda" accidental no contamina el número).
- **Espejo JS obligatorio:** `frontend/src/lib/cellCount.js` recibe el mismo `count_type` y replica la
  rama `checks` (sumando `worker_marks` filtrado por archivos presentes). Se agregan casos `checks` a
  `tests/fixtures/cell_count_cases.json` y el test cross-language los cubre en ambos lenguajes.
- **Dependencia circular:** `compute_cell_count` (core) no puede importar `compute_worker_count` (api)
  — `core/` no depende de `api/` (verificado: cero imports). **Resolución recomendada** (el cuerpo de
  `compute_worker_count` ya es una función pura sobre el dict): levantar esa suma a un helper en `core/`
  (p. ej. `core/cell_count.py::_sum_marks(cell, present_files)`) y que `api/state.py::compute_worker_count`
  **delegue** en él. La rama `checks` de `compute_cell_count` llama a `_sum_marks`. El contrato:
  **la rama `checks` devuelve el tally filtrado por presentes.**

### 3.4 Punto verde honesto (cell-status + all_reliable)

- **Frontend** (`frontend/src/lib/cell-status.js`): para `count_type === "checks"`,
  `isCellReady = confirmed || hasOverride || worker_status === "terminado"`. (Un tally "en_progreso" o sin
  empezar → ámbar.) Para los demás count_types, la lógica de Incr 1B/2 queda intacta.
- **Backend** (`compute_settled`/`all_reliable`, Incr 2): `compute_settled` **gana un parámetro
  `count_type`**. Hoy su firma es `(cell, folder, pages=None)` y exige incondicionalmente que cada archivo
  tenga `file_origin ∈ {R1, RN, Manual}` — para una celda `checks` con archivos OCR/pendientes eso daría
  False sin importar el tally. La rama nueva: `count_type == "checks"` → settled si
  `worker_status == "terminado"` (verificación humana). Los llamadores pasan `count_type_for(sigla)`.
  `refresh_all_reliable` se invoca **además tras el PATCH de worker-count** para celdas checks (hoy el
  PATCH no recalcula `all_reliable`).

### 3.5 Excel

La cuenta de maquinaria fluye por el **path normal de la celda** hacia su celda de la grilla. La cadena es
`api/routes/output.py::_build_cell_values` (línea 96) → `core/excel/writer.py::resolve_cell_value` (línea 15)
→ `compute_cell_count(cell, count_type="checks", present_files=...)`. **No** se agrega named range nuevo ni
entra en `WORKER_PURPOSE` (eso es para las columnas HH de charla/chintegral). Cambios: `resolve_cell_value`
en **`core/excel/writer.py`** gana `count_type`/`present_files`, y `_build_cell_values` en `output.py`
**los enhebra** derivando `count_type` de la sigla vía `count_type_for` y resolviendo la carpeta para
`present_files`. (Atención: `resolve_cell_value` NO vive en `output.py`.)

### 3.6 UI del visor + entrada

- **Render del módulo** (`DetailPanel.jsx`): el gate pasa de `sigla === "charla" || sigla === "chintegral"`
  a incluir checks **sin** arrastrar dif_pts:
  `count_type === "checks" || sigla === "charla" || sigla === "chintegral"`.
  (dif_pts se difiere a 3B junto con su mapeo HH/N15.)
- **Parametrización por unidad** (deriva de `count_type`, vía `scan-info`):
  - `checks` → título "Conteo de chequeos", botón "Contar chequeos" / "Continuar conteo" / "Revisar",
    sufijo "chequeos".
  - `documents_workers` (charla/chintegral) → textos actuales ("trabajadores"), sin cambios.
- **Voz:** solo para worker-counting. En `checks` el visor arranca con la voz **deshabilitada/oculta**
  (sin `useSpeechNumber`, sin tecla M de mic). El teclado funciona igual.
- El panel de detalle de maquinaria sigue mostrando la lista de PDF (informativa); el número grande es el
  tally.

## 4. Parte 2 — Bug F1 (divergencia de filtro)

### 4.1 Causa raíz (confirmada en código, §2)

El visor cuenta marcas sobre **todos los PDF del disco**; el detalle y el Excel cuentan solo sobre las
claves de **`per_file`**. Marcas en un PDF que existe pero no está en `per_file` se ven en el visor
(p. ej. 6070) pero se descartan en detalle/Excel (6034). El Excel **sí** recalcula fresco — recalcula un
total **filtrado** que bota esas marcas (resuelve la "contradicción": ambas cosas eran ciertas). El filtro
`per_file` se pensó para botar marcas **huérfanas** (PDF renombrado/borrado), no archivos presentes sin
entrada de pase-1.

### 4.2 Decisión de diseño — filtro canónico = "archivos presentes en la carpeta"

Las marcas de un PDF que **existe** en la carpeta de la celda deben contar en los tres sitios; solo se botan
**huérfanos reales** (PDF ya no presente). El backend pasa a ser **fuente única** del total.

- **Backend:** `compute_worker_count(cell, present_files: set[str] | None = None)`:
  - `present_files` provisto → filtra por ese set (los nombres de PDF presentes en la carpeta).
  - `present_files is None` → comportamiento actual (filtra por `per_file`), por retro-compatibilidad de
    llamadores/tests que aún no resuelven carpeta.
  - Llamadores que SÍ resuelven carpeta pasan `present_files` (glob de nombres, barato):
    el PATCH worker-count (`sessions.py:721`), y el builder del Excel
    (`output.py::_build_worker_values` y el path de cuenta de checks).
- **Frontend:** eliminar el filtro divergente. `WorkerCountModule` (`DetailPanel.jsx:149`) debe filtrar por
  **los archivos reales de la celda** (la misma lista `getCellFiles` que usa el visor, keyed en `filesTick`),
  no por `Object.keys(cell.per_file)`. Visor y detalle quedan sobre la misma regla; el contrato es:
  **total = Σ marcas sobre archivos presentes en la carpeta**, idéntico en backend y frontend.
- El PATCH ya devuelve `worker_count`; al recalcularlo con `present_files` queda autoritativo y el store lo
  refleja en `saveWorkerCount`.

### 4.3 Reproduce-first (disciplina anti-fix-a-ciegas)

La primera tarea de F1 es un **test que falla** que reproduce la divergencia, ANTES de tocar el arreglo:

- **Backend:** celda con `worker_marks` sobre un archivo `X.pdf` que existe en la carpeta pero **no** está
  en `per_file` → `compute_worker_count(cell)` (sin present_files, filtro per_file) da el total bajo;
  `compute_worker_count(cell, present_files={...X...})` da el total correcto. El test fija que el segundo
  es el esperado y que el path del Excel usa present_files.
- Recién con el test rojo se aplica el arreglo y se verifica que pasa a verde, sin romper el caso huérfano
  (marca sobre un PDF ausente → NO cuenta).

### 4.4 Por qué va con maquinaria

Los chequeos se enrutan por el mismo `compute_worker_count`. Arreglar el filtro es fundacional: maquinaria
usa `present_files` desde el día uno (su `compute_cell_count` rama checks lo pasa).

## 5. Contratos que cambian

| Símbolo | Antes | Después |
|---------|-------|---------|
| `core/cell_count.py::compute_cell_count(cell)` | 1 arg | `(cell, count_type="documents", present_files=None)`; rama `checks` |
| `frontend/src/lib/cellCount.js` (mirror) | mirror de lo anterior | + `count_type` + rama checks |
| `api/state.py::compute_worker_count(cell)` | filtra por `per_file` | `(cell, present_files=None)`; present_files manda |
| `PATCH .../worker-count` respuesta | `worker_count` filtrado por per_file | filtrado por archivos presentes |
| `core/excel/writer.py::resolve_cell_value` (+ `output.py::_build_cell_values` enhebra) / `_build_worker_values` | sin count_type / per_file | reciben count_type + present_files |
| `DetailPanel.jsx` render del módulo | `sigla in {charla,chintegral}` | `+ count_type==="checks"`; unidad parametrizada; sin voz en checks |
| `cell-status.js::isCellReady` | sin rama checks | `checks` → ready si `worker_status==="terminado"` |
| `compute_settled(cell, folder, pages=None)` / `refresh_all_reliable` | no consideran checks ni PATCH worker | `compute_settled` gana param `count_type`; checks settled en "terminado"; refresh tras PATCH worker |

Todos los demás contratos (eventos WS `cell_done`, snapshot de sesión, RN/tope de Incr 2) quedan intactos.

## 6. Estrategia de pruebas

- **Backend (pytest, fixtures reales, sin mockear DB):**
  - `compute_cell_count(count_type="checks")` → devuelve el tally; ignora per_file/ocr_count; respeta
    user_override.
  - F1: el test reproduce→converge de §4.3 (huérfano vs presente; Excel usa present_files).
  - `compute_settled`/`all_reliable` para checks (terminado → settled; en_progreso → no).
  - Integración: PATCH worker-count sobre maquinaria → cuenta de celda = tally; verde tras terminado;
    el Excel escribe el tally en la celda de maquinaria.
- **Cross-language:** casos `checks` nuevos en `tests/fixtures/cell_count_cases.json`; el test cross-language
  los corre en Python y JS (no pueden divergir). El harness (`tests/test_cell_count_cross_language.py:20`,
  hoy llama `compute_cell_count(case["cell"])`) y el schema de fixtures ganan un campo `count_type`
  **opcional con default `"documents"`** → los 7 casos existentes siguen verdes sin tocarlos.
- **Frontend (vitest):** `cellCount.js` rama checks; `cell-status.js` verde de checks; el enrutado del
  render por count_type + textos de unidad; el filtro de `WorkerCountModule` por archivos presentes.
- **Smoke conducido (chrome-devtools, data-safe):** respaldar `data/overseer.db` a `data/_smoke-backup-<ts>/`;
  sobre ABRIL: (a) contar chequeos en una `maquinaria` → número en la grilla + punto verde al terminar +
  el Excel generado lleva ese número; (b) repro de F1 — recontar un `charla` y confirmar que detalle y Excel
  coinciden con el visor. Restaurar la DB; **MAYO nunca se toca**.

## 7. Fuera de alcance (3B / 3C)

- **dif_pts** worker-counter + `WORKER_PURPOSE` + caso **N15** (HH capacitación, solo Puerto Varas) → 3B.
- **Indicador de trabajadores en la card del hospital** (M2, Variante B) → 3C.
- **Marks-list highlight de la página actual** (F4) → 3C.
- **Notas-con-estado** (N1, gate ámbar) → 3C.
- Cambiar `scan_strategy` de maquinaria a `none` (optimización, requiere bump de versión) — innecesario para
  correctitud; el resultado del scanner ya se ignora para checks.
- Gating de "OCR la celda" en celdas checks — nice-to-have, no en 3A.

## 8. Riesgos y casos borde

- **Dependencia circular core↔api** (§3.3): la suma de marcas debe vivir en `core/` para que `cell_count.py`
  la use sin importar `api`. Resolver en la primera tarea backend.
- **Perf del filtro present_files:** listar nombres de PDF (glob) es barato; NO abrir PDFs. El builder del
  Excel resuelve la carpeta una vez por celda worker/checks.
- **Retro-compatibilidad:** `present_files=None` mantiene el comportamiento viejo para tests/llamadores no
  migrados → migración incremental sin romper la suite de golpe.
- **maquinaria con escaneo previo:** si una celda checks ya tiene `per_file`/`ocr_count` de un escaneo, la
  rama checks los ignora — el tally manda. Verificar que el smoke cubra una maquinaria con y sin escaneo.
- **Celda checks sin marcas:** `compute_cell_count` → 0; punto ámbar; el Excel escribe 0 (no en blanco) por
  el comportamiento de Incr ("0 en celdas no contadas"). Confirmar consistencia.

## 9. Preguntas abiertas

Ninguna bloqueante. Las dos decisiones de diseño (reusar `worker_marks`; filtro canónico = presentes) fueron
aprobadas por Daniel el 2026-06-16.
