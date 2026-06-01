# Auditoría OCR per-sigla — Plan de correcciones

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolver los 7 hallazgos de la auditoría 2026-05-23 — progreso de scan por PDF (no por celda), guard de costo antes de OCR caro, heurística de compilación calibrada, y limpieza de inconsistencias/código muerto/docs.

**Architecture:** El cambio estructural está en el pase 2 OCR. Hoy `scan_cells_ocr` despacha una celda entera por subproceso y solo reporta progreso cuando la celda completa termina; un canal `multiprocessing.Queue` añade progreso por-PDF desde dentro del worker, drenado por un thread en el proceso principal. Un helper de enumeración compartido (`_enumerate_cell_pdfs`) unifica el conteo de PDFs entre el pre-cálculo del total y el scan real, respetando `recursive_glob`. Los demás fixes son aislados.

**Tech Stack:** Python 3.10+ (FastAPI, PyMuPDF, Tesseract, `concurrent.futures`, `multiprocessing`), React + Zustand + Vite, pytest + vitest.

**Source de la auditoría:** `docs/research/2026-05-23-auditoria-ocr-per-sigla.md`.

**Branch:** `feature/ocr-per-sigla`. Worktree: `.worktrees/ocr-per-sigla`.

**Convenciones del proyecto (recordatorio para el ejecutor):**
- `ruff check .` debe dar 0 violaciones antes de cada commit.
- Tipos 3.10+ (`X | None`, `list[X]`). No `print()` en librería (usar `logging`).
- No bare `except:`. No `shell=True`. SQL parametrizado.
- Constantes mágicas → `core/utils.py` o nivel de módulo, nunca inline.
- Commits: `type(scope): message` en inglés.
- Co-Authored-By trailer: `Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- Backend se lanza desde el worktree (`PYTHONPATH` = raíz del worktree) para que `core.scanners.patterns` resuelva al patterns.py rectificado.
- `A:\informe mensual` es **READ-ONLY** — los tests usan fixtures en `tests/fixtures/`, nunca el corpus real para escribir.

---

## File Structure

**Backend (modificar):**
- `core/scanners/utils/cell_enumeration.py` — **CREAR**. Helper `enumerate_cell_pdfs(folder, sigla)` que respeta `recursive_glob` de `patterns.py`. Única fuente de verdad para "qué PDFs tiene esta celda". Resuelve #1 (pre-conteo coherente) y #3 (inconsistencia rglob).
- `core/scanners/anchors_scanner.py` — `count_ocr` gana param `on_pdf` y usa el helper de enumeración.
- `core/scanners/pagination_scanner.py` — idem.
- `core/orchestrator.py` — `_init_ocr_worker` cachea la progress-queue; `_ocr_worker` emite `cell_started` + `pdf_done`; `scan_cells_ocr` crea la queue, lanza el thread drenador, pre-cuenta el total y emite `scan_started` + `pdf_progress` (con ETA real).
- `core/scanners/utils/page_count_heuristic.py` — factor ×3 + señal de ratio agregado.
- `api/routes/sessions.py` — `scan_ocr` devuelve `total_pdfs`.
- `api/CLAUDE.md`, `core/CLAUDE.md` — corregir documentación desactualizada.

**Frontend (modificar):**
- `frontend/src/store/session.js` — caso `pdf_progress` + `scan_started`; usar total de PDFs; guard de costo en `scanOcr`.
- `frontend/src/components/ScanProgress.jsx` — mostrar PDF actual + ETA real.
- `frontend/src/lib/constants.js` — umbral del guard de costo.
- `frontend/src/components/HospitalDetail.jsx` (o donde se dispare el scan) — confirmación de costo.

**Borrar:**
- `core/scanners/utils/page_count_pure.py` + `tests/unit/scanners/utils/test_page_count_pure.py`.

---

## Chunk 1: Progreso por-PDF + enumeración unificada (Hallazgos #1 y #3)

Resuelve la barra congelada. La unidad de progreso pasa de celda a PDF, vía un
canal IPC desde el worker. El helper de enumeración unifica pre-conteo y scan
(de paso arregla #3, la inconsistencia `recursive_glob`).

### Task 1.1: Helper de enumeración de PDFs por celda

**Files:**
- Create: `core/scanners/utils/cell_enumeration.py`
- Test: `tests/unit/scanners/utils/test_cell_enumeration.py`

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/unit/scanners/utils/test_cell_enumeration.py
from pathlib import Path

from core.scanners.utils.cell_enumeration import enumerate_cell_pdfs


def _touch(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"%PDF-1.4\n%%EOF\n")


def test_recursive_sigla_includes_subfolders(tmp_path):
    # charla tiene recursive_glob=True en patterns.py
    _touch(tmp_path / "a.pdf")
    _touch(tmp_path / "EMPRESA" / "b.pdf")
    result = enumerate_cell_pdfs(tmp_path, "charla")
    names = sorted(p.name for p in result)
    assert names == ["a.pdf", "b.pdf"]


def test_nonrecursive_sigla_skips_subfolders(tmp_path):
    # odi NO tiene recursive_glob → solo top-level
    _touch(tmp_path / "a.pdf")
    _touch(tmp_path / "SUB" / "b.pdf")
    result = enumerate_cell_pdfs(tmp_path, "odi")
    names = sorted(p.name for p in result)
    assert names == ["a.pdf"]


def test_missing_folder_returns_empty(tmp_path):
    assert enumerate_cell_pdfs(tmp_path / "nope", "odi") == []
```

