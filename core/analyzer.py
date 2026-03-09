"""
analyzer.py  —  Core logic from pdfcount.py (original engine)
=============================================================
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

import queue
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

DPI          = 150
DPI_FALLBACK = 200
CHUNK_SIZE   = 20
CROP_X_START = 0.38   # ignorar 38% izquierdo
CROP_Y_END   = 0.22   # solo 22% superior
TESS_CONFIG  = "--psm 6 --oem 1"

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


def extract_page_number(
    pil_img: Image.Image,
) -> tuple[Optional[int], Optional[int], str]:
    """
    Cascade de preprocessings. Retorna (curr, tot, metodo).
    Se detiene al primer match válido.
    """
    w, h = pil_img.size

    def crop_arr(x0: float = CROP_X_START, y1: float = CROP_Y_END) -> np.ndarray:
        return np.array(pil_img.crop((int(w * x0), 0, w, int(h * y1))))

    arr = crop_arr()

    # 1. Baseline
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    c, t = _ocr(_bin(_up(gray)))
    if c:
        return c, t, "baseline"

    # 2. Eliminación de tinta coloreada
    mask = _ink_mask(arr)
    if mask.any():
        clean = arr.copy()
        clean[mask] = [255, 255, 255]
        c, t = _ocr(_bin(_up(cv2.cvtColor(clean, cv2.COLOR_RGB2GRAY))))
        if c:
            return c, t, "color_removal"

    # 3. Canal rojo (la tinta azul, la más común, aparece clara en este canal)
    c, t = _ocr(_bin(_up(arr[:, :, 0])))
    if c:
        return c, t, "red_channel"

    # 4. Inpainting sobre zona coloreada
    if mask.any():
        mask_dil = cv2.dilate(mask.astype(np.uint8) * 255, _KERNEL, iterations=2)
        inp = cv2.inpaint(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR),
                          mask_dil, 5, cv2.INPAINT_TELEA)
        gray3 = cv2.cvtColor(inp, cv2.COLOR_BGR2GRAY)
        c, t = _ocr(_bin(_up(gray3, factor=3)))
        if c:
            return c, t, "inpaint"

    # 5. Crop más amplio (header no estándar, más a la izquierda o más abajo)
    arr_wide = crop_arr(x0=0.20, y1=0.30)
    c, t = _ocr(_bin(_up(cv2.cvtColor(arr_wide, cv2.COLOR_RGB2GRAY))))
    if c:
        return c, t, "wide_crop"

    # 6. Ancho completo
    arr_full = crop_arr(x0=0.0, y1=0.28)
    c, t = _ocr(_bin(_up(cv2.cvtColor(arr_full, cv2.COLOR_RGB2GRAY))))
    if c:
        return c, t, "full_width"

    return None, None, "failed"


# ── Máquina de estados ────────────────────────────────────────────────────────

def _convert_chunk(pdf_path: str, first: int, last: int, dpi: int) -> list[Image.Image]:
    """Convierte un rango de páginas del PDF a imágenes."""
    return convert_from_path(
        pdf_path, dpi=dpi, thread_count=6,
        first_page=first, last_page=last,
    )


def _convert_single_page(pdf_path: str, page: int, dpi: int) -> Image.Image:
    """Convierte una sola página del PDF a imagen."""
    imgs = convert_from_path(
        pdf_path, dpi=dpi, thread_count=1,
        first_page=page, last_page=page,
    )
    return imgs[0]


def _producer(pdf_path: str, total_pages: int, img_queue: queue.Queue,
              on_log: callable):
    """Hilo productor: convierte páginas en lotes y las pone en la cola."""
    for start in range(1, total_pages + 1, CHUNK_SIZE):
        end = min(start + CHUNK_SIZE - 1, total_pages)
        try:
            chunk_imgs = _convert_chunk(pdf_path, start, end, DPI)
            for offset, img in enumerate(chunk_imgs):
                img_queue.put((start + offset, img))  # (page_number, image)
        except Exception as e:
            on_log(f"Error convirtiendo págs {start}-{end}: {e}", "error")
            # Push None markers for failed pages so consumer doesn't hang
            for p in range(start, end + 1):
                img_queue.put((p, None))
    img_queue.put(None)  # Sentinel: production done


def analyze_pdf(
    pdf_path: str,
    on_progress: callable,
    on_log:      callable,
    pause_event: threading.Event | None = None,
    on_issue:    callable | None = None,
) -> list[Document]:
    """
    Procesa un PDF con pipeline productor-consumidor:
      - Productor: convierte páginas en lotes de CHUNK_SIZE a DPI base.
      - Consumidor: análisis OCR + máquina de estados.
      - Si OCR falla en todos los métodos a DPI base, re-renderiza la
        página a DPI_FALLBACK y reintenta.

    pause_event: espera a que esté set() antes de cada página.
    on_issue:    callback cuando se detecta un problema.
    """
    on_log("Leyendo metadatos...", "info")
    try:
        total_pages = int(pdfinfo_from_path(pdf_path)["Pages"])
    except Exception as e:
        on_log(f"Error leyendo PDF: {e}", "error")
        return []

    on_log(f"Total páginas: {total_pages}", "info")
    on_log(f"Procesando a {DPI} DPI en lotes de {CHUNK_SIZE}...", "info")

    # ── Producer-consumer pipeline ────────────────────────────────────────
    img_queue: queue.Queue = queue.Queue(maxsize=CHUNK_SIZE * 2)
    producer_thread = threading.Thread(
        target=_producer, args=(pdf_path, total_pages, img_queue, on_log),
        daemon=True,
    )
    producer_thread.start()

    documents:    list[Document] = []
    current:      Optional[Document] = None
    orphans:      list[int] = []
    method_tally: dict[str, int] = {}
    fallback_used = 0

    def _issue(page: int, kind: str, detail: str, pil_img: Image.Image):
        if on_issue is not None:
            on_issue(page, kind, detail, pil_img)

    while True:
        item = img_queue.get()
        if item is None:
            break  # Sentinel: all pages processed

        pdf_page, img = item

        # Conversion error for this page
        if img is None:
            on_log(f"  Pág {pdf_page:>4}: ⚠ error de conversión", "error")
            on_progress(pdf_page, total_pages)
            continue

        # ── Pause support ────────────────────────────────────────────────
        if pause_event is not None:
            pause_event.wait()

        curr, tot, method = extract_page_number(img)

        # ── DPI fallback: retry failed pages at higher resolution ────────
        if method == "failed":
            try:
                img_hi = _convert_single_page(pdf_path, pdf_page, DPI_FALLBACK)
                curr, tot, method = extract_page_number(img_hi)
                if method != "failed":
                    method = f"{method}@{DPI_FALLBACK}"
                    img = img_hi  # use the higher-res image for issue preview
                    fallback_used += 1
            except Exception:
                pass  # fallback failed, stick with original result

        method_tally[method] = method_tally.get(method, 0) + 1

        # Log
        if curr is not None:
            on_log(f"  Pág {pdf_page:>4}: {curr}/{tot}  [{method}]", "page_ok")
        else:
            on_log(f"  Pág {pdf_page:>4}: ???  [{method}]", "page_warn")

        # ── Transiciones ─────────────────────────────────────────────────
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
            # OCR falló (incluso con fallback)
            if current is not None and current.found_total < current.declared_total:
                current.inferred_pages.append(pdf_page)
                detail = (f"inferida como "
                          f"{current.found_total + 1}/{current.declared_total} "
                          f"en doc {current.index}")
                on_log(f"  → pág {pdf_page} {detail}", "warn")
                _issue(pdf_page, "inferida", detail, img)
            else:
                if current is not None:
                    documents.append(current)
                current = Document(
                    index          = len(documents) + 1,
                    start_pdf_page = pdf_page,
                    declared_total = 2,
                    pages          = [],
                    inferred_pages = [pdf_page],
                    sequence_ok    = False,
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
    if fallback_used > 0:
        on_log(f"Páginas recuperadas con DPI fallback ({DPI_FALLBACK}): {fallback_used}", "ok")

    return documents
