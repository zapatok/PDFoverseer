# Incremento 2 — RN + tratamientos en bloque + tope ≤páginas

**Fecha:** 2026-06-15
**Rama:** `po_overhaul`
**Depende de:** Incr 1A (`per_file_method`, `count_type`, merge incremental) + Incr 1B (punto verde por procedencia, toggle Por archivos·Manual, `parseOverrideInput`).
**Origen de decisiones:** `docs/backlog/2026-06-09-ideas-triage.md` — Decisión B-b (RN), N2 (Aplicar R1), Decisión 4 (tope ≤páginas), Decisión 1 (qué enciende verde). Decisiones de sesión 2026-06-15: páginas **lazy** (no persistir); arreglar el hueco verde de 1B (override-por-archivo) en este increment.

---

## 1. Contexto y objetivo

Tras 1A (fundación de conteo) y 1B (UI honesta), el operador puede ver y corregir
conteos, pero le falta una herramienta para el caso más común de los compilados:
**"este PDF de N páginas son N/k documentos"**. Hoy un `filename_glob` multipágina
queda **Pendiente** (ámbar, sin contar) y la única salida es teclear cada archivo a mano.

**Objetivo de Incr 2:** dar el tratamiento **RN** ("tratar como N páginas por documento")
como **acción en bloque** sobre los archivos pendientes de una celda, que **compone** con
correcciones puntuales y **enciende verde** (es determinístico). Cerrar de paso el tope
`≤ páginas` (lo diferido de 1B) y el hueco verde de 1B (override-por-archivo no encendía
verde). Páginas calculadas **lazy** (sin persistir) — ver §8.

---

## 2. Alcance

### Dentro (Incr 2)
- **RN** = acción en bloque "Aplicar ratio N…" en modo Por archivos: cada archivo
  **Pendiente** recibe `round(páginas ÷ N)` con método `ratio_n`. Solo pendientes.
- **"Aplicar R1"** = ratio N=1 (cierra N2).
- **Chip `RN`** por archivo (método `ratio_n`).
- **Punto verde honesto** vía señal `all_reliable` del backend (reemplaza el proxy
  `confidence` de 1B); RN y override-por-archivo encienden verde correctamente.
- **Tope `conteo ≤ páginas`** en el ajuste manual, solo celdas `count_type == "documents"`.
- **Helper `cell_page_counts(cell, folder)`** (lazy) — única puerta a las páginas.

### Fuera (diferido, con justificación)
- **Persistir `per_file_pages`** → cuando el Incr J (reorganización) lo necesite. Las páginas
  son derivables baratas y su fuente (los PDF) muta justo cuando el Incr J actúa → persistir
  daría staleness. Decidido 2026-06-15. El helper deja la puerta abierta.
- **Incr J (reorganización vía manifiesto)** — promovido a near-term pero es su propio
  increment (L, cross-proyecto). Ver `docs/backlog/2026-06-09-ideas-triage.md` Grupo J.
- **Contador por teclado / maquinaria=chequeos** → Incr 3.
- Redondeo "inteligente" / reparto de resto entre archivos → no; redondeo por archivo simple,
  la excepción se corrige a mano (triage B-b caveat).

---

## 3. Decisiones de origen (verbatim del triage — autoridad)

> Si esta capa entra en conflicto con el triage, **el triage manda**
> (`feedback_anchors_verbatim_at_every_layer`).

