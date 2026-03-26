"""
Prototipo: Super Resolution para el numero de pagina
Toma la primera pagina de un PDF real, la convierte a imagen, y compara:
- Cubic x4 (metodo actual)
- FSRCNN x4 (IA ligera)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path("g:/My Drive/Python/PDFoverseer")))

import cv2
import numpy as np
import pytesseract
import re
import time

from PIL import Image
from pdf2image import convert_from_path

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

MODEL_PATH = "models/FSRCNN_x4.pb"
TESS_CFG   = "--psm 6 --oem 1"

# =========================================================
# CAMBIA AQUI LA RUTA A UN PDF CON NUMEROS EN EL RINCON
# =========================================================
PDF_PATH = r"D:\Informe Mensual\RESUMEN EJECUTIVO AIF\4.- Charlas Generales\CRS -CH DIARIA (39).pdf"
# =========================================================

# DPI usados para convertir PDF a imagen
DPI = 150

# Crop: tomamos el 30% derecho de la pagina, 22% superior (donde esta el numero)
CROP_X_START = 0.70
CROP_Y_END   = 0.22

# ---- Cargar modelo FSRCNN ----
print("Cargando modelo FSRCNN...")
_sr = cv2.dnn_superres.DnnSuperResImpl_create()
_sr.readModel(MODEL_PATH)
_sr.setModel("fsrcnn", 4)
print("Modelo cargado.\n")


def ocr(gray):
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return pytesseract.image_to_string(thresh, lang="eng", config=TESS_CFG).strip()


def parse(text):
    m = re.search(r"P.{0,4}g.{0,2}\s*(\d{1,3})\s*(?:de|of|\/)\s*(\d{1,3})", text, re.I)
    if m:
        return f"[OK] Pagina {m.group(1)} de {m.group(2)}"
    m2 = re.search(r"(\d{1,3})\s*(?:de|of|\/)\s*(\d{1,3})", text, re.I)
    if m2:
        return f"[OK] {m2.group(1)} de {m2.group(2)}"
    return "[NO encontrado]"


# ---- Convertir primera pagina del PDF ----
print(f"Convirtiendo pagina 1 de: {PDF_PATH}")
pages = convert_from_path(PDF_PATH, dpi=DPI, first_page=1, last_page=1)
pil_page = pages[0]
print(f"Pagina completa: {pil_page.width}x{pil_page.height} px\n")

# ---- Crop del numero ----
w, h = pil_page.size
bgr_full = cv2.cvtColor(np.array(pil_page), cv2.COLOR_RGB2BGR)
bgr_crp  = bgr_full[0 : int(h * CROP_Y_END), int(w * CROP_X_START) : w]
gray_crp = cv2.cvtColor(bgr_crp, cv2.COLOR_BGR2GRAY)
print(f"Region del numero (crop): {bgr_crp.shape[1]}x{bgr_crp.shape[0]} px\n")

# ---- Comparacion ----

# 1. Directo
t = time.time(); text1 = ocr(gray_crp)
print(f"[1] Directo           ({int((time.time()-t)*1000):3d} ms): {parse(text1)}")
print(f"    Raw: {repr(text1[:100])}\n")

# 2. Cubic x4 (actual: la funcion _up del analyzer)
t = time.time()
gray_cubic = cv2.resize(gray_crp, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
text2 = ocr(gray_cubic)
print(f"[2] Cubic x4          ({int((time.time()-t)*1000):3d} ms): {parse(text2)}")
print(f"    Raw: {repr(text2[:100])}\n")

# 3. FSRCNN x4 (nuevo)
t = time.time()
bgr_sr   = _sr.upsample(bgr_crp)
gray_sr  = cv2.cvtColor(bgr_sr, cv2.COLOR_BGR2GRAY)
text3 = ocr(gray_sr)
print(f"[3] FSRCNN x4 (IA)    ({int((time.time()-t)*1000):3d} ms): {parse(text3)}")
print(f"    Raw: {repr(text3[:100])}\n")

# ---- Guardar imagenes para comparacion visual ----
cv2.imwrite("sr_0_crop.png",       bgr_crp)
cv2.imwrite("sr_1_cubic_x4.png",   gray_cubic)
cv2.imwrite("sr_2_fsrcnn_x4.png",  gray_sr)
print("Imagenes guardadas: sr_0_crop.png | sr_1_cubic_x4.png | sr_2_fsrcnn_x4.png")
