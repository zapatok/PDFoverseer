# Pulido post-revisión 2026-07-11 — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development
> (if subagents available) or superpowers:executing-plans to implement this plan.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ejecutar los tracks A (frontend UX), B (backend) y C (tests+docs) del
spec `docs/superpowers/specs/2026-07-11-pulido-post-revision-design.md`.

**Architecture:** 26 items quirúrgicos sin cambio de derivación de conteos:
cache SWR de files en el store Zustand, cluster self-lend v1.1 en el registro
de presencia, refresher `all_reliable` atómico bajo el RLock único, pre-skip de
celdas bloqueadas antes del ProcessPool, y una capa de tests/docs que pinea el
estado final.

**Tech Stack:** Python 3.10+/FastAPI/SQLite (backend), React+Vite+Zustand v5+
Tailwind po-* (frontend), pytest + vitest.

---

## Contexto para el ejecutor (LEER PRIMERO)

- **El spec es la autoridad de diseño.** Cada task cita su sección
  (`§A1`…`§C6`); el detalle de defecto/diseño/AC vive ahí. Si este plan y el
  spec difieren, manda el spec. Ruta:
  `docs/superpowers/specs/2026-07-11-pulido-post-revision-design.md`.
- Trabajar directo en `po_overhaul` (convención del repo, sin worktrees).
- Comandos base (desde `a:/PROJECTS/PDFoverseer`):
  - Backend: `source .venv-cuda/Scripts/activate && python -m pytest <ruta> -q`
  - Frontend: `cd frontend && npx vitest run <ruta>`
  - Lint: `ruff check .` (0 violaciones antes de cada commit)
- Microcopy nueva: español neutro (tú, jamás vos). Clases Tailwind: SOLO
  tokens `po-*`; jamás `/opacity` sobre un token po-*.
- Zustand v5: jamás `?? []` ni literales frescos DENTRO de un selector.
- El DB real (`data/overseer.db`) y el corpus (`A:\informe mensual`) no se
  tocan. Nunca `git add -A` (stagear rutas explícitas).
- **OUTPUT GUARD (cierre):** `python tools/dump_counts.py --db <copia>` en el
  commit base vs HEAD → byte-idéntico (Task 26).

---

## Chunk 1: Backend — confiabilidad atómica (§B4 → §B1)

### Task 1: `recompute_all_reliable` atómico en SessionManager (§B4)

**Files:**
- Modify: `api/state.py` (nuevo método junto a `set_all_reliable`)
- Modify: `api/routes/sessions/_common.py:305-345` (`refresh_all_reliable`
  delega; el gate anti-colados se MUEVE al método)
- Test: `tests/unit/api/test_all_reliable_atomic.py` (nuevo)

- [ ] **Step 1: Test rojo** — en el archivo nuevo, con el idioma de
  `tests/unit/api/test_agent_claim.py` (`_make_manager` sobre tmp_path):
  (a) `recompute_all_reliable` persiste el valor que `compute_settled` da con
  el estado FRESCO leído bajo el lock (sembrar celda, llamar, assert en
  estado); (b) **gate anti-colados**: celda con `colado_suspects` abierto
  contado → `all_reliable` False aunque `compute_settled` diera True (usar el
  shape de suspect de `tests/unit/api` existentes que ejercitan
  `has_open_counted_suspects`).
- [ ] **Step 2:** Correr: `python -m pytest tests/unit/api/test_all_reliable_atomic.py -q` → FAIL (método no existe).
- [ ] **Step 3: Implementar** en `api/state.py`:

