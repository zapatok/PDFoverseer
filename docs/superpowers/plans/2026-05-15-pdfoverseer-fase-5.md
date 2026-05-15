# FASE 5 — UX slice — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar tres pendientes del roadmap post-FASE 4 — histórico drill-in (drawer lateral), cancelación de OCR a nivel de página (<3 s), y auto-retry silencioso de OCR.

**Architecture:** Tres features independientes sobre la base FASE 4. (1) Drill-in: un primitive `ui/Drawer.jsx` no-modal + un componente `HistoryDrawer.jsx`, alimentado por la cache que ya tiene `useHistoryStore` — cero backend. (2) Cancelación: threadear el `CancellationToken` hacia las dos utils OCR que tienen loop de páginas, con checkpoint por página que levanta `CancelledError`. (3) Auto-retry: el subproceso `_ocr_worker` reintenta su propio scan 2× en silencio — sin tocar los loops de `scan_cells_ocr`, lo que evita el problema del pool ya apagado.

**Tech Stack:** Python 3.10+ (FastAPI, pytest), React + Vite + Zustand + Tailwind 3. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-05-15-fase-5-design.md`

**Branch:** `po_overhaul` (continúa desde `fase-4-mvp`). Tag `fase-5-mvp` al cierre.

**Convenciones del proyecto que el implementador DEBE respetar:**
- Commits: inglés, `type(scope): mensaje`, cuerpo en español explicando el por-qué. Trailer `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- `ruff check .` debe dar 0 violaciones antes de cada commit (un hook PostToolUse corre `ruff --fix` + `ruff format` automáticamente sobre `.py`).
- Python 3.10+: `X | None`, no `Optional[X]`.
- No `print()` en código de librería; no `except:` desnudo.
- Tests: sin mocking de base de datos. Mockear render/OCR para tests de flujo de control SÍ está permitido (no es data fabricada, es un doble de prueba de flujo).
- pytest se corre con el venv del proyecto: `.venv-cuda/Scripts/python.exe -m pytest ...`.
- Frontend: no hay runner de tests JS; la verificación de tareas frontend es `npm run build` verde + smoke al final. Usar tokens `po-*`, nunca clases de paleta crudas.

---

## File Structure

**Feature 2 — Cancelación (backend):**
- `core/scanners/utils/corner_count.py` — modificar `count_paginations`: nuevo kwarg `cancel`, checkpoint por página.
- `core/scanners/utils/header_detect.py` — modificar `count_form_codes`: ídem.
- `core/scanners/art_scanner.py` — pasar `cancel` a `count_paginations`.
- `core/scanners/_header_detect_base.py` — pasar `cancel` a `count_form_codes`.
- (`core/scanners/utils/page_count_pure.py` — sin cambios: `count_documents_in_pdf` es un conteo de páginas puro, sin loop de OCR.)

**Feature 3 — Auto-retry (backend):**
- `core/utils.py` — dos constantes nuevas: `OCR_RETRY_COUNT`, `OCR_RETRY_BACKOFF_S`.
- `core/orchestrator.py` — modificar `_ocr_worker`: loop de reintento.

**Feature 1 — Drill-in (frontend):**
- `frontend/src/lib/anomaly.js` — **nuevo**: `anomalyTone` extraído de SparkGrid (DRY: lo usan SparkGrid y HistoryDrawer).
- `frontend/src/ui/Drawer.jsx` — **nuevo**: primitive panel lateral no-modal.
- `frontend/src/components/HistoryDrawer.jsx` — **nuevo**: contenido del drill-in.
- `frontend/src/components/SparkGrid.jsx` — celdas clickeables + resaltado de celda activa.
- `frontend/src/store/session.js` — estado `historyDrawer` + acciones.
- `frontend/src/views/MonthOverview.jsx` — cablear SparkGrid → drawer.

**Tests nuevos:**
- `tests/test_corner_count_cancel.py`
- `tests/test_header_detect_cancel.py`
- `tests/test_ocr_worker_retry.py`

---

## Chunk 1: Backend — cancelación + auto-retry

### Task 1: `count_paginations` honra cancelación por página

**Files:**
- Modify: `core/scanners/utils/corner_count.py` (`count_paginations` línea 92, loop línea 99-115)
- Modify: `core/scanners/art_scanner.py:58` (`count_paginations(pdfs[0])`)
- Test: `tests/test_corner_count_cancel.py` (nuevo)

**Contexto:** `count_paginations` itera todas las páginas del PDF haciendo OCR del recorte de esquina. Hoy no recibe el `CancellationToken`, así que un cancel a mitad espera a que termine el PDF completo. `art_scanner.count_ocr` ya tiene `except CancelledError: raise` y ya recibe `cancel` — solo falta pasarlo a la util.

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_corner_count_cancel.py
"""count_paginations honra cancelación por página — FASE 5 Feature 2."""
from pathlib import Path

import pytest
from PIL import Image

from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.utils import corner_count


def _patch_render(monkeypatch, render_calls, pages):
    """Render/OCR instantáneos y get_page_count fijo — el test es de flujo de
    control, no de OCR real."""
    monkeypatch.setattr(corner_count, "get_page_count", lambda p: pages)

    def fake_render(pdf_path, page_idx, *, bbox, dpi):
        render_calls.append(page_idx)
        return Image.new("RGB", (10, 10))

    monkeypatch.setattr(corner_count, "render_page_region", fake_render)
    monkeypatch.setattr(
        corner_count.pytesseract, "image_to_string", lambda *a, **k: ""
    )


def test_precancelled_token_stops_before_first_page(monkeypatch):
    render_calls: list[int] = []
    _patch_render(monkeypatch, render_calls, pages=20)
    token = CancellationToken()
    token.cancel()

    with pytest.raises(CancelledError):
        corner_count.count_paginations(Path("dummy.pdf"), cancel=token)

    assert render_calls == []  # cortó antes de renderizar la página 0


