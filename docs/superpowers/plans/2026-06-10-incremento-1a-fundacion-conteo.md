# Incremento 1A — Fundación: conteo robusto + sin pisar — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el OCR de celda completa fusione resultados por archivo de forma incremental (sin pisar conteos R1/manuales/OCR previo, conservando lo escaneado al cancelar, saltando lo ya contado), formalice el tipo de conteo por sigla, y serialice las mutaciones de estado.

**Architecture:** El OCR de celda deja de reemplazar el mapa `per_file` entero al `cell_done`; en su lugar cada PDF se fusiona apenas termina vía `apply_per_file_ocr_result` (la función probada del escaneo de un archivo). La ruta calcula el set de archivos *pendientes* (multipágina contados por nombre, sin override) y se lo pasa al orquestador para saltar lo confiable. `cell_done` pasa a finalizar solo metadata de celda. Un `RLock` por `SessionManager` serializa el read-modify-write del blob de sesión.

**Tech Stack:** Python 3.10, FastAPI, `ProcessPoolExecutor` + `multiprocessing.Queue` (IPC), SQLite (WAL, autocommit), pytest.

**Spec:** `docs/superpowers/specs/2026-06-10-incremento-1a-fundacion-conteo-design.md` (autoridad; ante duda, el spec manda).

**Rama:** trabajo **directo en `po_overhaul`** (convención del proyecto — NO worktree; ver `CLAUDE.md` §Consolidación). Anula la guía de worktree del skill.

---

## File Structure

**Modify:**
- `api/state.py` — `SessionManager`: `RLock` en todos los mutadores; nueva `finalize_cell_ocr` (metadata-only); `apply_ocr_result` → shim deprecado; borrar `apply_cell_result` si está muerto.
- `core/scanners/patterns.py` — `count_type` en las 18 entradas + campo en el TypedDict `SiglaPattern`.
- `core/scanners/scan_info.py` — exponer `count_type`.
- `core/utils.py` — `COUNT_TYPES` (frozenset de validación) + bump `SCANNER_PATTERNS_VERSION`.
- `core/scanners/anchors_scanner.py` — `count_ocr`: `skip: set[str] | None`; `on_pdf` enriquecido (patrón de captura).
- `core/scanners/pagination_scanner.py` — idem (verificar conteo por-PDF al `finally`).
- `core/scanners/simple_factory.py` — tick enriquecido en el camino sin-OCR/no-flavors.
- `core/scanners/base.py` — tipo del callback `on_pdf` si está en el Protocol/contrato.
- `core/orchestrator.py` — `_ocr_worker`/`pdf_cb` propagan count/method/near_matches (dict) por IPC; `scan_cells_ocr` pasa `skip` y `_drain` reenvía `file_result`; camino sync `_emit_pdf` idem; `cell_done` deja de cargar `per_file`.
- `api/routes/sessions.py` — `scan_ocr`: calcula `skip` por celda; `on_progress` agrega rama `file_result` (merge guard) y `cell_done` → `finalize_cell_ocr`.

**Test (create/extend):**
- `tests/unit/api/test_state_lock.py` *(create)* — concurrencia sin lost-update.
- `tests/unit/api/test_state.py` *(extend)* — `finalize_cell_ocr` no toca `per_file`.
- `tests/unit/scanners/test_count_type.py` *(create)* — gate de completitud + `scan_info`.
- `tests/unit/scanners/test_anchors_scanner.py` *(extend)* — `skip` + callback enriquecido.
- `tests/unit/scanners/test_pagination_scanner.py` *(extend)* — idem.
- `tests/unit/test_orchestrator_ocr.py` *(extend)* — merge incremental sync + cancel-keeps-partial.
- `tests/integration/test_scan_ocr_full.py` *(extend)* — merge respeta manual/R1/OCR previo; re-scan salta.

### Convenciones de test (leer antes de ejecutar — corrige hallazgos del revisor)

