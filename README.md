# PDFoverseer

**PDF document analyzer** that counts internal documents in lecture PDFs using an OCR + AI inference engine. Process folders of PDFs with real-time progress, pause/resume, and per-document error reporting.

## Features

- 📁 **Folder browsing** with native OS dialogs (Windows file picker + tkinter)
- 📄 **Batch PDF processing** with pause/resume and per-document progress
- 🔍 **Dual-tier OCR** pipeline: Tesseract (CPU) + EasyOCR fallback (GPU optional)
- 🧠 **Multi-phase inference engine** (soft-alignment-v3-sweep1): period detection + Dempster-Shafer evidence fusion
- ⚡ **Real-time updates** via WebSocket, no page refresh
- 📊 **Session history** with persistent database (SQLite)
- 🎯 **Per-issue correction UI** for manual validation and retraining feedback

## Quick Start

```bash
# Install Python dependencies
pip install -r requirements.txt  # CPU-only
# OR
pip install -r requirements-gpu.txt  # GPU (EasyOCR + PyTorch CUDA)

# Backend (FastAPI)
source .venv-cuda/Scripts/activate  # or: .\.venv-cuda\Scripts\activate (Windows)
python server.py                     # → http://localhost:8000

# Frontend (React + Vite)
cd frontend && npm install
npm run dev                          # → http://localhost:5173
```

Then open http://localhost:5173 in your browser.

## Requirements

- **Python 3.10+**
- **Node.js 18+** (for frontend)
- **Tesseract OCR** (system PATH or `TESSERACT_CMD` env var)
  - Windows: [Descargar](https://github.com/UB-Mannheim/tesseract/wiki)
  - Ubuntu: `sudo apt install tesseract-ocr`
- **Ghostscript** (for PyMuPDF)
- *Optional:* **CUDA 12.1+** for GPU EasyOCR (see requirements-gpu.txt)

## Architecture

### V4 OCR Pipeline (Producer-Consumer)

1. **Producers** (6 parallel workers): PyMuPDF render + Tesseract Tier 1 (standard crop) + Tier 2 (super-resolution 4x)
2. **GPU Consumer** (1 thread): EasyOCR fallback on failed pages
3. **Post-scan**: Period detection (autocorrelation) + D-S evidence fusion + confidence calibration

### Inference Engine (soft-alignment-v3-sweep1)

- **Phase 1–2:** Forward/backward propagation of OCR reads
- **Phase 3:** Cross-validation of inferred boundaries
- **Phase 4:** Gap solver for missing detections
- **Phase 5:** Dempster-Shafer post-validation with neighbor evidence
- **Phase 5b:** Period-aware boundary correction
- **Multi-period (MP):** Local sliding-window correction for repeated doc patterns

**Key parameters** (eval-tuned):
- `MIN_CONF_FOR_NEW_DOC = 0.65` — confidence threshold for new boundaries
- `CLASH_BOUNDARY_PEN = 2.0` — gap-solver penalty
- `PH5B_CONF_MIN = 0.60` — period confidence floor

## Page Number Pattern

Spanish-centric regex (adaptable):
```regex
P.{0,2}[gq](?:ina?)?\.?\s*(\d{1,3})\s*\.?\s*de\s*(\d{1,3})
```

Matches: "Página 1 de 10", "Pag 1 de 10", "page 1 of 10", etc.
