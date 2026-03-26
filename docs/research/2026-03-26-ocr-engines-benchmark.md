# OCR Engines Research — Benchmark & Recommendations (2026-03-26)

## TL;DR para PDFoverseer

El stack actual es **Tesseract Tier 1 + Tier 2 SR** (EasyOCR y el GPU consumer fueron removidos;
PaddleOCR fue probado y descartado — no se adapta bien al dominio específico).
La investigación queda como referencia general del estado del arte OCR en 2025-2026.

---

## Benchmarks clave (motores tradicionales/no-LLM)

| Engine | FPS (throughput) | CER (error) | VRAM | Modelo (MB) | GPU |
|--------|-----------------|-------------|------|-------------|-----|
| **Tesseract 5** | 8.2 fps (CPU) | 18% promedio / **2% doc limpio** | 300 MB RAM | 30 MB | ❌ experimental |
| **EasyOCR** | 3.1 fps (GPU) | **9%** | 2.8–3.4 GB | 200+ MB | ✅ |
| **PaddleOCR PP-OCRv4** | **12.7 fps (GPU)** | 10% | **1.2 GB** | **15 MB** | ✅ |
| **DocTR** | ~10 fps (GPU est.) | ~5–6% en docs estructurados | ~1.5 GB | 50–100 MB | ✅ |

Fuentes: [TildAlice benchmark](https://tildalice.io/ocr-tesseract-easyocr-paddleocr-benchmark/),
[IntuitionLabs](https://intuitionlabs.ai/articles/non-llm-ocr-technologies)

---

## Los contendientes

### 1. PaddleOCR PP-OCRv5 (Baidu) ⭐ RECOMENDADO

- **Lanzado:** Mayo 2025 como parte de PaddleOCR 3.0
- **Velocidad:** ~12.7 FPS GPU — **3x más rápido que EasyOCR**
- **Tamaño del modelo:** ~15 MB (vs 200 MB EasyOCR) — 13x más pequeño
- **Idiomas:** 106 lenguajes incluyendo **español explícitamente**
- **Precisión:** +13 puntos porcentuales vs PP-OCRv4 en documentos complejos; supera a PaddleOCR anterior, EasyOCR y Tesseract en OmniDocBench
- **VRAM:** ~1.2 GB (vs 2.8 GB EasyOCR)
- **Licencia:** Apache 2.0
- **Relevancia:** Reconoce texto impreso en PDFs, soporta español, GPU-native, más rápido que EasyOCR
- Fuente: [PP-OCRv5 Hugging Face](https://huggingface.co/blog/baidu/ppocrv5), [PaddleOCR GitHub](https://github.com/PaddlePaddle/PaddleOCR)

### 2. Surya (datalab-to)

- **Enfoque:** Line-level detection + recognition, 90+ idiomas incluyendo español
- **Velocidad:** ~0.13s por imagen en GPU A10
- **VRAM:** Alto por defecto (recognition: ~20 GB en batch 512); configurable con batches pequeños
- **Stars:** 19.5k en GitHub (muy activo)
- **Diferenciador:** Layout analysis completo (tablas, headers, columnas) + reading order
- **Contra para PDFoverseer:** VRAM alto por defecto; batch reducido lo baja pero también la velocidad
- Fuente: [Surya GitHub](https://github.com/datalab-to/surya)

### 3. DocTR (Mindee)

- **Enfoque:** Documentos estructurados (forms, facturas, papers)
- **Precisión:** ~95.6% con PARSeq; ~73.7% recall en formularios
- **GPU:** ✅ PyTorch + TensorFlow
- **API:** 3 líneas de Python para extraer texto
- **Ideal para:** docs con layout complejo; no para escena de texto
- **Contra:** Más orientado a documentos en inglés/europeos occidentales
- Fuente: [IntuitionLabs non-LLM analysis](https://intuitionlabs.ai/articles/non-llm-ocr-technologies)

### 4. RapidOCR

- Wrapper ultraligero sobre modelos PaddleOCR exportados a ONNX — corre sin PaddlePaddle
- Mínima memoria, CPU-first, pero pierde con word spacing en algunos casos
- Útil si se quiere PaddleOCR sin la dependencia del framework PaddlePaddle

---

## Motores LLM/VLM (nueva ola, octubre 2025)

Procesan la página como imagen y la "leen" semánticamente. Overkill para page numbers.

| Modelo | Accuracy (OlmOCR bench) | Throughput | VRAM | Tamaño |
|--------|------------------------|-----------|------|--------|
| **Chandra-OCR** | **83.1%** | 1.29 p/s | alto | 9B |
| **OlmOCR-2** | 82.4% | 1.78 p/s | moderado | 7.7B |
| **PaddleOCR-VL** | 80.0% | 2.20 p/s | muy bajo | 0.9B |
| **DeepSeek-OCR** | 75.7% | 4.65 p/s | bajo | 3B |
| **LightOn OCR** | 76.1% | **5.55 p/s** | mínimo | — |

Fuente: [E2E Networks guide 2025](https://www.e2enetworks.com/blog/complete-guide-open-source-ocr-models-2025)

> Para PDFoverseer (page numbers `Página N de M` en texto impreso): los VLMs son overkill.
> Los motores clásicos son más apropiados y mucho más rápidos.

---

## Veredicto para PDFoverseer

| Pregunta | Respuesta |
|----------|-----------|
| ¿Tesseract actual es el mejor para Tier 1? | **No.** PaddleOCR PP-OCRv5 es 3x más rápido en GPU y más preciso |
| ¿EasyOCR como fallback GPU sigue siendo válido? | **Sí pero mejorable.** PaddleOCR lo supera en velocidad con menos VRAM |
| ¿Hay algo mejor para el caso específico? | **PaddleOCR PP-OCRv5** — español nativo, GPU, 15 MB modelo, 12.7 FPS |
| ¿Vale la pena probar Surya? | Sí si se necesita layout analysis; VRAM es alto |
| ¿Cambiar a VLMs? | No — overkill para page numbers en texto impreso limpio |

### Nota sobre PaddleOCR

PaddleOCR fue probado en producción para este caso de uso y **no dio buenos resultados**.
El dominio específico (strip pequeño, "Página N de M", texto impreso español) no se adapta bien al pipeline de PaddleOCR. Descartado.

---

## Fuentes

- [8 Top Open-Source OCR Models Compared — Modal](https://modal.com/blog/8-top-open-source-ocr-models-compared)
- [PaddleOCR vs Tesseract vs EasyOCR benchmark — TildAlice](https://tildalice.io/ocr-tesseract-easyocr-paddleocr-benchmark/)
- [Technical Analysis of Non-LLM OCR Engines — IntuitionLabs](https://intuitionlabs.ai/articles/non-llm-ocr-technologies)
- [7 Best Open-Source OCR Models 2025 — E2E Networks](https://www.e2enetworks.com/blog/complete-guide-open-source-ocr-models-2025)
- [PP-OCRv5 on Hugging Face](https://huggingface.co/blog/baidu/ppocrv5)
- [PaddleOCR GitHub](https://github.com/PaddlePaddle/PaddleOCR)
- [Surya GitHub](https://github.com/datalab-to/surya)
- [10 Awesome OCR Models for 2025 — KDnuggets](https://www.kdnuggets.com/10-awesome-ocr-models-for-2025)
- [DeepSeek-OCR vs Tesseract 2025 — Skywork](https://skywork.ai/blog/ai-agent/deepseek-ocr-vs-tesseract-2025-comparison-2/)