```python
@_synchronized
def recompute_all_reliable(
    self, session_id: str, hospital: str, sigla: str, *,
    pages: dict[str, int], count_type: str,
) -> bool:
    """Load→compute→persist de all_reliable en UNA adquisición del RLock (§B4).

    ``pages`` se computa FUERA (I/O de disco); compute_settled es puro. El
    gate anti-colados (§4.5) vive aquí: un suspect contado abierto bloquea
    el verde aunque los archivos estén settled.
    """
    state = self._load_state(session_id)          # usar el helper interno real
    cell = state["cells"][hospital][sigla]
    settled = compute_settled(cell, pages=pages, count_type=count_type)
    blocked = has_open_counted_suspects(
        cell.get("colado_suspects") or [], state.get("reorg_ops") or [],
        hospital, sigla,
    )
    value = settled and not blocked
    cell["all_reliable"] = value
    self._persist_state(session_id, state)        # usar el helper interno real
    return value
```

  Ajustar nombres de helpers internos a los reales de `state.py` (leer cómo
  `set_all_reliable` carga/persiste y calcar: `_load_and_migrate` +
  `update_session_state`). **OJO firma real:** `compute_settled(cell, folder,
  pages=None, count_type=None)` (`_common.py:277`) tiene `folder` posicional
  — threadear `folder` a `recompute_all_reliable(…, folder, *, pages,
  count_type)` y pasarlo. Hoy, con `pages=None`, el walk de disco ocurre
  DENTRO de `compute_settled` (`:293-294`): ese walk SE MUEVE al wrapper —
  `_common.refresh_all_reliable` llama `cell_page_counts(folder)` cuando
  `pages is None` y delega con pages ya resueltas (ese es el punto de §B4:
  I/O fuera del lock). `compute_settled` / `has_open_counted_suspects`: el
  import circular real es api.state ↔ `_common` (que importa de api.state) —
  import local plano dentro del método.
  Firma pública de `refresh_all_reliable` SIN cambios para los callers.
- [ ] **Step 4:** Correr el test nuevo → PASS. Correr
  `python -m pytest tests/unit/api -q` → verde (los callers no cambian).
- [ ] **Step 5: Commit** — `fix(api): atomic recompute_all_reliable under a single lock acquisition`

### Task 2: `scan_file_ocr` recalcula `all_reliable` (§B1)

**Files:**
- Modify: `api/routes/sessions/scan.py:668-683` (handler de `file_scan_done`)
- Test: `tests/unit/api/test_scan_file_ocr_reliability.py` (nuevo) o el archivo
  existente que ya ejercita `file_scan_done` (buscar `file_scan_done` en
  tests/ y extenderlo si existe).

- [ ] **Step 1: Test rojo** — celda con `all_reliable=True` sembrado;
  simular el flujo de `file_scan_done` con resultado low-trust (calcar el
  arnés del test existente de scan_file_ocr); assert: estado queda
  `all_reliable=False` Y el `cell_updated` difundido lo lleva.
- [ ] **Step 2:** Correr → FAIL (queda True).
- [ ] **Step 3: Implementar** — tras el merge (`apply_per_file_ocr_result`) en
  el handler, llamar `refresh_all_reliable(...)` ANTES de construir el evento
  `cell_updated`. Nota: la closure de la ruta YA tiene `folder` en scope
  (`scan.py:628`) — usarlo directo; si no aplica, resolver con el patrón de
  `_apply_scan_event` (`scan.py:294-300`).
- [ ] **Step 4:** Correr test → PASS; `python -m pytest tests/ -q -m "not slow" -k "scan_file or reliability"` verde.
- [ ] **Step 5: Commit** — `fix(api): scan_file_ocr recomputes all_reliable (dishonest green)`

---

## Chunk 2: Backend — self-lend completo (§B2 → §B3 → §C4)

### Task 3: re-promoción del lanzador al terminar el scan (§B2)

**Files:**
- Modify: `api/presence.py` (nueva primitiva `promote_to_editor`, junto a
  `demote_to_viewer`)
- Modify: `api/state.py:932-978` (`agent_claim_cell` señala el lend;
  pass-through `promote_lender`)
- Modify: `api/routes/sessions/scan.py` (`ctx["lent"]`, branch terminal)
- Test: `tests/unit/api/test_agent_claim.py` + `tests/integration/test_scanner_lock_skip.py`

**Mecanismo del lend-signal (decisión del plan, spec lo delega):**
`agent_claim_cell` conserva su retorno `dict | None`; se añade un parámetro
opcional de salida por lista: `lent_out: list | None = None` — si hubo lend,
apendea `(hospital, sigla, lend_from)`. Cero cambio para los callers actuales.

