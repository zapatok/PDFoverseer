# Track D — OCR speed (tesserocr + RCH→paginación) + visor reorg — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development
> (if subagents available) or superpowers:executing-plans to implement this plan.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ejecutar el Track D del spec
`docs/superpowers/specs/2026-07-12-track-d-ocr-speed-design.md`: D1 spike
tesserocr (seam pluggable, ~2x), D2 experimento RCH→paginación (eval-first,
gate por sigla), D3 visor reorg (teclado + miniaturas reales).

**Architecture:** D1 = un seam `ocr_backend.py` con backend seleccionable por
env y gate de equivalencia de conteos. D2 = caracterización → prototipo en
`eval/pagination_count/` → benchmark → gate por sigla → flip de registro de
una línea (o registro de fracaso). D3 = frontend puro sobre la lógica
`reorg-range` y el pipeline de thumbnails existentes.

**Tech Stack:** Python 3.10+ (pytesseract/tesserocr, PyMuPDF, pytest),
React+Vite+Zustand (vitest).

---

## Contexto para el ejecutor (LEER PRIMERO — vinculante)

- **El spec es la autoridad de diseño**:
  `docs/superpowers/specs/2026-07-12-track-d-ocr-speed-design.md`. Si este
  plan y el spec difieren, manda el spec. Leerlo ENTERO antes del Chunk D1.
- **D1 y D2 son EXPERIMENTOS con gates**: un gate no pasado NO se
  racionaliza — se ejecuta la salida por fracaso que el spec define (que
  también es un entregable válido). Los reviewers deben verificar los gates
  CORRIENDO los benchmarks, no leyendo.
- Trabajar directo en `po_overhaul` (sin worktrees). Push al cierre.
- Comandos base (desde `a:/PROJECTS/PDFoverseer`):
  - Backend/eval: `.venv-cuda/Scripts/python.exe -m pytest <ruta> -q`
  - Frontend: `cd frontend && npx vitest run <ruta>`
  - Lint: `ruff check .` = 0 antes de cada commit
- **Samples only**: escaneos de prueba SOLO sobre `data/samples/` +
  fixtures sintéticos. El corpus `A:\informe mensual` es READ-ONLY y no se
  barre nunca completo. El DB real `data/overseer.db` no se toca (tests →
  tmp_path; está en WAL y lo sostiene el backend vivo).
- **OUTPUT GUARD** (si algún chunk tocó `core/`): copiar el DB real con la
  API de backup de sqlite (`src.backup(dst)` — copia plana NO es fiel por el
  WAL), `python tools/dump_counts.py --db <copia>` con el código del commit
  base de la ronda (worktree detached temporal) vs HEAD → byte-idéntico
  salvo diffs que el benchmark de D2 haya predicho y Daniel aprobado.
- Nunca `git add -A`/`.` — stagear rutas explícitas. Commits en inglés
  `type(scope): message`. Microcopy nueva: español neutro (tú, jamás vos).
  Tailwind: solo tokens `po-*`. Zustand v5: jamás literales frescos dentro
  de un selector.
- `SCANNER_PATTERNS_VERSION` (core/utils.py, hoy `v7-irl-cover`): bump
  **manual** en cualquier migración de sigla — ningún hook lo recuerda.

---

## Chunk D1: spike tesserocr + seam (spec §2)

### Task 1: spike de instalación (timebox)

**Files:** ninguno del repo (solo el venv). Registro:
`docs/research/2026-07-XX-tesserocr-spike.md` (crear al final del chunk).

- [ ] **Step 1:** `.venv-cuda/Scripts/python.exe -m pip install tesserocr` —
  si instala, saltar a Step 3.
- [ ] **Step 2:** Si falló: buscar en
  `https://github.com/simonflueckiger/tesserocr-windows_build/releases` el
  wheel para el Python del venv (`python --version`) y Tesseract 5.x;
  `pip install <url del .whl>`. Si tampoco: **ABORT D1** — escribir el
  research doc con el error exacto (pip log) y saltar al Chunk D2. El
  abort es un resultado válido; NO intentar compilar desde fuente ni
  instalar conda.
- [ ] **Step 3:** Verificación funcional mínima (script suelto en el
  scratchpad, no en el repo): `PyTessBaseAPI(lang="spa+eng")` +
  `SetImage` de un PIL.Image de `data/samples/test_page1_300dpi.png` +
  `GetUTF8Text()` no vacío. Si `TESSDATA_PREFIX` hace falta, apuntarlo a
  `C:\Program Files\Tesseract-OCR\tessdata` y anotarlo.