**Decisión B-b — RN como método por archivo aplicado en bloque:**
> R1 (1 pág = 1 doc) queda **intacto y automático**. Aparte, **RN** = el operador afirma "N
> páginas por documento". **NO es un tercer modo del selector**. Es una **acción en bloque
> dentro del modo Archivo**: un botón "Tratar como N págs/doc" que pone a *cada archivo
> pendiente* el método ratio (`páginas_del_archivo ÷ N`). Como `Σ(páginas_i ÷ N) == (Σ
> páginas) ÷ N`, el total es el mismo, pero al vivir por archivo **compone** con las
> correcciones. **No pisa lo ya resuelto:** la acción RN cae **solo sobre archivos
> pendientes** — nunca toca R1, ni manual, ni OCR previo. **Regla viva:** recalcula si
> cambian las páginas. Determinístico → confiable, **enciende verde**; set confiable =
> {R1, Manual, RN}. Caveat: redondeo por archivo (3 págs ÷ 2) → se corrige la excepción a
> mano. Los tratamientos en bloque del modo Archivo quedan agrupados: `OCR la celda ·
> Aplicar R1 · Aplicar ratio N…`.

**Decisión 1 — qué enciende verde:**
> El verde se enciende SOLO si: la celda está `confirmed`, **o** tiene override manual de
> celda, **o** *todos* los archivos son **R1 o Manual** (incluida la mezcla). Cualquier
> archivo OCR / Pendiente / Error → ámbar. (Incr 2 añade **RN** al set confiable.)

**Decisión 4 — validación (tope, parte diferida a Incr 2):**
> El tope **`conteo ≤ páginas` aplica SOLO al conteo de documentos** (`count_type ==
> "documents"`). Worker-counting y check-counting no tienen tope.

**N2 — "aplicar R1" a toda la celda:**
> Botón "aplicar R1" (páginas = nº de documentos, ratio por sigla) a **todos** los archivos
> de una celda, de una. (= ratio N=1.)

---

## 4. RN — backend

### 4.1 Endpoint
`POST /api/sessions/{id}/cells/{hospital}/{sigla}/apply-ratio`, body `{ "n": int }` (n ≥ 1).
Síncrono (es `páginas ÷ N`, sin OCR ni ProcessPool). Devuelve el snapshot de la celda
actualizada (como hace el override) y/o broadcast WS para refrescar la lista.

Lógica:
1. Resolver carpeta de la celda (`_find_category_folder`, ya existe).
2. `pages = cell_page_counts(cell, folder)` (lazy, §8).
3. Para cada PDF cuyo **origin actual es `"Pendiente"`** (= `filename_glob` multipágina sin
   override, sin método confiable previo — reusar la misma lógica de `_origin_for`):
   - `count = max(1, round(pages[f] / n))`
   - `mgr.apply_per_file_ocr_result(..., filename=f, count=count, method="ratio_n",
     near_matches=[])` (reusa el merge por-archivo de 1A; escribe `per_file[f]` +
     `per_file_method[f]`). **`near_matches` es obligatorio** (sin default en la firma): RN
     no produce casi-matches → `[]`.
   - Si el PDF no abre (`pages[f] == 0`): saltar, registrar en `errors` (queda Error/Pendiente).
4. `mgr.finalize_cell_ocr(...)` (metadata + `ocr_count = sum(per_file)`), como el OCR.
5. Recalcular `all_reliable` (§6) y persistirlo: `mgr.set_all_reliable(hospital, sigla,
   compute_settled(cell, folder))`.

**Invariante (clobber-guard):** RN **solo** toca archivos `Pendiente`. Nunca R1 (1-pág),
Manual, OCR, ni RN previo. Mismo principio que `_cell_has_work` / Decisión 2. El skip se
decide por el `origin` actual de cada archivo, no por sobreescritura ciega.

### 4.2 Redondeo
`round(pages / n)` (banker's rounding de Python es aceptable; el caveat del triage dice que
la excepción se corrige a mano). `max(1, …)` para que un archivo de 1 página con N grande no
dé 0 documentos.

### 4.3 "Aplicar R1" = N=1
Mismo endpoint con `n=1` → `count = pages[f]` (cada página un documento). No requiere código
aparte; el frontend manda `n=1`.

---

## 5. Chip `RN` y vocabulario de método