- [ ] **Step 1: Tests rojos** (en `test_agent_claim.py`, sección self-lend):
  (a) lend → `agent_leave` → `promote_lender` re-promueve: lanzador vuelve a
  `mode="editor"`; (b) si el lanzador cambió de foco → NO se promueve;
  (c) si otro humano ya es editor de la celda → NO se destrona (sigue ese
  humano); (d) lanzador con lease expirado → no-op.
- [ ] **Step 2:** Correr → FAIL.
- [ ] **Step 3: Implementar**:

```python
# api/presence.py — junto a demote_to_viewer
def promote_to_editor(self, session_id: str, cell: str, participant_id: str) -> bool:
    """Re-promueve al lender tras el scan (§B2). Solo si sigue vivo, sigue
    enfocado en `cell` y la celda NO tiene editor — jamás destrona. Caller
    holds the RLock. True iff cambió el registro."""
    self._purge_expired(session_id)
    rec = self._participants.get(session_id, {}).get(participant_id)
    if rec is None or rec["focused_cell"] != cell or rec["mode"] == "editor":
        return False
    if self._editor_of(session_id, cell) is not None:
        return False
    rec["mode"] = "editor"
    return True
```

  En `state.py`: `agent_claim_cell(..., lend_from=None, lent_out=None)` —
  en el branch de lend, `if lent_out is not None: lent_out.append((hospital,
  sigla, lend_from))`. Nuevo pass-through `@_synchronized promote_lender(
  session_id, hospital, sigla, participant_id)` → `promote_to_editor`.
  En `scan.py`: `ctx["lent"] = []`; el call-site de `cell_scanning` pasa
  `lent_out=ctx["lent"]`; en el branch terminal (`scan_complete`/
  `scan_cancelled`, tras `mgr.agent_leave`): `for h2, s2, pid in ctx["lent"]:
  mgr.promote_lender(session_id, h2, s2, pid)` — el broadcast de presence ya
  existe en ese branch, queda DESPUÉS de las promociones. Nota consciente: el
  crash-path de `_run` (`scan.py:541-557`) también hace `agent_leave` pero NO
  promueve — decisión spec-aligned (§B2 solo cubre el terminal; tras un crash
  el lanzador se auto-sana al re-enfocar); dejar un comentario de una línea
  ahí.
- [ ] **Step 4:** Correr `test_agent_claim.py` + `test_scanner_lock_skip.py` → verdes (añadir un handler-level test: lend → scan_complete → snapshot muestra al lanzador editor de nuevo).
- [ ] **Step 5: Commit** — `feat(scan): self-lend v1.1 — the lender gets editorship back at scan end`

### Task 4: pase-1 con self-lend (§B3)

**Files:**
- Modify: `api/routes/sessions/scan.py:145-153` (`ScanRequest` +
  `participant_id`), `:178-198` (check de skip con exención del lanzador)
- Modify: `frontend/src/lib/api.js` (`scan` envía participant_id) +
  `frontend/src/store/session.js` (`runScan` lo pasa)
- Test: el archivo que hoy cubre el skip de pase-1 (buscar
  `test_pase1` / `skipped` en tests de scan) — extender.

- [ ] **Step 1: Test rojo** — lanzador enfocado en HRB|odi + POST `/scan` con
  `{"participant_id": "<launcher>"}` → `skipped` NO contiene esa celda y su
  estado se actualizó; con holder AJENO → sigue en `skipped`.
- [ ] **Step 2:** Correr → FAIL.
- [ ] **Step 3: Implementar** — `ScanRequest` gana
  `participant_id: str | None = None`. En el loop de skip: tras obtener
  `holder`, `if holder is not None and holder.get("participant_id") ==
  body.participant_id: holder = None` (comentario: pase-1 no reclama — sin
  demote ni badge; los clobber-guards de `apply_filename_result` protegen, y
  el lanzador pidió el rescan §B3). Frontend: `api.js scan(sessionId, scope,
  participantId=null)` → body `{scope, participant_id}`; `runScan` pasa
  `getParticipantId()`.
