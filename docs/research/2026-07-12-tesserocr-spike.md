# Spike tesserocr (Track D · D1 · Task 1) — registro

**Fecha:** 2026-07-12 · **Veredicto FINAL D1: SHIPPED — seam + gate de
equivalencia PASADO (conteos idénticos, esquina 1.92-3.33x) + tesserocr es
el backend default con fallback automático a pytesseract.**

## Instalación (Windows, Python 3.10.11, venv `.venv-cuda`)

- `pip install tesserocr` desde PyPI: **falla** (no hay wheel; build desde
  fuente muere en `Failed to build 'tesserocr' when getting requirements
  to build wheel`). Esperado.
- Wheel funcional: `tesserocr-2.10.0-cp310-cp310-win_amd64.whl` del release
  `tesserocr-v2.10.0-tesseract-5.5.2` de
  `https://github.com/simonflueckiger/tesserocr-windows_build/releases`
  — instala limpio, embebe Tesseract **5.5.2** + leptonica 1.87.0
  (self-contained; el Tesseract local es 5.5.0, compatible).
- `TESSDATA_PREFIX` debe apuntar a
  `C:\Program Files\Tesseract-OCR\tessdata` (los `spa`/`eng` traineddata
  ya instalados sirven tal cual).

## Verificación funcional

`PyTessBaseAPI(lang="spa+eng", psm=PSM.SINGLE_BLOCK, oem=OEM.LSTM_ONLY)`
sobre el crop de esquina (216 DPI, `_CORNER_PORTRAIT`) de la página 1 de
`data/samples/CH_9.pdf` devuelve **texto idéntico** a
`pytesseract.image_to_string(..., config="--psm 6 --oem 1",
lang="spa+eng")` (incluye el código `F-CH-CRS-01` y el header Rev.: 01).

## Micro-benchmark (señal informativa — el gate vinculante es Task 3)

17 crops de esquina reales de `CH_9.pdf`, misma imagen a ambos motores:

| motor | media ms/crop | mediana |
|---|---|---|
| pytesseract (spawn por llamada) | 367 | 358 |
| tesserocr (API persistente) | **164** | 159 |

**Speedup 2.23x** — consistente con la hipótesis: el piso de ~200 ms de
spawn de `tesseract.exe` desaparece; lo que queda es OCR puro.

Script: `tesserocr_spike.py` (scratchpad de la sesión 2026-07-12; el
benchmark reproducible del repo es `eval/pagination_count/tesserocr_bench.py`,
Task 3).

## Task 2 — seam `ocr_backend.py` (hecho)

Nuevo módulo `core/scanners/utils/ocr_backend.py`: `ocr_image(img, *, config,
lang) -> str`, backend seleccionado por `OVERSEER_OCR_BACKEND` (`pytesseract`
default | `tesserocr`), import de tesserocr en try/except (patrón torch),
fallback automático a pytesseract con warning si el paquete no está. Los 3
call-sites migrados: `pagination_count._corner_text`,
`header_band_anchors.count_covers_by_anchors` (pasada raw + pasada E6
preprocesada). Una `PyTessBaseAPI` por hilo vía `threading.local()`, cacheada
por `(lang, psm, oem)`.

**Gotcha real encontrado al correr contra el motor de producción** (no
apareció en el spike de Task 1, que usaba un script suelto en el
scratchpad): a diferencia del binario `tesseract.exe`, este build de
tesserocr para Windows **no** lee `TESSDATA_PREFIX` por sí solo para su
argumento `path` — su default es `"./"`, que revienta con `RuntimeError:
Failed to init API, possibly an invalid tessdata path: ./` fuera de un cwd
con `tessdata/` adentro. Fix: `ocr_backend.py` arma `path` explícito (el
mismo valor de `TESSDATA_PREFIX`, con `/` final) y lo pasa a
`PyTessBaseAPI(path=..., lang=..., psm=..., oem=...)` — ver
`_tessdata_path()`. Sin este fix, TODO el GT con `OVERSEER_OCR_BACKEND=tesserocr`
revienta con esa excepción (11 tests fallaron en el primer intento del gate
de equivalencia, todos por esta única causa raíz).

`tests/unit/scanners -q` (252 tests) verde en ambos backends (default y
`OVERSEER_OCR_BACKEND=tesserocr`, tras el fix de `path`). Los 2 tests
§C2 de error-mid-pool se parametrizaron sobre `["pytesseract", "tesserocr"]`
(`pytest.importorskip("tesserocr")` en el param tesserocr — auto-skip si el
paquete no está). Dos tests preexistentes que hardcodeaban un stub de
`pytesseract.image_to_string` sin fijar el backend (`test_count_covers_uses_first_passing_flavor`,
`test_count_covers_threaded_equals_sequential`) se corrigieron para fijar
`OVERSEER_OCR_BACKEND=pytesseract` explícitamente — de lo contrario, corridas
con el env ambiental en `tesserocr` los desviaban al motor real (texto
distinto al stub, conteos rotos por diseño del test, no por el seam).
Commit: `feat(ocr): pluggable OCR backend seam (pytesseract default, tesserocr opt-in)`.

## Task 3 — gate de equivalencia + benchmark real (hecho)

### Gate de equivalencia (conteos)

Con `OVERSEER_OCR_BACKEND=tesserocr`:

- `tests/unit/scanners -q` → **252 passed, 48 skipped** (mismos 252 que con
  el backend default) — el conjunto de fixtures GT por-sigla
  (`tests/fixtures/scanners/` vía `fixture_gt.py`) corre OCR real end-to-end
  y asserta el conteo exacto esperado; verde en ambos backends = conteos
  idénticos.
- `eval/tests/test_pagination_benchmark.py -q` → **14 passed**. **Nota
  honesta**: este archivo no ejercita el seam — `eval/pagination_count/benchmark.py`
  usa el motor PROTOTIPO `eval/pagination_count/engine.py`, que tiene su
  propio `import pytesseract` directo, independiente de
  `core.scanners.utils.ocr_backend` (confirmado por `eval/CLAUDE.md`:
  `pagination_count/` es un "Prototype", no el motor de producción). Correrlo
  bajo el env var no prueba nada del seam — pasa igual con o sin la variable.
  La señal real de equivalencia es `tests/unit/scanners -q` (arriba), que sí
  pasa por los 3 call-sites migrados.

### Benchmark real (`eval/pagination_count/tesserocr_bench.py`)

3 samples de `data/samples/`, capados a 40 páginas (ART_674.pdf tiene 2719 —
una tasa por-página es representativa en un subconjunto; CH_9.pdf con 17
páginas corre completo), hilos ON (`OCR_PAGE_THREADS=6` en esta máquina, 12
cores), ambos backends:

**s/pág esquina (motor de paginación):**

| sample | pytesseract | tesserocr | speedup |
|---|---|---|---|
| CH_9.pdf (17p) | 105.9 ms/pág | 55.3 ms/pág | **1.92x** |
| ART_674.pdf (40p) | 79.1 ms/pág | 23.8 ms/pág | **3.33x** |
| CH_74docs.pdf (40p) | 95.4 ms/pág | 49.6 ms/pág | **1.92x** |

**s/pág anclas (motor de anclas, peor caso 2 pasadas — los flavors de charla
no matchean páginas no-charla, así que TODAS las páginas de ART_674/CH_74docs
disparan la pasada 2):**

| sample | pytesseract | tesserocr | speedup |
|---|---|---|---|
| CH_9.pdf (17p) | 338.6 ms/pág | 245.0 ms/pág | 1.38x |
| ART_674.pdf (40p) | 381.8 ms/pág | 274.5 ms/pág | 1.39x |
| CH_74docs.pdf (40p) | 310.0 ms/pág | 221.7 ms/pág | 1.40x |

**RSS (tesserocr, motor de paginación, ART_674 capado a 40p, 2 corridas
seguidas):** 413.8 MB antes → 406.8 MB tras corrida 1 → 412.7 MB tras corrida
2. Sin crecimiento — estable dentro del ruido normal del proceso.

### GATE spec §2.5 — veredicto: **PASA, D1 continúa a Task 4**

AC(b) del spec fija el umbral explícitamente **"≥1.5x en esquina"** (el
motor de paginación — la mayoría de las siglas migradas, 12/20 según
`core/CLAUDE.md`). Ese número: **1.92x–3.33x, clarísimamente sobre el
umbral.** Conteos GT idénticos en ambos backends. RSS estable. Los 2 tests
§C2 pasan parametrizados sobre ambos backends.

**Caveat honesto** (no forma parte del AC(b) literal, pero se registra sin
maquillar): el motor de **anclas** (charla/chintegral/dif_pts/senal/chps/
maquinaria, 6/20 siglas) mide **~1.4x** — por debajo del umbral de 1.5x. La
causa es estructural, no un artefacto de medición: el costo fijo de spawn
que tesserocr elimina es una fracción menor de su costo total por-página
(banda OCR más grande que la esquina, más el pipeline de preprocesamiento
E6 — deskew + limpieza de color — en la pasada 2), así que hay
proporcionalmente menos spawn que amortizar. El benchmark corrió el peor
caso (2 pasadas en TODAS las páginas, ya que los flavors de charla usados
como driver no matchean contenido no-charla); en producción, páginas que sí
matchean en la pasada 1 (una sola llamada OCR) verían un salto más parecido
al de la esquina — pero no se re-midió con contenido charla real para
confirmarlo (data-safety: solo `data/samples/`, y ninguno de los 3 samples
es un archivo charla "limpio" de principio a fin). Decisión: como el AC
vinculante es "en esquina", el flip de Task 4 procede: **tesserocr pasa a
default para TODO el OCR** (ambos motores comparten el seam — no hay forma
de aplicarlo solo al motor de paginación sin duplicar el mecanismo), con
fallback automático a pytesseract si el paquete falta. El motor de anclas
sigue siendo ~1.4x más rápido con tesserocr que sin él — una mejora real,
solo por debajo del umbral que hubiera exigido para sí mismo si el AC lo
gatillara.

Commit: `eval(ocr): tesserocr equivalence gate + benchmark`.

## Task 4 — flip de default (hecho, `b5ea0b7`)

Default = `tesserocr` cuando el paquete importa, `pytesseract` si no
(fallback automático, cero cambios para máquinas sin el wheel — AC-a).
`requirements.txt` documenta el wheel como línea comentada opcional.
Suite completa `-m "not slow"` 916/49/0 + ruff 0 con el default nuevo.