`api/routes/sessions.py:_origin_for` — añadir rama: `elif method == "ratio_n": return "RN"`.
Para componer y testear, **extraer** la decisión por-archivo a un helper puro
`file_origin(method, override, page_count, per_file_count) -> str` (módulo-nivel), que tanto
`_origin_for` como `compute_settled` (§6) reusan — fuente única de la semántica de chips.
> **Nota para el plan:** `_origin_for` hoy es una **closure** anidada en `get_cell_files` que
> captura `per_file_method` y `cell_method` del scope. La extracción debe **convertir esas
> capturas en parámetros explícitos** de `file_origin(method, override, page_count,
> per_file_count)`; `_origin_for` pasa a ser un wrapper delgado que resuelve el método por
> archivo y delega.

Frontend:
- `frontend/src/components/OriginChip.jsx` — variante `"RN"` (tono propio; reusar la familia
  de tokens existente, p.ej. un verde/teal distinto del R1 para que se lea "tratado", o el
  mismo tono confiable — definir en plan, sin color crudo).
- `frontend/src/lib/file-origin.js` — `fileCountDisplay`: la rama por defecto **ya** muestra
  `effective_count` para cualquier origin ≠ "Pendiente", así que `"RN"` **ya funciona sin
  cambios funcionales**. Solo añadir el caso a los tests para fijarlo; opcionalmente un comentario.

---

## 6. Punto verde honesto — señal `all_reliable`

### 6.1 El problema (heredado de 1B)
El punto se pinta para las 18 celdas **sin cargar páginas**, así que el frontend no distingue
un `filename_glob` R1 (1 pág) de un Pendiente (multipágina). 1B usó `confidence==="high"` como
proxy. Ese proxy **no cubre RN** (RN no cambia `confidence`) **ni** override-por-archivo de
todos los pendientes (confidence sigue low) → ambos se quedarían ámbar siendo confiables.

### 6.2 La señal
Nuevo campo de celda **`all_reliable: bool`** = "todo archivo de la celda ∈ {R1, RN, Manual}"
(ningún Pendiente / OCR / Revisar / Error). Lo computa el **backend** (tiene las páginas
barato) y lo expone en el objeto de celda. Se calcula con `compute_settled(cell, folder)`:

```
compute_settled(cell, folder):
    pages = cell_page_counts(cell, folder)          # lazy
    files = sorted(folder.rglob("*.pdf"))
    if not files: return False                       # celda vacía no es "lista"
    for f in files:
        origin = file_origin(method=per_file_method.get(f.name) or cell_method,
                             override=per_file_overrides.get(f.name),
                             page_count=pages.get(f.name, 0),
                             per_file_count=per_file.get(f.name))  # .get → None = Pendiente
        if origin not in {"R1", "RN", "Manual"}: return False
    return True
```
> **Nota:** usar `.get()` en todos los accesos — un archivo en la carpeta puede no tener aún
> entrada en `per_file`/`per_file_method` (no escaneado) → `file_origin` lo trata como Pendiente
> (page_count==1 → R1; multipágina → Pendiente). Nunca indexar con `[]`.

### 6.3 Dónde se setea (cobertura de caminos, sin frenar pase-1)
- **`apply_filename_result`** (pase-1, bulk): **NO** abre PDFs (sería lento). El scanner ya
  determinó la confiabilidad: **`all_reliable = (result.confidence == HIGH and bool(result.per_file))`**.
  Para filename_glob / page_count_pure con archivos, `HIGH ⟺ todos R1` → equivalente a
  `compute_settled`. **El `and bool(result.per_file)` es necesario:** `simple_factory` devuelve
  `confidence=HIGH, per_file={}` para una **carpeta vacía/ausente** — sin él, una celda sin
  archivos quedaría `all_reliable=True` (verde), contradiciendo `compute_settled` que devuelve
  `False` para celda vacía (§6.2 `if not files: return False`). Una celda sin PDFs **no** está
  lista. Cheap, consistente con el camino lazy.