- [ ] **Step 4:** Correr tests de scan pase-1 + vitest de api.js si existe → verdes.
- [ ] **Step 5: Commit** — `feat(scan): pase-1 self-lend — month rescan no longer skips the launcher's own cell`

### Task 5: self-lend end-to-end por HTTP (§C4)

**Files:**
- Test: `tests/integration/test_scanner_lock_skip.py` (o el archivo de
  integración de scan-ocr existente con TestClient — usar el que ya tenga el
  arnés `with TestClient(create_app()) as client` + WS/polling del batch).

- [ ] **Step 1: Test nuevo** — POST `/api/sessions/{id}/scan-ocr` con
  `{cells: [[h, s]], participant_id: <holder de esa celda>}` → esperar el
  terminal del batch → `scan_complete.skipped` (o el estado post-scan) NO
  contiene la celda; segundo caso con `participant_id` ajeno → sí la contiene.
  Si el arnés de batch-por-HTTP resulta frágil (pool real), fallback aceptado:
  test de la RUTA que verifique `ctx["launcher_id"]` == body.participant_id
  monkeypatcheando `scan_cells_ocr` para capturar el `on_progress` y dispararle
  un `cell_scanning` sintético — lo vinculante es cubrir el eslabón
  `body.participant_id → ctx → agent_claim_cell(lend_from=...)` por HTTP.
- [ ] **Step 2:** Correr → verde (la feature ya existe; este test PINEA el
  eslabón HTTP que hoy nadie ejercita — si falla, hay bug real: investigar).
- [ ] **Step 3: Commit** — `test(scan): pin the HTTP participant_id -> self-lend wiring end-to-end`

---

## Chunk 3: Backend — robustez (§B5, §B6, §B7, §B8)

### Task 6: pre-skip de celdas bloqueadas antes del pool (§B5)

**Files:**
- Modify: `api/routes/sessions/scan.py` (ruta `scan_ocr`: filtro antes de
  `cells_with_paths`; siembra de ctx; branch de flush en
  `_handle_scan_progress` al ver `scan_started`)
- Test: `tests/integration/test_scanner_lock_skip.py`

- [ ] **Step 1: Tests rojos** — (a) ruta: 2 celdas, una con holder ajeno →
  spy sobre `scan_cells_ocr` recibe SOLO la libre y `total_pdfs` la excluye;
  (b) handler: ctx pre-sembrado con 1 skip → al pasar `scan_started` se emite
  `scan_started` seguido de exactamente 1 `cell_skipped` (shape idéntico al
  actual: hospital/sigla/reason/lock_holder); (c) `scan_complete.skipped` la
  lista una sola vez (sin duplicado del drain).
- [ ] **Step 2:** Correr → FAIL.
- [ ] **Step 3: Implementar** según §B5 (pre-check con
  `presence_lock_holder(exclude=AGENT_PARTICIPANT_ID)` + exención
  self-lend por `launcher_id`; las bloqueadas se apartan de
  `cells_with_paths`/`total_pdfs`, se siembran en
  `ctx["skipped_set"]`/`skipped_cells` + `ctx["preseeded_skips"]` con el
  holder; el branch de `scan_started` en `_handle_scan_progress` emite el
  evento y luego un `cell_skipped` por entrada pre-sembrada). El skip del
  drain queda como red (in-flight).
- [ ] **Step 4:** Correr el archivo completo → verde.
- [ ] **Step 5: Commit** — `perf(scan): pre-skip locked cells before submitting workers (no wasted OCR)`

### Task 7: `POST /sessions` con modelo forbid + bounds (§B6)

- [ ] **Step 1: Tests rojos** en el archivo que cubre lifecycle: key extra →
  422; `year=99999` → 422; `month=13` → 422; camino feliz idéntico. Buscar y
  MIGRAR cualquier test que pinee el 400 actual (`lifecycle.py:32-33`) a 422
  (decisión registrada §B6).
- [ ] **Step 2:** Correr → FAIL.
- [ ] **Step 3:** Implementar `OpenSessionRequest` (ConfigDict extra="forbid",
  `year: int = Field(ge=2020, le=2100)`, `month: int = Field(ge=1, le=12)`)
  en `api/routes/sessions/lifecycle.py`; la ruta lo consume.