def test_cancel_mid_loop_stops_within_a_few_pages(monkeypatch):
    render_calls: list[int] = []
    _patch_render(monkeypatch, render_calls, pages=20)

    # Token que se cancela cuando ya se renderizaron 3 páginas.
    token = CancellationToken()

    real_render = corner_count.render_page_region

    def render_then_maybe_cancel(pdf_path, page_idx, *, bbox, dpi):
        img = real_render(pdf_path, page_idx, bbox=bbox, dpi=dpi)
        if len(render_calls) >= 3:
            token.cancel()
        return img

    monkeypatch.setattr(corner_count, "render_page_region", render_then_maybe_cancel)

    with pytest.raises(CancelledError):
        corner_count.count_paginations(Path("dummy.pdf"), cancel=token)

    # Se detuvo a mitad: renderizó ~3-4 páginas, no las 20.
    assert len(render_calls) <= 5


def test_no_cancel_param_still_works(monkeypatch):
    """Backward compat: cancel es opcional, default None."""
    render_calls: list[int] = []
    _patch_render(monkeypatch, render_calls, pages=3)

    result = corner_count.count_paginations(Path("dummy.pdf"))

    assert result.pages_total == 3
    assert len(render_calls) == 3
```

- [ ] **Step 2: Correr el test, verificar que falla**

Run: `.venv-cuda/Scripts/python.exe -m pytest tests/test_corner_count_cancel.py -v`
Expected: FAIL — `count_paginations() got an unexpected keyword argument 'cancel'`.

- [ ] **Step 3: Modificar `count_paginations`**

En `core/scanners/utils/corner_count.py`:

Agregar el import bajo `TYPE_CHECKING` (las anotaciones son strings perezosos por el `from __future__ import annotations` de la línea 10, así que no hay import en runtime ni riesgo circular). Justo después de los imports existentes (después de la línea 19):

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.scanners.cancellation import CancellationToken
```

Cambiar la firma de `count_paginations` (línea 92) para aceptar el kwarg:

```python
def count_paginations(
    pdf_path: Path,
    *,
    dpi: int = 200,
    cancel: CancellationToken | None = None,
) -> CornerCountResult:
```

Y agregar el checkpoint al tope del loop de páginas (el `for page_idx in range(pages_total):` de la línea 99) — primera sentencia dentro del loop, antes del `render_page_region`:

```python
    for page_idx in range(pages_total):
        if cancel is not None:
            cancel.check()
        img: Image.Image = render_page_region(pdf_path, page_idx, bbox=_CORNER_BBOX, dpi=dpi)
        ...
```

(`cancel.check()` levanta `CancelledError` si el token está cancelado. No se importa `CancelledError` acá — la excepción la levanta el token y se propaga sola.)

- [ ] **Step 4: Pasar `cancel` desde art_scanner**

En `core/scanners/art_scanner.py`, línea 58, cambiar:

```python
            ocr = count_paginations(pdfs[0])
```

por:

```python
            ocr = count_paginations(pdfs[0], cancel=cancel)
```

(`art_scanner.count_ocr` ya recibe `cancel: CancellationToken` y ya tiene `except CancelledError: raise` en la línea 59-60 — no se toca nada más.)

- [ ] **Step 5: Correr el test, verificar que pasa**

Run: `.venv-cuda/Scripts/python.exe -m pytest tests/test_corner_count_cancel.py -v`
Expected: PASS — 3/3.

- [ ] **Step 6: Commit**

```bash
git add core/scanners/utils/corner_count.py core/scanners/art_scanner.py tests/test_corner_count_cancel.py
git commit -m "$(cat <<'EOF'
feat(scanners): count_paginations honra cancelación por página

count_paginations acepta un CancellationToken opcional y lo chequea al
tope de cada iteración del loop de páginas, levantando CancelledError.
art_scanner pasa su token. Antes el cancel esperaba a que terminara el
PDF completo; ahora se honra dentro de una página. Spec FASE 5 Feature 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 2: `count_form_codes` honra cancelación por página

**Files:**
- Modify: `core/scanners/utils/header_detect.py` (`count_form_codes` línea 40, loop línea 71-78)
- Modify: `core/scanners/_header_detect_base.py:61` (`count_form_codes(...)`)
- Test: `tests/test_header_detect_cancel.py` (nuevo)

**Contexto:** Estructura idéntica a Task 1. `count_form_codes` itera páginas haciendo OCR del tercio superior. `_header_detect_base.count_ocr` ya recibe `cancel` y ya tiene `except CancelledError: raise`.

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_header_detect_cancel.py
"""count_form_codes honra cancelación por página — FASE 5 Feature 2."""
from pathlib import Path

import pytest
from PIL import Image

from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.utils import header_detect


def _patch_render(monkeypatch, render_calls, pages):
    monkeypatch.setattr(header_detect, "get_page_count", lambda p: pages)

    def fake_render(pdf_path, page_idx, *, bbox, dpi):
        render_calls.append(page_idx)
        return Image.new("RGB", (10, 10))

    monkeypatch.setattr(header_detect, "render_page_region", fake_render)
    monkeypatch.setattr(
        header_detect.pytesseract, "image_to_string", lambda *a, **k: ""
    )


def test_precancelled_token_stops_before_first_page(monkeypatch):
    render_calls: list[int] = []
    _patch_render(monkeypatch, render_calls, pages=20)
    token = CancellationToken()
    token.cancel()

    with pytest.raises(CancelledError):
        header_detect.count_form_codes(
            Path("dummy.pdf"), sigla_code="ODI", cancel=token
        )

    assert render_calls == []


def test_cancel_mid_loop_stops_within_a_few_pages(monkeypatch):
    render_calls: list[int] = []
    _patch_render(monkeypatch, render_calls, pages=20)
    token = CancellationToken()
    real_render = header_detect.render_page_region

    def render_then_maybe_cancel(pdf_path, page_idx, *, bbox, dpi):
        img = real_render(pdf_path, page_idx, bbox=bbox, dpi=dpi)
        if len(render_calls) >= 3:
            token.cancel()
        return img

    monkeypatch.setattr(header_detect, "render_page_region", render_then_maybe_cancel)

    with pytest.raises(CancelledError):
        header_detect.count_form_codes(
            Path("dummy.pdf"), sigla_code="ODI", cancel=token
        )

    assert len(render_calls) <= 5


def test_no_cancel_param_still_works(monkeypatch):
    render_calls: list[int] = []
    _patch_render(monkeypatch, render_calls, pages=3)

    result = header_detect.count_form_codes(Path("dummy.pdf"), sigla_code="ODI")

    assert result.pages_total == 3
    assert len(render_calls) == 3
```

- [ ] **Step 2: Correr el test, verificar que falla**

