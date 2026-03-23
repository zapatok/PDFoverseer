# PDFoverseer

Supervisor de documentos en archivos PDF. Selecciona una carpeta y analiza todos los PDFs que contiene, contando los documentos internos mediante OCR.

## Requisitos

- **Python 3.10+**
- **Tesseract OCR** instalado en el sistema
  - Windows: [Descargar Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
  - La ruta por defecto es `C:\Program Files\Tesseract-OCR\tesseract.exe`

## Instalación

```bash
git clone https://github.com/zapatok/PDFoverseer.git
cd PDFoverseer
pip install -r requirements.txt
```

## Uso

```bash
# Backend
source .venv-cuda/Scripts/activate
python server.py          # FastAPI en http://localhost:8000

# Frontend (desarrollo)
cd frontend && npm run dev  # Vite en http://localhost:5173
```

1. Abre `http://localhost:5173` en el navegador
2. Introduce la ruta de la carpeta de PDFs y haz clic en **Agregar**
3. Usa el botón **▶ Iniciar** para lanzar el análisis
4. Usa **⏸ Pausar** / **⏹ Detener** en cualquier momento
5. Los resultados se muestran en tiempo real vía WebSocket

## Funcionalidades

- 📁 **Selección de carpeta** con escaneo recursivo de PDFs
- 🔍 **Análisis OCR** de cada página para detectar numeración "Página X de N"
- ⏸ **Pausa/Reanudación** del proceso en cualquier momento
- 📊 **Doble barra de progreso** (global por PDFs + individual por páginas)
- 📋 **Panel de PDFs** con estado visual (pendiente/procesando/completado/error)
- 📝 **Log detallado** del análisis de cada archivo

## Algoritmo de detección (Pipeline V4)

**Fase OCR — Patrón productor-consumidor:**

1. **Productores** (6 workers paralelos): PyMuPDF renderiza páginas → Tesseract Tier 1 (crop estándar) → Tier 2 con super-resolución 4x (FSRCNN)
2. **Consumidor GPU** (1 hilo dedicado): EasyOCR en páginas que fallaron con Tesseract

El patrón buscado es `Página N de M` (regex español) en la esquina superior derecha del PDF.

**Fase de inferencia (multi-fase):**

1. Detección de período por autocorrelación
2. Fusión de evidencias (Dempster-Shafer)
3. Relleno de huecos por vecindad y propagación
4. Corrección de contradicciones (Phase 5b)
5. Supresión de páginas huérfanas de baja confianza
