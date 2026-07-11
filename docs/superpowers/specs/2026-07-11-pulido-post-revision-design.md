# Pulido post-revisión 2026-07-11 — Diseño

**Origen:** ronda "Fable revisa la app" (2026-07-11): 3 revisores paralelos
(frontend / backend / tests+docs) + revisión directa de core y producto.
~46 hallazgos verificados; Daniel aprobó ejecutar los tracks A (frontend UX),
B (backend) y C (tests+docs) en una ronda determinista. El track D (research
OCR: RCH→paginación, spike tesserocr, modo reorg del visor) va en un spec
aparte con gates eval-first — **NO está en este alcance**.

**Ya corregido durante la revisión (fuera de alcance, no re-hacer):**
- `c173468` — clamp de scrollTop obsoleto en `computeWindow` (lista en blanco
  al filtrar estando scrolleado).
- `697250a` — `pdf_page_progress` se filtra por la identidad de SU celda, no
  por el booleano de la última celda.

**Restricción global:** ningún item de este spec cambia la derivación de
conteos. Guardia de salida: `tools/dump_counts.py` contra una copia del DB en
el commit base vs HEAD debe ser byte-idéntico.

## Convenciones que rigen la ejecución

- TDD rojo-primero donde el item tenga contrato observable; un commit por
  tarea (`type(scope): message`, inglés).
- Frontend: tokens `po-*` únicamente (nunca `/opacity` sobre tokens po-*);
  microcopy español neutro (tú, jamás vos); primitivas en `frontend/src/ui/`.
- Zustand v5: jamás `?? []` / literales frescos dentro de un selector.
- Gates por tarea: `ruff check .` = 0; suites relevantes verdes. Gates de
  cierre: pytest `-m "not slow"` completo, vitest completo, `npm run build`.
- El DB real (`data/overseer.db`) y el corpus (`A:\informe mensual`) no se
  tocan; cualquier smoke usa copia aislada (`OVERSEER_DB_PATH`/
  `OVERSEER_OUTPUT_DIR`).
- Nunca `git add -A`; stagear rutas explícitas.

---

## Track A — Frontend: el loop diario sin fricción

### A1. Cache de files en el store + stale-while-revalidate (mata el flash)

**Defecto.** Tres consumidores fetchean `getCellFiles` por separado con el
mismo trigger `filesTick`: `FileList.jsx:263` (además hace `setFiles(null)` →
Skeleton → remount del `<ul>` en CADA save per-file), `DetailPanel.jsx:285`
(totalPages+nombres) y `PDFLightbox.jsx:209`. Cada guardado produce 2-3 GETs
idénticos y un flash visible; un doble-click rápido en "+" pierde el target
porque el botón desaparece mid-interaction.

**Diseño.** Mover el fetch al store (única fuente):
- Estado nuevo `cellFiles: {}` keyed `` `${hospital}|${sigla}` `` →
  `{ files: array|null, error: string|null }`.
- Acción `fetchCellFiles(sessionId, hospital, sigla)` — la dispara un efecto
  ÚNICO (en el componente contenedor o suscrito al tick dentro del store) por
  cambio de `filesTick[key]` o de celda seleccionada. Deduplicación: si ya hay
  un fetch en vuelo para la misma key+tick, no relanzar.
- **SWR:** al refetch de la MISMA celda, `files` previos se mantienen
  renderizados hasta que resuelve el nuevo (no hay estado null intermedio).
  El Skeleton solo aparece cuando la celda no tiene datos aún (primer open).
- Los 3 consumidores leen del store con selectores por-campo. `FileList`
  elimina su `setFiles`/fetch local; los updates optimistas de steppers/
  InlineEditCount mutan la entrada del store (acción `patchCellFile`).
- Existe un CUARTO consumidor de `getCellFiles`: `WorkerCountViewer.jsx:329`
  — se dispara al abrir el visor, NO por `filesTick`. Queda FUERA de A1
  (conserva su fetch propio); no migrarlo.