Run: `.venv-cuda/Scripts/python.exe -m pytest tests/test_header_detect_cancel.py -v`
Expected: FAIL — `count_form_codes() got an unexpected keyword argument 'cancel'`.

- [ ] **Step 3: Modificar `count_form_codes`**

En `core/scanners/utils/header_detect.py` (tiene `from __future__ import annotations` en la línea 8):

Agregar el import bajo `TYPE_CHECKING` después de los imports existentes (después de la línea 17):

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.scanners.cancellation import CancellationToken
```

Cambiar la firma de `count_form_codes` (línea 40) para agregar el kwarg al final:

```python
def count_form_codes(
    pdf_path: Path,
    *,
    sigla_code: str,
    dpi: int = 200,
    cancel: CancellationToken | None = None,
) -> HeaderDetectResult:
```

Agregar el checkpoint al tope del loop de páginas (`for page_idx in range(pages_total):`, línea 71):

```python
    for page_idx in range(pages_total):
        if cancel is not None:
            cancel.check()
        img: Image.Image = render_page_region(pdf_path, page_idx, bbox=_TOP_THIRD_BBOX, dpi=dpi)
        ...
```

- [ ] **Step 4: Pasar `cancel` desde _header_detect_base**

En `core/scanners/_header_detect_base.py`, línea 61, cambiar:

```python
            ocr = count_form_codes(pdfs[0], sigla_code=self.sigla_code)
```

por:

```python
            ocr = count_form_codes(pdfs[0], sigla_code=self.sigla_code, cancel=cancel)
```

- [ ] **Step 5: Correr el test, verificar que pasa**

Run: `.venv-cuda/Scripts/python.exe -m pytest tests/test_header_detect_cancel.py -v`
Expected: PASS — 3/3.

- [ ] **Step 6: Commit**

```bash
git add core/scanners/utils/header_detect.py core/scanners/_header_detect_base.py tests/test_header_detect_cancel.py
git commit -m "$(cat <<'EOF'
feat(scanners): count_form_codes honra cancelación por página

Idéntico a corner_count: count_form_codes acepta un CancellationToken
opcional y lo chequea por página. _header_detect_base (base de irl/odi/
dif_pts/chintegral) pasa su token. Spec FASE 5 Feature 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 3: `_ocr_worker` reintenta scans fallidos en silencio

**Files:**
- Modify: `core/utils.py` (dos constantes nuevas)
- Modify: `core/orchestrator.py` (`_ocr_worker`, líneas 226-256)
- Test: `tests/test_ocr_worker_retry.py` (nuevo)

**Contexto:** `_ocr_worker` corre en un subproceso del `ProcessPoolExecutor`. Hoy, si el `count_ocr` del scanner lanza una excepción, se devuelve el error sin reintentar. El retry va **dentro de `_ocr_worker`** — no en los loops de `scan_cells_ocr` — lo que (a) cubre ambos caminos (sincrónico y multi-worker) con un solo cambio, y (b) evita el `RuntimeError` de re-submitir a un pool ya apagado, porque no hay re-submisión: el worker ya en ejecución simplemente reintenta su propia llamada.

`_ocr_worker` actual (líneas 226-256) — leer antes de modificar. Devuelve `(hosp, sigla, ScanResult|None, err|None)`.

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_ocr_worker_retry.py
"""_ocr_worker reintenta scans OCR fallidos en silencio — FASE 5 Feature 3."""
import core.scanners as scanner_registry
from core import orchestrator
from core.scanners.cancellation import CancelledError


class _FlakyScanner:
    """count_ocr falla `fail_times` veces y después tiene éxito."""

    def __init__(self, fail_times):
        self.fail_times = fail_times
        self.calls = 0

    def count_ocr(self, folder, *, cancel):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("transient tesseract crash")
        return "OK_RESULT"


def _setup(monkeypatch, scanner):
    monkeypatch.setattr(orchestrator, "_WORKER_EVENT", None)
    monkeypatch.setattr(scanner_registry, "get", lambda sigla: scanner)
    # Backoff instantáneo — no esperar en el test.
    monkeypatch.setattr(orchestrator.time, "sleep", lambda s: None)


def test_recovers_after_retries(monkeypatch):
    scanner = _FlakyScanner(fail_times=2)
    _setup(monkeypatch, scanner)

    h, s, result, err = orchestrator._ocr_worker(("HRB", "art", "/tmp/x"))

    assert err is None
    assert result == "OK_RESULT"
    assert scanner.calls == 3  # 2 fallos + 1 éxito


def test_gives_up_after_two_retries(monkeypatch):
    scanner = _FlakyScanner(fail_times=99)
    _setup(monkeypatch, scanner)

    h, s, result, err = orchestrator._ocr_worker(("HRB", "art", "/tmp/x"))

    assert result is None
    assert "transient tesseract crash" in err
    assert scanner.calls == 3  # intento inicial + 2 reintentos


def test_cancelled_does_not_retry(monkeypatch):
    class _CancelScanner:
        def __init__(self):
            self.calls = 0

        def count_ocr(self, folder, *, cancel):
            self.calls += 1
            raise CancelledError()

    scanner = _CancelScanner()
    _setup(monkeypatch, scanner)

    h, s, result, err = orchestrator._ocr_worker(("HRB", "art", "/tmp/x"))

    assert err == "cancelled"
    assert scanner.calls == 1  # sin reintento
