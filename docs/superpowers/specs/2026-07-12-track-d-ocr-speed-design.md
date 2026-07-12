# Track D — velocidad OCR (tesserocr + RCH→paginación) y visor reorg — Design

**Fecha:** 2026-07-12 · **Estado:** aprobado por Daniel (diseño presentado en sesión)
**Ejecutor previsto:** Opus (o Fable si alcanza) vía superpowers:subagent-driven-development
**Plan:** `docs/superpowers/plans/2026-07-12-track-d-ocr-speed.md`

## 0. Contexto y motivación

Tras la ronda `pulido-post-revision` (2026-07-12), el escaneo OCR es utilizable
pero las celdas más pesadas siguen siendo lentas:

- **El piso de spawn**: cada página paga ~195 ms solo en arrancar
  `tesseract.exe` (medido 2026-07-11). Los hilos (`OCR_PAGE_THREADS`) dieron
  2.9-3.8x, pero el piso por-llamada sigue ahí. → **D1 (tesserocr)** lo ataca.
- **Las siglas RCH** (charla, chintegral, dif_pts) siguen en el motor de
  **anclas** (`header_band_anchors.py`: franja superior completa, 2 pasadas
  OCR ≈ 1.2-1.5 s/pág) porque el motor de **paginación** (esquina superior
  derecha, ≈ 0.35 s/pág) sobre-cuenta en su plantilla: **las páginas de
  continuación (grillas de firmas) también leen "Página 1 de 2"** — template
  bug verificado con sample de Daniel y documentado en
  `core/scanners/patterns.py:194-198`. Son las celdas más grandes del corpus
  (charlas de miles de páginas). → **D2 (RCH→paginación)** lo ataca (~5-8x
  si el gate pasa).
- **El modo reorg del visor** (marcar rangos de páginas para extraer colados)
  no tiene atajos de teclado y sus miniaturas son placeholders. → **D3**.

**Naturaleza del track**: D1 y D2 son **eval-first con resultado incierto** —
cada uno tiene un gate explícito y una salida por fracaso documentada que NO
toca `core/`. D3 es UX determinista. D1 y D2 son independientes entre sí;
D1 va primero solo porque, si funciona, acelera los benchmarks de D2.

## 1. Restricciones globales (vigentes de rondas anteriores)

- **Samples only**: todo escaneo de prueba corre sobre `data/samples/` y
  fixtures sintéticos — jamás el corpus `A:\informe mensual` completo
  (regla de Daniel, 2026-07-11). El corpus real es READ-ONLY siempre.
- **eval-before-core**: los prototipos viven en `eval/` (aquí:
  `eval/pagination_count/`, extendiendo el arnés de la ronda
  `ocr-pagination-mvp`) antes de cualquier edición a `core/`. Es una regla
  de esta ronda, NO un hook automatizado: el hook `eval-before-core` de
  hookify solo cubre `core/inference.py` — el ejecutor la cumple por
  disciplina, no porque algo lo bloquee.
- **OUTPUT GUARD**: al cierre de cualquier chunk que toque `core/`,
  `tools/dump_counts.py` sobre una **copia sqlite-backup** del DB real
  (¡está en WAL — copia plana NO es fiel!) en commit base vs HEAD debe ser
  byte-idéntico, SALVO diffs esperados y aprobados por benchmark.
- Versionado: una migración de scanner por sigla exige bump **manual** de
  `SCANNER_PATTERNS_VERSION` en `core/utils.py` (hoy `v7-irl-cover`). OJO:
  el hook `bump-version-tags` NO cubre `core/scanners/*.py` (su regex solo
  matchea `core/{pipeline,ocr,inference,image}.py` y `vlm/*`) — nadie lo
  recuerda automáticamente; el plan lo lista como paso explícito.
- Gates por commit: `ruff check .` = 0, pytest fast verde, vitest verde
  (si toca frontend). TDD.
- Trabajo directo en `po_overhaul`, push al cierre de la ronda.