- **E1 se simplifica:** el `<ul>` ya no se desmonta en save → el scroll se
  conserva naturalmente. Se mantiene el reset-al-top en cambio genuino de
  celda. El baile `savedScrollRef`/`prevCellKeyRef`/`useLayoutEffect` se
  reduce a ese reset (borrar lo que sobre, conservar el comentario histórico
  en una línea).

**AC.** (1) Un solo GET por bump de tick con FileList+DetailPanel+lightbox
montados (vitest con api mockeada cuenta llamadas). (2) Cero Skeleton en un
save de la misma celda; Skeleton sí en el primer open de una celda sin datos.
(3) Scroll intacto tras save (test de FileList — ver C1). (4) Cambio de celda
resetea scroll al top.

### A2. Errores huérfanos → toasts (fin de los fallos silenciosos)

**Defecto.** El banner de error global solo se renderiza en
`MonthOverview.jsx:231`, pero lo setean acciones que corren en la vista
hospital: `scanOcr` (`session.js:160`), `cancelScan` (`:227`), `scanFileOcr`
(`:177`), `clearNearMatches` (`:210`) y el caso WS `file_scan_error`
(`:1177`). Un fallo ahí es invisible hasta volver al mes (y aparece obsoleto,
sin dismiss).

**Diseño.** Migrar esos 5 paths al patrón U2 existente (`toast.error` con
contexto de celda/archivo en el mensaje, español neutro). Retirar los
`set({ error })` correspondientes. `error` global queda reservado para los
fallos que se RENDERIZAN donde vive el banner (MonthOverview): `openMonth`,
`loadMonths` (`session.js:59`) y el pase-1 `runScan` (`:135`) — esos tres NO
se migran. `generateOutput` deja SOLO el toast (hoy duplica toast + banner).

**AC.** Cada path con test vitest: acción falla → `toast.error` llamado con
mensaje que identifica la operación; `error` global no se setea.

### A3. ReorgMenu → popover portalizado

**Defecto.** `ReorgMenu` es un `<details>` con form `absolute` DENTRO del
`<ul>` scrolleable y ahora virtualizado (`FileList.jsx:117` form, `:420` ul):
en filas bajas el form se recorta; scrollear con el menú abierto desmonta la
fila (ventana virtual) y pierde lo tipeado sin aviso.

**Diseño.** Migrar a Radix Popover (nuevo primitive `ui/Popover.jsx` si no
existe, siguiendo el patrón de los primitives actuales), contenido portalizado
a body. El form interno queda idéntico (mismos campos, misma lógica de
submit). Si la fila ancla se desmonta por scroll, el popover se CIERRA limpio
(comportamiento Radix por defecto) — pérdida aceptada y visible, nunca
recorte ni input fantasma.

**AC.** (1) Popover abre/cierra y crea la op (tests actuales de ReorgMenu
migrados). (2) Renderizado en portal (no descendiente del `<ul>`) — assert
`baseElement` vs `container` en vitest. (3) A11y: focus entra al form al
abrir, Escape cierra.

### A4. InlineEditCount: blur commitea el draft válido

**Defecto.** `InlineEditCount.jsx:103` — blur descarta el draft sin feedback,
mientras el mismo número editado vía OverridePanel autosalva por keystroke.
Dos semánticas para el mismo valor según dónde se edite.

**Diseño.** En blur: si el draft es válido, distinto del valor actual y NO hay
confirmación over-cap pendiente → commit (mismo camino que Enter). Si hay
over-cap pendiente → descartar (comportamiento actual del blur incondicional,
documentado — el patrón mousedown-preventDefault de los botones Sí/No sigue
intacto). Escape sigue siendo descarte explícito.

**AC.** Vitest: (1) tipear valor válido + blur → `onCommit` llamado; (2)
Escape + blur → no commit; (3) over-cap pendiente + blur en otro lado →
descarta (test existente se mantiene); (4) blur con draft inválido → no
commit, editor cierra.

### A5. Cost-guard de OCR: diálogo propio + estimación recalibrada

**Defecto.** `session.js:146-150` usa `window.confirm` (fuera del design
system, bloquea el thread, no puede listar el desglose). Además
`OCR_EST_SECONDS_PER_PDF = 4` (`constants.js:7`) quedó pre-hilos: el aviso
exagera ~4× ("~51 min" por ~13 reales).