```

- [ ] **Step 2: Correr el test, verificar que falla**

Run: `.venv-cuda/Scripts/python.exe -m pytest tests/test_ocr_worker_retry.py -v`
Expected: FAIL — `test_recovers_after_retries` falla porque hoy no hay retry (`scanner.calls == 1`, no 3); o `AttributeError` en `orchestrator.time` si `time` no está importado a nivel de módulo.

- [ ] **Step 3: Agregar las constantes a `core/utils.py`**

En `core/utils.py`, junto a las otras constantes de configuración (cerca de `BATCH_SIZE`), agregar:

```python
# OCR auto-retry (FASE 5) — el orquestador reintifica un scan de celda fallido
# en silencio antes de reportar el error.
OCR_RETRY_COUNT = 2          # reintentos tras el intento inicial (3 intentos totales)
OCR_RETRY_BACKOFF_S = 0.5    # pausa entre intentos
```

- [ ] **Step 4: Agregar `import time` al tope de orchestrator.py**

`core/orchestrator.py` NO importa `time` a nivel de módulo (sus imports del tope son `__future__`, `collections.abc`, `dataclasses`, `pathlib`, `typing`, `core.domain`). Agregar `import time` al bloque de imports del tope, en orden alfabético (el hook de `ruff format` lo reordenará si hace falta). El test hace `monkeypatch.setattr(orchestrator.time, "sleep", ...)`, lo que requiere que `time` sea un atributo del módulo.

- [ ] **Step 5: Reescribir `_ocr_worker`**

Reemplazar el cuerpo de `_ocr_worker` (`core/orchestrator.py`, líneas 226-256) por:

```python
def _ocr_worker(
    cell_tuple: tuple[str, str, str],
) -> tuple[str, str, ScanResult | None, str | None]:
    """Run OCR for a single cell. Runs in a worker subprocess.

    On a transient failure the scan is retried up to ``OCR_RETRY_COUNT`` times
    with a short backoff (FASE 5 Feature 3). A cancelled token never triggers a
    retry. Returns ``(hospital, sigla, ScanResult | None, error_str | None)`` —
    exactly one of ScanResult or error_str is non-None.
    """
    from core import scanners as scanner_registry  # noqa: E402
    from core.scanners.cancellation import (  # noqa: E402
        CancellationToken,
        CancelledError,
    )
    from core.utils import OCR_RETRY_BACKOFF_S, OCR_RETRY_COUNT  # noqa: E402

    hosp, sigla, folder_str = cell_tuple
    folder = Path(folder_str)
    scanner = scanner_registry.get(sigla)
    token = CancellationToken.from_event(_WORKER_EVENT) if _WORKER_EVENT else CancellationToken()

    fn = getattr(scanner, "count_ocr", None)
    if fn is None:
        # No OCR technique for this sigla — single filename_glob attempt, no retry.
        try:
            result = scanner.count(folder)
        except Exception as exc:  # noqa: BLE001
            return (hosp, sigla, None, f"{type(exc).__name__}: {exc}")
        return (hosp, sigla, result, None)

    last_err: str | None = None
    for attempt in range(OCR_RETRY_COUNT + 1):
        if token.cancelled:
            return (hosp, sigla, None, "cancelled")
        try:
            result = fn(folder, cancel=token)
            return (hosp, sigla, result, None)
        except CancelledError:
            return (hosp, sigla, None, "cancelled")
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
            if attempt < OCR_RETRY_COUNT:
                time.sleep(OCR_RETRY_BACKOFF_S)
    return (hosp, sigla, None, last_err)
```

Notas:
- El reintento solo aplica al camino con `count_ocr`. El fallback `scanner.count(folder)` (filename_glob, sin OCR) no se reintenta — no es un fallo OCR.
- `token.cancelled` se chequea ANTES de cada intento: si un cancel llega durante la ventana de backoff, el siguiente intento no corre.
- `time.sleep` usa el `time` importado a nivel de módulo (Step 4).

- [ ] **Step 6: Correr el test, verificar que pasa**

Run: `.venv-cuda/Scripts/python.exe -m pytest tests/test_ocr_worker_retry.py -v`
Expected: PASS — 3/3.

- [ ] **Step 7: Commit**

```bash
git add core/utils.py core/orchestrator.py tests/test_ocr_worker_retry.py
git commit -m "$(cat <<'EOF'
feat(orchestrator): auto-retry silencioso de OCR en _ocr_worker

_ocr_worker reintenta un count_ocr fallido hasta OCR_RETRY_COUNT veces
(2) con backoff corto, en silencio. El retry vive dentro del worker —no
en los loops de scan_cells_ocr— así cubre el camino sincrónico y el
multi-worker con un solo cambio, y evita re-submitir a un pool ya
apagado. Un CancelledError nunca dispara retry. Spec FASE 5 Feature 3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 3.5: Regresión de Chunk 1

- [ ] **Step 1: Correr la suite de scanners + orquestador**

Run: `.venv-cuda/Scripts/python.exe -m pytest tests/ -k "scanner or orchestrator or corner or header or ocr_worker" -q`
Expected: todo verde. Si algo se rompió, arreglar antes de seguir.

- [ ] **Step 2: Ruff**

Run: `.venv-cuda/Scripts/python.exe -m ruff check .`
Expected: `All checks passed!`

---

## Chunk 2: Frontend — histórico drill-in

### Task 4: Extraer `anomalyTone` a `lib/anomaly.js`

**Files:**
- Create: `frontend/src/lib/anomaly.js`
- Modify: `frontend/src/components/SparkGrid.jsx` (quitar la función local, importar)

**Contexto:** `SparkGrid.jsx` define `anomalyTone` localmente (líneas 7-17). El `HistoryDrawer` (Task 7) necesita la misma lógica. Se extrae a un módulo compartido (DRY) antes de que haya dos copias.

- [ ] **Step 1: Crear `frontend/src/lib/anomaly.js`**

```js
// Detector de caída. Devuelve "warn" cuando el último mes cae bajo 0.7x el
// promedio de los 6 meses previos, con baseline efectivo >= 6 puntos. NO marca
// picos hacia arriba — es un detector de caída, no de anomalía genérica.
// Compartido por SparkGrid (tono de celda) y HistoryDrawer (línea + fila).
export function anomalyTone(series) {
  if (!series || series.length < 7) return "neutral";
  const last = series[series.length - 1].count;
  const baseline = series.slice(-7, -1);
  const valid = baseline.filter((p) => p && p.count > 0);
  if (valid.length < 6) return "neutral";
  const mean = valid.reduce((a, b) => a + b.count, 0) / valid.length;
  if (mean === 0) return "neutral";
  return last / mean < 0.7 ? "warn" : "neutral";
}
```

- [ ] **Step 2: Modificar `SparkGrid.jsx`**

Quitar la función `anomalyTone` local (líneas 7-17 completas, incluyendo la línea en blanco que la separa). Agregar el import junto a los otros del tope:

```js
import Sparkline from "./Sparkline";
import Tooltip from "../ui/Tooltip";
import { SIGLAS } from "../lib/sigla-labels";
import { anomalyTone } from "../lib/anomaly";
```

El resto de `SparkGrid.jsx` no cambia — sigue llamando `anomalyTone(series)` igual.