- [ ] **Step 2: Correr el test, verificar que falla**

Run: `python -m pytest tests/unit/scanners/utils/test_cell_enumeration.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.scanners.utils.cell_enumeration'`

- [ ] **Step 3: Implementar el helper**

```python
# core/scanners/utils/cell_enumeration.py
"""Single source of truth for enumerating the PDFs of a cell.

Both the OCR scanners (pase 2) and the pre-scan PDF count must agree on which
files belong to a cell — otherwise the progress bar's `done` and `total`
diverge. Honors the per-sigla ``recursive_glob`` flag from ``patterns.py`` so
pase 1 (filename) and pase 2 (OCR) count the same set (audit finding #3).
"""

from __future__ import annotations

from pathlib import Path

from core.scanners.patterns import PATTERNS


def enumerate_cell_pdfs(folder: Path, sigla: str) -> list[Path]:
    """Return the sorted list of PDFs for ``sigla`` inside ``folder``.

    Args:
        folder: The cell's category folder.
        sigla: Category key; its ``recursive_glob`` flag decides whether
            subfolders are included.

    Returns:
        Sorted list of PDF paths (empty if the folder does not exist).
    """
    if not folder.exists():
        return []
    pattern = PATTERNS.get(sigla)
    recursive = bool(pattern.get("recursive_glob")) if pattern is not None else False
    globber = folder.rglob if recursive else folder.glob
    return sorted(globber("*.pdf"))
```

- [ ] **Step 4: Correr el test, verificar que pasa**

Run: `python -m pytest tests/unit/scanners/utils/test_cell_enumeration.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add core/scanners/utils/cell_enumeration.py tests/unit/scanners/utils/test_cell_enumeration.py
git commit -m "feat(scanners): add enumerate_cell_pdfs honoring recursive_glob"
```

### Task 1.2: `AnchorsScanner.count_ocr` usa el helper + emite progreso por-PDF

**Files:**
- Modify: `core/scanners/anchors_scanner.py:40-147`
- Test: `tests/unit/scanners/test_anchors_scanner_progress.py`

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/unit/scanners/test_anchors_scanner_progress.py
from pathlib import Path

from core.scanners.anchors_scanner import AnchorsScanner
from core.scanners.cancellation import CancellationToken


def test_count_ocr_invokes_on_pdf_per_file(tmp_path, monkeypatch):
    # Two 1-page PDFs (A7 path — no real OCR needed) under an anchors sigla.
    for name in ("x.pdf", "y.pdf"):
        (tmp_path / name).write_bytes(b"%PDF-1.4\n%%EOF\n")

    # get_page_count → 1 so both take the A7 branch (no Tesseract).
    monkeypatch.setattr(
        "core.scanners.anchors_scanner.get_page_count", lambda p: 1
    )

    seen: list[str] = []
    AnchorsScanner(sigla="odi").count_ocr(
        tmp_path, cancel=CancellationToken(), on_pdf=lambda name: seen.append(name)
    )
    assert sorted(seen) == ["x.pdf", "y.pdf"]


def test_count_ocr_on_pdf_optional(tmp_path, monkeypatch):
    (tmp_path / "x.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    monkeypatch.setattr("core.scanners.anchors_scanner.get_page_count", lambda p: 1)
    # No on_pdf → must not raise.
    AnchorsScanner(sigla="odi").count_ocr(tmp_path, cancel=CancellationToken())
```

- [ ] **Step 2: Correr el test, verificar que falla**

Run: `python -m pytest tests/unit/scanners/test_anchors_scanner_progress.py -v`
Expected: FAIL — `count_ocr() got an unexpected keyword argument 'on_pdf'`

- [ ] **Step 3: Implementar**

En `core/scanners/anchors_scanner.py`:

1. Importar el helper y quitar el `rglob` directo:
```python
from core.scanners.utils.cell_enumeration import enumerate_cell_pdfs
```

2. Firma nueva (añadir `on_pdf`):
```python
    def count_ocr(
        self,
        folder: Path,
        *,
        cancel: CancellationToken,
        on_pdf: Callable[[str], None] | None = None,
    ) -> ScanResult:
```
(Importar `from collections.abc import Callable` arriba.)

3. Reemplazar `pdfs = sorted(folder.rglob("*.pdf"))` por:
```python
        pdfs = enumerate_cell_pdfs(folder, self.sigla)
```

4. Al final de CADA iteración del `for pdf in pdfs:` (las 3 ramas: A7, anchors-ok,
   fallback-error), invocar el callback. La forma DRY es envolver el cuerpo del
   loop y llamar `on_pdf` en un `finally` por iteración:
```python
        for pdf in pdfs:
            cancel.check()
            try:
                # ... cuerpo existente (page_count, A7, count_covers_by_anchors) ...
            finally:
                if on_pdf is not None:
                    on_pdf(pdf.name)
```
   **Cuidado:** el `cancel.check()` que hoy abre la iteración lanza `CancelledError`
   ANTES de procesar el PDF; ese caso NO debe contar el PDF como hecho. Mover el
   `cancel.check()` fuera del `try/finally` (que quede antes), para que un cancel
   no dispare `on_pdf`.

- [ ] **Step 4: Correr el test, verificar que pasa**

Run: `python -m pytest tests/unit/scanners/test_anchors_scanner_progress.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Correr la suite de scanners (sin regresión)**

Run: `python -m pytest tests/unit/scanners/ -q`
Expected: mismos pass/skip que antes del cambio (12 skipped esperados del postmortem).

- [ ] **Step 6: Commit**

```bash
git add core/scanners/anchors_scanner.py tests/unit/scanners/test_anchors_scanner_progress.py
git commit -m "feat(scanners): AnchorsScanner.count_ocr emits per-PDF progress + uses shared enumeration"
```

### Task 1.3: `PaginationScanner.count_ocr` — mismo contrato

**Files:**
- Modify: `core/scanners/pagination_scanner.py:55-150`
- Test: `tests/unit/scanners/test_pagination_scanner_progress.py`

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/unit/scanners/test_pagination_scanner_progress.py
from core.scanners.pagination_scanner import PaginationScanner
from core.scanners.cancellation import CancellationToken


def test_pagination_count_ocr_invokes_on_pdf(tmp_path, monkeypatch):
    for name in ("a.pdf", "b.pdf"):
        (tmp_path / name).write_bytes(b"%PDF-1.4\n%%EOF\n")
    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda p: 1)
    seen: list[str] = []
    PaginationScanner(sigla="insgral").count_ocr(
        tmp_path, cancel=CancellationToken(), on_pdf=lambda n: seen.append(n)
    )
    assert sorted(seen) == ["a.pdf", "b.pdf"]