- **`finalize_cell_ocr`** (cierre de OCR **y** de RN): el route, que tiene la carpeta, calcula
  `compute_settled(cell, folder)` (lazy; bajo volumen, una vez por celda) y lo persiste vía
  `mgr.set_all_reliable(...)`. Para una celda OCR queda `False` (OCR no confiable); para RN
  queda `True` si todo quedó {R1,RN,Manual}.
- **`apply_per_file_override`** (override por-archivo): el route recalcula `compute_settled` y
  lo persiste → cierra el hueco de 1B (override de todos los pendientes → verde).
- **El I/O de archivos vive en el route / helper, NO en `state.py`** (state.py no abre PDFs).
  `state.py` gana un setter `set_all_reliable(hospital, sigla, value)` y `apply_filename_result`
  setea el booleano desde `result.confidence`.

### 6.4 Frontend (`cell-status.js`)
```
isCellReady(cell) = !!cell.confirmed
                 || hasOverride(cell)
                 || (cell.all_reliable ?? legacyAllReliable(cell))
```
- `cell.all_reliable` (nuevo) manda cuando existe.
- `legacyAllReliable(cell)` = la regla de 1B (`confidence==="high" && !anyUnreliableOcrFile`)
  como **fallback para sesiones viejas** (MAYO no tiene `all_reliable` hasta re-escanear) →
  sin regresión de display. `OCR_METHODS`/`anyUnreliableOcrFile`/`allFilesReliable` de 1B se
  conservan solo para ese fallback.
- `dotVariantFor` sin cambios (precedencia scanning > error > neutral > ready/pendiente).

**Migración:** celdas pre-Incr-2 (MAYO) → `all_reliable` undefined → fallback 1B (comportamiento
idéntico al actual). Re-escanear una celda la migra a la señal nueva. Sin backfill masivo.

---

## 7. Tope `≤ páginas` (Decisión 4)

**Qué celdas:** el tope aplica al **conteo de DOCUMENTOS** de las celdas
`count_type in {"documents", "documents_workers"}`. **`documents_workers`** (charla, chintegral,
dif_pts) **sí cuentan documentos** (esa cifra va a la columna principal del Excel); Decisión 4
exime el conteo de **trabajadores** (campo aparte, contador por teclado), NO el de documentos de
esas celdas. **`checks`** (maquinaria) sí queda sin tope (su número son chequeos = columnas de
fecha, supera las páginas por diseño). `count_type` es sigla-level, vía `scan_info_for` (el
`DetailPanel` ya lo trae en `scanInfo`). Helper de predicado: `count_type_for(sigla) in
{"documents", "documents_workers"}`.

**Backend (autoritativo) — override de CELDA** — ruta `PATCH …/override` (hoy solo valida
`0 ≤ value ≤ 10000`): cuando la sigla es capeable y `value` no es None:
`total = sum(cell_page_counts(cell, folder).values())`; si `value > total` → `HTTP 422`
con `{ "error": "count_exceeds_pages", "max": total }`. Lazy, una vez por guardado.

**Backend (autoritativo) — override POR-ARCHIVO** — ruta `PATCH …/files/{filename}/override`:
mismo principio a granularidad de archivo. Si la sigla es capeable y `value > page_count(filename)`
→ `HTTP 422 { "error": "count_exceeds_pages", "max": page_count }`. Las páginas del archivo se
leen lazy (`cell_page_counts` o abrir ese PDF). Se capea **ambos** niveles porque la inconsistencia
"capear el agregado pero no las partes" sería rara, y el dato ya está disponible.

**Frontend (prevención en vivo):**
- `parseOverrideInput(raw, { maxPages })` gana un parámetro opcional: si `maxPages != null` y
  `value > maxPages` → `{ value: null, valid: false }`.
- **Override de celda:** `OverridePanel` recibe `maxPages` (= total de páginas) y `countType` por
  props desde `DetailPanel`; solo pasa `maxPages` cuando la sigla es capeable. Error inline:
  "máx. {N} (páginas)". El total lo obtiene `DetailPanel` de los datos del file-list (mismo
  `get_cell_files` que `FileList` ya consume; wiring exacto en el plan — levantar el total o un
  fetch ligero, **sin persistir**).