- [ ] **Step 3: Verificar build**

Run: `cd frontend && npm run build`
Expected: build verde.

- [ ] **Step 4: Commit**

```bash
cd a:/PROJECTS/PDFoverseer
git add frontend/src/lib/anomaly.js frontend/src/components/SparkGrid.jsx
git commit -m "$(cat <<'EOF'
refactor(frontend): extraer anomalyTone a lib/anomaly.js

anomalyTone vivía dentro de SparkGrid; el HistoryDrawer de FASE 5 necesita
la misma lógica. Movido a un módulo compartido antes de duplicar. Idéntica
lógica, cero cambio de comportamiento.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 5: Primitive `ui/Drawer.jsx`

**Files:**
- Create: `frontend/src/ui/Drawer.jsx`

**Contexto:** Panel lateral derecho **no-modal**. A diferencia de `ui/Dialog.jsx` (Radix Dialog: modal, focus-trap, overlay opaco que bloquea el fondo), el `Drawer` NO bloquea ni atrapa el foco — el `SparkGrid` detrás debe seguir clickeable para poder cambiar de serie. Por eso es un componente propio, no un wrap de Radix Dialog. Sin overlay/scrim. Cierra con ESC y con la X.

- [ ] **Step 1: Crear `frontend/src/ui/Drawer.jsx`**

```jsx
import { useEffect } from "react";
import { X } from "lucide-react";

/**
 * Panel lateral derecho, no-modal. El contenido detrás permanece interactivo
 * (sin overlay, sin focus-trap) — a propósito: el SparkGrid debe seguir
 * clickeable mientras el drawer está abierto.
 *
 *   <Drawer open={...} onClose={...} title={<...>}>
 *     ...contenido...
 *   </Drawer>
 *
 * Siempre montado (para la transición). Cuando !open: deslizado fuera de
 * pantalla + pointer-events-none para no capturar clicks.
 */
export default function Drawer({ open, onClose, title, children }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <aside
      aria-hidden={!open}
      className={[
        "fixed top-0 right-0 bottom-0 z-40 w-[420px]",
        "bg-po-panel border-l border-po-border shadow-2xl",
        "flex flex-col transition-transform duration-200 ease-out",
        open ? "translate-x-0" : "translate-x-full pointer-events-none",
      ].join(" ")}
    >
      <header className="px-4 py-3 border-b border-po-border flex items-center gap-3 shrink-0">
        <div className="flex-1 min-w-0">{title}</div>
        <button
          type="button"
          onClick={onClose}
          className="text-po-text-muted hover:text-po-text shrink-0"
          aria-label="Cerrar"
        >
          <X size={18} strokeWidth={1.75} />
        </button>
      </header>
      <div className="flex-1 min-h-0 overflow-y-auto">{children}</div>
    </aside>
  );
}
```

- [ ] **Step 2: Verificar build**

Run: `cd frontend && npm run build`
Expected: build verde (el componente todavía no se importa en ningún lado — solo debe parsear).

- [ ] **Step 3: Commit**

```bash
cd a:/PROJECTS/PDFoverseer
git add frontend/src/ui/Drawer.jsx
git commit -m "$(cat <<'EOF'
feat(ui): primitive Drawer — panel lateral no-modal

Panel que desliza desde la derecha. No-modal a propósito: sin overlay ni
focus-trap, el contenido detrás (SparkGrid) sigue interactivo para poder
cambiar de serie sin cerrar. Cierra con ESC y con la X. Spec FASE 5
Feature 1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 6: Estado `historyDrawer` en el store

**Files:**
- Modify: `frontend/src/store/session.js`

**Contexto:** El store Zustand ya tiene `historyView` (FASE 4) y resetea estado en `setView`. Se agrega `historyDrawer: { hospital, sigla } | null` siguiendo ese patrón. El drawer solo existe dentro de la vista Histórico, así que el estado se limpia al salir de ese contexto.

- [ ] **Step 1: Agregar el campo de estado**

En `frontend/src/store/session.js`, después de `historyView: false,` (línea 15), agregar:

```js
  historyView: false,
  historyDrawer: null,   // { hospital, sigla } | null — drill-in del SparkGrid
```

- [ ] **Step 2: Agregar las acciones**

Después de `setHistoryView` (líneas 34-35), agregar las dos acciones del drawer, y modificar `setHistoryView` para que limpie el drawer al cambiar de vista:

```js
  toggleHistoryView: () => set((s) => ({ historyView: !s.historyView, historyDrawer: null })),
  setHistoryView: (v) => set({ historyView: !!v, historyDrawer: null }),

  openHistoryDrawer: (hospital, sigla) => set({ historyDrawer: { hospital, sigla } }),
  closeHistoryDrawer: () => set({ historyDrawer: null }),
```

(Cambiar `toggleHistoryView` y `setHistoryView` para incluir `historyDrawer: null` — al togglear la vista, un drawer abierto debe cerrarse porque el SparkGrid se desmonta.)

- [ ] **Step 3: Limpiar el drawer al cambiar de mes**

Localizar la acción `openMonth`:

Run: `grep -n "openMonth" frontend/src/store/session.js`

En el `set({...})` de `openMonth` (cambiar de mes implica otra serie histórica), agregar `historyDrawer: null` al objeto que se pasa a `set`. Si `openMonth` hace varios `set` o uno solo, agregarlo al `set` que establece la sesión nueva. Ejemplo de la forma esperada:

```js
  openMonth: async (sessionId, year, month) => {
    // ...lógica existente...
    set({ session: ..., historyDrawer: null /* ◀ NUEVO */, ... });
  },
```

- [ ] **Step 4: Verificar build**

Run: `cd frontend && npm run build`
Expected: build verde.

- [ ] **Step 5: Commit**

