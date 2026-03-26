# Archived Files

Scripts y copias pre-modularización archivados. Solo tienen valor histórico.

## old_core.py / old_core_utf8.py

Mismo script en dos encodings (UTF-16 / UTF-8). Prototipo standalone para comparar métodos de OCR sobre el número de página:

- **[1] Directo** — Tesseract sin upscaling
- **[2] Cubic x4** — resize bicúbico + Tesseract
- **[3] FSRCNN x4** — super-resolución por red neuronal + Tesseract

Usaba `pdf2image`, rutas hardcodeadas a `G:/My Drive/Python/PDFoverseer` y `D:\Informe Mensual\...`. Antecede la arquitectura modular actual (`core/ocr.py`, `core/image.py`).

## old_analyzer_utf8.py

Copia UTF-8 de `old_analyzer.py` (que permanece en el root como referencia). Monolito V4 pre-modularización con EasyOCR GPU + SR + pipeline producer-consumer. EasyOCR fue posteriormente eliminado (ver postmortem `docs/superpowers/reports/2026-03-25-easyocr-paddle-postmortem.md`).

## old_server_utf8.py

Copia UTF-8 de `old_server.py` (que permanece en el root como referencia). Servidor FastAPI + WebSocket monolítico, antes de la separación en `api/routes/`, `api/state.py`, `api/worker.py`, etc.