- **Override por-archivo:** la fila del `FileList` (`InlineEditCount`) **ya tiene `f.page_count`** →
  pasar `maxPages = f.page_count` cuando la sigla es capeable. Trivial (el dato está en la fila).

**Por qué backend + frontend:** el backend es la verdad (no se puede colar por la API); el
frontend evita la mala UX de teclear y que rebote. Si el frontend no tiene el total a mano
(p.ej. file-list aún cargando), el backend igual protege.

---

## 8. Helper de páginas lazy

`cell_page_counts(cell, folder) -> dict[str, int]` (en `api/routes/sessions.py` o un util
hermano): para cada `pdf` en `sorted(folder.rglob("*.pdf"))`, `page_count` vía `fitz.open`
(0 si no abre). **Hoy** lee del disco; **mañana** (Incr J) puede leer `cell.get("per_file_pages")`
si existe — punto de extensión único, sin tocar consumidores. Reusa el patrón que `get_cell_files`
ya tiene (extraer el bucle de apertura a este helper y que `get_cell_files` lo use también →
DRY, una sola implementación de "abrir y contar páginas").

---

## 9. Frontend — clúster de acciones en bloque

En `DetailPanel`, **modo Por archivos**, una fila de acciones en bloque agrupadas (Decisión
B-b: `OCR la celda · Aplicar R1 · Aplicar ratio N…`):
- **"Aplicar R1"** → `applyRatio(…, n=1)`.
- **"Aplicar ratio N…"** → revela un input numérico inline (N, default 2) + confirmar →
  `applyRatio(…, n=N)`.
- El botón de OCR de celda existente se agrupa visualmente aquí si ya existe; si no, Incr 2 solo
  añade las dos acciones ratio (no introduce un OCR-por-celda nuevo — eso es otro flujo).
- Solo visibles/activas en modo Por archivos (en modo Manual el total lo manda el override).
- Tras aplicar: refresca el detalle + la lista de archivos (mismo `filesTick` que el OCR
  por-archivo usa) + el punto (vía `all_reliable` del broadcast).

`api/lib/api.js` (frontend) — `applyRatio(sessionId, hospital, sigla, n)`.

---

## 10. Estructura de archivos / unidades

| Archivo | Responsabilidad | Acción |
|---------|-----------------|--------|
| `api/routes/sessions.py` | endpoint `apply-ratio`; `file_origin` extraído; `_origin_for` usa `file_origin` + RN; `cell_page_counts` + `compute_settled`; cap en `patch_override`; recompute `all_reliable` en finalize/override paths | Modify |
| `api/state.py` | `set_all_reliable` setter; `apply_filename_result` setea `all_reliable` desde confidence | Modify |
| `frontend/src/lib/cell-status.js` | `isCellReady` usa `all_reliable ?? legacyAllReliable`; conservar lógica 1B como legacy | Modify |
| `frontend/src/lib/override-input.js` | `parseOverrideInput(raw, {maxPages})` | Modify |
| `frontend/src/lib/file-origin.js` | `"RN"` en `fileCountDisplay` | Modify |
| `frontend/src/components/OriginChip.jsx` | variante `"RN"` | Modify |
| `frontend/src/components/DetailPanel.jsx` | clúster ratio (Por archivos); pasa `maxPages`+`countType` a OverridePanel | Modify |
| `frontend/src/components/OverridePanel.jsx` | cap vía `maxPages`/`countType` | Modify |
| `frontend/src/lib/api.js` | `applyRatio` | Modify |

---

## 11. Estrategia de tests