- [ ] **Step 4:** Correr lifecycle + forbid suites → verdes.
- [ ] **Step 5: Commit** — `fix(api): POST /sessions joins the extra=forbid surface with year/month bounds`

### Task 8: leak del batch handle si el dispatch falla (§B7)

- [ ] **Step 1: Test rojo** — monkeypatch `_DISPATCH_POOL.submit` para lanzar
  → la ruta propaga el error Y un segundo POST NO recibe 409.
- [ ] **Step 2:** Correr → FAIL (segundo POST da 409).
- [ ] **Step 3:** try/except alrededor de ambos submits (`scan.py:579`, `:710`):
  `app.state.batches.pop(session_id, None)` + re-raise.
- [ ] **Step 4:** Correr → PASS.
- [ ] **Step 5: Commit** — `fix(api): release the batch handle when dispatch fails (eternal 409)`

### Task 9: nits de consistencia §B8 (un commit)

Los 6 items de §B8, cada uno con su assert mínimo (o suite verde si es
retiro puro): (1) `_validate_session_id` en cancel (`scan.py:583`);
(2) `apply_ratio` enriquecida (patrón `writes.py:320-328`); (3) retiro del
shim `apply_cell_result` (`state.py:898`; caller `scan.py:199` →
`apply_filename_result`; ajustar docstring del RLock `state.py:96-99`);
(4) `output.py:216` body muerto + `:281` commit ritual fuera, con el
comentario honesto de §B8.4; (5) `_PAGE_COUNT_CACHE.clear()` en POST
/sessions + comentario preserve_date; (6) docstring `_method_for_history`
(`output.py:28-30`) citando `_OCR_METHODS`.

- [ ] **Step 1:** Tests/asserts según cada item (rojo donde aplique).
- [ ] **Step 2:** Implementar los 6.
- [ ] **Step 3:** `python -m pytest tests/ -q -m "not slow"` verde + ruff 0.
- [ ] **Step 4: Commit** — `fix(api): consistency nits — cancel validation, enriched apply_ratio, dead shim/body, cache purge, docstrings`

---

## Chunk 4: Frontend — cache SWR de files (§A1 → §A8 → §C1)

### Task 10: store `cellFiles` + fetch único + SWR (§A1)

**Files:**
- Modify: `frontend/src/store/session.js` (estado `cellFiles`, acciones
  `fetchCellFiles`/`patchCellFile`; el bump de `filesTick` dispara el fetch)
- Test: `frontend/src/store/session.cellFiles.test.js` (nuevo; idioma de los
  `session.*.test.js` existentes, api mockeada)

- [ ] **Step 1: Tests rojos** — (a) `fetchCellFiles` puebla
  `cellFiles["H|s"]`; (b) bump de tick de la MISMA celda: los files previos
  QUEDAN hasta que el nuevo fetch resuelve (SWR — assert intermedio con
  promesa pendiente); (c) dedup: dos bumps con fetch en vuelo → 1 sola
  llamada api extra como máximo; (d) `patchCellFile` muta la entrada
  (optimista de steppers); (e) error de fetch → `error` en la entrada, files
  previos intactos; (f) **primer open de una celda** (sin entrada previa en
  `cellFiles`) → fetch disparado — ver el segundo trigger del Step 3.
- [ ] **Step 2:** `npx vitest run src/store/session.cellFiles.test.js` → FAIL.
- [ ] **Step 3:** Implementar en el store. Forma:
  `cellFiles: {}` → `{ [key]: { files, error, fetchedTick } }`. **DOS
  triggers** (§A1): (1) los bumps de `filesTick` — todos viven en el store
  (~8 sitios: session.js:244/:438/:470/:489/:953/:1002/:1134/:1166), cada
  bump llama `fetchCellFiles`; (2) el **cambio de celda seleccionada** — la
  selección es estado local de `HospitalDetail.jsx:18`, INVISIBLE al store:
  mantener UN efecto delgado (en HospitalDetail, junto al `setFocus` de
  `:23-27` que ya espeja la selección, o en FileList) que llame
  `fetchCellFiles` en el cambio genuino de celda — ese cubre el primer open.
  Fuera de esos dos, ningún componente fetchea.
