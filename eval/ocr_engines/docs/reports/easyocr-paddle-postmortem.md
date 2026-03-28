# Postmortem: EasyOCR y PaddleOCR como fallback GPU en PDFoverseer

**Fecha:** 2026-03-25
**Rama:** `cuda-gpu`
**Decisión final:** EasyOCR eliminado del pipeline. PaddleOCR descartado. Pipeline queda como Tesseract Tier 1 + SR Tier 2 solamente.

---

## Contexto

El pipeline V4 implementaba un patrón producer-consumer:
- **6 productores Tesseract** (Tier 1 directo + Tier 2 con super-resolución 4x GPU)
- **1 consumidor EasyOCR GPU** (Tier 3): recibía páginas fallidas en una queue, las procesaba en paralelo con los productores

El objetivo del Tier 3 era recuperar páginas que Tesseract no pudo leer (páginas degradadas, texto pequeño, fondos complejos).

---

## Lo que se probó

### 1. EasyOCR vs. sin EasyOCR — producción en ART_670 (2719 páginas)

Comparación directa: mismo PDF, misma máquina, mismos parámetros de inferencia.

| Métrica | con EasyOCR (W6+GPU) | sin EasyOCR (W6+noGPU) | Delta |
|---------|---------------------|------------------------|-------|
| Tiempo total | 453.6s (167ms/p) | 464.2s (171ms/p) | +10.6s (+2%) |
| DOC total | 667 | 668 | +1 |
| COM completos | 603 (90%) | **606 (91%)** | +3 |
| INC incompletos | 64 | **62** | -2 |
| INF inferidas | 603 | 603 | = |
| EasyOCR hits | 2 | — | — |

**Hallazgo:** EasyOCR tuvo 2 hits en 2719 páginas (0.07%). Esas 2 lecturas introdujeron ruido en la inferencia, resultando en 3 documentos menos completos que sin EasyOCR.

**Causa:** El consumidor GPU opera en paralelo, pero el verdadero cuello de botella es Tesseract + SR Tier 2 (hasta 3340 llamadas Tesseract para 2719 páginas). EasyOCR no reduce ese bottleneck.

### 2. Benchmark EasyOCR vs. PaddleOCR — eval/ocr_benchmark.py en ART_670

Benchmark formal contra 796 páginas con ground truth (GT).

| Engine | Modelo | GT correctas | ms/página |
|--------|--------|-------------|-----------|
| EasyOCR | default | 5/796 (1%) | 276ms |
| PaddleOCR | PP-OCRv4 mobile det + rec | 0/796 (0%) | 33ms |
| PaddleOCR | **PP-OCRv5 server det + mobile rec** | **0/796 (0%)** | **68ms** |

**Potenciales recuperaciones** (no-GT, parseó algo): EasyOCR 82, PaddleOCR 0.

**Hallazgo clave:** Ni EasyOCR ni PaddleOCR (incluyendo la versión más reciente PP-OCRv5) logran leer los números de página `Página N de M` en estos PDFs de charlas CRS. El motivo probable:
- El crop es una franja estrecha (`top 22%, right 30%`) con texto pequeño y variaciones de fondo
- Tesseract con `--psm 6 --oem 1` + preprocesamiento específico (blue ink removal, unsharp mask) está afinado exactamente para este patrón
- EasyOCR y PaddleOCR son motores de propósito general; sin fine-tuning en este tipo de imagen, no compiten

---

## Falencias identificadas

### EasyOCR
- **Precisión insuficiente:** 1% en GT (5/796). El problema no es el modelo sino el mismatch con el tipo específico de imagen.
- **Sin beneficio de velocidad:** Corre en paralelo al Tier 2, por lo que no reduce latencia total.
- **Impacto negativo en inferencia:** Las 2 lecturas válidas que obtuvo introdujeron lecturas "raras" que el engine de inferencia interpretó como fronteras de documento donde no las había.
- **~3GB de VRAM:** Carga el modelo en startup aunque casi nunca lo use.

### PaddleOCR
- **Peor que EasyOCR:** 0/796 en todas las configuraciones probadas, incluyendo PP-OCRv5 server-level detection.
- **Sin soporte de español real:** `en_PP-OCRv5_mobile_rec` está entrenado en inglés; no hay modelo español oficial. El reconocimiento de "Página" falla.
- **Falsa esperanza de velocidad:** 33ms/página suena bien, pero 0% de accuracy lo hace irrelevante.

---

## Decisión

**Se elimina EasyOCR definitivamente del pipeline.** Cambios aplicados:

1. `core/ocr.py`: removidos `_easyocr_reader`, `_easyocr_lock`, `_init_easyocr()`, `EASYOCR_DPI`
2. `core/pipeline.py`: removido el GPU consumer thread, la queue, y toda la lógica asociada; telemetría actualizada a `[MOD:v6-tess-sr]`
3. `requirements-gpu.txt`: removido `easyocr==1.7.2`; `torch` se mantiene para SR Tier 2 GPU bicubic

**El pipeline queda:** Tesseract Tier 1 (directo) → Tesseract Tier 2 (SR 4x GPU bicubic) → Inferencia D-S

---

## Alternativas descartadas

| Alternativa | Veredicto |
|------------|-----------|
| PaddleOCR como Tier 1 | Descartado: 0% accuracy en ART_670 |
| EasyOCR como Tier 1 | Descartado: 1% accuracy, 276ms/p |
| Surya (layout analysis) | No evaluado: VRAM alto, overkill para page numbers |
| VLMs (Claude, GPT-4V) | Descartado: overkill para texto impreso limpio |

---

## Lecciones

- Benchmarks de literatura (PaddleOCR "3x más rápido, más preciso") no son transferibles a casos específicos. Tesseract con configuración domain-specific supera a modelos generales de última generación en esta tarea concreta.
- El patrón producer-consumer con cola GPU tiene sentido cuando el fallback añade hits reales. Con <0.1% de hits, el overhead de infraestructura supera el beneficio.
- Medir primero: la comparación con/sin EasyOCR tomó < 30 minutos y respondió la pregunta definitivamente.
