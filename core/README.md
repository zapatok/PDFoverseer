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

**Nota para los Desarrolladores:** 
No se debe volver a reintroducir `fitz` ni `cv2` dentro de `inference.py`; del mismo modo, mantengan los bloques mutables fuera de este último. Todas las optimizaciones deben respetar este nuevo _sandbox_ establecido.
