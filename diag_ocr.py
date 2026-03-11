"""
Diagnostico: muestra el texto raw que lee OCR en el 30% derecho de cada pagina
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path("g:/My Drive/Python/PDFoverseer")))

import cv2
import numpy as np
import pytesseract
from pdf2image import convert_from_path

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

TESS_CFG     = "--psm 6 --oem 1"
CROP_X_START = 0.70
CROP_Y_END   = 0.22
PDF_PATH     = r"G:\My Drive\Python\CH Diaria P saez 0(05).pdf"

from PIL import Image

pages = convert_from_path(PDF_PATH, dpi=150, first_page=1, last_page=5)
for i, pil_img in enumerate(pages, 1):
    w, h = pil_img.size
    bgr  = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    crp  = bgr[0:int(h * CROP_Y_END), int(w * CROP_X_START):w]
    gray = cv2.cvtColor(crp, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    text = pytesseract.image_to_string(th, lang="eng", config=TESS_CFG).strip()
    print(f"=== Pagina {i} (crop {crp.shape[1]}x{crp.shape[0]}) ===")
    print(text or "(vacio)")
    print()
    # Guardar crop de las primeras 2 paginas
    if i <= 2:
        cv2.imwrite(f"diag_p{i}_crop.png", crp)
        cv2.imwrite(f"diag_p{i}_thresh.png", th)
