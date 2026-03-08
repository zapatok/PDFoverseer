"""
analyzer.py  —  Core logic from pdfcount.py (optimized)
========================================================
Contador de documentos en PDFs de charlas (CRS).

Dependencias:
    pip install pdf2image pytesseract pillow opencv-python
    + Tesseract OCR instalado en el sistema (tesseract.exe en Windows)

Algoritmo
---------
Por cada página del PDF:
  1. Recortar encabezado superior-derecho (donde vive "Página X de N").
  2. Cascade de preprocessings hasta que uno produzca un match:
       a. Baseline: grayscale + Otsu x2
       b. Eliminación de tinta coloreada (azul, rojo, verde) + Otsu x2
       c. Canal rojo (tinta azul se vuelve fondo claro) + Otsu x2
       d. Inpainting sobre zona coloreada + Otsu x3
       e. Crop más amplio (header en posición no estándar)
       f. Ancho completo (último recurso)
  3. Regex robusto que maneja errores típicos del OCR en estos formularios.
  4. Máquina de estados:
       - curr == 1 → nuevo documento
       - OCR falla y doc actual no completó su total → inferir como continuación
       - OCR falla y doc actual ya completó → marcar página huérfana
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

import cv2
import numpy as np
import pytesseract
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image

# ── Configuración ─────────────────────────────────────────────────────────────

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

DPI            = 150
CROP_X_START   = 0.38   # ignorar 38% izquierdo
CROP_Y_END     = 0.22   # solo 22% superior
POPPLER_THREADS = 4     # hilos paralelos para renderizar páginas

# Whitelist: solo caracteres relevantes para "Página X de N"
_TESS_WHITELIST = "PpÁáAaéEgGqQiInN0123456789 de.,"
TESS_CONFIG  = f"--psm 6 --oem 1 -c tessedit_char_whitelist={_TESS_WHITELIST}"

# Regex: maneja variaciones del OCR en "Página X de N"
# - á/a/é/4 en "Página"  →  .{0,2}
# - g/q (OCR frecuente)  →  [gq]
# - "ina" puede faltar   →  (?:ina?)?
# - punto extra          →  \.?
# - Z aislado → 2        →  pre-sustitución con _Z2
_PAGE_RE = re.compile(
    r"P.{0,2}[gq](?:ina?)?\.?\s*(\d{1,3})\s*\.?\s*de\s*(\d{1,3})",
    re.IGNORECASE,
)
_Z2 = re.compile(r"(?<!\d)Z(?!\d)")

_KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))


# ── Modelo de datos ───────────────────────────────────────────────────────────

@dataclass
class Document:
    index:          int
    start_pdf_page: int
    declared_total: int
    pages:          list[int] = field(default_factory=list)
    inferred_pages: list[int] = field(default_factory=list)
    sequence_ok:    bool      = True

    @property
    def found_total(self) -> int:
        return len(self.pages) + len(self.inferred_pages)

    @property
    def is_complete(self) -> bool:
        return self.sequence_ok and self.found_total == self.declared_total


# ── Preprocessing + OCR ───────────────────────────────────────────────────────

def _parse(text: str) -> tuple[Optional[int], Optional[int]]:
    t = _Z2.sub("2", text)
    m = _PAGE_RE.search(t)
    if m:
        c, tot = int(m.group(1)), int(m.group(2))
        if 0 < c <= tot <= 99:
            return c, tot
    return None, None


def _ocr(img_bin: np.ndarray) -> tuple[Optional[int], Optional[int]]:
    text = pytesseract.image_to_string(img_bin, lang="eng", config=TESS_CONFIG)
    return _parse(text)


def _up(gray: np.ndarray, factor: int = 2) -> np.ndarray:
    return cv2.resize(gray, None, fx=factor, fy=factor,
                      interpolation=cv2.INTER_CUBIC)


def _bin(gray: np.ndarray) -> np.ndarray:
    _, b = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return b


def _ink_mask(arr: np.ndarray) -> np.ndarray:
    """
    Detecta tinta coloreada (azul, rojo, verde) excluyendo texto negro y fondo blanco.
    Estrategia: un canal domina sobre los otros dos en al menos 15 puntos,
    el píxel no es casi-negro (<100 en todos) ni casi-blanco (>200 en todos).
    """
    r = arr[:, :, 0].astype(int)
    g = arr[:, :, 1].astype(int)
    b = arr[:, :, 2].astype(int)
    not_text = ~((r < 100) & (g < 100) & (b < 100))
    not_bg   = ~((r > 200) & (g > 200) & (b > 200))
    blue  = (b - r > 15) & (b - g > 7)
    red   = (r - b > 15) & (r - g > 7)
    green = (g - r > 15) & (g - b > 7)
    return (blue | red | green) & not_text & not_bg


# ── Métodos de extracción individuales (para cache adaptativo) ────────────────

def _try_baseline(arr, gray):
    c, t = _ocr(_bin(_up(gray)))
    return (c, t, "baseline") if c else None

def _try_color_removal(arr, gray):
    mask = _ink_mask(arr)
    if not mask.any():
        return None
    clean = arr.copy()
    clean[mask] = [255, 255, 255]
    c, t = _ocr(_bin(_up(cv2.cvtColor(clean, cv2.COLOR_RGB2GRAY))))
    return (c, t, "color_removal") if c else None

def _try_red_channel(arr, gray):
    c, t = _ocr(_bin(_up(arr[:, :, 0])))
    return (c, t, "red_channel") if c else None

def _try_inpaint(arr, gray):
    mask = _ink_mask(arr)
    if not mask.any():
        return None
    mask_dil = cv2.dilate(mask.astype(np.uint8) * 255, _KERNEL, iterations=2)
    inp = cv2.inpaint(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR),
                      mask_dil, 5, cv2.INPAINT_TELEA)
    gray3 = cv2.cvtColor(inp, cv2.COLOR_BGR2GRAY)
    c, t = _ocr(_bin(_up(gray3, factor=3)))
    return (c, t, "inpaint") if c else None

def _try_wide_crop(arr, gray, pil_img=None):
    if pil_img is None:
        return None
    w, h = pil_img.size
    arr_wide = np.array(pil_img.crop((int(w * 0.20), 0, w, int(h * 0.30))))
    c, t = _ocr(_bin(_up(cv2.cvtColor(arr_wide, cv2.COLOR_RGB2GRAY))))
    return (c, t, "wide_crop") if c else None

def _try_full_width(arr, gray, pil_img=None):
    if pil_img is None:
        return None
    w, h = pil_img.size
    arr_full = np.array(pil_img.crop((0, 0, w, int(h * 0.28))))
    c, t = _ocr(_bin(_up(cv2.cvtColor(arr_full, cv2.COLOR_RGB2GRAY))))
    return (c, t, "full_width") if c else None

# Orden canónico de la cascade
_METHOD_ORDER = [
    ("baseline",      _try_baseline),
    ("color_removal", _try_color_removal),
    ("red_channel",   _try_red_channel),
    ("inpaint",       _try_inpaint),
    ("wide_crop",     _try_wide_crop),
    ("full_width",    _try_full_width),
]

_NEEDS_PIL = {"wide_crop", "full_width"}


def extract_page_number(
    pil_img: Image.Image,
    hint_method: str | None = None,
) -> tuple[Optional[int], Optional[int], str]:
    """
    Cascade de preprocessings. Retorna (curr, tot, metodo).
    Si hint_method es proporcionado, intenta ese método primero
    antes de caer al cascade completo (cache adaptativo).
    """
    w, h = pil_img.size
    arr = np.array(pil_img.crop((int(w * CROP_X_START), 0, w, int(h * CROP_Y_END))))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

    # ── Intento rápido: usar el hint del método anterior ──────────────
    if hint_method:
        for name, fn in _METHOD_ORDER:
            if name == hint_method:
                kwargs = {"pil_img": pil_img} if name in _NEEDS_PIL else {}
                result = fn(arr, gray, **kwargs)
                if result:
                    return result
                break  # hint falló, caer al cascade completo

    # ── Cascade completo ──────────────────────────────────────────────
    for name, fn in _METHOD_ORDER:
        if name == hint_method:
            continue  # ya lo intentamos arriba
        kwargs = {"pil_img": pil_img} if name in _NEEDS_PIL else {}
        result = fn(arr, gray, **kwargs)
        if result:
            return result

    return None, None, "failed"


# ── Máquina de estados ────────────────────────────────────────────────────────

def analyze_pdf(
    pdf_path: str,
    on_progress: callable,
    on_log:      callable,
    pause_event: threading.Event | None = None,
    on_issue:    callable | None = None,
) -> list[Document]:
    """
    Regla de inferencia cuando OCR falla completamente:
    - Si el doc actual aún no alcanzó su total declarado:
        → la página se asigna como siguiente de la secuencia (inferred_pages).
    - Si el doc actual ya está completo o no hay doc activo:
        → la página se marca como huérfana.

    Esto cubre el supuesto de páginas de firmas rayadas, muy borrosas,
    o con baja calidad de scan que Tesseract no puede leer.

    pause_event: si se proporciona, se espera a que esté set() antes de
                 procesar cada página (permite pausar externamente).
    on_issue:    callback(pdf_page, issue_type, detail, pil_image) llamado
                 cuando se detecta un problema en una página.
    """
    on_log("Leyendo metadatos...", "info")
    try:
        total_pages = int(pdfinfo_from_path(pdf_path)["Pages"])
    except Exception as e:
        on_log(f"Error leyendo PDF: {e}", "error")
        return []

    on_log(f"Total páginas: {total_pages}", "info")
    on_log("Procesando páginas...", "info")

    documents:    list[Document] = []
    current:      Optional[Document] = None
    orphans:      list[int] = []
    method_tally: dict[str, int] = {}
    last_method:  str | None = None   # cache adaptativo

    def _issue(page: int, kind: str, detail: str, pil_img: Image.Image):
        if on_issue is not None:
            on_issue(page, kind, detail, pil_img)

    for pdf_page in range(1, total_pages + 1):
        # ── Pause support ────────────────────────────────────────────────
        if pause_event is not None:
            pause_event.wait()

        # ── Conversión página por página ─────────────────────────────────
        try:
            pages = convert_from_path(
                pdf_path, dpi=DPI,
                first_page=pdf_page, last_page=pdf_page,
                thread_count=POPPLER_THREADS,
            )
            img = pages[0]
        except Exception as e:
            on_log(f"  Pág {pdf_page:>4}: error renderizando — {e}", "error")
            on_progress(pdf_page, total_pages)
            continue

        curr, tot, method = extract_page_number(img, hint_method=last_method)
        method_tally[method] = method_tally.get(method, 0) + 1
        if method != "failed":
            last_method = method  # actualizar cache

        # Log
        if curr is not None:
            on_log(f"  Pág {pdf_page:>4}: {curr}/{tot}  [{method}]", "page_ok")
        else:
            on_log(f"  Pág {pdf_page:>4}: ???  [{method}]", "page_warn")

        # ── Transiciones ─────────────────────────────────────────────────────
        if curr == 1:
            if current is not None:
                documents.append(current)
            current = Document(
                index          = len(documents) + 1,
                start_pdf_page = pdf_page,
                declared_total = tot,
                pages          = [pdf_page],
            )

        elif curr is not None:
            if current is None:
                orphans.append(pdf_page)
                on_log(f"  → huérfana: curr={curr} sin doc activo", "warn")
                _issue(pdf_page, "huérfana",
                       f"curr={curr} sin doc activo", img)
            else:
                expected = current.found_total + 1
                if curr == expected and tot == current.declared_total:
                    current.pages.append(pdf_page)
                else:
                    current.sequence_ok = False
                    current.pages.append(pdf_page)
                    detail = (f"secuencia rota en doc {current.index}: "
                              f"esperaba {expected}/{current.declared_total}, "
                              f"llegó {curr}/{tot}")
                    on_log(f"  → {detail}", "warn")
                    _issue(pdf_page, "secuencia rota", detail, img)

        else:
            # OCR falló
            if current is not None and current.found_total < current.declared_total:
                # Continuación de un doc en curso: la página falta en mitad del doc
                current.inferred_pages.append(pdf_page)
                detail = (f"inferida como "
                          f"{current.found_total + 1}/{current.declared_total} "
                          f"en doc {current.index}")
                on_log(f"  → pág {pdf_page} {detail}", "warn")
                _issue(pdf_page, "inferida", detail, img)
            else:
                # Doc activo completo (o sin doc activo):
                # probablemente es la pág 1/N de un doc nuevo cuyo encabezado
                # Tesseract no pudo leer → crear documento provisional.
                if current is not None:
                    documents.append(current)
                current = Document(
                    index          = len(documents) + 1,
                    start_pdf_page = pdf_page,
                    declared_total = 2,     # estimación; se valida con la pág siguiente
                    pages          = [],
                    inferred_pages = [pdf_page],
                    sequence_ok    = False,  # inicio incierto → siempre marcado
                )
                detail = (f"inferida como inicio del doc {current.index} "
                          f"(OCR falló en pág 1, declared_total estimado=2)")
                on_log(f"  → pág {pdf_page} {detail}", "warn")
                _issue(pdf_page, "inferida", detail, img)

        on_progress(pdf_page, total_pages)

    if current is not None:
        documents.append(current)

    if orphans:
        on_log(f"Páginas huérfanas: {orphans}", "warn")
    on_log(f"Métodos OCR usados: {method_tally}", "info")

    return documents