- [ ] **Step 4:** Correr → PASS.
- [ ] **Step 5: Commit** — `feat(web): store-level cellFiles cache with stale-while-revalidate`

### Task 11: migrar los tres consumidores (§A1 cont.)

**Files:**
- Modify: `frontend/src/components/FileList.jsx` (borra fetch/`setFiles`
  local; lee del store; conserva SOLO el reset de scroll en cambio de celda),
  `frontend/src/components/DetailPanel.jsx:285`,
  `frontend/src/components/PDFLightbox.jsx:209`.
  **NO tocar** `WorkerCountViewer.jsx:329` (cuarto consumidor, fuera de
  alcance §A1).

- [ ] **Step 1:** Migrar FileList (selector por-campo de su entrada
  `cellFiles`); los updates optimistas usan `patchCellFile`. El Skeleton solo
  cuando la entrada no existe aún. Borrar `savedScrollRef`/`prevCellKeyRef`/
  `useLayoutEffect` de restore salvo el reset-al-top en cambio de celda.
- [ ] **Step 2:** Migrar DetailPanel y PDFLightbox al mismo selector.
- [ ] **Step 3:** `npx vitest run` completo → verde (tests existentes de
  DetailPanel/PDFLightbox pueden requerir sembrar `cellFiles` en el store del
  test en vez de mockear api — ajustarlos con ese criterio).
- [ ] **Step 4: Commit** — `refactor(web): FileList/DetailPanel/PDFLightbox read files from the store cache`

### Task 12: reset de búsqueda/filtros al cambiar de celda (§A8)

- [ ] **Step 1:** Test rojo (irá dentro de C1 si se prefiere): filtro activo +
  cambio de celda → `search=""`, `activeOrigins=[]`; tick de la misma celda →
  intactos.
- [ ] **Step 2:** Implementar sobre el mecanismo de cambio-de-celda de FileList.
- [ ] **Step 3:** Verde. **Commit** — `fix(web): FileList filters reset on genuine cell change`

### Task 13: `FileList.test.jsx` (§C1)

- [ ] **Step 1:** Crear `frontend/src/components/FileList.test.jsx` pineando
  los 4 contratos de §C1 (montaje virtualizado + invariante de spacers;
  búsqueda pre-slice; regresión shrink-con-scroll a nivel componente; SWR sin
  Skeleton + scroll intacto en save / reset en cambio de celda). Sembrar el
  store real (idioma de los tests de componentes existentes), api mockeada.
- [ ] **Step 2:** `npx vitest run src/components/FileList.test.jsx` → verde.
- [ ] **Step 3: Commit** — `test(web): FileList render contract — virtualization, SWR, filters`

---

## Chunk 5: Frontend — UX (§A2–§A7, §A9–§A12)

### Task 14: errores huérfanos → toasts (§A2)

- [ ] **Step 1:** Tests rojos (vitest de store): los 5 paths (§A2) con api
  mockeada fallando → `toast.error` llamado con mensaje que nombra la
  operación; `error` global NO seteado. `openMonth`/`loadMonths`/`runScan`
  quedan como están (banner).
- [ ] **Step 2:** Implementar (patrón U2 de los save actions existentes).
  `generateOutput`: retirar el `set({error})`, queda solo toast.
- [ ] **Step 3:** Verde. **Commit** — `fix(web): orphaned error paths surface as toasts (no more silent failures)`

### Task 15: ReorgMenu → Radix Popover portalizado (§A3)

- [ ] **Step 1:** Crear `frontend/src/ui/Popover.jsx` (Radix Popover, tokens
  po-*, portal; API mínima: trigger + content). Test de humo del primitive.
- [ ] **Step 2:** Migrar `ReorgMenu` (`FileList.jsx:26-211`): mismo form, el
  `<details>` desaparece. Tests existentes de ReorgMenu migrados + assert de
  portal (content en `baseElement`, no bajo el `<ul>`) + focus/Escape.