- [ ] **Step 4:** Micro-benchmark spike (mismo script): 20 recortes de
  esquina de `CH_9.pdf` (216 DPI, crop `_CORNER_PORTRAIT`) OCR'd con
  pytesseract vs tesserocr (API reusada), tiempos medios. **Señal
  informativa solamente** — el gate vinculante de velocidad es el de Task 3
  (spec §2.5) sobre el benchmark real; este número chico y ruidoso NO
  autoriza abortar (el único abort de Task 1 es el de instalación, Step 2).

### Task 2: seam `ocr_backend.py` (TDD)

**Files:**
- Create: `core/scanners/utils/ocr_backend.py`
- Modify: `core/scanners/utils/pagination_count.py:185-198` (`_corner_text`),
  `core/scanners/utils/header_band_anchors.py:227,:232`
- Test: `tests/unit/scanners/utils/test_ocr_backend.py` (nuevo)

- [ ] **Step 1: Tests rojos** — (a) default (`OVERSEER_OCR_BACKEND` ausente)
  → usa pytesseract (monkeypatch de `pytesseract.image_to_string` con spy);
  (b) `OVERSEER_OCR_BACKEND=tesserocr` SIN el paquete → cae a pytesseract
  con un warning de log (caplog); (c) flag con paquete presente (mockear
  módulo `tesserocr` con `sys.modules` si no está instalado) → una API por
  hilo (`threading.local`), spy de llamadas; (d) config PSM/OEM/lang se
  preserva.
- [ ] **Step 2:** Correr → FAIL. Implementar `ocr_image(img, *, config,
  lang) -> str` según spec §2.2 (import de tesserocr en try/except patrón
  torch). Migrar los 3 call-sites. Correr → PASS.
- [ ] **Step 3:** Suite scanner completa:
  `python -m pytest tests/unit/scanners -q` verde; los 2 tests §C2 de
  error-mid-pool (`test_count_documents_threaded_error_propagates_and_closes_docs`
  + `test_count_covers_threaded_error_propagates`) se parametrizan sobre
  ambos backends (el param de tesserocr se auto-skipea con el paquete
  ausente vía `pytest.importorskip`).
- [ ] **Step 4:** Docstring de módulo en `ocr_backend.py` (AC §2-d):
  documenta el env flag, el wheel de Windows
  (`simonflueckiger/tesserocr-windows_build`) y el fallback automático.
- [ ] **Step 5: Commit** — `feat(ocr): pluggable OCR backend seam (pytesseract default, tesserocr opt-in)`

### Task 3: gate de equivalencia + benchmark real

- [ ] **Step 1:** Con `OVERSEER_OCR_BACKEND=tesserocr` (PowerShell:
  `$env:OVERSEER_OCR_BACKEND='tesserocr'; ...`; bash: prefijo
  `OVERSEER_OCR_BACKEND=tesserocr ...`): correr los fixtures GT por-sigla
  (`python -m pytest tests/unit/scanners -q`) y el benchmark
  (`python -m pytest eval/tests/test_pagination_benchmark.py -q`) → conteos
  idénticos (los tests ya asertan GT — verde = idéntico).
- [ ] **Step 2:** Benchmark de samples reales (script eval corto, guardarlo
  como `eval/pagination_count/tesserocr_bench.py`): s/pág esquina y s/pág
  anclas en `CH_9.pdf`, `ART_674.pdf` y `CH_74docs.pdf`, ambos backends,
  hilos ON. Chequeo de estabilidad RSS (2 corridas grandes seguidas).
- [ ] **Step 3:** Escribir `docs/research/2026-07-XX-tesserocr-spike.md`
  con la tabla. **GATE spec §2.5**: conteos idénticos + ≥1.5x → seguir;
  si no → dejar el backend opt-in (default pytesseract), documentar, fin
  del chunk.
- [ ] **Step 4: Commit** — `eval(ocr): tesserocr equivalence gate + benchmark`

### Task 4 (CONDICIONAL — solo si el gate de Task 3 pasó): default flip

- [ ] **Step 1:** Default de `OVERSEER_OCR_BACKEND` → `tesserocr` con
  fallback automático a pytesseract si el import falla (test rojo primero:
  paquete ausente → pytesseract sin error). `requirements.txt`: línea
  comentada documentando el wheel de Windows (NUNCA hard-required).
- [ ] **Step 2:** Suite completa `-m "not slow"` verde + ruff 0.
- [ ] **Step 3: Commit** — `feat(ocr): tesserocr becomes the default OCR backend (pytesseract fallback)`

---

## Chunk D2: RCH→paginación (spec §3)

### Task 5: Fase 0 — caracterización (BLOQUEA el diseño del de-dup)

**Files:**
- Create: `eval/pagination_count/rch_survey.py`
- Output: `docs/research/2026-07-XX-rch-corner-survey.md`

- [ ] **Step 1:** Leer el prior art: `eval/pagination_count/samples.py`
  (sample RCH-control de chintegral con GT ±3 "a ojo") y
  `eval/fixtures/ground_truth.json` (GT de los CH_*/CHAR_*).
