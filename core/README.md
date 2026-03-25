# PDFoverseer Core

Este directorio contiene el motor principal de análisis, inferencia y orquestación de procesamiento de PDFs para PDFoverseer. 

## Arquitectura y Modularización (v1)

Anteriormente estructurado como un monolito gigante (`core/analyzer.py` de ~1200 líneas), el núcleo ha sido refactorizado en cinco submódulos especializados para lograr una mejor mantenibilidad, encapsulación de dependencias (para GPU y modelos) y desacoplamiento de estado.

A continuación se detalla la responsabilidad exacta y el contenido de cada archivo tras la modularización:

### 1. `utils.py` (Fundamentos Compartidos)
Contiene las estructuras de datos y definiciones estáticas transversales.
*   **Dataclasses:** `Document` y `_PageRead`.
*   **Constantes de Negocio:** Lógica compartida (`ANOMALY_DROPOUT`, `MIN_CONF_FOR_NEW_DOC`, métricas por defecto).
*   **Expresiones Regulares:** Compilaciones pre-hechas como `RX_PAGE` y `RX_ROMAN`.
*   **Pequeños Parsers:** Utilidades puras enfocadas a texto como `_to_int(s)` y `_parse(text)`.

### 2. `image.py` (Procesamiento Visual)
Aísla las dependencias que manejan OpenCV y la manipulación de imágenes a nivel gráfico.
*   **Renderizado:** `_render_clip()` intercepta las páginas de de los archivos extraídos por `fitz` (PyMuPDF) convirtiéndolas en buffers de imagen.
*   **Modelos de Súper Resolución:** Setup perezoso y manejo de resoluciones visuales como el EDSR `_setup_sr()` y el `_upsample_4x()`.