```bash
cd a:/PROJECTS/PDFoverseer
git add frontend/src/store/session.js
git commit -m "$(cat <<'EOF'
feat(store): estado historyDrawer para el drill-in del histórico

historyDrawer { hospital, sigla } | null, siguiendo el patrón de
historyView. openHistoryDrawer/closeHistoryDrawer lo controlan; se limpia
al togglear la vista o cambiar de mes (el SparkGrid se desmonta). Spec
FASE 5 Feature 1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 7: Componente `HistoryDrawer.jsx`

**Files:**
- Create: `frontend/src/components/HistoryDrawer.jsx`

**Contexto:** Componente presentacional que consume `Drawer` y renderea el contenido del drill-in (validado en mockup): header, stats strip, gráfico de línea, tabla mes-a-mes con chips de método. Recibe la serie ya resuelta como prop — no hace fetch (la data viene de la cache de `useHistoryStore`, MonthOverview hace el lookup en Task 8).

`series` es un array de `{ year, month, count, confidence, method }`, ordenado de más viejo a más nuevo (así lo devuelve el endpoint `/history`).

- [ ] **Step 1: Crear `frontend/src/components/HistoryDrawer.jsx`**

```jsx
import Drawer from "../ui/Drawer";
import OriginChip from "./OriginChip";
import { SIGLA_LABELS } from "../lib/sigla-labels";
import { anomalyTone } from "../lib/anomaly";

// Método de historical_counts → variante de OriginChip.
function methodToOrigin(method) {
  if (method === "manual") return "manual";
  if (method === "filename_glob") return "R1";
  return "OCR"; // header_detect / corner_count / page_count_pure
}

const MES = (p) => `${String(p.month).padStart(2, "0")}/${p.year}`;

// Gráfico de línea inline — 12 puntos, último resaltado.
function SeriesChart({ counts, tone }) {
  const W = 380;
  const H = 110;
  const PAD = 12;
  if (counts.length === 0) return null;
  const max = Math.max(...counts, 1);
  const min = Math.min(...counts);
  const range = Math.max(max - min, 1);
  const xFor = (i) =>
    PAD + (i / Math.max(counts.length - 1, 1)) * (W - 2 * PAD);
  const yFor = (c) => PAD + (1 - (c - min) / range) * (H - 2 * PAD);
  const points = counts.map((c, i) => `${xFor(i).toFixed(1)},${yFor(c).toFixed(1)}`).join(" ");
  const stroke = tone === "warn" ? "stroke-po-suspect" : "stroke-po-accent";
  const fill = tone === "warn" ? "fill-po-suspect" : "fill-po-accent";
  const lastIdx = counts.length - 1;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} className="block">
      <polyline fill="none" strokeWidth={2} className={stroke} points={points} />
      <circle cx={xFor(lastIdx)} cy={yFor(counts[lastIdx])} r={3.5} className={fill} />
    </svg>
  );
}

/**
 * Drill-in read-only de una serie histórica (hospital x sigla).
 *
 * Props:
 *   open      — bool
 *   hospital  — string | null
 *   sigla     — string | null
 *   series    — [{year, month, count, confidence, method}] | undefined
 *               (orden viejo → nuevo, como lo devuelve /history)
 *   onClose   — () => void
 */