- [ ] **Step 3:** Verde + build OK. **Commit** — `fix(web): ReorgMenu becomes a portalized popover (virtualization-safe)`

### Task 16: InlineEditCount commitea en blur (§A4)

- [ ] **Step 1:** Tests rojos según AC §A4 (4 casos; los existentes de
  over-cap se conservan).
- [ ] **Step 2:** Implementar (blur → commit si draft válido ≠ actual y sin
  over-cap pendiente).
- [ ] **Step 3:** Verde. **Commit** — `fix(web): InlineEditCount commits a valid draft on blur`

### Task 17: ScanConfirmDialog + estimación recalibrada (§A5)

- [ ] **Step 1:** Tests rojos según AC §A5 (4 casos sobre el store +
  `pendingScanConfirm`).
- [ ] **Step 2:** `constants.js`: `OCR_EST_SECONDS_PER_PDF = 1` (comentario:
  recalibrado post-hilos 2026-07-11). Store: `scanOcr` → si supera umbral,
  setea `pendingScanConfirm` y retorna; acción interna `_launchScanOcr` con
  el cuerpo actual. Componente `ScanConfirmDialog.jsx` sobre `ui/Dialog`
  (desglose N celdas / N PDFs / ETA; Confirmar/Cancelar; español neutro),
  montado junto a ScanProgress.
- [ ] **Step 3:** Verde; `git grep -n "window.confirm" frontend/src` → vacío.
- [ ] **Step 4: Commit** — `feat(web): scan cost guard becomes an in-app dialog with recalibrated ETA`

### Task 18: selectores `session_id` (§A6)

- [ ] **Step 1:** Migrar los 9 sitios listados en §A6 a
  `useSessionStore((s) => s.session?.session_id)` (verificar campo por campo
  si el componente usa algo más del objeto).
- [ ] **Step 2:** `npx vitest run` completo verde.
- [ ] **Step 3: Commit** — `perf(web): per-field session_id selectors in 9 leaf components`

### Task 19: CategoryRow por teclado (§A7)

- [ ] **Step 1:** Test rojo: Tab alcanza la fila; Enter y Space la seleccionan.
- [ ] **Step 2:** `role="button"` + `tabIndex={0}` + onKeyDown + focus-visible
  ring po-*. SIN roving ↑/↓ (YAGNI §A7).
- [ ] **Step 3:** Verde. **Commit** — `fix(web): CategoryRow is keyboard-operable`

### Task 20: resync respeta saves en vuelo (§A9)

- [ ] **Step 1:** Tests rojos (NotePanel y OverridePanel): tipear + blur
  inmediato → el input NUNCA muestra el valor viejo; `cell_updated` remoto
  SIN save pendiente sí resincroniza.
- [ ] **Step 2:** Exponer el selector de pending-save del store (el
  bookkeeping F15 ya existe — reutilizarlo, no duplicarlo) y consultarlo en
  el resync de ambos paneles.
- [ ] **Step 3:** Verde. **Commit** — `fix(web): debounced editors keep the typed value while a save is in flight`

### Task 21: menores — defaults ReorgHud, label de scan, aria (§A10–§A12)

- [ ] **Step 1:** §A10: defaults del ReorgHud = celda origen
  (`WorkerCountViewer.jsx:117-118`) + assert. §A11: el botón de scan solo
  dice "Escaneando…" cuando escanea (flag derivado según §A11) + assert.
  §A12: `aria-label="Cerrar"` en `ui/Dialog.jsx:31` + assert en un test
  existente.
- [ ] **Step 2:** Verde. **Commit** — `fix(web): reorg dest defaults, honest scan label, dialog close a11y`

---

## Chunk 6: Suite + docs + cierre (§C2, §C3, §C5, §C6)

### Task 22: motores threaded — error a mitad del pool (§C2)

- [ ] **Step 1:** Tests nuevos en
  `tests/unit/scanners/utils/test_pagination_count.py` y
  `test_header_band_anchors.py`: stub que lanza `RuntimeError` (paginación) /
  `PdfRenderError` (anclas) en una página con `ocr_threads>=2` →
  `pytest.raises` propaga; en paginación, spy sobre `fitz.open` verifica que
  TODOS los docs thread-local se cierran (contar `close()`).