## 2. D1 — Spike tesserocr (~2x adicional en TODO el OCR; riesgo: wheels)

### Defecto / oportunidad

`pytesseract` lanza un proceso `tesseract.exe` por llamada. Hay exactamente
**3 call-sites** en los motores activos:

- `core/scanners/utils/pagination_count.py:198` (`_corner_text`, 1 llamada/pág)
- `core/scanners/utils/header_band_anchors.py:227` (pasada raw) y `:232`
  (pasada preprocesada E6) — hasta 2 llamadas/pág

`tesserocr` (binding C-API) mantiene el motor cargado → elimina el spawn.
Estimación honesta: ~2x sobre el estado actual con hilos (el spawn es ~50-60%
del costo por página en la esquina).

### Diseño

1. **Spike de instalación (timebox ~1h de ejecución)**: `pip install
   tesserocr` en `.venv-cuda`. Si compila/instala mal (lo esperado en
   Windows), probar el wheel de
   `https://github.com/simonflueckiger/tesserocr-windows_build/releases`
   que calce con el Python del venv (3.10+) y el Tesseract instalado
   (`C:\Program Files\Tesseract-OCR`, `TESSDATA_PREFIX` a su `tessdata`).
   **Salida por fracaso**: si en el timebox no hay un import limpio +
   `PyTessBaseAPI` funcional con `lang="spa+eng"`, documentar en
   `docs/research/` y ABORTAR D1 — cero cambios en core, cero dependencia
   nueva en `requirements*.txt`.
2. **Seam pluggable**: nuevo módulo `core/scanners/utils/ocr_backend.py`
   que expone `ocr_image(img, *, config, lang) -> str` con dos backends:
   - `pytesseract` (default, comportamiento actual byte-idéntico), y
   - `tesserocr` (una instancia `PyTessBaseAPI` **por hilo**,
     `threading.local()` — tesserocr NO es thread-safe entre llamadas
     concurrentes sobre la misma API; calza con el patrón thread-local de
     docs fitz ya existente). PSM 6 / OEM 1 idénticos a los call-sites
     actuales.
   Selección por env `OVERSEER_OCR_BACKEND` (`pytesseract` default |
   `tesserocr`); import de tesserocr en try/except (patrón torch) — si no
   está instalado, el flag cae a pytesseract con un warning de log.
   Los 3 call-sites migran a `ocr_backend.ocr_image(...)`.
3. **Gate de equivalencia**: con `OVERSEER_OCR_BACKEND=tesserocr`, los
   conteos sobre el **GT completo** (fixtures por-sigla de
   `tests/unit/scanners/fixture_gt.py` + benchmark
   `eval/tests/test_pagination_benchmark.py` + los samples reales de
   `data/samples/`) deben ser **idénticos** a pytesseract. El texto OCR
   crudo puede diferir en whitespace; los CONTEOS no.
4. **Benchmark**: medir s/pág esquina y s/pág anclas en 3+ samples reales
   (`CH_9.pdf`, `ART_674.pdf`, uno grande) con ambos backends, hilos ON.
   Registrar en `docs/research/2026-07-XX-tesserocr-spike.md`.
5. **Default flip**: SOLO si el gate 3 pasa y el benchmark muestra ≥1.5x,
   el default de `OVERSEER_OCR_BACKEND` pasa a `tesserocr` (con pytesseract
   como fallback automático si el import falla). `requirements.txt` gana
   `tesserocr` como dependencia **opcional comentada** (wheel manual en
   Windows) — NUNCA hard-required: la app debe seguir funcionando sin él.

### Criterios de aceptación (D1)

- (a) Con tesserocr ausente, TODO funciona exactamente como hoy (suite verde
  sin el paquete instalado — CI-safe).
- (b) Con `OVERSEER_OCR_BACKEND=tesserocr` y el paquete instalado: conteos
  GT idénticos, benchmark ≥1.5x en esquina, sin fugas de memoria evidentes
  (correr 2 celdas grandes seguidas, RSS estable).