- **Backend (pytest, fixtures reales — sin mocking de DB):**
  - `apply-ratio`: una celda con pendientes multipágina → cada uno `round(pp/N)`, método
    `ratio_n`; R1/Manual/OCR/RN previos **intactos** (clobber-guard); `n=1` → `count==pp`;
    PDF ilegible → Error, no rompe el resto; total = suma.
  - `file_origin` (helper puro): tabla R1/RN/Manual/OCR/Revisar/Pendiente/Error.
  - `compute_settled`: todo-R1 → True; con un Pendiente → False; con un OCR → False; todo-RN →
    True; mezcla R1+RN+Manual → True; vacía → False.
  - cap celda: `documents`/`documents_workers` + value>total → 422; `checks` sin tope.
  - cap por-archivo: value > páginas del archivo → 422 (siglas capeables); `checks` sin tope.
  - `all_reliable` se setea en finalize/override/filename paths; celda sin archivos → False.
- **Frontend (vitest):**
  - `parseOverrideInput` con `maxPages` (sobre el tope → inválido; igual al tope → válido; sin
    maxPages → comportamiento 1B).
  - `cell-status`: `all_reliable===true` → ready; `false` → no; `undefined` → cae al legacy 1B
    (re-verificar la tabla de 1B intacta en fallback).
  - `fileCountDisplay("RN", n)` muestra el número.
- **Smoke conducido (chrome-devtools, sandbox / con respaldo+restauración como 1B):** una celda
  con compilado pendiente → "Aplicar ratio 2" → archivos pasan a RN con `round(pp/2)`, punto
  **verde**, chip RN; "Aplicar R1" en otra → `count==pp`; tope: teclear > páginas en celda
  `documents` se rechaza; worker/check sin tope. **Sin tocar datos reales sin respaldo.**
- `ruff check .` 0 violaciones; `vitest` + `npm run build` verdes.

---

## 12. Riesgos y mitigaciones

- **Regresión del punto en MAYO** por el cambio de `isCellReady`. Mitigación: fallback
  `all_reliable ?? legacyAllReliable` → celdas sin el campo conservan el comportamiento exacto
  de 1B; el smoke compara MAYO antes/después.
- **`compute_settled` abre PDFs.** Mitigación: solo en mutaciones interactivas (finalize,
  override, RN), una vez por celda; pase-1 usa el atajo `confidence`. Pocos PDFs por celda.
- **RN pisando trabajo resuelto.** Mitigación: skip por `origin == "Pendiente"`; tests del
  clobber-guard; mismo invariante ya probado en 1A/rescan-incident.
- **Redondeo sorprende al operador** (3÷2=2). Mitigación: es el caveat aceptado del triage; el
  número por-archivo queda visible y editable a mano.

---

## 13. Criterios de aceptación

1. "Aplicar ratio N" en una celda con compilados pendientes pone a cada pendiente
   `round(páginas÷N)` con chip **RN**, sin tocar R1/Manual/OCR/RN previos; el total se actualiza.
2. "Aplicar R1" = ratio N=1 (cada página un documento) sobre los pendientes.
3. Una celda cuyos archivos quedan todos {R1, RN, Manual} muestra punto **verde**; si queda un
   OCR/Pendiente/Error → ámbar.
4. Override-por-archivo de **todos** los pendientes ahora **enciende verde** (hueco 1B cerrado).
5. Celdas MAYO (sin `all_reliable`) conservan su color actual (fallback 1B) hasta re-escanear.
6. En celdas `documents` y `documents_workers`, el ajuste manual de **celda** rechaza `valor >
   total de páginas` y el de **archivo** rechaza `valor > páginas de ese archivo` (frontend en
   vivo + backend 422); `checks` (maquinaria) sin tope; negativos/0/vacío como 1B.
7. `ruff` 0, `vitest` + `build` verdes, smoke conducido OK, suite backend verde.

---

## 14. Fuera de alcance — recordatorio

- Persistir `per_file_pages` → Incr J. Reorganización/manifiesto (Incr J, promovido). Contador
  por teclado + maquinaria=chequeos → Incr 3. Multiplayer → después del Incr J.