- [ ] **Step 2:** Escribir `rch_survey.py`: para cada sample de charla
  (`CHAR_17.PDF`, `CHAR_25.pdf`, `CH_9.pdf`, `CH_39.pdf`, `CH_51docs.pdf`,
  `CH_74docs.pdf`, `CH_BSM_18.pdf`) y los que haya de chintegral/dif_pts,
  por página: texto crudo de esquina, `parse_pagination`, y qué anclas de
  `CRS_RCH_ANCHORS` aparecen en (i) la esquina actual, (ii) esquina
  ampliada `(0.35, 0, 1.0, 0.20)`, (iii) mitad superior izquierda
  `(0, 0, 0.5, 0.20)`. Tabla por sample.
- [ ] **Step 3:** Correr y volcar la tabla + conclusiones al research doc:
  ¿el patrón "1 de M repetido" es uniforme? ¿qué región mínima lee ≥2
  anclas cover-only con qué tasa? ¿hay samples/GT utilizables de dif_pts?
  (si no los hay y no se pueden producir a mano desde samples: anotar que
  **dif_pts queda fuera de la migración**, spec §3-gate).
- [ ] **Step 4: Commit** — `eval(ocr): RCH corner survey — characterize the repeated-pagination template bug`

### Task 6: fixtures sintéticos + prototipo de de-dup