- (c) Los tests de error-mid-pool de §C2 (2026-07-12) pasan con ambos
  backends (parametrizar o duplicar los 2 tests clave).
- (d) Docstring/README de `ocr_backend.py` documenta el wheel de Windows y
  el fallback.

## 3. D2 — RCH→paginación (el premio: ~5-8x en charla/chintegral/dif_pts)

### Hechos pineados (verificados en código/spec previos — re-verificar en Fase 0)

- Las 3 siglas comparten la plantilla RCH `F-CRS-RCH-01`
  (`CRS_RCH_ANCHORS`, `patterns.py:203-216`; chintegral la reusa como flavor
  `f_rch` y ademas tiene `f_japa` y `f_previene` — plantillas NO-RCH).
- **El bug**: las páginas de continuación (grillas de firmas) repiten
  "Página 1 de 2" en el mismo lugar → `count_starts` contaría cada página
  como portada (sobre-conteo ~2x). El código de formulario `F-CRS-RCH-01`
  también se repite en TODAS las páginas (no discrimina).
- **El discriminador probado existe**: los campos cover-only de
  `CRS_RCH_ANCHORS` ("nombre de la charla", "obra", "relator", "cargo
  relator", "hora de inicio"/"tiempo duracion charla", …) aparecen SOLO en
  la portada — es exactamente lo que el motor de anclas usa hoy con regla
  ≥3 matches. La pregunta de D2 es si se pueden leer MÁS BARATO que la
  franja completa a 2 pasadas.
- Motor de paginación: `core/scanners/utils/pagination_count.py`
  (`_CORNER_PORTRAIT=(0.50,0,1.0,0.15)`, `parse_pagination`,
  `dominant_total`, `recover_sequence`, `count_starts`, garantía
  undercount-safe documentada). Arnés de prototipo:
  `eval/pagination_count/{engine,benchmark,report,samples}.py`.
- Samples de charla disponibles: `CHAR_17.PDF`, `CHAR_25.pdf`, `CH_9.pdf`,
  `CH_39.pdf`, `CH_51docs.pdf`, `CH_74docs.pdf`, `CH_BSM_18.pdf` — con GT
  real (`doc_count`) en `eval/fixtures/ground_truth.json`.
- **Prior art que el ejecutor DEBE leer**: `eval/pagination_count/samples.py`
  ya define un sample RCH-control de chintegral con **GT aproximado**
  (±3, contado "a ojo") y una nota que marca un conteo previo registrado
  como erróneo. Regla para GT aproximado en el gate: caer dentro de la
  tolerancia declarada cuenta como empate; los fixtures con GT exacto
  mandan.
- **dif_pts NO tiene GT real que ejercite el bug RCH** (sus fixtures
  actuales son casos A7-locked/shadow-cover de 1-2 páginas que ni invocan
  OCR): el gate de dif_pts NO puede satisfacerse vacíamente — ver gate.

### Fase 0 — caracterización (OBLIGATORIA antes de diseñar el de-dup)

Script eval (`eval/pagination_count/rch_survey.py`) que sobre los samples
de charla (y los de chintegral/dif_pts — para dif_pts, Fase 0 además DEBE
producir GT nuevo utilizable o dejar constancia de que no se puede: ver el
gate por sigla) imprime,
por página: el texto crudo de la esquina, `parse_pagination`, y qué anclas
cover-only aparecen en (i) la esquina actual, (ii) una esquina ampliada
(p. ej. `x0=0.35`, `y1=0.20`), (iii) la mitad superior izquierda. Salida:
tabla por sample → responde QUÉ señal de portada es legible en qué región
mínima y con qué tasa de acierto. **Ningún diseño se fija antes de esto.**

### Enfoques candidatos (el eval los compara; decisión por datos)

1. **De-dup aritmético**: si el total dominante es M y TODAS las páginas del
   archivo leen "1 de M" → contar `ceil(páginas/M)`. Barato (cero OCR
   extra); frágil en compilaciones mixtas (docs de distinto M, portadas
   ilegibles) y en archivos con apéndices. Solo viable si Fase 0 muestra que
   el patrón repetido es uniforme.
2. **Discriminador de portada en región ampliada**:
   paginación normal, pero cuando se detecta el patrón repetido (mayoría de
   páginas leyendo "1 de M"), una segunda lectura SOLO de las páginas
   candidatas sobre una región ampliada busca ≥2 anclas cover-only
   (`CRS_RCH_ANCHORS`) para confirmar portada. Costo extra acotado (una
   pasada más por página candidata, región pequeña); conserva la garantía
   undercount-safe (una portada no confirmada NO cuenta → LOW confidence,
   igual que hoy).
3. **Híbrido detect-and-fallback**: paginación normal; si un archivo
   dispara el patrón repetido, ese archivo cae al motor de anclas actual.
   Gana velocidad solo en los archivos "sanos"; cero riesgo de conteo.
   Es el piso garantizado si 1 y 2 fallan.

### Gate de migración (idéntico en espíritu al de `ocr-pagination-mvp`)

El prototipo elegido debe, sobre TODOS los fixtures GT + samples con GT
conocido de las 3 siglas:

- ganar o empatar la exactitud de anclas en CADA fixture (ni un solo
  retroceso; GT aproximado = empate dentro de su tolerancia declarada), y
- mantener confianza honesta (LOW ante recuperación/portadas no confirmadas
  → va al contador de teclado, nunca verde falso), y
- mostrar ganancia de velocidad **≥2x medida** vs anclas en samples reales
  (expectativa ~3-5x; bajo 2x el riesgo no paga — regla única, sin zona
  gris).

**El gate es POR SIGLA, las tres por separado**, y exige que esa sigla tenga
GT que ejercite el bug RCH (multipágina real, portadas + continuaciones):

- **charla**: GT real existente en `ground_truth.json` — gate directo.
- **chintegral**: sus flavors `f_japa`/`f_previene` no son RCH; su gate exige
  fixtures que cubran también esos flavors. Si no pasan, chintegral queda en
  anclas (decisión registrada, no fracaso).
- **dif_pts**: HOY NO tiene GT que ejercite el bug — la Fase 0 debe producir
  fixtures GT nuevos (desde samples reales de dif_pts contados a mano, o
  sintéticos que reproduzcan la plantilla). **Sin GT nuevo adecuado, dif_pts
  NO se migra** — un gate sin evidencia no se declara pasado.

**Si el gate de una sigla pasa**: migración = flip de esa sigla en el
registro de `patterns.py` (una línea, reversible; flavors de anclas
RETENIDOS, patrón de la migración 2026-06-21) + bump manual de
`SCANNER_PATTERNS_VERSION`.

**Si el gate falla**: las siglas quedan en anclas; el eval + survey quedan
como registro en `docs/research/`; el enfoque 3 (híbrido) puede shippearse
como consuelo SOLO si su gate propio pasa (conteos idénticos a anclas en
todo el GT por construcción del fallback).

### Criterios de aceptación (D2)

- (a) `rch_survey.py` corrido y su tabla en `docs/research/` ANTES de
  cualquier línea del prototipo de conteo.
- (b) Prototipo en `eval/pagination_count/` con tests sintéticos propios
  (fixtures que reproduzcan el patrón "1 de 2 repetido" — generador nuevo
  en `samples.py`).
- (c) Benchmark contra anclas en los samples reales con GT, tabla en el
  decision record.
- (d) Migración (si procede) con: fixtures por-sigla actualizados al motor
  nuevo, `SCANNER_PATTERNS_VERSION` bump, OUTPUT GUARD con SOLO los diffs
  que el benchmark predijo (idealmente ninguno: las celdas RCH del DB real
  ya tienen conteos manuales/OCR persistidos que no se re-derivan sin
  re-scan).
- (e) El flip es reversible en un commit de una línea.

## 4. D3 — Visor modo reorg: teclado + miniaturas reales (UX puro)

### Defecto

En `WorkerCountViewer mode="reorg"` (alcanzable desde el lightbox →
"Reorganizar páginas"): seleccionar un rango de páginas para
`extract_pages` es solo-mouse y las miniaturas del carril no son las reales
del documento (placeholder), lo que hace lento ubicar los límites del
colado.

### Diseño

- **Teclado** (solo en modo reorg, respetando el guard `focusIsInInput`
  existente): `[` marca inicio de rango en la página actual, `]` marca fin,
  `Enter` abre/confirma la creación de la op con el rango marcado (el HUD
  existente, con sus defaults §A10 ya shippeados), `Escape` cancela la
  marca. Leyenda de atajos: en modo reorg NO existe hoy — crear
  `REORG_SHORTCUTS` espejo del `WORKER_SHORTCUTS` de
  `lib/worker-shortcuts.js` y renderizarla en `ReorgHud.jsx` (mismo idioma).
  La lógica de rango es pura y ya existe (`lib/reorg-range.js`) — el
  teclado solo la alimenta; los 3 gates que impiden escribir worker marks
  en modo reorg NO se tocan.
- **Miniaturas reales**: el carril de miniaturas en modo reorg reusa el
  pipeline REAL de miniaturas del modo worker-count —
  `frontend/src/components/WorkerThumbnails.jsx` (`Thumb` + `THUMB_CACHE`
  WeakMap + `getCachedThumb`, prop `rotation` ya existente) — en vez del
  `ReorgThumbnails` placeholder actual (div estático, sin imagen). OJO:
  `lib/page-cache.js` NO es el cache de miniaturas (es el LRU de ~6
  ImageBitmaps de página completa de `PdfPage.jsx`) — no usarlo aquí ni
  crear un segundo cache de thumbs. Marcar visualmente el rango
  seleccionado en el carril (tokens po-*, tinte `po-override-*` como el
  resto de la selección reorg).

### Criterios de aceptación (D3)

- (a) Con el visor en modo reorg: `[`/`]`/`Enter`/`Escape` operan el rango
  sin mouse; en modo worker-count NADA cambia (los atajos no existen ahí).
- (b) `focusIsInInput` sigue protegiendo los inputs del HUD (tipear "[" en
  un campo no marca rango).
- (c) Miniaturas reales visibles en modo reorg con el rango tintado;
  sin regresión de perf (el `THUMB_CACHE` existente de `WorkerThumbnails`
  absorbe el costo — no crear un segundo cache de miniaturas).
- (d) vitest para la lógica de teclado (pura) + render tests del carril;
  smoke visual manual queda para Daniel (o chrome-devtools MCP si la
  sesión ejecutora lo tiene).

## 5. Fuera de alcance

- Re-scan del corpus real o cambio de conteos persistidos (la migración D2
  cambia el MOTOR; los conteos de celdas ya trabajadas no se re-derivan
  solos).
- senal (landscape, dropped-with-cause 2026-06-24), V4 (cuarentena D10),
  VLM (postmortem).
- Cualquier endpoint/backend nuevo para D3 (es frontend puro).
- Migrar `reunion`/`chps`/`maquinaria` (no son RCH ni paginables hoy).

## 6. Orden de ejecución y entregables

1. **Chunk D1** (spike + seam + gate) — si aborta, documenta y sigue.
2. **Chunk D2** (Fase 0 → prototipo → benchmark → gate → migración o
   registro de fracaso).
3. **Chunk D3** (teclado + miniaturas).
4. **Cierre**: gates completos + OUTPUT GUARD + CLAUDE.md (Pending Work +
   Project history) + push + tag `track-d-ocr` (si D1 o D2 shippearon algo
   en core) + memoria de proyecto.

Cada chunk = implementador fresco + review de spec + review de calidad +
fix loops (patrón SDD de las rondas previas). Los reviews de D1/D2 deben
verificar los GATES con corridas reales, no por lectura.