```

- [ ] **Step 2: Correr el test, verificar que falla**

Run: `python -m pytest tests/unit/scanners/test_pagination_scanner_progress.py -v`
Expected: FAIL — unexpected keyword `on_pdf`.

- [ ] **Step 3: Implementar** — mismos 4 cambios que 1.2 aplicados a
  `pagination_scanner.py` (importar `enumerate_cell_pdfs` + `Callable`, firma con
  `on_pdf`, reemplazar `sorted(folder.rglob(...))`, `finally: on_pdf(pdf.name)`
  con `cancel.check()` fuera del try).

- [ ] **Step 4: Correr el test, verificar que pasa**

Run: `python -m pytest tests/unit/scanners/test_pagination_scanner_progress.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/scanners/pagination_scanner.py tests/unit/scanners/test_pagination_scanner_progress.py
git commit -m "feat(scanners): PaginationScanner.count_ocr emits per-PDF progress"
```

### Task 1.4: Worker propaga progreso por la queue IPC

**Files:**
- Modify: `core/orchestrator.py:217-272` (`_WORKER_EVENT`, `_init_ocr_worker`, `_ocr_worker`)
- Test: `tests/unit/test_orchestrator_ocr_progress.py`

- [ ] **Step 1: Escribir el test que falla** (camino síncrono `max_workers=1`)

```python
# tests/unit/test_orchestrator_ocr_progress.py
from pathlib import Path

from core.orchestrator import scan_cells_ocr
from core.scanners.cancellation import CancellationToken


def test_scan_cells_ocr_emits_pdf_progress(tmp_path, monkeypatch):
    folder = tmp_path / "3.-ODI Visitas"
    folder.mkdir()
    for name in ("a.pdf", "b.pdf", "c.pdf"):
        (folder / name).write_bytes(b"%PDF-1.4\n%%EOF\n")
    # Force the A7 path (1-page) so no Tesseract runs.
    monkeypatch.setattr("core.scanners.anchors_scanner.get_page_count", lambda p: 1)

    events: list[dict] = []
    scan_cells_ocr(
        [("HPV", "odi", folder)],
        on_progress=events.append,
        cancel=CancellationToken(),
        max_workers=1,
    )
    types = [e["type"] for e in events]
    assert "scan_started" in types
    pdf_events = [e for e in events if e["type"] == "pdf_progress"]
    assert [e["done"] for e in pdf_events] == [1, 2, 3]
    assert pdf_events[-1]["total"] == 3
    assert types[-1] == "scan_complete"
```

- [ ] **Step 2: Correr el test, verificar que falla**

Run: `python -m pytest tests/unit/test_orchestrator_ocr_progress.py -v`
Expected: FAIL — no `scan_started`/`pdf_progress` events emitted yet.

- [ ] **Step 3: Implementar el worker + initializer**

En `core/orchestrator.py`:

```python
_WORKER_EVENT: Any = None  # set per-subprocess by _init_ocr_worker
_WORKER_PROGRESS_Q: Any = None  # mp.Queue for per-PDF progress (None in sync path)


def _init_ocr_worker(event: Any, progress_q: Any = None) -> None:
    """ProcessPoolExecutor initializer — caches the cancel event AND the
    progress queue in the subprocess."""
    global _WORKER_EVENT, _WORKER_PROGRESS_Q
    _WORKER_EVENT = event
    _WORKER_PROGRESS_Q = progress_q
```

En `_ocr_worker`, antes de llamar `fn`, construir el callback y emitir
`cell_started`:

```python
    def _emit(ev: dict) -> None:
        if _WORKER_PROGRESS_Q is not None:
            _WORKER_PROGRESS_Q.put(ev)

    _emit({"type": "cell_started", "hospital": hosp, "sigla": sigla})

    def _on_pdf(name: str) -> None:
        _emit({"type": "pdf_done", "hospital": hosp, "sigla": sigla, "pdf_name": name})
```

Y pasar `on_pdf=_on_pdf` a la llamada OCR:
```python
            result = fn(folder, cancel=token, on_pdf=_on_pdf)