### 3. `ocr.py` (Motor de Reconocimiento)
Gestiona exclusivamente los llamados a los intérpretes de reconocimiento óptico de caracteres y restringe el cargado de la GPU.
*   **Preprocesamiento Tier 1/2 (`_tess_ocr`):** Blue ink removal (HSV mask + inpainting) → grayscale (luminance) → unsharp mask (sigma=1.0, strength=0.3) → Tesseract LSTM. No se aplica binarización externa — el LSTM usa gradientes en bordes de caracteres que Otsu destruye (Tesseract issue #1780). Parámetros validados por OCR preprocessing sweep (tag `POST-OTSU`): 149/697 rescates, 42/200 regresiones vs 83/200 de producción anterior.
*   **Fases del OCR:** Tier 1 (Tesseract directo) y Tier 2 (Tesseract + Super Resolución 4x) encapsulados en `_process_page()`.
*   **EasyOCR (Tier 3):** Inicialización lazy (`_init_easyocr()`), thread-local Torch con candado seguro (`_easyocr_lock`).

### 4. `inference.py` (Inteligencia Lógica sin Estado)
Corazón de las deducciones, totalmente purificado para prescindir de estado mutacional, garantizando que el diseño de *Human-In-The-Loop* nunca se entrelace con estados sucios.
*   **Versión:** `s2t-helena` — parámetros optimizados vía sweep2 sobre 40 fixtures (21 reales + 13 sintéticos + 6 degradados). Nombrado por *Muraena helena* (morena mediterránea).
*   **Teoría de Dempster-Shafer:** `_ds_combine()` ejecuta la fusión algorítmica.
*   **Detecciones Cíclicas:** `_detect_period()` revisa la recurrencia algorítmica de los números curr.
*   **Gap Solver Bidireccional:** Fases 1-2 generan hipótesis forward/backward para páginas fallidas; tie-breaker prefiere hipótesis que crean fronteras de documento (reversibles) sobre continuaciones (irreversibles).
*   **Fases 0-6 + 5b:** Phase 0 (anomaly dropout), Phase 1-2 (gap solver), Phase 1b (orphan marking), Phase 3 (cross-validation), Phase 4 (fallback, conf=0.15), Phase 5 (D-S post-validation), Phase 5b (period-contradiction, ratio≥0.95), Phase 6 (orphan suppression, conf≥0.55).
*   **Generador y Ensamblador:** `_infer_missing()`, `_build_documents()`, `classify_doc()`.

### 5. `pipeline.py` (Orquestación del Productor-Consumidor)
Implementa los procesos multihilos, la coordinación de operaciones largas asíncronas de I/O y la telemetría en tiempo real.
*   **Entrypoints Directos:** `analyze_pdf()` y el actualizador condicional `re_infer_documents()`.
*   **Comunicación en Colas:** Balanceo robusto utilizando `ThreadPoolExecutor` para paralelismo, manteniendo la cola de reserva por defecto de la CPU (el productor) empalmada con el consumidor GPU del singleton de EasyOCR.
*   **Logs y Métricas:** Emisión de eventos progresivos (`on_log`, `on_issue`) y emisor de rastros AI `[MOD:v1]`.

### Punto de Acceso (`__init__.py`)
A nivel de aplicación superior (como en `server.py` o los scripts bajo `eval/`), la topología modular es **completamente transparente**. Toda importación fluye a través de `core/__init__.py`, que exporta únicamente la superficie del contrato público existente:
```python
# API principal mantenida de cara a la lógica externa:
from core import (
    analyze_pdf, re_infer_documents, 
    Document, _PageRead, _build_documents, 
    classify_doc, _CORE_HASH, INFERENCE_ENGINE_VERSION
)
```

---

## Changelog de Versiones (MOD Tags)

### `[MOD:v5-max-total]` (2026-03-25)

**Problema:** Regresión de OCR ghost-zero — Tesseract appends stray `0` to single-digit totals (e.g., `total=4` → `total=40`), causando que `_parse()` acepte lecturas corruptas. En ART_670 esto generó 124/139 errores (89% de los fallos), creando 21 documentos fantasma de `40p` y bajando COM de 90% (613) a 74% (484).

**Fix:** Validación `max_total=10` en `_parse()` (`core/utils.py:55`):
```python
if 0 < c <= tot <= 10:  # was: tot <= 99
```
Justificación: los 21 fixtures reales tienen `max_total ≤ 5`. El límite de 10 deja margen amplio sin permitir ghost-zeros.

**Resultados (ART_670, 796 páginas):**

| Métrica | v4-post-otsu | v5-max-total | Delta |
|---------|-------------|-------------|-------|
| COM (documentos completos) | 484 (74%) | 603 (90%) | +119 |
| Distribución | 4p×646, **40p×21** | 4p×665, 2p×1, 5p×1 | limpio |
| D-S confianza | 83% | 85% | +2pp |
| OCR: direct | 434 | 305 | -129 |
| OCR: super_resolution | 169 | 278 | +109 |
| OCR: easyocr | 0 | 20 | +20 |
| OCR: failed | 193 | 193 | = |

**Recuperación:** 119/129 documentos perdidos = 92.2%.

**Gap residual:** 603 vs 613 (pre-regresión). 10 docs short, atribuido a cambios en el mix de tiers OCR por el preprocesamiento post-Otsu, no al fix de max_total.

**Tests:** `tests/test_max_total.py` — 7 tests unitarios para validación de max_total.

### `[MOD:v4-post-otsu]` (2026-03-24)

Eliminación de binarización Otsu externa en `_tess_ocr()`. Tesseract LSTM usa gradientes internos; Otsu destruye bordes de caracteres (Tesseract issue #1780). Preprocesamiento: blue ink removal (HSV) → grayscale → unsharp mask (sigma=1.0, strength=0.3).

### `[MOD:v3.1-fix]` — `[MOD:v1]`

Versiones anteriores del pipeline. Ver historial git para detalles.

---

**Nota para los Desarrolladores:**
No se debe volver a reintroducir `fitz` ni `cv2` dentro de `inference.py`; del mismo modo, mantengan los bloques mutables fuera de este último. Todas las optimizaciones deben respetar este nuevo _sandbox_ establecido.