**Diseño.**
- `OCR_EST_SECONDS_PER_PDF` → `1` (medido post-threading: ~0.35 s/pág × ~3
  págs promedio ≈ 1 s/PDF; la estimación es orientativa por diseño).
- El guard deja de usar `window.confirm`: la acción `scanOcr` setea
  `pendingScanConfirm = { pairs, totalPdfs, mins }` en el store; un componente
  `ScanConfirmDialog` (sobre `ui/Dialog`) lo renderiza con el desglose (N
  celdas, N PDFs, ETA) y botones Confirmar/Cancelar (español neutro). Confirmar
  invoca la continuación (`_launchScanOcr` interno); Cancelar limpia el estado.
- Umbral `OCR_CONFIRM_PDF_THRESHOLD` no cambia.

**AC.** Vitest: (1) bajo el umbral → lanza directo sin diálogo; (2) sobre el
umbral → `pendingScanConfirm` seteado, `api.scanOcr` NO llamado; (3) Confirmar
→ `api.scanOcr` con los mismos pairs + participant_id; (4) Cancelar → limpio.
`window.confirm` no aparece en `git grep` del src.

### A6. Selectores de `session_id` (re-render de 20 filas por write)

**Defecto.** 9 componentes se suscriben al objeto `session` completo solo para
leer `session_id`: `CategoryRow.jsx:30`, `CategoryGroup.jsx:22`,
`FileList.jsx:215`, `ScanControls.jsx:6`, `CategoryBulkActions.jsx:11`,
`NotePanel.jsx:14`, `OverridePanel.jsx:8`, `PDFLightbox.jsx:178`,
`ScanProgress.jsx:9`. Cada `cell_updated`/`cell_done` re-renderiza todo.

**Diseño.** Cambio mecánico: `useSessionStore((s) => s.session?.session_id)`
en los 9 sitios (verificar que el componente no use OTROS campos de session;
si los usa, selector por-campo para cada uno).

**AC.** Los 9 sitios migrados; suites verdes; grep de
`useSessionStore((s) => s.session)` solo donde el objeto entero es necesario.

### A7. CategoryRow accesible por teclado

**Defecto.** La selección de categoría es `<div onClick>` sin
`tabIndex`/`role`/`onKeyDown` (`CategoryRow.jsx:51-53`) — no hay camino de
teclado para el loop central de la app.

**Diseño.** `role="button"` + `tabIndex={0}` + Enter/Space seleccionan (mismo
handler del click), `focus-visible:ring` con tokens po-*. La navegación
roving ↑/↓ entre filas queda FUERA (YAGNI hasta que Daniel la pida).

**AC.** Vitest: Tab alcanza la fila, Enter la selecciona; axe/aria sin
regresión en los tests existentes.

### A8. Reset de búsqueda/filtros al cambiar de celda

**Defecto.** `search` y `activeOrigins` (`FileList.jsx:225-226`) persisten al
cambiar de celda: un filtro "Manual" activado en una celda filtra la
siguiente en silencio (único cue: el footer "N de M").

**Diseño.** En el cambio genuino de cellKey (el mecanismo `prevCellKeyRef` ya
lo distingue de un tick), resetear `search=""` y `activeOrigins=[]`.

**AC.** Vitest en FileList (C1): filtro activo + cambio de celda → filtros
limpios; tick de la misma celda → filtros intactos.

### A9. Editores debounced: no revertir visualmente mientras el save vuela