- [ ] **Step 2:** Correr → verdes (la implementación ya existe; si algo falla
  es bug real — investigar antes de tocar el test).
- [ ] **Step 3: Commit** — `test(ocr): threaded engines propagate mid-pool errors and close thread-local docs`

### Task 23: `pdf_page_progress` frontend (§C3)

- [ ] **Step 1:** `frontend/src/store/session.pageProgress.test.js`: el case
  setea `page`/`pagesTotal`/`pageCell`; el siguiente `pdf_progress` los
  resetea a null. Render test de ScanProgress: "pág. X/Y" visible con page
  progress, ausente tras el reset.
- [ ] **Step 2:** Verdes. **Commit** — `test(web): pin the pdf_page_progress reducer and ScanProgress page detail`

### Task 24: dieta de la suite (§C5)

- [ ] **Step 1:** `eval/tests/test_pagination_benchmark.py`: fixture
  module-scoped con UNA corrida compartida de `run_benchmark` (solo
  `skips_missing_glob` y `temp_dir_cleaned_up` corren aparte). OJO pytest
  ScopeMismatch: una fixture module-scoped NO puede pedir `tmp_path`
  (function-scoped) — usar `tmp_path_factory` y construir el corpus sintético
  dentro de la fixture de módulo.
- [ ] **Step 2:** `tests/integration/test_forbid_extra_keys.py`: fixture
  module-scoped (env monkeypatch a tmp_path SIGUE por-módulo — lección DB
  2026-07-03; mismo aviso `tmp_path_factory`).
- [ ] **Step 3:** CREAR `tests/unit/api/conftest.py` (no existe) con la
  fixture autouse que hace `_PAGE_COUNT_CACHE.clear()`.
- [ ] **Step 4:** Dedup `_make_pdf` (7 copias) y `_make_manager` (4 copias) →
  fixtures en `tests/conftest.py` (precedente `make_pagination_pdf`); las
  fixtures se INYECTAN por nombre en la firma del test (no se importan).
  Antes de dedupear, diffear las 7/4 copias — pueden no ser idénticas; la
  fixture unificada debe cubrir todas las variantes (parámetros con default).
- [ ] **Step 5:** Medir: `python -m pytest -m "not slow" -q --durations=10` —
  objetivo: ≥30 s menos que el baseline (~185 s). Anotar el número real en el
  commit.
- [ ] **Step 6: Commit** — `test: suite diet — shared benchmark run, module-scoped setups, cache hygiene, fixture dedup`

### Task 25: docs al día (§C6)

- [ ] **Step 1:** Los 3 grupos de §C6 (api/CLAUDE.md; CLAUDE.md raíz —
  incluye el puntero "superseded" en la entrada M3b y el Pending Work;
  tools/README + comentario zombi de survey_form_codes).
- [ ] **Step 2: Commit** — `docs: CLAUDE.md drift fixes (presence GET, OCR threads env, self-lend supersedes M3b §8)`

### Task 26: cierre de ronda

- [ ] **Step 1:** Gates completos: `python -m pytest -m "not slow" -q` /
  `cd frontend && npx vitest run && npm run build` / `ruff check .` — todo
  verde/0.
- [ ] **Step 2:** OUTPUT GUARD: copiar `data/overseer.db` al scratchpad;
  `python tools/dump_counts.py --db <copia>` con el código en el commit BASE
  de la ronda (worktree detached temporal) vs HEAD → diff vacío.
- [ ] **Step 3:** CLAUDE.md raíz: entrada de Project history + Pending Work de
  esta ronda (denso, estilo de las entradas existentes).
- [ ] **Step 4:** `git push origin po_overhaul` + tag `pulido-post-revision`
  + push del tag.
- [ ] **Step 5:** Actualizar la memoria del proyecto
  (`~/.claude/projects/a--PROJECTS-PDFoverseer/memory/`): archivo de ronda +
  línea en MEMORY.md + `project_roadmap_next.md`.