- **PDFs fixture = inline, no fixtures compartidos.** 1 página: `(folder/"x.pdf").write_bytes(_one_page_pdf())` (helper local en `test_anchors_scanner.py`). Para simular **multipágina sin** un PDF real: `monkeypatch.setattr(mod, "get_page_count", lambda _: 3)`. Para aislar el OCR: `monkeypatch.setattr("core.scanners.anchors_scanner.count_covers_by_anchors", stub)` donde `stub` devuelve un objeto con `.count` y `.near_matches`. Patrón vivo en `tests/unit/scanners/test_anchors_scanner.py:39-74`.
- **Los nombres de fixture de los tests de abajo (`art_cell_folder`, `two_pdf_cell`, `cancellable_cell`, `insgral_cell_folder`) son ILUSTRATIVOS** — defínelos inline en cada test con el patrón de arriba (o un `@pytest.fixture` local), **no** asumas que existen, o pytest da error de colección (no test rojo).
- **Estado:** fixture `manager` en `tests/unit/api/test_state.py:56` (sesión **`2026-04`**, `month_root=tmp_path`, ya abierta) + helper `_filename_result(count)`; fixture `conn` al tope del mismo archivo. **Nunca** `month_root=...`.
- **Integración:** reusar el cliente/sesión reales de `tests/integration/test_scan_ocr_full.py` (verificar el nombre del fixture al implementar), **no** inventar `client_with_session`.

---

## Chunk 1: Estado — lock, finalize_cell_ocr, count_type

> Fundación pura, sin orquestación. Independientemente entregable y testeable.

### Task 1: `RLock` en las mutaciones de `SessionManager`

**Files:**
- Modify: `api/state.py` (`SessionManager.__init__` + cada mutador)
- Test: `tests/unit/api/test_state_lock.py` *(create)*

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/api/test_state_lock.py
"""El SessionManager serializa el read-modify-write del blob de sesión."""
from __future__ import annotations

import threading

from api.state import SessionManager
from core.db.connection import open_connection
from core.db.migrations import init_schema


def _mgr(tmp_path):
    conn = open_connection(tmp_path / "lock.db")
    init_schema(conn)
    return SessionManager(conn=conn)


def test_concurrent_mutations_no_lost_update(tmp_path):
    mgr = _mgr(tmp_path)
    mgr.open_session(year=2026, month=5, month_root=tmp_path)
    # apply_per_file_ocr_result usa setdefault → crea la celda (sin KeyError) y
    # muta per_file[filename]; dos hilos sobre celdas distintas del mismo blob.
    barrier = threading.Barrier(2)

    def bump(hosp, sigla, fname):
        barrier.wait()
        for i in range(50):
            mgr.apply_per_file_ocr_result("2026-05", hosp, sigla, fname,
                                          count=i, method="header_band_anchors", near_matches=[])

    t1 = threading.Thread(target=bump, args=("HLL", "odi", "a.pdf"))
    t2 = threading.Thread(target=bump, args=("HRB", "art", "b.pdf"))
    t1.start(); t2.start(); t1.join(); t2.join()

    state = mgr.get_session_state("2026-05")
    # Sin lock, una rama pisa a la otra (lost update) → una de las dos celdas
    # desaparece o queda con un valor viejo. Con lock, ambas persisten.
    assert state["cells"]["HLL"]["odi"]["per_file"]["a.pdf"] == 49
    assert state["cells"]["HRB"]["art"]["per_file"]["b.pdf"] == 49


def test_rlock_allows_reentrant_mutator(tmp_path):
    """apply_cell_result delega en apply_filename_result; con Lock no reentrante
    esto deadlockea. Si apply_cell_result sigue vivo, debe no colgar."""
    mgr = _mgr(tmp_path)
    mgr.open_session(year=2026, month=5, month_root=tmp_path)
    # No debe colgar (RLock) ni lanzar.
    if hasattr(mgr, "apply_cell_result"):
        from core.scanners.base import ConfidenceLevel, ScanResult
        r = ScanResult(count=1, confidence=ConfidenceLevel.HIGH, method="filename_glob",
                       breakdown=None, flags=[], errors=[], duration_ms=0,
                       files_scanned=1, per_file={"x.pdf": 1})
        mgr.apply_cell_result("2026-05", "HLL", "odi", r)  # no debe deadlockear
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/api/test_state_lock.py -v`
Expected: `test_concurrent_mutations_no_lost_update` FAIL intermitente (lost update) — correr 3× si hace falta para verlo rojo.

- [ ] **Step 3: Implement — add RLock + wrap mutators**

En `api/state.py`:
```python
import threading  # al tope