**Files:**
- Modify: `eval/pagination_count/samples.py` (generador sintético RCH:
  portada con anclas cover-only + continuaciones que repiten "Página 1 de
  2"), `eval/pagination_count/engine.py` (variantes de conteo)
- Test: `eval/tests/` (tests de los enfoques sobre los sintéticos)

- [ ] **Step 1:** Generador sintético que reproduzca el patrón medido en
  Fase 0 (no el imaginado). Casos: uniforme 2pp, mixto 2pp+3pp, portada
  ilegible, apéndice sin paginación.
- [ ] **Step 2:** Implementar en `engine.py` los enfoques que Fase 0 dejó
  vivos (spec §3: de-dup aritmético / discriminador en región ampliada /
  híbrido detect-and-fallback), cada uno como función pura comparable.
- [ ] **Step 3:** Tests: cada enfoque sobre los sintéticos, asserts de
  conteo + de la propiedad undercount-safe (portada no confirmada NO suma).
- [ ] **Step 4: Commit** — `eval(ocr): synthetic RCH fixtures + de-dup approach prototypes`

### Task 7: benchmark contra anclas + decision record

- [ ] **Step 1:** Extender `benchmark.py` para correr: anclas (producción)
  vs cada enfoque vivo, sobre TODOS los samples con GT (exactos primero,
  aproximados con su tolerancia = empate). Medir exactitud + s/pág.
- [ ] **Step 2:** `docs/research/2026-07-XX-rch-pagination-decision.md`:
  tabla por sigla × enfoque, y el veredicto del **gate por sigla** (spec §3,
  restatement vinculante — las tres por separado):
  - **charla**: GT real existente en `ground_truth.json` — gate directo
    (sin retrocesos en CADA fixture; GT aproximado = empate dentro de su
    tolerancia; confianza honesta LOW; **≥2x** medido).
  - **chintegral**: sus flavors `f_japa`/`f_previene` NO son RCH; su gate
    exige fixtures que cubran también esos flavors. Si no pasan, chintegral
    queda en anclas (decisión registrada, no fracaso). Evidencia solo-RCH
    NO basta para declararla migrable.
  - **dif_pts**: HOY no tiene GT que ejercite el bug — sin GT nuevo
    adecuado producido en Fase 0, dif_pts NO se migra (un gate sin
    evidencia no se declara pasado).
  Nombrar explícitamente qué siglas pasan y cuáles no, con evidencia.
- [ ] **Step 3: Commit** — `eval(ocr): RCH pagination benchmark + per-sigla migration verdict`

### Task 8 (CONDICIONAL — solo siglas cuyo gate PASÓ): migración

**Files:**
- Modify: `core/scanners/utils/pagination_count.py` (el mecanismo de de-dup
  ganador, portado del eval con TDD), `core/scanners/patterns.py` (flip por
  sigla, flavors de anclas RETENIDOS), `core/utils.py`
  (`SCANNER_PATTERNS_VERSION` bump — manual, ningún hook avisa)
- Test: `tests/unit/scanners/` (fixtures por-sigla de las migradas pasan al
  motor nuevo; tests del mecanismo portado)

- [ ] **Step 1:** TDD: tests rojos del mecanismo en
  `tests/unit/scanners/utils/test_pagination_count.py` (calcados de los del
  eval) → implementar en `pagination_count.py` → verdes.
- [ ] **Step 2:** Flip de registro SOLO de las siglas aprobadas + bump de
  versión. Fixtures por-sigla actualizados.
- [ ] **Step 3:** Suite completa `-m "not slow"` + ruff 0. **OUTPUT GUARD**
  (ver contexto): byte-idéntico esperado — las celdas RCH del DB real
  tienen conteos persistidos que no se re-derivan sin re-scan; cualquier
  diff = STOP e investigar.
- [ ] **Step 4: Commit** — `feat(ocr): migrate <siglas> to the pagination engine with RCH cover de-dup`

---

## Chunk D3: visor reorg — teclado + miniaturas reales (spec §4)

### Task 9: marcado de rango por teclado (TDD)

**Files:**
- Modify: `frontend/src/components/WorkerCountViewer.jsx` (handler de
  teclado en modo reorg; leyenda), `frontend/src/lib/reorg-range.js` (si la
  lógica pura necesita un helper de marca-por-teclado)
- Test: `frontend/src/lib/reorg-range.test.js` +
  `frontend/src/components/WorkerCountViewer.reorgKeys.test.jsx` (nuevo)

- [ ] **Step 1: Tests rojos** — lógica pura: `[` marca inicio en página
  actual, `]` marca fin (normaliza inicio>fin), `Escape` limpia; componente:
  `Enter` con rango marcado abre/confirma el HUD de creación (defaults §A10
  intactos); en `mode!=="reorg"` los atajos NO existen; con foco en un
  input (`focusIsInInput`) NO marcan.
- [ ] **Step 2:** Implementar respetando los 3 `// GATE:` existentes (jamás
  escribir worker marks en modo reorg). Leyenda: en modo reorg NO existe
  hoy — crear `REORG_SHORTCUTS` espejo de `WORKER_SHORTCUTS`
  (`frontend/src/lib/worker-shortcuts.js`) y renderizarla en `ReorgHud.jsx`
  con el mismo idioma (incl. su test de cobertura si el patrón lo tiene).
- [ ] **Step 3:** Verdes. **Commit** — `feat(web): keyboard range marking in the reorg viewer`

### Task 10: miniaturas reales + tinte de rango

- [ ] **Step 1: Test rojo** — el carril en modo reorg renderiza las
  miniaturas por el MISMO pipeline lazy del modo worker-count (mock del
  renderer, assert de llamadas) y las páginas dentro del rango marcado
  llevan el tinte `po-override-*`.
- [ ] **Step 2:** Implementar reusando el pipeline REAL de miniaturas:
  `frontend/src/components/WorkerThumbnails.jsx` (`Thumb` +
  `THUMB_CACHE` WeakMap + `getCachedThumb`, con su prop `rotation` ya
  existente) — el `ReorgThumbnails` actual es un placeholder estático (div
  `…`, sin imagen ni cache). NO usar `lib/page-cache.js` (ese LRU de ~6
  ImageBitmaps es el cache de página completa de `PdfPage.jsx`, no el de
  miniaturas). Extender/reusar `WorkerThumbnails` con una prop de tinte de
  rango en vez de duplicar el componente.
- [ ] **Step 3:** Verdes + `npm run build` OK. **Commit** — `feat(web): real thumbnails + range tint in the reorg viewer rail`

---

## Cierre de ronda

### Task 11: gates + docs + push + tag + memoria

- [ ] **Step 1:** `python -m pytest -m "not slow" -q` / `cd frontend && npx
  vitest run && npm run build` / `ruff check .` — todo verde/0.
- [ ] **Step 2:** OUTPUT GUARD global de la ronda (si Task 4 u 8 tocaron
  core): sqlite-backup del DB real → dump_counts en el commit base de la
  ronda vs HEAD → byte-idéntico (o los diffs exactos que Task 7 predijo y
  Daniel aprobó).
- [ ] **Step 3:** CLAUDE.md raíz: entrada de Project history (qué gates
  pasaron/abortaron, con números) + Pending Work actualizado. Actualizar
  `core/CLAUDE.md`/`api/CLAUDE.md` si el seam/env nuevo lo amerita
  (`OVERSEER_OCR_BACKEND`). **Si Task 8 migró alguna sigla RCH**: actualizar
  también la tabla de distribución de scanners y el párrafo de cierre
  ("RCH stays on anchors…") de la sección "Scanner Architecture" en
  `core/CLAUDE.md` — hoy hardcodean "6 anchors (charla, chintegral,
  dif_pts…)" y quedan obsoletos con el primer flip.
- [ ] **Step 4:** `git push origin po_overhaul` + tag `track-d-ocr` (solo si
  D1 o D2 shippearon algo en core; si todo abortó, push sin tag).
- [ ] **Step 5:** Memoria del proyecto: archivo de ronda + línea en
  MEMORY.md + `project_roadmap_next.md` (incluir los VEREDICTOS de los
  gates — un abort documentado también es estado durable).