```
(El path `fn is None` — siglas `none` como reunion — no recibe `on_pdf`; queda
igual. Esas celdas no emiten pdf_done, lo cual es correcto: no hacen OCR.)

- [ ] **Step 4 + Step 5:** la implementación se completa en 1.5 (scan_cells_ocr
  consume estos eventos). El test de 1.4 pasará al terminar 1.5 — dejar el test
  escrito y rojo, marcar en el commit de 1.5.

### Task 1.5: `scan_cells_ocr` — pre-conteo, queue, thread drenador, ETA

**Files:**
- Modify: `core/orchestrator.py:274-415` (`scan_cells_ocr`)

- [ ] **Step 1: Implementar el pre-conteo + `scan_started`**

Al inicio de `scan_cells_ocr`, tras validar `cancel`:
```python
    from core.scanners.utils.cell_enumeration import enumerate_cell_pdfs  # noqa: E402

    total_pdfs = sum(len(enumerate_cell_pdfs(f, s)) for (_, s, f) in cells)
    on_progress({
        "type": "scan_started",
        "total_cells": total,
        "total_pdfs": total_pdfs,
    })
    _t0 = time.perf_counter()
    pdfs_done = 0
```

- [ ] **Step 2: Camino síncrono (`max_workers == 1`)** — pasar `on_pdf` directo

Definir el callback que emite `pdf_progress` con ETA y pasarlo a `_ocr_worker`.
Cambiar la firma interna de `_ocr_worker` para aceptar `on_pdf` en el camino
síncrono (en el camino multi-worker el worker lo arma desde la queue):

```python
    def _emit_pdf(name: str) -> None:
        nonlocal pdfs_done
        pdfs_done += 1
        eta_ms = _eta_ms(_t0, pdfs_done, total_pdfs)
        on_progress({
            "type": "pdf_progress", "done": pdfs_done,
            "total": total_pdfs, "pdf_name": name, "eta_ms": eta_ms,
        })
```

Donde `_eta_ms` es un helper a nivel de módulo:
```python
def _eta_ms(t0: float, done: int, total: int) -> int | None:
    """Linear ETA from elapsed time. None until we have ≥1 sample."""
    if done <= 0 or total <= done:
        return None
    elapsed = time.perf_counter() - t0
    per_item = elapsed / done
    return int(per_item * (total - done) * 1000)
```

En el camino síncrono, `_ocr_worker(ct)` debe propagar `on_pdf`. Como el worker
síncrono corre en el proceso principal, pasarle `_emit_pdf` directamente
requiere que `_ocr_worker` acepte un `on_pdf` opcional que use cuando
`_WORKER_PROGRESS_Q is None`. Ajustar `_ocr_worker` para aceptar
`on_pdf: Callable | None = None` y usar ese (o el de la queue) al llamar `fn`.
Emitir también `cell_scanning` antes de procesar la celda (ya existe el evento).

- [ ] **Step 3: Camino multi-worker** — queue + thread drenador

```python
    import queue as _queue  # noqa: E402
    import threading  # noqa: E402

    ctx = mp.get_context("spawn")
    progress_q = ctx.Queue()
    stop_drain = threading.Event()

    def _drain() -> None:
        nonlocal pdfs_done
        while not stop_drain.is_set() or not _q_empty(progress_q):
            try:
                ev = progress_q.get(timeout=0.2)
            except _queue.Empty:
                continue
            if ev["type"] == "cell_started":
                on_progress({"type": "cell_scanning",
                             "hospital": ev["hospital"], "sigla": ev["sigla"]})
            elif ev["type"] == "pdf_done":
                pdfs_done += 1
                on_progress({"type": "pdf_progress", "done": pdfs_done,
                             "total": total_pdfs, "pdf_name": ev["pdf_name"],
                             "eta_ms": _eta_ms(_t0, pdfs_done, total_pdfs)})

    drain_thread = threading.Thread(target=_drain, daemon=True)
    drain_thread.start()
```
Pasar la queue al pool: `initargs=(event, progress_q)`. Tras el `with
ProcessPoolExecutor(...)` bloque: `stop_drain.set(); drain_thread.join(timeout=2.0)`.
Quitar el `on_progress({"type": "cell_scanning", ...})` que hoy se emite
post-`fut.result()` (queda obsoleto: el worker ya emitió `cell_started` al
arrancar de verdad — esto arregla el hallazgo #1b).

Helper `_q_empty` (cross-version, evita romper si `Queue.empty()` es poco fiable):
```python
def _q_empty(q: Any) -> bool:
    try:
        return q.empty()
    except (OSError, ValueError):
        return True
```

- [ ] **Step 4: Correr los tests de 1.4 + 1.5**

Run: `python -m pytest tests/unit/test_orchestrator_ocr_progress.py tests/unit/test_orchestrator*.py -v`
Expected: PASS. El `pdf_progress` debe llevar `done` 1..N y `eta_ms` presente desde done≥1.

- [ ] **Step 5: Test multi-worker (real subprocess, smoke)**

```python
def test_scan_cells_ocr_multiworker_pdf_progress(tmp_path, monkeypatch):
    # No se puede monkeypatch a través de spawn; usar PDFs reales de 1 página.
    # Copiar un fixture A7 de tests/fixtures/scanners/bodega/ (1-page).
    ...
    events = []
    scan_cells_ocr(cells, on_progress=events.append,
                   cancel=CancellationToken(), max_workers=2)
    assert any(e["type"] == "pdf_progress" for e in events)
    assert events[-1]["type"] in ("scan_complete", "scan_cancelled")