class SessionManager:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._lock = threading.RLock()  # RLock: apply_cell_result re-entra (C1)
```
Envolver el cuerpo de **cada** mutador (`apply_filename_result`, `apply_ocr_result`,
`apply_per_file_ocr_result`, `apply_user_override`, `apply_per_file_override`,
`apply_worker_count`, `apply_confirmed`, `clear_near_matches`, `finalize`, y la futura
`finalize_cell_ocr`) con `with self._lock:`. Patrón:
```python
def apply_per_file_override(self, session_id, hospital, sigla, filename, count):
    with self._lock:
        state, _ = self._load_and_migrate(session_id)
        ...
        update_session_state(self._conn, session_id, state_json=json.dumps(state))
```
`get_session_state` también toma el lock para devolver una vista coherente.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/api/test_state_lock.py -v` (correr 3×) → PASS estable.

- [ ] **Step 5: Commit**

```bash
git add api/state.py tests/unit/api/test_state_lock.py
git commit -m "fix(state): serialize SessionManager mutations with an RLock"
```

---

### Task 2: `finalize_cell_ocr` (metadata-only) + deprecar `apply_ocr_result`

**Files:**
- Modify: `api/state.py`
- Test: `tests/unit/api/test_state.py` *(extend)*

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/api/test_state.py  (añadir; usa el fixture `manager` ya existente)
def test_finalize_cell_ocr_does_not_touch_per_file(manager):
    mgr = manager  # sesión "2026-04" ya abierta (month_root=tmp_path)
    # Celda con per_file ya fusionado por archivo.
    mgr.apply_per_file_ocr_result("2026-04", "HRB", "art", "doc1.pdf",
                                  count=3, method="header_band_anchors", near_matches=[])
    from core.scanners.base import ConfidenceLevel, ScanResult
    meta = ScanResult(count=999, confidence=ConfidenceLevel.LOW, method="header_band_anchors",
                      breakdown=None, flags=["a7_one_page_locked"], errors=[], duration_ms=120,
                      files_scanned=1, per_file={"IGNORAR.pdf": 999})
    mgr.finalize_cell_ocr("2026-04", "HRB", "art", meta)
    cell = mgr.get_session_state("2026-04")["cells"]["HRB"]["art"]
    # per_file / per_file_method NO se tocan (se fusionaron por archivo).
    assert cell["per_file"] == {"doc1.pdf": 3}
    assert cell["per_file_method"] == {"doc1.pdf": "header_band_anchors"}
    # metadata SÍ se finaliza.
    assert cell["method"] == "header_band_anchors"
    assert cell["confidence"] == "low"
    assert cell["flags"] == ["a7_one_page_locked"]
    # ocr_count belt-and-suspenders = suma del per_file existente (no el 999 del meta).
    assert cell["ocr_count"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/api/test_state.py::test_finalize_cell_ocr_does_not_touch_per_file -v`
Expected: FAIL — `finalize_cell_ocr` no existe.

- [ ] **Step 3: Implement `finalize_cell_ocr` + deprecate**

```python
def finalize_cell_ocr(self, session_id, hospital, sigla, result: ScanResult) -> None:
    """Finaliza la metadata de celda tras un OCR de celda incremental.

    NO toca per_file/per_file_method (ya se fusionaron por archivo vía
    apply_per_file_ocr_result). Escribe método/confianza/flags/errores/duración
    y un ocr_count belt-and-suspenders = suma del per_file actual (fallback;
    el conteo real lo da compute_cell_count). Preserva user_override,
    per_file_overrides, manual_entry, confirmed, worker_marks, filename_count.
    """
    with self._lock:
        state, _ = self._load_and_migrate(session_id)
        cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
        cell["method"] = result.method
        cell["confidence"] = result.confidence.value
        cell["breakdown"] = result.breakdown
        cell["flags"] = list(result.flags)
        cell["errors"] = list(result.errors)
        cell["duration_ms_ocr"] = result.duration_ms
        cell["ocr_count"] = sum((cell.get("per_file") or {}).values())
        cell.setdefault("per_file_overrides", {})
        cell.setdefault("manual_entry", False)
        cell.setdefault("user_override", None)
        cell.setdefault("override_note", None)
        cell.setdefault("excluded", False)
        cell.setdefault("confirmed", False)
        update_session_state(self._conn, session_id, state_json=json.dumps(state))
```
Marcar `apply_ocr_result` como deprecado (docstring `.. deprecated::`) — sigue vivo para
compat de tests hasta migrarlos en el Chunk 3. Auditar `apply_cell_result`: si no lo llama
nadie en `api/`, borrarlo.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/api/test_state.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add api/state.py tests/unit/api/test_state.py
git commit -m "feat(state): add finalize_cell_ocr (metadata-only) for incremental OCR"
```

---

### Task 3: `count_type` por sigla + `scan_info` + gate

**Files:**
- Modify: `core/scanners/patterns.py`, `core/scanners/scan_info.py`, `core/utils.py`
- Test: `tests/unit/scanners/test_count_type.py` *(create)*

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/scanners/test_count_type.py
from core.domain import SIGLAS
from core.scanners.patterns import PATTERNS
from core.scanners.scan_info import scan_info_for
from core.utils import COUNT_TYPES

WORKERS = {"charla", "chintegral", "dif_pts"}
CHECKS = {"maquinaria"}

def test_every_sigla_has_valid_count_type():
    for sigla in SIGLAS:
        ct = PATTERNS[sigla].get("count_type")
        assert ct in COUNT_TYPES, f"{sigla}: count_type inválido ({ct!r})"

def test_count_type_classification():
    for sigla in SIGLAS:
        ct = PATTERNS[sigla]["count_type"]
        if sigla in WORKERS:
            assert ct == "documents_workers", sigla
        elif sigla in CHECKS:
            assert ct == "checks", sigla
        else:
            assert ct == "documents", sigla

def test_scan_info_exposes_count_type():
    assert scan_info_for("charla")["count_type"] == "documents_workers"
    assert scan_info_for("maquinaria")["count_type"] == "checks"
    assert scan_info_for("odi")["count_type"] == "documents"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/scanners/test_count_type.py -v`
Expected: FAIL — `COUNT_TYPES` no existe / falta `count_type` en entries.

- [ ] **Step 3: Implement**

`core/utils.py`:
```python
COUNT_TYPES: frozenset[str] = frozenset({"documents", "documents_workers", "checks"})
```
Bump `SCANNER_PATTERNS_VERSION` (p.ej. `"v3-count-type"`).

`core/scanners/patterns.py`: agregar `"count_type": "<valor>"` a las 18 entradas
(`charla`/`chintegral`/`dif_pts` → `"documents_workers"`; `maquinaria` → `"checks"`; resto →
`"documents"`). Extender el TypedDict `SiglaPattern` con
`count_type: Literal["documents", "documents_workers", "checks"]`.

`core/scanners/scan_info.py`: añadir `count_type` al dict que devuelve `scan_info_for`
(`PATTERNS.get(sigla, {}).get("count_type", "documents")`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/scanners/test_count_type.py -v` + el gate de completitud existente de patterns → PASS.

- [ ] **Step 5: Commit**

```bash
git add core/scanners/patterns.py core/scanners/scan_info.py core/utils.py tests/unit/scanners/test_count_type.py
git commit -m "feat(scanners): per-sigla count_type (documents/workers/checks) + scan-info"
```

---

## Chunk 2: Scanners — skip + callback enriquecido

> Cambia el contrato de `count_ocr`. Testeable de forma aislada con PDFs fixture.

### Task 4: `AnchorsScanner.count_ocr` — `skip` + `on_pdf` enriquecido

**Files:**
- Modify: `core/scanners/anchors_scanner.py`, `core/scanners/base.py` (tipo del callback)
- Test: `tests/unit/scanners/test_anchors_scanner.py` *(extend)*

- [ ] **Step 1: Write the failing tests**

```python
def test_count_ocr_skips_files_in_skip_set(art_cell_folder):
    """skip excluye archivos del escaneo; no aparecen en per_file ni en los ticks."""
    seen = []
    scanner = AnchorsScanner(sigla="art")
    skip = {"ya_contado.pdf"}
    r = scanner.count_ocr(art_cell_folder, cancel=CancellationToken(),
                          on_pdf=lambda name, count, method, nm: seen.append(name),
                          skip=skip)
    assert "ya_contado.pdf" not in seen
    assert "ya_contado.pdf" not in (r.per_file or {})

def test_count_ocr_enriched_callback_carries_count_method_nm(art_cell_folder):
    rows = []
    scanner = AnchorsScanner(sigla="art")
    scanner.count_ocr(art_cell_folder, cancel=CancellationToken(),
                      on_pdf=lambda name, count, method, nm: rows.append((name, count, method)))
    # Multipágina por anclas → method header_band_anchors, count = per_file.
    multi = [r for r in rows if r[2] == "header_band_anchors"]
    assert multi and all(isinstance(c, int) for _, c, _ in multi)
    # A7 (1 página) → method filename_glob, count 1 (la ruta lo tratará como R1).
    a7 = [r for r in rows if r[2] == "filename_glob"]
    assert all(c == 1 for _, c, _ in a7)
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/unit/scanners/test_anchors_scanner.py -k "skip or enriched" -v`
Expected: FAIL — firma vieja de `on_pdf`/sin `skip` (TypeError).

- [ ] **Step 3: Implement**

`count_ocr`: nuevo parámetro `skip: set[str] | None = None`. Tras `enumerate_cell_pdfs`, si
`skip`: `pdfs = [p for p in pdfs if p.name not in skip]`. Aplicar el **patrón de captura** del
spec §3.2 (`_count`/`_method` reseteados por PDF, fijados antes de cada `continue`; en el
`finally`, `on_pdf(pdf.name, _count, _method, _file_near_matches(pdf.name))`). Helper local
`_file_near_matches(name)` filtra la lista `near_matches` por `pdf_name == name` y la **serializa
a dict** (shape WS). Actualizar el tipo del callback en `base.py` y los docstrings.

> El camino "sin flavors" (línea ~94): emitir `on_pdf(pdf.name, base.per_file.get(pdf.name, 0),
> "filename_glob", [])` (solo-progreso aguas arriba).

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/scanners/test_anchors_scanner.py -v` → PASS (incl. los tests de progreso existentes, adaptados a la firma nueva).

- [ ] **Step 5: Commit**

```bash
git add core/scanners/anchors_scanner.py core/scanners/base.py tests/unit/scanners/test_anchors_scanner.py
git commit -m "feat(scanners): AnchorsScanner.count_ocr skip-set + enriched per-file callback"
```

---

### Task 5: `PaginationScanner.count_ocr` — `skip` + enriquecido

**Files:**
- Modify: `core/scanners/pagination_scanner.py`
- Test: `tests/unit/scanners/test_pagination_scanner.py` *(extend)*

- [ ] **Step 1: Write the failing test**

```python
def test_pagination_count_ocr_enriched_and_skip(insgral_cell_folder):
    rows = []
    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count_ocr(insgral_cell_folder, cancel=CancellationToken(),
                          on_pdf=lambda name, count, method, nm: rows.append((name, count, method)),
                          skip={"omitir.pdf"})
    assert "omitir.pdf" not in [name for name, _, _ in rows]
    assert all(isinstance(c, int) for _, c, _ in rows if c is not None)
```

- [ ] **Step 2: Run to verify fail** — `pytest tests/unit/scanners/test_pagination_scanner.py -k enriched -v` → FAIL.

- [ ] **Step 3: Implement** — mismo `skip` + patrón de captura; verificar que `count_documents_v4` expone el conteo por-PDF al `finally` (spec Q4 resuelto). Si una rama no produce conteo, `_count=None` (solo-progreso).

- [ ] **Step 4: Run to verify pass** — `pytest tests/unit/scanners/test_pagination_scanner.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add core/scanners/pagination_scanner.py tests/unit/scanners/test_pagination_scanner.py
git commit -m "feat(scanners): PaginationScanner.count_ocr skip-set + enriched callback"
```

---

### Task 6: camino "none"/`simple_factory` — tick enriquecido

**Files:**
- Modify: `core/orchestrator.py` (la rama `fn is None` en `_ocr_worker`), `core/scanners/simple_factory.py` (si emite ticks)
- Test: `tests/unit/test_orchestrator_ocr.py` *(extend)*

- [ ] **Step 1: Write the failing test**

```python
def test_none_strategy_emits_progress_only_tick(reunion_cell):
    """scan_strategy 'none' (reunion): tick con method filename_glob (solo-progreso)."""
    rows = []
    # invocar _ocr_worker con on_pdf enriquecido para reunion
    ...
    assert all(method == "filename_glob" for _, _, method, _ in rows)
```

- [ ] **Step 2: Run to verify fail** → FAIL (firma vieja).

- [ ] **Step 3: Implement** — en `_ocr_worker`, la rama `fn is None` emite
`pdf_cb(pdf.name, result.per_file.get(pdf.name, 0), "filename_glob", [])`. Mantener el método
real (`page_count_pure` para FIXED_PAGE_SIGLAS si aplica; pero esos no pasan por aquí salvo OCR explícito).

- [ ] **Step 4: Run to verify pass** → PASS.

- [ ] **Step 5: Commit**

```bash
git add core/orchestrator.py core/scanners/simple_factory.py tests/unit/test_orchestrator_ocr.py
git commit -m "feat(orchestrator): enriched progress tick for none/no-flavor OCR paths"
```

---

## Chunk 3: Orquestación + ruta — merge incremental

> Une todo. El camino sync (`max_workers=1`) cubre la lógica sin subprocesos; validar ahí primero.

### Task 7: orquestación — propagar resultado por-archivo + `cell_done` finaliza

**Files:**
- Modify: `core/orchestrator.py` (`_ocr_worker`/`pdf_cb`, `scan_cells_ocr`, `_drain`, `_emit_pdf`)
- Test: `tests/unit/test_orchestrator_ocr.py` *(extend)*

- [ ] **Step 1: Write the failing tests (sync path)**

```python
def test_incremental_merge_sync_path(monkeypatch, two_pdf_cell):
    """max_workers=1: cada PDF emite un file_result con count/method/near_matches (dict)."""
    events = []
    scan_cells_ocr([("HRB", "art", two_pdf_cell)],
                   on_progress=events.append, cancel=CancellationToken(), max_workers=1)
    file_results = [e for e in events if e["type"] == "file_result"]
    assert file_results, "debe emitir file_result por PDF"
    fr = file_results[0]
    assert {"hospital", "sigla", "filename", "count", "method", "near_matches"} <= fr.keys()
    assert isinstance(fr["near_matches"], list)  # dicts, no NearMatchEntry
    assert all(isinstance(nm, dict) for nm in fr["near_matches"])

def test_cancel_keeps_partial_sync(cancellable_cell):
    """Cancelar tras el 1er PDF: el file_result del 1ro ya salió; el 2do no."""
    events = []
    token = CancellationToken()
    def on_progress(e):
        events.append(e)
        if e["type"] == "file_result":
            token.cancel()  # cancelar tras el primer resultado
    scan_cells_ocr([("HRB", "art", cancellable_cell)],
                   on_progress=on_progress, cancel=token, max_workers=1)
    file_results = [e for e in events if e["type"] == "file_result"]
    assert len(file_results) == 1  # solo el primero persiste
    assert any(e["type"] == "scan_cancelled" for e in events)
```

- [ ] **Step 2: Run to verify fail** → FAIL (no existe `file_result`).

- [ ] **Step 3: Implement**

- `scan_cells_ocr`: aceptar `skip_by_cell: dict[tuple[str,str], set[str]] | None`; pasar el
  `skip` de cada celda a `count_ocr` (vía `cell_tuple` extendido en multi-worker, o directo en sync).
- Sync `_emit_pdf` → ahora `on_pdf(name, count, method, nm)`: emitir `pdf_progress` (tick) **y**
  `{"type": "file_result", "hospital", "sigla", "filename": name, "count", "method", "near_matches": nm}`.
- Multi-worker `pdf_cb` (subproceso): poner en la cola
  `{"type": "pdf_done", "hospital", "sigla", "pdf_name", "count", "method", "near_matches": nm}`
  (nm ya serializado a dict por el scanner). `_drain`: por cada `pdf_done` emitir `pdf_progress`
  (como hoy) **y** `file_result` a `on_progress`.
- `cell_done`: dejar de incluir `per_file`; **sí incluir `flags`/`errors`/`breakdown`** en el
  payload (hoy NO van — el evento solo carga `ocr_count`/`method`/`confidence`/`duration_ms_ocr`;
  `finalize_cell_ocr` los necesita y `_meta_result` los lee).
- Pre-cancel y `scan_cancelled` sin cambios.

> **Migración de callers del `on_pdf` (advisory del revisor):** ningún test en
> `test_anchors_scanner.py`/`test_pagination_scanner.py` pasa `on_pdf` (usan monkeypatch) → no
> rompen por la firma. Los tests de orquestación que mockean `count_ocr` con `MagicMock` sí: al
> llamar el worker `on_pdf(name, count, method, nm)`, actualizar esos stubs en esta tarea.
> **Orden multi-worker (advisory):** `pdf_cb` (subproceso) pasa de 1-arg a 4-arg **en esta tarea**;
> entre los Tasks 5–7 solo el camino sync (`max_workers=1`, el de los tests) queda consistente — no
> probar con `max_workers=2` antes de cerrar Task 7.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_orchestrator_ocr.py tests/unit/test_orchestrator_ocr_progress.py tests/unit/test_orchestrator_ocr_anchors.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add core/orchestrator.py tests/unit/test_orchestrator_ocr.py
git commit -m "feat(orchestrator): emit per-file file_result for incremental merge + skip plumbing"
```

---

### Task 8: ruta `scan_ocr` — `skip` desde estado + `file_result` merge + `cell_done` finaliza

**Files:**
- Modify: `api/routes/sessions.py` (`scan_ocr` + su `on_progress`)
- Test: `tests/integration/test_scan_ocr_full.py` *(extend)*

- [ ] **Step 1: Write the failing tests**

```python
def test_full_cell_ocr_does_not_clobber_manual_or_prior(client_with_session):
    """A3: una celda con un override manual + un archivo ya OCR-eado + uno pendiente.
    OCR de celda → solo el pendiente cambia; los otros dos quedan idénticos."""
    # sembrar estado: a.pdf override manual=5; b.pdf per_file_method=header_band_anchors,
    # per_file=2; c.pdf filename_glob multipágina (pendiente).
    ...
    resp = client.post(f"/api/sessions/{sid}/scan-ocr", json={"cells": [["HRB", "art"]]})
    wait_for_scan_complete(ws)
    files = client.get(f"/api/sessions/{sid}/cells/HRB/art/files").json()
    by = {f["name"]: f for f in files}
    assert by["a.pdf"]["override_count"] == 5            # manual intacto
    assert by["b.pdf"]["per_file_count"] == 2            # OCR previo intacto
    assert by["c.pdf"]["origin"] in {"OCR", "Revisar"}   # el pendiente se escaneó

def test_rescan_skips_already_scanned(client_with_session):
    """H2: re-OCR de una celda ya OCR-eada no re-escanea (rápido, sin cambios)."""
    # OCR una vez, capturar per_file; OCR de nuevo; per_file idéntico.
    ...
```

- [ ] **Step 2: Run to verify fail** → FAIL (hoy pisa).

- [ ] **Step 3: Implement**

En `scan_ocr`, antes de despachar, por cada `(hosp, sigla)` cargar la celda del estado y calcular:
```python
cell = state["cells"].get(hosp, {}).get(sigla, {})
pfm = cell.get("per_file_method") or {}
overrides = cell.get("per_file_overrides") or {}
skip = {f for f, m in pfm.items() if m and m != "filename_glob"} | set(overrides)
```
Pasar `skip_by_cell` a `scan_cells_ocr`. En `on_progress`:
```python
if event["type"] == "file_result":
    method, count = event["method"], event["count"]
    if count is not None and method != "filename_glob":   # merge guard §3.3
        mgr.apply_per_file_ocr_result(session_id, event["hospital"], event["sigla"],
                                      event["filename"], count=count, method=method,
                                      near_matches=event.get("near_matches") or [])
elif event["type"] == "cell_done":
    # reconstruir ScanResult de metadata (sin per_file) → finalize_cell_ocr
    mgr.finalize_cell_ocr(session_id, event["hospital"], event["sigla"], _meta_result(event))
```
Quitar la rama vieja `cell_done → apply_ocr_result`. Definir `_meta_result` (helper en
`sessions.py`) que reconstruye el `ScanResult` de metadata desde el evento:
```python
def _meta_result(event: dict) -> ScanResult:
    return ScanResult(
        count=event.get("ocr_count") or 0,
        confidence=ConfidenceLevel(event["confidence"]),
        method=event["method"], breakdown=event.get("breakdown"),
        flags=event.get("flags") or [], errors=event.get("errors") or [],
        duration_ms=event.get("duration_ms_ocr") or 0, files_scanned=1,
    )
```
(Los tests de integración reusan el cliente/sesión de `test_scan_ocr_full.py` — verificar el nombre
del fixture, no inventar `client_with_session`.)

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/integration/test_scan_ocr_full.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add api/routes/sessions.py tests/integration/test_scan_ocr_full.py
git commit -m "feat(api): full-cell OCR merges per-file incrementally, skips reliable files"
```

---

### Task 9: no-regresión + migrar tests de `apply_ocr_result`

**Files:**
- Modify: tests que llamaban `apply_ocr_result` directamente (migrar a `finalize_cell_ocr` +
  `apply_per_file_ocr_result` según corresponda); `tests/integration/test_abril_full_corpus.py` (verificar totales)
- Test: toda la suite

- [ ] **Step 1: Run the full suite, catalog failures**

Run: `pytest -q` → listar los tests que dependían del reemplazo total de `apply_ocr_result`.

- [ ] **Step 2: Migrate / assert no-regression**

Ajustar los tests legacy al modelo nuevo (no mockear DB — regla del proyecto). La **no-regresión de
ABRIL es el test automatizado ya existente** `tests/integration/test_abril_full_corpus.py` (NO
escribir un test nuevo que embeba conteos en vivo): debe seguir **verde, sin cambios de totales**.
`test_cell_count_cross_language` también verde sin tocar fixtures.

- [ ] **Step 3: Lint + full green**

Run: `ruff check .` → 0; `pytest -q` → verde.

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test(1a): migrate legacy apply_ocr_result tests; assert no count regression"
```

---

## Smoke conducido (post-merge, chrome-devtools)

Tras Chunk 3, smoke en Brave debug (conducido por mí, no checklist para Daniel):
1. OCR una celda multipágina → la lista/detalle refleja conteos **a medida** (no de golpe).
2. Ajustar un archivo a mano → re-OCR celda → el ajuste **sobrevive**.
3. Re-OCR de una celda ya escaneada → rápido, sin cambios (skip).
4. Cancelar a mitad → lo escaneado queda; lo demás, pendiente.

Capturas a `docs/research/incr1a-smoke-*.png`.

---

## Definición de hecho (1A)
- `ruff check .` 0 · `pytest` verde (nuevos + no-regresión) · build/vitest sin tocar (salvo que
  `scan_info` rompa un consumidor FE — verificar).
- Smoke OK. Commits atómicos. `SCANNER_PATTERNS_VERSION` bumpeado.
- Memoria de milestone al cerrar 1A (o junto con 1B).
