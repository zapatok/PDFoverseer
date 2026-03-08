# PDFoverseer

Supervisor de documentos en archivos PDF. Selecciona una carpeta y analiza todos los PDFs que contiene, contando los documentos internos mediante OCR.

## Requisitos

- **Python 3.10+**
- **Tesseract OCR** instalado en el sistema
  - Windows: [Descargar Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
  - La ruta por defecto es `C:\Program Files\Tesseract-OCR\tesseract.exe`
- **Poppler** para `pdf2image`
  - Windows: [Descargar Poppler](https://github.com/oschwartz10612/poppler-windows/releases/)

## Instalación

```bash
git clone https://github.com/zapatok/PDFoverseer.git
cd PDFoverseer
pip install -r requirements.txt
```

## Uso

```bash
python app.py
```

1. Haz clic en **📁 Seleccionar Carpeta** y elige una carpeta que contenga archivos PDF
2. La aplicación escaneará recursivamente todos los PDFs y los procesará en orden
3. Usa el botón **⏸ Pausar** para pausar/reanudar el análisis en cualquier momento
4. Los resultados se muestran en tiempo real en el log y en los contadores superiores

## Funcionalidades

- 📁 **Selección de carpeta** con escaneo recursivo de PDFs
- 🔍 **Análisis OCR** de cada página para detectar numeración "Página X de N"
- ⏸ **Pausa/Reanudación** del proceso en cualquier momento
- 📊 **Doble barra de progreso** (global por PDFs + individual por páginas)
- 📋 **Panel de PDFs** con estado visual (pendiente/procesando/completado/error)
- 📝 **Log detallado** del análisis de cada archivo

## Algoritmo de detección

El motor OCR utiliza una cascada de preprocesamiento de imágenes:

1. Baseline: escala de grises + Otsu
2. Eliminación de tinta coloreada
3. Canal rojo (para tinta azul)
4. Inpainting sobre zonas coloreadas
5. Crop amplio / ancho completo (fallback)

La máquina de estados detecta documentos nuevos cuando encuentra "Página 1 de N", y maneja páginas con OCR fallido mediante inferencia contextual.