export default function HistoryDrawer({ open, hospital, sigla, series, onClose }) {
  const points = series ?? [];
  const counts = points.map((p) => p.count);
  const tone = anomalyTone(points);

  const title = (
    <div>
      <div className="text-sm font-semibold text-po-text">
        {hospital} · {sigla}
      </div>
      {sigla && (
        <div className="text-xs text-po-text-muted truncate">
          {SIGLA_LABELS[sigla] ?? sigla}
        </div>
      )}
    </div>
  );

  const hasData = counts.length > 0;
  const last = hasData ? counts[counts.length - 1] : 0;
  const avg = hasData ? Math.round(counts.reduce((a, b) => a + b, 0) / counts.length) : 0;
  const lo = hasData ? Math.min(...counts) : 0;
  const hi = hasData ? Math.max(...counts) : 0;
  // Fila anómala: solo si la serie entera es "warn", el último mes la marca.
  const anomalyKey = tone === "warn" && hasData ? MES(points[points.length - 1]) : null;

  return (
    <Drawer open={open} onClose={onClose} title={title}>
      {!hasData ? (
        <div className="p-6 text-sm text-po-text-muted">
          Sin datos históricos para esta serie.
        </div>
      ) : (
        <div className="p-4 space-y-4">
          {/* Stats strip */}
          <div className="flex gap-4">
            <Stat value={last} label="Último" />
            <Stat value={avg} label="Promedio 12m" />
            <Stat value={`${lo}–${hi}`} label="Rango" />
          </div>

          {/* Gráfico */}
          <div className="rounded-lg bg-po-bg border border-po-border p-2">
            <SeriesChart counts={counts} tone={tone} />
          </div>

          {/* Tabla mes-a-mes (más reciente arriba) */}
          <div className="text-sm">
            <div className="grid grid-cols-[1fr_auto_64px] gap-2 px-1 pb-1.5 text-[10px] uppercase tracking-wide text-po-text-subtle">
              <span>Mes</span>
              <span className="text-right">Conteo</span>
              <span className="text-center">Método</span>
            </div>
            {[...points].reverse().map((p) => {
              const isAnomaly = MES(p) === anomalyKey;
              return (
                <div
                  key={`${p.year}-${p.month}`}
                  className={[
                    "grid grid-cols-[1fr_auto_64px] gap-2 px-1 py-1.5 items-center border-t border-po-border",
                    isAnomaly ? "bg-po-suspect-bg rounded" : "",
                  ].join(" ")}
                >
                  <span className="text-po-text-muted tabular-nums">{MES(p)}</span>
                  <span
                    className={[
                      "text-right tabular-nums",
                      isAnomaly ? "text-po-suspect font-semibold" : "text-po-text",
                    ].join(" ")}
                  >
                    {p.count}
                  </span>
                  <div className="flex justify-center">
                    <OriginChip origin={methodToOrigin(p.method)} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Drawer>
  );
}

function Stat({ value, label }) {
  return (
    <div className="flex-1">
      <div className="text-xl font-semibold text-po-text tabular-nums">{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-po-text-subtle mt-0.5">
        {label}
      </div>
    </div>
  );
}
```

Notas:
- `po-suspect-bg` es un token pre-compuesto de FASE 3 (fondo alpha ámbar) — usar ese, no `po-suspect` con modificador de opacidad (los tokens `po-*` no aceptan `/opacity`, ver memoria del proyecto).
- Si `npm run build` se queja de que `po-suspect-bg` no existe, verificar el nombre exacto del token en `frontend/tailwind.config.js` y usar el correcto de la familia suspect.

- [ ] **Step 2: Verificar build**

Run: `cd frontend && npm run build`
Expected: build verde (el componente todavía no se monta — solo debe parsear y resolver imports/tokens).

- [ ] **Step 3: Commit**

```bash
cd a:/PROJECTS/PDFoverseer
git add frontend/src/components/HistoryDrawer.jsx
git commit -m "$(cat <<'EOF'
feat(history): componente HistoryDrawer — drill-in read-only

Consume el primitive Drawer y renderea el contenido validado en mockup:
header hospital·sigla, stats strip (último/promedio/rango), gráfico de
línea de 12 meses y tabla mes-a-mes con chips de método (OriginChip).
Fila ámbar para el mes anómalo. Presentacional puro — la serie llega por
prop desde la cache de useHistoryStore. Spec FASE 5 Feature 1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 8: SparkGrid clickeable + cableado en MonthOverview

**Files:**
- Modify: `frontend/src/components/SparkGrid.jsx`
- Modify: `frontend/src/views/MonthOverview.jsx`

**Contexto:** Última pieza — hacer las celdas del SparkGrid clickeables y montar el `HistoryDrawer` en `MonthOverview`. La celda activa (cuya serie está abierta) lleva un anillo de resaltado.

- [ ] **Step 1: SparkGrid acepta `onCellClick` + `activeCell`**

En `frontend/src/components/SparkGrid.jsx`, cambiar la firma del componente:

```jsx
export default function SparkGrid({ history, onCellClick, activeCell }) {
```

Dentro del `.map` de hospitales (el bloque `HOSPITALS.map((h) => { ... })`, líneas ~52-73), el contenido de la celda hoy es un `<div>` envuelto en `<Tooltip>`. Cambiar ese `<div>` por un `<button>` que invoque `onCellClick`, y agregar el anillo cuando la celda está activa:

```jsx
          {HOSPITALS.map((h) => {
            const series = history?.[`${h}|${code}`] ?? [];
            const tone = anomalyTone(series);
            const last = series.length > 0 ? series[series.length - 1].count : "—";
            const isActive = activeCell?.hospital === h && activeCell?.sigla === code;
            return (
              <Tooltip key={h} content={<TooltipRows series={series} />}>
                <button
                  type="button"
                  onClick={() => onCellClick(h, code)}
                  className={[
                    "px-3 py-2 flex items-center justify-between gap-2 w-full text-left",
                    "hover:bg-po-panel-hover transition",
                    isActive ? "ring-2 ring-inset ring-po-accent bg-po-panel-hover" : "",
                  ].join(" ")}
                >
                  <Sparkline data={series.map((p) => p.count)} tone={tone} />
                  <span
                    className={`text-sm tabular-nums ${
                      tone === "warn"
                        ? "text-po-suspect font-semibold"
                        : "text-po-text"
                    }`}
                  >
                    {last}
                    {tone === "warn" && " ↓"}
                  </span>
                </button>
              </Tooltip>
            );
          })}
```

(Cambios: `<div ... cursor-default>` → `<button type="button" onClick=...>`, ancho `w-full text-left` para que el botón llene la celda del grid, y la clase condicional `ring` para `isActive`.)

- [ ] **Step 2: MonthOverview cablea el drawer**

En `frontend/src/views/MonthOverview.jsx`:

Agregar el import de `HistoryDrawer` junto a los otros (después de `import SparkGrid`):

```jsx
import SparkGrid from "../components/SparkGrid";
import HistoryDrawer from "../components/HistoryDrawer";
```

Extender el destructuring del store (líneas 13-17) para incluir el estado y acciones del drawer:

```jsx
  const {
    months, session, loading, error,
    loadMonths, openMonth, selectHospital, runScan, generateOutput,
    historyView, setHistoryView,
    historyDrawer, openHistoryDrawer, closeHistoryDrawer,
  } = useSessionStore();
```

Cambiar el render del `SparkGrid` (línea 121) para pasarle los handlers, y montar el `HistoryDrawer` justo después. Reemplazar:

```jsx
            {historyView ? (
              <SparkGrid history={history} />
            ) : (
```

por:

```jsx
            {historyView ? (
              <SparkGrid
                history={history}
                onCellClick={openHistoryDrawer}
                activeCell={historyDrawer}
              />
            ) : (
```

Y montar el `HistoryDrawer` al final del componente — justo antes del `{error && ...}` de la línea 140, agregar:

```jsx
      <HistoryDrawer
        open={!!historyDrawer}
        hospital={historyDrawer?.hospital ?? null}
        sigla={historyDrawer?.sigla ?? null}
        series={
          historyDrawer
            ? history?.[`${historyDrawer.hospital}|${historyDrawer.sigla}`]
            : undefined
        }
        onClose={closeHistoryDrawer}
      />

      {error && <p className="text-po-error">{error}</p>}
```

(El `HistoryDrawer` queda montado siempre — el `Drawer` se encarga de la animación open/close. `series` se resuelve desde el mismo objeto `history` que ya alimenta al SparkGrid: cero fetch nuevo.)

- [ ] **Step 3: Verificar build**

Run: `cd frontend && npm run build`
Expected: build verde.

- [ ] **Step 4: Commit**

```bash
cd a:/PROJECTS/PDFoverseer
git add frontend/src/components/SparkGrid.jsx frontend/src/views/MonthOverview.jsx
git commit -m "$(cat <<'EOF'
feat(history): SparkGrid clickeable + HistoryDrawer en MonthOverview

Las celdas del SparkGrid pasan a ser botones que abren el drill-in; la
celda activa lleva un anillo po-accent. MonthOverview cablea
onCellClick → openHistoryDrawer y monta el HistoryDrawer, resolviendo la
serie desde el mismo objeto history cacheado por useHistoryStore — sin
requests nuevos. Spec FASE 5 Feature 1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Chunk 3: Smoke + cierre

### Task 9: Smoke E2E vía chrome-devtools MCP

**Files:** ninguno (a menos que el smoke encuentre bugs)

**Contexto:** Verificación visual end-to-end manejada por Claude vía chrome-devtools MCP (Brave corre en modo debugging — ver memoria `feedback_browser_testing_via_devtools`). NO entregar un checklist al usuario.

- [ ] **Step 1: Arrancar backend + frontend**

Backend: `.venv-cuda/Scripts/python.exe server.py` (background).
Frontend: `cd frontend && npm run dev` (background).
Esperar a que ambos respondan (el backend bindea en `localhost:8000`, el frontend en `localhost:5173` — nota: en esta máquina los servers escuchan en IPv6 `::1`, usar `localhost`, no `127.0.0.1`).

- [ ] **Step 2: Smoke AC1 — Drill-in**

- [ ] Navegar a `http://localhost:5173`, abrir un mes (ABRIL 2026).
- [ ] Click en el toggle "Histórico" → aparece el SparkGrid.
- [ ] Click en una celda → el drawer lateral derecho abre con esa serie: header, stats, gráfico, tabla.
- [ ] Click en otra celda → el drawer cambia de serie sin cerrarse; la celda activa muestra el anillo.
- [ ] El grid detrás permanece clickeable con el drawer abierto.
- [ ] ESC cierra el drawer; la X cierra el drawer.
- [ ] Una celda sin datos históricos muestra el estado vacío sin crashear.
- [ ] Verificar en la pestaña Network de chrome-devtools que abrir el drawer NO dispara requests nuevos.
- [ ] Capturar screenshots → `docs/research/fase5-smoke-drill-*.png`.

- [ ] **Step 3: Smoke AC2 — Cancelación**

- [ ] Entrar a un hospital con compilaciones (HRB), seleccionar una o más siglas de compilación, lanzar OCR.
- [ ] Con el escaneo en curso, presionar Cancelar.
- [ ] Verificar que el escaneo se detiene rápido (≤3 s; cronometrar a ojo).
- [ ] Verificar que las celdas ya completadas conservan su OCR y la interrumpida queda en su conteo R1.
- [ ] Capturar screenshot → `docs/research/fase5-smoke-cancel.png`.

- [ ] **Step 4: Smoke AC4 — Cross-cutting / no-regresión**

- [ ] `.venv-cuda/Scripts/python.exe -m ruff check .` → 0 violaciones.
- [ ] `.venv-cuda/Scripts/python.exe -m pytest -q` → toda la suite verde.
- [ ] `cd frontend && npm run build` → verde; anotar el delta de bundle vs FASE 4 (baseline 92.38 kB gzipped).
- [ ] Verificar que las features FASE 4 no regresionaron: HLL manual flow, per-file overrides en FileList, toggle Histórico/SparkGrid.

(AC3 — auto-retry — se verifica por los tests unitarios de Task 3; no requiere smoke manual porque el fallo es difícil de provocar a mano.)

- [ ] **Step 5: Para cada bug encontrado**

Backend: escribir el test que falla, arreglar, commit aparte `fix(<scope>): <bug>`.
Frontend: arreglar, commit aparte. Mover el tag (Task 10) después de los fixes.

- [ ] **Step 6: Commit de los screenshots**

```bash
git add docs/research/fase5-smoke-*.png
git commit -m "$(cat <<'EOF'
docs(research): FASE 5 smoke screenshots

Capturas E2E del drill-in (drawer, cambio de serie, estado vacío) y de la
cancelación, vía chrome-devtools MCP.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 10: Actualizar CLAUDE.md + tag `fase-5-mvp`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Inspeccionar las secciones FASE en CLAUDE.md**

Run: `grep -n "^## FASE\|^### FASE" CLAUDE.md`

- [ ] **Step 2: Demote FASE 4 a predecesor**

Seguir el patrón exacto con el que FASE 4 demotó a FASE 3:
- `## FASE 4 UX slice — ...` → `### FASE 4 UX slice — predecessor, ...`
- Cualquier subsección `### ` dentro del bloque FASE 4 → `#### `.

- [ ] **Step 3: Agregar la sección FASE 5 al tope (sobre FASE 4)**

```markdown
## FASE 5 UX slice — `po_overhaul` branch (shipped 2026-05-XX)

Slice UX cerrando 3 pendientes del roadmap post-FASE 4:

1. **Histórico drill-in**: click en celda del SparkGrid abre `HistoryDrawer`
   (primitive `ui/Drawer.jsx` no-modal); serie de 12 meses con stats, gráfico
   de línea y tabla mes-a-mes con chips de método. Read-only, estado
   `historyDrawer` en Zustand, cero backend (lee la cache de `useHistoryStore`).
2. **Cancelación a nivel de página**: `count_paginations` y `count_form_codes`
   reciben el `CancellationToken` y lo chequean por página (levanta
   `CancelledError`); un cancel se honra en <3 s.
3. **Auto-retry OCR**: `_ocr_worker` reintenta un scan fallido 2× en silencio
   (`OCR_RETRY_COUNT`/`OCR_RETRY_BACKOFF_S` en `core/utils.py`); un
   `CancelledError` nunca dispara retry.

- **Spec:** `docs/superpowers/specs/2026-05-15-fase-5-design.md`
- **Plan:** `docs/superpowers/plans/2026-05-15-pdfoverseer-fase-5.md`
- **Tag:** `fase-5-mvp` (local, awaiting push approval)
- **Bundle delta:** [completar tras smoke] (baseline FASE 4 92.38 kB gzipped)
- **New deps:** ninguna

### Next (roadmap restante)
- Refinamiento de motores OCR por tipo de documento (fase FINAL — cada doc type
  con sus parámetros propios; ver memoria `project_ocr_refinement_deferred`).
```

- [ ] **Step 4: Verificar ruff + tests verdes**

Run: `.venv-cuda/Scripts/python.exe -m ruff check .` → `All checks passed!`
Run: `.venv-cuda/Scripts/python.exe -m pytest -q` → verde.

- [ ] **Step 5: Commit + tag**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(claude-md): FASE 5 section + demote FASE 4 to predecessor

Mismo patrón que FASE 4 con FASE 3. Incluye spec/plan links, tag, bundle
delta, deps, y el next-step del roadmap (refinamiento OCR, fase final).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git tag fase-5-mvp
git log --oneline -1
```

- [ ] **Step 6: Surface al usuario — aprobación de push**

Imprimir resumen: commits sobre `po_overhaul`, tag local `fase-5-mvp`, bundle delta. NO hacer push automático — esperar aprobación explícita (regla mantenida desde FASE 3).

---

## Done

Al completar las 10 tasks: FASE 5 implementada, testeada y smoke-verificada, tag `fase-5-mvp` local esperando aprobación de push.