```
Run: `python -m pytest tests/unit/test_orchestrator_ocr_progress.py -v`
Expected: PASS (el drenador entrega al menos un `pdf_progress`).

- [ ] **Step 6: Commit**

```bash
git add core/orchestrator.py tests/unit/test_orchestrator_ocr_progress.py
git commit -m "feat(orchestrator): per-PDF scan progress via IPC queue + real ETA"
```

### Task 1.6: Endpoint expone `total_pdfs`

**Files:**
- Modify: `api/routes/sessions.py:143-264` (`scan_ocr`)
- Test: `tests/unit/api/test_scan_ocr_routes.py`

- [ ] **Step 1: Test que falla** — el response incluye `total_pdfs`.

```python
def test_scan_ocr_returns_total_pdfs(client, ocr_session):
    resp = client.post(f"/api/sessions/{ocr_session}/scan-ocr",
                       json={"cells": [["HRB", "bodega"]]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["accepted"] is True
    assert "total_pdfs" in body and body["total_pdfs"] >= 1
```

- [ ] **Step 2: Correr, verificar fallo** (`KeyError: 'total_pdfs'`).

- [ ] **Step 3: Implementar** — en `scan_ocr`, tras construir `cells_with_paths`:
```python
    from core.scanners.utils.cell_enumeration import enumerate_cell_pdfs
    total_pdfs = sum(len(enumerate_cell_pdfs(f, s)) for (_, s, f) in cells_with_paths)
    ...
    return {"accepted": True, "total": len(cells_with_paths), "total_pdfs": total_pdfs}
```

- [ ] **Step 4: Correr, verificar pasa.**

Run: `python -m pytest tests/unit/api/test_scan_ocr_routes.py -v`

- [ ] **Step 5: Commit**

```bash
git add api/routes/sessions.py tests/unit/api/test_scan_ocr_routes.py
git commit -m "feat(api): scan-ocr returns total_pdfs for the progress bar"
```

### Task 1.7: Frontend — barra por-PDF + PDF actual + ETA real

**Files:**
- Modify: `frontend/src/store/session.js:83-90` (`scanOcr`) y `:393-395` (switch)
- Modify: `frontend/src/components/ScanProgress.jsx`
- Test: `frontend/src/store/session.test.js` (vitest; crear si no existe el caso)

- [ ] **Step 1: Test que falla** (vitest, reducer del evento)

```js
// session.test.js — el handler procesa pdf_progress
import { describe, it, expect } from "vitest";
import { useSessionStore } from "./session";

describe("pdf_progress", () => {
  it("updates scanProgress with done/total/pdfName", () => {
    const { _handleWSEvent } = useSessionStore.getState();
    _handleWSEvent({ type: "scan_started", total_pdfs: 5, total_cells: 2 });
    _handleWSEvent({ type: "pdf_progress", done: 2, total: 5, pdf_name: "x.pdf", eta_ms: 9000 });
    const sp = useSessionStore.getState().scanProgress;
    expect(sp.done).toBe(2);
    expect(sp.total).toBe(5);
    expect(sp.pdfName).toBe("x.pdf");
    expect(sp.etaMs).toBe(9000);
  });
});
```

- [ ] **Step 2: Correr, verificar fallo**

Run: `cd frontend && npx vitest run src/store/session.test.js`
Expected: FAIL (no maneja `scan_started`/`pdf_progress`).

- [ ] **Step 3: Implementar** en `session.js`:

`scanOcr` action — usar el `total_pdfs` del response:
```js
  scanOcr: async (sessionId, cellPairs) => {
    try {
      const resp = await api.scanOcr(sessionId, cellPairs);
      set({ scanProgress: { done: 0, total: resp?.total_pdfs ?? 0, unit: "pdf" } });
    } catch (error) {
      set({ error: String(error) });
    }
  },
```

Casos nuevos en el switch:
```js
      case "scan_started":
        set({ scanProgress: { done: 0, total: event.total_pdfs, unit: "pdf" } });
        break;
      case "pdf_progress":
        set({ scanProgress: {
          done: event.done, total: event.total,
          pdfName: event.pdf_name, etaMs: event.eta_ms, unit: "pdf",
        }});
        break;
```
Arreglar `scan_complete` para no recalcular `total` en celdas (mantener el total
de PDFs ya mostrado):
```js
      case "scan_complete":
        set({
          scanningCells: new Set(),
          scanProgress: { ...state.scanProgress, terminal: "complete" },
        });
        setTimeout(...);  // igual que hoy
        break;
```
(El `scan_progress` viejo — granularidad celda — puede quedar como fallback; ya
no es el driver.)

- [ ] **Step 4: ScanProgress.jsx** — mostrar PDF actual; el ETA ahora llega:
```jsx
        <span className="text-sm font-medium text-po-text">{label}</span>
        {scanProgress.pdfName && !scanProgress.terminal && (
          <span className="text-xs text-po-text-muted truncate max-w-[180px]">
            {scanProgress.pdfName}
          </span>
        )}
        <Badge variant="neutral" className="ml-auto">{done}/{total}</Badge>
```
(El bloque `etaMs && !terminal` ya existe y ahora cobra vida.)

- [ ] **Step 5: Correr el test, verificar pasa + build**

Run: `cd frontend && npx vitest run src/store/session.test.js && npm run build`
Expected: test PASS, build sin errores.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/store/session.js frontend/src/components/ScanProgress.jsx frontend/src/store/session.test.js
git commit -m "feat(frontend): per-PDF scan progress bar with current file + live ETA"
```

### Task 1.8: Smoke manual (chrome-devtools) — opcional, lo corre el orquestador

- [ ] Reiniciar backend+frontend desde el worktree, abrir Brave debug, escanear una
  celda con varios PDFs multi-página (p.ej. HRB/chintegral) y confirmar que la
  barra avanza por PDF, muestra el nombre del PDF y un ETA decreciente. Capturar
  un screenshot a `docs/research/`.

---

## Chunk 2: Heurística de compilación calibrada (Hallazgo #4)

Hoy `flag_compilation_suspect` usa `expected × 5` (factor único). HRB/andamios
(PDFs 6-9pp, expected 2 → umbral 10) no dispara siendo compilación real.

### Task 2.1: Factor ×3 + señal de ratio agregado

**Files:**
- Modify: `core/scanners/utils/page_count_heuristic.py`
- Modify: `core/utils.py` (constantes)
- Test: `tests/unit/scanners/utils/test_page_count_heuristic.py`

- [ ] **Step 1: Tests que fallan** (casos de la calibración Fase A/B)

```python
def test_andamios_moderate_compilation_flagged(tmp_path, monkeypatch):
    # 1 PDF de 9 páginas, expected andamios=2. Con ×3 (umbral 6) → suspect.
    (tmp_path / "check_list_a.pdf").write_bytes(b"x")
    monkeypatch.setattr(
        "core.scanners.utils.page_count_heuristic._page_count", lambda p: 9
    )
    assert flag_compilation_suspect(tmp_path, sigla="andamios") is True


def test_regime1_art_not_flagged(tmp_path, monkeypatch):
    # ART de 4 páginas, expected art=10 → no suspect (régimen 1 sano).
    (tmp_path / "art1.pdf").write_bytes(b"x")
    monkeypatch.setattr(
        "core.scanners.utils.page_count_heuristic._page_count", lambda p: 4
    )
    assert flag_compilation_suspect(tmp_path, sigla="art") is False


def test_aggregate_ratio_flags_many_medium_pdfs(tmp_path, monkeypatch):
    # 5 PDFs de 5pp cada uno, expected 2 → ningún PDF supera ×3 (6),
    # pero el ratio total (25pp / 5 PDFs = 5 ≥ 2×2) marca sospecha agregada.
    for i in range(5):
        (tmp_path / f"f{i}.pdf").write_bytes(b"x")
    monkeypatch.setattr(
        "core.scanners.utils.page_count_heuristic._page_count", lambda p: 5
    )
    assert flag_compilation_suspect(tmp_path, sigla="exc") is True
```

- [ ] **Step 2: Correr, verificar fallo** (con el ×5 actual, andamios 9<10 → False).

- [ ] **Step 3: Implementar** — mover el factor a `core/utils.py`:
```python
# core/utils.py
COMPILATION_PAGE_FACTOR = 3       # PDF suspect if pages > expected × factor
COMPILATION_RATIO_FACTOR = 2      # folder suspect if avg pages/pdf > expected × this
```
En `page_count_heuristic.py`, reemplazar `_TIGHT_FACTOR = 5` por import de
`COMPILATION_PAGE_FACTOR`, y añadir la señal agregada en `flag_compilation_suspect`:
```python
    counts = [_page_count(p) for p in folder.rglob("*.pdf")]
    counts = [c for c in counts if c > 0]
    if not counts:
        return False
    expected = EXPECTED_PAGES_PER_DOC.get(sigla, 2)
    # Per-PDF signal: any single PDF much longer than one document.
    if any(c > expected * COMPILATION_PAGE_FACTOR for c in counts):
        return True
    # Aggregate signal: many medium PDFs whose average length per file is
    # well above one document (compilation spread across files).
    avg = sum(counts) / len(counts)
    return len(counts) >= 3 and avg > expected * COMPILATION_RATIO_FACTOR
```

- [ ] **Step 4: Correr, verificar pasa** + suite del módulo.

Run: `python -m pytest tests/unit/scanners/utils/test_page_count_heuristic.py -v`

- [ ] **Step 5: Commit**

```bash
git add core/scanners/utils/page_count_heuristic.py core/utils.py tests/unit/scanners/utils/test_page_count_heuristic.py
git commit -m "fix(scanners): calibrate compilation heuristic (×3 + aggregate ratio)"
```

---

## Chunk 3: Guard de costo antes de OCR (Hallazgo #2)

Antes de lanzar OCR sobre celdas con muchos PDFs, confirmar con el operador y
recordar que en régimen 1 el filename ya cuenta. Reutiliza el `pdf_count_hint`
que ya viaja en el inventario de celdas.

### Task 3.1: Umbral + estimación en constants

**Files:**
- Modify: `frontend/src/lib/constants.js`

- [ ] **Step 1: Añadir constantes** (sin test — datos):
```js
// Cost guard for pase-2 OCR (audit finding #2). Single-user/LAN app, so these
// are UX thresholds, not hard limits.
export const OCR_CONFIRM_PDF_THRESHOLD = 50;   // ask to confirm above this many PDFs
export const OCR_EST_SECONDS_PER_PDF = 4;      // rough ETA basis for the dialog
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/constants.js
git commit -m "chore(frontend): OCR cost-guard thresholds"
```

### Task 3.2: Confirmación antes de `scanOcr` (en la action del store)

**Decisión:** el scan se dispara desde DOS sitios — `CategoryGroup.jsx:27` y
`ScanControls.jsx:14`, ambos llaman `scanOcr(session.session_id, pairs)`. Poner el
guard en cada componente duplicaría lógica. Lo ponemos **una vez en la action
`scanOcr` del store**, así ambos call-sites quedan cubiertos sin tocarlos. El
`window.confirm` dentro de una action async de Zustand es aceptable en esta app
single-user/escritorio (no hay SSR).

**El total de PDFs por celda** sale del inventario que el store ya tiene: cada
celda lleva `pdf_count_hint` (ver `CellInventory` en `core/orchestrator.py`); el
endpoint `GET /api/sessions/{id}` lo expone en el state. La action suma los hints
de los `pairs` seleccionados. Si el hint no estuviera disponible para algún par,
se asume 0 (no bloquea — el guard es UX, no límite duro).

**Files:**
- Create: `frontend/src/lib/scanCost.js`
- Create: `frontend/src/lib/scanCost.test.js`
- Modify: `frontend/src/store/session.js:83-90` (`scanOcr` action)
- (NO se tocan `CategoryGroup.jsx` ni `ScanControls.jsx`.)

- [ ] **Step 1: Helper puro testeable** en `frontend/src/lib/scanCost.js`:
```js
import { OCR_EST_SECONDS_PER_PDF } from "./constants";

export function estimateScanSeconds(totalPdfs) {
  return totalPdfs * OCR_EST_SECONDS_PER_PDF;
}

export function shouldConfirmScan(totalPdfs, threshold) {
  return totalPdfs > threshold;
}

/** Sum of pdf_count_hint for the selected [hospital, sigla] pairs. */
export function totalPdfsForPairs(sessionState, pairs) {
  const cells = sessionState?.cells ?? {};
  let total = 0;
  for (const [hosp, sigla] of pairs) {
    const cell = cells?.[hosp]?.[sigla];
    total += cell?.pdf_count_hint ?? cell?.count ?? 0;
  }
  return total;
}
```

- [ ] **Step 2: Test que falla** — `frontend/src/lib/scanCost.test.js`:
```js
import { describe, it, expect } from "vitest";
import { shouldConfirmScan, estimateScanSeconds, totalPdfsForPairs } from "./scanCost";

describe("scanCost", () => {
  it("confirms above threshold", () => {
    expect(shouldConfirmScan(60, 50)).toBe(true);
    expect(shouldConfirmScan(10, 50)).toBe(false);
  });
  it("estimates seconds", () => { expect(estimateScanSeconds(10)).toBe(40); });
  it("sums pdf_count_hint over pairs", () => {
    const state = { cells: { HPV: { art: { pdf_count_hint: 767 } }, HRB: { odi: { pdf_count_hint: 1 } } } };
    expect(totalPdfsForPairs(state, [["HPV", "art"], ["HRB", "odi"]])).toBe(768);
  });
});
```
Run: `cd frontend && npx vitest run src/lib/scanCost.test.js` → FAIL (módulo no existe).

- [ ] **Step 3: Implementar** el helper (arriba) y meter el guard en la action
  `scanOcr` de `session.js`:
```js
  scanOcr: async (sessionId, cellPairs) => {
    const state = get();
    const totalPdfs = totalPdfsForPairs(state.session, cellPairs);
    if (shouldConfirmScan(totalPdfs, OCR_CONFIRM_PDF_THRESHOLD)) {
      const mins = Math.max(1, Math.round(estimateScanSeconds(totalPdfs) / 60));
      const ok = window.confirm(
        `Vas a escanear con OCR ${totalPdfs} PDFs (~${mins} min). En categorías ` +
        `de régimen 1 el conteo por nombre de archivo ya suele ser correcto. ¿Continuar?`
      );
      if (!ok) return;
    }
    try {
      const resp = await api.scanOcr(sessionId, cellPairs);
      set({ scanProgress: { done: 0, total: resp?.total_pdfs ?? 0, unit: "pdf" } });
    } catch (error) {
      set({ error: String(error) });
    }
  },
```
Imports al tope de `session.js`:
```js
import { OCR_CONFIRM_PDF_THRESHOLD } from "../lib/constants";
import { shouldConfirmScan, estimateScanSeconds, totalPdfsForPairs } from "../lib/scanCost";
```

- [ ] **Step 4: Correr test + build**

Run: `cd frontend && npx vitest run src/lib/scanCost.test.js && npm run build`
Expected: PASS + build OK.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/scanCost.js frontend/src/lib/scanCost.test.js frontend/src/store/session.js
git commit -m "feat(frontend): confirm OCR scans over the PDF-count threshold (store-level guard)"
```

---

## Chunk 4: Higiene — código muerto + docs + asimetría (Hallazgos #5, #6, #7)

### Task 4.1: Borrar `page_count_pure` (código muerto)

**Files:**
- Delete: `core/scanners/utils/page_count_pure.py`
- Delete: `tests/unit/scanners/utils/test_page_count_pure.py`

- [ ] **Step 1: Confirmar que nadie de producción lo importa**

Run: `grep -rn "page_count_pure" --include="*.py" core/ api/ | grep -v test`
Expected: solo comentarios/docstrings (en `output.py`, `sessions.py`, `state.py`
como nombre de método histórico) — ninguna **importación** de producción.

- [ ] **Step 2: Borrar archivo + test**
```bash
git rm core/scanners/utils/page_count_pure.py tests/unit/scanners/utils/test_page_count_pure.py
```

- [ ] **Step 3: Suite verde**

Run: `python -m pytest tests/ -q`
Expected: sin fallos nuevos; el conteo de tests baja por los borrados.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(scanners): remove dead page_count_pure helper + its test"
```

### Task 4.2: Corregir documentación desactualizada

**Files:**
- Modify: `api/CLAUDE.md` (rutas/env vars borradas en FASE 1)
- Modify: `core/CLAUDE.md` (orden: scanner triad primero, V4 como motor de pagination)

- [ ] **Step 1: `api/CLAUDE.md`** — reemplazar la sección "Routes" por las reales
  (`months.py`, `sessions.py`, `output.py`, `history.py`, `ws.py`) y la tabla de
  env vars por las reales (`OVERSEER_DB_PATH`, `INFORME_MENSUAL_ROOT`,
  `OVERSEER_OUTPUT_DIR`, `TESSERACT_CMD`, `HOST`, `PORT`). Quitar `PDF_ROOT`,
  `SESSION_TTL`, `/api/browse`, `routes/files.py`, `routes/pipeline.py`.

- [ ] **Step 2: `core/CLAUDE.md`** — mover la sección "Scanner Architecture
  (ocr-per-sigla)" al inicio (es lo activo) y marcar la sección "V4 Pipeline"
  como "motor interno, alcanzado solo vía PaginationScanner".

- [ ] **Step 3: Commit**

```bash
git add api/CLAUDE.md core/CLAUDE.md
git commit -m "docs: refresh api/core CLAUDE.md to post-rectification architecture"
```

- [ ] **Step 4: Actualizar la memoria Serena** (fuera del repo — lo hace el
  orquestador, no commiteable): corregir `codebase_structure` para reflejar que
  `core/pipeline.py`, `inference.py`, `ocr.py` viven (usados por
  PaginationScanner) y listar los archivos nuevos del scanner triad.

### Task 4.3: Alinear el default de conteo per-file (Hallazgo #7)

**Files:**
- Modify: `api/routes/sessions.py:439-441` (`get_cell_files` `effective_count`)
- Test: `tests/unit/api/test_cell_files.py`

- [ ] **Step 1: Test que falla** — un archivo SIN dato pre-scan se reporta
  coherente con `compute_cell_count` (que no lo cuenta). Decisión de diseño:
  mantener `effective_count = 1` en la vista (un PDF es al menos 1 doc para el
  operador) pero documentar la divergencia pre-scan con un comentario; el test
  fija el contrato actual para evitar drift:
```python
def test_effective_count_defaults_to_one_without_data(client, ocr_session):
    files = client.get(f"/api/sessions/{ocr_session}/cells/HRB/bodega/files").json()
    # Pre-scan: sin per_file ni override, cada PDF cuenta 1 en la vista.
    assert all(f["effective_count"] >= 1 for f in files)
```

- [ ] **Step 2-3:** correr; si pasa ya (comportamiento actual), añadir solo el
  comentario explicativo en el código aclarando la asimetría intencional con
  `compute_cell_count`. Si se decide unificar a 0, ajustar ambos lados — **pero la
  recomendación es dejar 1 en la vista** (más intuitivo para el operador) y
  documentar.

- [ ] **Step 4: Commit**

```bash
git add api/routes/sessions.py tests/unit/api/test_cell_files.py
git commit -m "docs(api): document the intentional per-file effective_count default"
```

---

## Cierre

- [ ] **Suite completa verde**

Run: `python -m pytest tests/ -q && cd frontend && npx vitest run && npm run build && cd .. && ruff check .`
Expected: backend sin fallos nuevos (12 skips esperados del postmortem), vitest PASS,
build OK, ruff 0 violaciones.

- [ ] **Smoke manual** (chrome-devtools) del flujo completo: escanear una celda
  grande y confirmar barra por-PDF + ETA + guard de costo. Screenshot a
  `docs/research/`.

- [ ] **Actualizar memoria** (`project_ocr_per_sigla_shipped`) y postmortem con el
  cierre de los 7 hallazgos.

### Orden de ejecución

Chunk 1 → Chunk 2 → Chunk 3 → Chunk 4. El Chunk 1 es prerequisito del 3 (el guard
de costo se apoya en el `total_pdfs` y el progreso fino). Los Chunks 2 y 4 son
independientes y podrían intercalarse.

### Notas de diseño (decisiones tomadas, no preguntar)

1. **Progreso por PDF, no por página.** La página es demasiado fina (un ETA por
   página parpadea) y requeriría un canal de progreso desde dentro de
   `count_covers_by_anchors`/V4. El PDF es la unidad correcta: avanza rápido en
   régimen 1 (A7) y lento en compilaciones, que es honesto.
2. **Queue IPC, no reescritura a despacho-por-PDF.** Despachar cada PDF como un
   futuro daría paralelismo intra-celda pero obliga a reensamblar la agregación
   (A7, near-matches, confidence) que ya está validada en Fase A/B. La queue da el
   progreso visible —el problema real— con riesgo acotado. El paralelismo
   intra-celda queda como mejora futura si hace falta.
3. **ETA lineal.** `elapsed/done × remaining`. Simple y suficiente; no vale un
   modelo más fino para single-user.
4. **Guard de costo en el frontend.** El inventario ya trae `pdf_count_hint`; no
   hace falta un endpoint de estimación. `window.confirm` o el Dialog de Radix ya
   presente — sin nueva dependencia.
5. **Heurística #4: ×3 + ratio agregado.** Captura compilaciones moderadas
   (andamios) y repartidas (varios PDFs medianos) sin disparar falsos positivos en
   régimen 1 (ART expected alto). Constantes en `core/utils.py` por convención.
6. **#7 se deja en `1`** (vista) documentado, no se unifica a `0`: 1 doc/PDF es lo
   intuitivo para el operador y tras un scan la divergencia desaparece.