**Defecto.** `NotePanel.jsx:25-27` (mismo patrón `OverridePanel.jsx:32-38`):
el resync `if (!focused) setText(cell?.note ?? "")` corre en blur con el store
aún stale → por ~500 ms el textarea muestra el valor ANTERIOR ("se borró lo
que escribí").

**Diseño.** Saltar el resync mientras exista un save pendiente para esa key
(el store ya lleva bookkeeping de pending-saves para el guard F15 — exponer
un selector `hasPendingSave(key)` y consultarlo en ambos paneles antes del
resync). Cuando el save resuelve y el store refleja el valor nuevo, el resync
vuelve a ser no-op inofensivo.

**AC.** Vitest rojo-primero: tipear + blur inmediato → el input NUNCA muestra
el valor viejo; al resolver el save muestra el nuevo; un `cell_updated` remoto
LEGÍTIMO (sin save pendiente) sí resincroniza.

### A10. ReorgHud: destino por defecto = celda origen

**Defecto.** `WorkerCountViewer.jsx:117-118` — defaults `HOSPITALS[0]`/
`SIGLAS[0]` (HPV·reunion siempre); invita a crear extract_pages hacia un
destino incorrecto.

**Diseño.** `destHospital = sourceHospital`, `destSigla = sourceSigla` (el
guard destino≠origen ya bloquea el submit hasta que el operador elija — igual
que hace el ReorgMenu de FileList).

**AC.** Test del guard existente sigue verde; nuevo assert de defaults.

### A11. Label "Escaneando…" mentiroso

**Defecto.** `MonthOverview.jsx:126` muestra "Escaneando…" para cualquier
`loading` global — también durante Generar Excel y openMonth.

**Diseño.** Flags dedicados en el store (`scanning` derivado de
`scanProgress != null && !terminal`; `generating` propio de generateOutput) o
labels por-acción. El botón de scan solo dice "Escaneando…" cuando escanea.

**AC.** Vitest: durante generateOutput el botón de scan NO dice "Escaneando…".

### A12. `ui/Dialog`: nombre accesible del botón cerrar

**Defecto.** `ui/Dialog.jsx:31` — close icon-only sin `aria-label`
(inconsistente con MonthReorgPanel que sí lo pone).

**Diseño.** `aria-label="Cerrar"` en el primitive.

**AC.** Assert en un test existente de cualquier consumidor del Dialog.

---

## Track B — Backend: honesto y robusto

### B1. `scan_file_ocr` recalcula `all_reliable` (verde deshonesto)

**Defecto.** El handler de `file_scan_done` (`api/routes/sessions/scan.py:668-683`)
fusiona con `apply_per_file_ocr_result` + broadcast pero nunca llama
`refresh_all_reliable` — contradice el docstring de `_common.py:329`. Una
celda verde (todo R1) queda verde tras OCR-ear un archivo que resultó
"Revisar"; el broadcast propaga el stale al segundo usuario.

**Diseño.** Tras el merge en ese handler, resolver folder y llamar el
refresher (patrón exacto de `_apply_scan_event`, `scan.py:294-300`). Con B4
shippeado, usar la versión atómica.

**AC.** Test de ruta rojo-primero: celda all_reliable=true, `file_scan_done`
con resultado low-trust → `all_reliable` false en estado y en el
`cell_updated` difundido.

### B2. Self-lend v1.1: devolver la editoría al lanzador

**Defecto.** `agent_claim_cell(lend_from=...)` demota al lanzador a viewer
(`api/state.py:964`) pero `agent_leave` (`:969`) solo borra al agente: tras el
scan el lanzador queda `mode="viewer"`. Ventana real con 2 usuarios: Carla
enfoca la celda → se vuelve editor → el siguiente autosave del lanzador
recibe 409 con un panel que se veía editable.

**Diseño.** Registrar los préstamos en el ctx del scan
(`lent: list[(h, s, launcher_id)]` — el mecanismo exacto para que
`agent_claim_cell` señale "hubo lend" lo decide el plan: cambio de retorno,
out-param o flag; las condiciones de la re-promoción de abajo son las
vinculantes). En el terminal (`scan_complete`/`scan_cancelled`), tras
`agent_leave`: para cada préstamo, nueva primitiva
`PresenceRegistry.promote_to_editor(session_id, cell, participant_id)` —
solo si ese participante sigue vivo, sigue `focused_cell == cell` y la celda
NO tiene editor (nunca destrona a nadie). Pass-through `@_synchronized` en el
manager. Broadcast presence después (ya existe en ese branch).

**AC.** Unit: lend → scan termina → lanzador vuelve a editor; si el lanzador
cambió de foco mientras tanto → no se promueve; si otro humano ya es editor →
no se destrona. Handler-level: secuencia completa con eventos sintéticos.

### B3. Pase-1 con self-lend (simetría con pase-2)

**Defecto.** `POST /sessions/{id}/scan` salta cualquier celda con holder
humano (`scan.py:181-198`) incluido el lanzador; su body (`ScanRequest`,
`scan.py:145`) ni siquiera lleva `participant_id`. El rescan del mes salta en
silencio la celda que tienes abierta.

**Diseño.** `ScanRequest` gana `participant_id: str | None = None` (forbid ya
está). En el check de skip: si `holder["participant_id"] ==
body.participant_id` → NO saltar y proceder (pase-1 no reclama celdas — sin
demote ni badge; los clobber-guards existentes de `apply_filename_result`
protegen el trabajo previo, y el lanzador pidió el rescan). Frontend:
`api.scan()` envía `getParticipantId()`. El skip de holders AJENOS queda
idéntico (incluido su `skipped` en la respuesta).

**AC.** Test de ruta: lanzador enfocado en una celda + POST scan con su
participant_id → la celda NO aparece en `skipped` y su estado se actualiza;
con holder ajeno → sigue en `skipped`.

### B4. `refresh_all_reliable` atómico

**Defecto.** `_common.py:330-340` — read-compute-write en DOS adquisiciones
del RLock (get_session_state → set_all_reliable, con `compute_settled` puro
entre medio), la misma clase de carrera que F4 cerró para los deltas reorg.
Interleaving durante un batch puede persistir un `all_reliable` calculado
contra estado viejo.

**Diseño.** Nuevo método `SessionManager.recompute_all_reliable(session_id,
hospital, sigla, *, pages, count_type)` `@_synchronized`: load→compute→persist
en UNA adquisición. `pages` (I/O de disco) se computa FUERA del lock, como
hoy; `compute_settled` es puro. **El gate anti-colados que hoy vive en el
cuerpo del refresher (`_common.py:332-334`,
`has_open_counted_suspects(...)` → `and not blocked`) SE MUEVE ADENTRO del
método atómico** — un suspect contado abierto sigue bloqueando el verde
(§4.5); omitirlo sería regresión. `_common.refresh_all_reliable` delega en él
(firma pública sin cambios para los callers).

**AC.** Unit del método nuevo (compute con estado fresco bajo el lock);
callers sin cambios; suites verdes.

### B5. Pre-skip de celdas bloqueadas antes de encolar workers

**Defecto.** El skip de `_handle_scan_progress` solo suprime eventos: el
worker ya fue submitted (`ocr_scan.py:355`) y OCR-ea la celda COMPLETA para
botar el resultado — minutos de CPU quemados, el batch handle ocupado, y un
crash de esa celda aún emite `cell_error` visible para una celda "saltada".

**Diseño.** En la ruta `scan_ocr`, ANTES de armar `cells_with_paths`: chequear
el lock de cada celda (`presence_lock_holder(exclude=AGENT)`, con la exención
self-lend de `launcher_id`). Las bloqueadas: se excluyen de `cells_with_paths`
y de `total_pdfs`, se siembran en `ctx["skipped_set"]`/`skipped_cells`, y se
emite un `cell_skipped` por cada una (mismo shape que hoy). **Punto de
emisión:** `scan_started` lo emite el orquestador dentro del `_run` pooleado
(`ocr_scan.py:193`), así que los `cell_skipped` pre-sembrados se FLUSHEAN
cuando `scan_started` pasa por `_handle_scan_progress` (nuevo branch: al ver
`scan_started`, emitirlo y a continuación un `cell_skipped` por entrada
pre-sembrada) — nunca antes, para preservar el orden observable. El skip del
drain QUEDA como red para claims que aparezcan en vuelo (entre el pre-check y
el `cell_scanning` del worker).

**AC.** Test de ruta: 2 celdas, una bloqueada por humano ajeno → el
ProcessPool recibe SOLO la libre (spy sobre `scan_cells_ocr`: su arg `cells`),
`scan_started.total_pdfs` excluye la bloqueada, `cell_skipped` emitido, y
`scan_complete.skipped` la lista. El test handler-level de carrera en vuelo
existente se mantiene.

### B6. `POST /sessions`: modelo con forbid + bounds

**Defecto.** `lifecycle.py:26` — `body: dict = Body(...)` escapa la doctrina
`extra="forbid"`; `year` sin cota permite acuñar filas de sesión huérfanas
(`year=99999` → id que `_validate_session_id` luego rechaza).

**Diseño.** Modelo Pydantic `OpenSessionRequest` con
`ConfigDict(extra="forbid")`, `year: int = Field(ge=2020, le=2100)`,
`month: int = Field(ge=1, le=12)`. Semántica de error: 422 de validación
(consistente con el resto de la superficie forbid). **Decisión registrada:**
el `year`/`month` faltante o inválido hoy responde 400 (`lifecycle.py:32-33`)
y pasa a 422 — cualquier test existente que pinee ese 400 se ACTUALIZA a 422
como parte del item.

**AC.** Tests: key extra → 422; year fuera de rango → 422; camino feliz
idéntico; tests que pineaban 400 migrados a 422.

### B7. Leak del batch handle si el dispatch falla

**Defecto.** `register_batch_handle` instala el handle (`batch.py:54`) pero el
`pop` vive solo en el `finally` de `_run`; si `_DISPATCH_POOL.submit` lanza
(`scan.py:579` y `:710`), el slot queda ocupado → todo scan posterior de esa
sesión recibe 409 "another batch is already running" hasta reiniciar.

**Diseño.** try/except alrededor del submit (ambos sitios): en fallo,
`app.state.batches.pop(session_id, None)` y re-raise (500 honesto).

**AC.** Test: submit monkeypatcheado para lanzar → la ruta propaga el error Y
un segundo intento NO recibe 409.

### B8. Nits de consistencia (un commit, items mecánicos)

1. `POST /sessions/{id}/cancel` (`scan.py:583`): añadir
   `_validate_session_id` (400 por formato, como el resto del paquete).
2. `apply_ratio` (`scan.py:141-142`): pasar la respuesta por
   `enrich_cell_worker_count` + `enrich_cell_colado_suspects` (patrón
   `writes.py:320-328`) — hoy devuelve la celda cruda, distinta del broadcast.
3. Retirar el shim deprecado `apply_cell_result` (`state.py:898`): su único
   caller productivo (`scan.py:199`) pasa a `apply_filename_result`; ajustar
   el docstring del RLock (`state.py:96-99`) que lo cita como razón de
   reentrancia.
4. `output.py:216` — quitar el `body` muerto; `:281` — quitar el
   `mgr._conn.commit()` ritual (la conexión es autocommit,
   `connection.py:34`); dejar UNA línea de comentario honesto: los ~80
   upserts de historia son statements independientes (crash a mitad = historia
   parcial; se auto-corrige en el próximo export).
5. Purga del `_PAGE_COUNT_CACHE` al abrir sesión (`POST /sessions` →
   `_PAGE_COUNT_CACHE.clear()`): evita crecimiento sin cota entre meses y
   cierra el agujero teórico preserve_date del corpus reescrito por paso-1.
   Documentar la suposición en el comentario del cache.
6. `output.py:28-30` — docstring de `_method_for_history` reescrito citando
   `_OCR_METHODS` (`_common.py:55`) como fuente (hoy cita métodos muertos).

**AC.** Cada item con su assert (o suite existente verde si es puro retiro);
ruff 0.

**Diferidos con razón (NO hacer en esta ronda):** cola de salida por WebSocket
(B14 del reporte — mitigado por snapshots idempotentes; medir antes) y
batching de `pdf_done` en el drain (B5 del reporte — churn O(blob) real pero
solo duele en batches masivos; medir con los hilos nuevos primero).

---

## Track C — Tests + suite + docs

### C1. `FileList.test.jsx` (nuevo)

Pinear, post-A1/A8: (1) con 100 archivos solo se montan ~visible+overscan
`<li>` + 2 spacers cuya suma de alturas = `total*ROW_H`; (2) la búsqueda
encuentra archivos fuera de la ventana (filtra pre-slice); (3) regresión del
shrink-por-filtro con scroll profundo (hotfix `c173468`) a nivel componente;
(4) SWR: save de la misma celda no muestra Skeleton y conserva scroll; cambio
de celda resetea scroll y filtros (A8).

### C2. Motores threaded: error a mitad del pool

`pagination_count.py` y `header_band_anchors.py`: monkeypatch de
`_corner_text`/`render_page_region` que lanza en una página con
`ocr_threads>=2` → `pytest.raises` propaga (nunca `parsed` parcial silencioso),
el executor no cuelga, y en paginación los docs thread-local se CIERRAN
(spy sobre `fitz.open` contando `close()`).

### C3. `pdf_page_progress` en el frontend

Vitest: reducer (`session.js` — set de `page`/`pagesTotal`/`pageCell`, y el
reset a null en el siguiente `pdf_progress`) + render de "pág. X/Y" en
`ScanProgress`.

### C4. Self-lend end-to-end por HTTP

Test de ruta (patrón de los existentes en `test_scanner_lock_skip.py` /
integración): POST `/scan-ocr` con `{cells, participant_id: <holder>}` → su
celda NO aparece en `skipped`; con `participant_id` ajeno → sí. (Cierra el
único eslabón sin ejercitar: `body.participant_id → ctx["launcher_id"]`.)

### C5. Dieta de la suite (~35-50 s)

1. `eval/tests/test_pagination_benchmark.py`: fixture module-scoped que corre
   `run_benchmark` UNA vez y comparte `rows` (solo `skips_missing_glob` y
   `temp_dir_cleaned_up` conservan corrida propia) — ahorra ~15-18 s.
2. Setups de integración: fixture module-scoped para clusters read-only
   (empezar por `test_forbid_extra_keys.py`, ~14 s de setup para 8 tests de
   422), RESPETANDO la lección de aislamiento DB del 2026-07-03 (el env
   monkeypatch a tmp_path sigue por-módulo).
3. Autouse `_PAGE_COUNT_CACHE.clear()` en el conftest de `tests/unit/api/`
   (blinda contra hits heredados entre tests con paths reutilizados).
4. Dedup de helpers: `_make_pdf` (7 copias) y `_make_manager` (4 copias) →
   fixtures en el conftest raíz (precedente: `make_pagination_pdf`).

### C6. Docs al día

1. `api/CLAUDE.md`: añadir `GET /sessions/{id}/presence` a la línea de
   presence; `OVERSEER_OCR_THREADS` a la tabla de env vars; self-lend +
   `participant_id` en la línea de scan.py.
2. `CLAUDE.md` raíz: la entrada M3b que dice "No lock-lending endpoint (§8 —
   the edge is conversational)" gana el puntero "superseded 2026-07-11:
   self-lend"; Pending Work refleja el batch post-ronda (commits
   `780856f..697250a`) y esta ronda al cierre.
3. `tools/README.md`: documentar `survey_form_codes.py`; borrar el comentario
   zombi "Replace with the import once Task 12 lands"
   (`tools/survey_form_codes.py:47-51` — Task 12 se abortó).

---

## Orden de ejecución sugerido (el plan lo detalla)

1. **B4 → B1** (el refresher atómico primero; B1 lo consume).
2. **B2 → B3 → C4** (cluster self-lend completo con su test e2e).
3. **B5, B6, B7, B8** (independientes).
4. **A1 → A8 → C1** (cache SWR primero; el test de FileList pinea el estado
   final).
5. **A2–A7, A9–A12** (independientes entre sí).
6. **C2, C3, C5, C6** (cierran la ronda).

## Gates de cierre de la ronda

- pytest `-m "not slow"` completo verde; vitest completo verde; ruff 0;
  `npm run build` OK.
- OUTPUT GUARD: `tools/dump_counts.py --db <copia>` en commit base vs HEAD →
  byte-idéntico.
- Push de `po_overhaul` + tag `pulido-post-revision`.
- Si ejecuta Opus: leer este spec + el plan; las convenciones del encabezado
  son vinculantes; ante ambigüedad, la decisión registrada aquí manda sobre
  cualquier inferencia del código.
