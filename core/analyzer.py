"""
analyzer.py  —  V2 Pipeline Engine
====================================
Contador de documentos en PDFs de charlas (CRS).

Dependencias:
    pip install pytesseract opencv-contrib-python PyMuPDF
    + Tesseract OCR instalado en el sistema (tesseract.exe en Windows)
    + FSRCNN_x4.pb model in models/ folder

Pipeline V2
-----------
Por cada página del PDF:
  1. PyMuPDF clip rendering (solo la esquina superior-derecha, no la página completa)
  2. Tier 1: Tesseract directo con Otsu threshold
  3. Tier 2: FSRCNN x4 + Tesseract (si Tier 1 falla)
Post-scan:
  4. Constraint Propagation + Bayesian inference para páginas fallidas
  5. Reportar páginas inferidas con confianza < 0.90 como issues
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import pytesseract
import fitz  # PyMuPDF

# ── Configuración ─────────────────────────────────────────────────────────────

import os as _os
pytesseract.pytesseract.tesseract_cmd = _os.getenv(
    "TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

MODELS_DIR   = Path(__file__).parent.parent / "models"
FSRCNN_PATH  = str(MODELS_DIR / "FSRCNN_x4.pb")
EDSR_PATH    = str(MODELS_DIR / "EDSR_x4.pb")

DPI          = 150
CROP_X_START = 0.70   # rightmost 30%
CROP_Y_END   = 0.22   # top 22%
TESS_CONFIG  = "--psm 6 --oem 1"

# Regex: maneja variaciones del OCR en "Página X de N"
_PAGE_RE = re.compile(
    r"P.{0,2}[gq](?:ina?)?\.?\s*(\d{1,3})\s*\.?\s*de\s*(\d{1,3})",
    re.IGNORECASE,
)
_Z2 = re.compile(r"(?<!\d)Z(?!\d)")


# ── Super Resolution Model ───────────────────────────────────────────────────

_sr_model = None


def _load_sr():
    """Load the FSRCNN super resolution model (1MB, fast on CPU)."""
    global _sr_model
    _sr_model = cv2.dnn_superres.DnnSuperResImpl_create()
    _sr_model.readModel(FSRCNN_PATH)
    _sr_model.setModel("fsrcnn", 4)


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


# ── Inference result for each page ────────────────────────────────────────────

@dataclass
class _PageRead:
    """Internal per-page OCR result used for inference."""
    pdf_page: int
    curr: int | None
    total: int | None
    method: str
    confidence: float


# ── OCR helpers ───────────────────────────────────────────────────────────────

def _parse(text: str) -> tuple[Optional[int], Optional[int]]:
    t = _Z2.sub("2", text)
    m = _PAGE_RE.search(t)
    if m:
        c, tot = int(m.group(1)), int(m.group(2))
        if 0 < c <= tot <= 99:
            return c, tot
    return None, None


def _tess_ocr(gray: np.ndarray) -> str:
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return pytesseract.image_to_string(th, lang="eng", config=TESS_CONFIG)


# ── PyMuPDF clip rendering ───────────────────────────────────────────────────

def _render_clip(page: fitz.Page) -> np.ndarray:
    """Render only the top-right corner of a PDF page. Returns BGR numpy array."""
    rect = page.rect
    clip = fitz.Rect(
        rect.width * CROP_X_START,
        0,
        rect.width,
        rect.height * CROP_Y_END,
    )
    pix = page.get_pixmap(dpi=DPI, clip=clip)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    if pix.n == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    elif pix.n == 3:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    else:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return img


# ── 2-Tier OCR Pipeline ──────────────────────────────────────────────────────

def _extract_page_number(page: fitz.Page, page_idx: int) -> _PageRead:
    """Tier 1: Tesseract direct. Tier 2: FSRCNN x4 + Tesseract."""
    bgr = _render_clip(page)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # Tier 1: Direct Tesseract
    text = _tess_ocr(gray)
    c, t = _parse(text)
    if c:
        return _PageRead(page_idx, c, t, "direct", 1.0)

    # Tier 2: FSRCNN x4 + Tesseract
    bgr_sr = _sr_model.upsample(bgr)
    gray_sr = cv2.cvtColor(bgr_sr, cv2.COLOR_BGR2GRAY)
    text_sr = _tess_ocr(gray_sr)
    c, t = _parse(text_sr)
    if c:
        return _PageRead(page_idx, c, t, "SR", 1.0)

    return _PageRead(page_idx, None, None, "failed", 0.0)


# ── Tier 4: Inference Engine ─────────────────────────────────────────────────

def _infer_missing(reads: list[_PageRead]) -> list[_PageRead]:
    """
    Constraint Propagation + Bayesian inference for pages where OCR failed.
    Runs AFTER all pages are scanned.
    """
    n = len(reads)
    if n == 0:
        return reads

    # Phase 0: Build prior P(total=N) from successful reads
    totals = [r.total for r in reads if r.total is not None]
    total_counts: dict[int, int] = {}
    for t in totals:
        if t is not None:
            total_counts[t] = total_counts.get(t, 0) + 1
    total_sum = sum(total_counts.values()) or 1
    prior: dict[int, float] = {k: v / total_sum for k, v in total_counts.items()}
    if not prior:
        prior = {2: 0.85, 3: 0.10, 1: 0.05}

    # Phase 1: Forward propagation
    for i in range(n):
        r = reads[i]
        if r.method != "failed":
            continue
        if i > 0:
            prev = reads[i - 1]
            if prev.curr is not None and prev.total is not None:
                if prev.curr < prev.total:
                    r.curr = prev.curr + 1
                    r.total = prev.total
                    r.method = "inferred"
                    r.confidence = 0.95
                elif prev.curr == prev.total:
                    best_total = max(prior, key=lambda k: prior[k]) if prior else 2
                    r.curr = 1
                    r.total = best_total
                    r.method = "inferred"
                    r.confidence = 0.70

    # Phase 2: Backward propagation
    for i in range(n - 2, -1, -1):
        r = reads[i]
        if r.method != "failed":
            continue
        if i < n - 1:
            nxt = reads[i + 1]
            if nxt.curr is not None and nxt.total is not None:
                if nxt.curr > 1:
                    r.curr = nxt.curr - 1
                    r.total = nxt.total
                    r.method = "inferred"
                    r.confidence = 0.90
                elif nxt.curr == 1 and i > 0:
                    prev = reads[i - 1]
                    if prev.curr is not None and prev.total is not None:
                        r.curr = prev.curr + 1
                        r.total = prev.total
                        r.method = "inferred"
                        r.confidence = 0.90

    # Phase 3: Cross-validation
    for i in range(n):
        r = reads[i]
        if r.method != "inferred":
            continue
        consistent = True
        if i > 0:
            prev = reads[i - 1]
            if prev.curr is not None and prev.total is not None:
                if not ((prev.total == r.total and prev.curr == r.curr - 1) or
                        (prev.curr == prev.total and r.curr == 1)):
                    consistent = False
        if i < n - 1:
            nxt = reads[i + 1]
            if nxt.curr is not None and nxt.total is not None:
                if not ((nxt.total == r.total and nxt.curr == r.curr + 1) or
                        (r.curr == r.total and nxt.curr == 1)):
                    consistent = False
        if not consistent:
            r.confidence = min(r.confidence, 0.50)

    # Phase 4: Handle remaining failures
    for i in range(n):
        r = reads[i]
        if r.method == "failed":
            best_total = max(prior, key=lambda k: prior[k]) if prior else 2
            r.curr = 1
            r.total = best_total
            r.method = "inferred"
            r.confidence = 0.40

    return reads


# ── Main analysis function ────────────────────────────────────────────────────

def analyze_pdf(
    pdf_path: str,
    on_progress: callable,
    on_log:      callable,
    pause_event: threading.Event | None = None,
    cancel_event: threading.Event | None = None,
    on_issue:    callable | None = None,
    doc_mode:    str = "charla",
) -> tuple[list[Document], list[_PageRead]]:
    """
    Procesa un PDF con pipeline V2:
      1. PyMuPDF clip rendering (solo esquina superior-derecha)
      2. Tesseract directo → FSRCNN+Tesseract como fallback
      3. Inference engine post-scan para páginas fallidas
      4. Máquina de estados para construir documentos

    pause_event: espera a que esté set() antes de cada página.
    on_issue:    callback cuando se detecta un problema.
    """
    # Load SR model on first call
    global _sr_model
    if _sr_model is None:
        on_log("Cargando FSRCNN x4...", "info")
        _load_sr()

    # Open PDF with PyMuPDF
    on_log("Leyendo metadatos...", "info")
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
    except Exception as e:
        on_log(f"Error leyendo PDF: {e}", "error")
        return [], []

    on_log(f"Total páginas: {total_pages}", "info")
    on_log(f"Pipeline V2: Tesseract → FSRCNN → Inferencia", "info")

    def _issue(page: int, kind: str, detail: str):
        if on_issue is not None:
            on_issue(page, kind, detail, None)

    # ── Phase 1-2: OCR all pages ──────────────────────────────────────────
    reads: list[_PageRead] = []
    method_tally: dict[str, int] = {}
    t0 = time.time()

    for i in range(total_pages):
        # Cancel support
        if cancel_event is not None and cancel_event.is_set():
            on_log(f"Análisis abortado a petición del usuario.", "warn")
            doc.close()
            return [], []

        # Pause support
        if pause_event is not None:
            pause_event.wait()

        page = doc[i]
        pdf_page = i + 1

        try:
            r = _extract_page_number(page, pdf_page)
        except Exception as e:
            on_log(f"  Pág {pdf_page:>4}: ⚠ error de procesamiento: {e}", "error")
            r = _PageRead(pdf_page, None, None, "failed", 0.0)

        reads.append(r)
        method_tally[r.method] = method_tally.get(r.method, 0) + 1

        # Log per page
        if r.curr is not None:
            on_log(f"  Pág {pdf_page:>4}: {r.curr}/{r.total}  [{r.method}]", "page_ok")
        else:
            on_log(f"  Pág {pdf_page:>4}: ???  [{r.method}]", "page_warn")

        if on_progress:
            on_progress(pdf_page, total_pages)

    doc.close()

    # ── Phase 3: Inference ────────────────────────────────────────────────
    failed_count = sum(1 for r in reads if r.method == "failed")
    if failed_count > 0:
        on_log(f"Inferencia: procesando {failed_count} páginas fallidas...", "info")
        reads = _infer_missing(reads)
        inferred = sum(1 for r in reads if r.method == "inferred")
        on_log(f"Inferencia: {inferred} páginas recuperadas", "ok")

    # Report inferred pages with low/medium confidence as issues
    for r in reads:
        if r.method == "inferred" and r.confidence <= 0.60:
            conf_label = "MEDIA" if r.confidence >= 0.50 else "BAJA"
            detail = (f"Pág {r.pdf_page}: inferida como {r.curr}/{r.total} "
                      f"(confianza {conf_label}: {r.confidence:.0%})")
            on_log(f"  → {detail}", "warn")
            _issue(r.pdf_page, f"inferida ({conf_label} {r.confidence:.0%})", detail)

    # ── Phase 4: Build documents from reads ───────────────────────────────
    documents = _build_documents(reads, on_log, _issue)

    # ── Summary ───────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    # The 'orphans' list is now internal to _build_documents, so this check is removed.
    # if orphans:
    #     on_log(f"Páginas huérfanas: {orphans}", "warn")
    on_log(f"Métodos OCR: {method_tally}", "info")
    on_log(f"Tiempo: {elapsed:.1f}s ({total_pages} páginas, "
           f"{elapsed / total_pages * 1000:.0f}ms/pág)", "info")

    return documents, reads


def _build_documents(reads: list[_PageRead], on_log: callable, on_issue: callable) -> list[Document]:
    documents:    list[Document] = []
    current:      Optional[Document] = None
    orphans:      list[int] = [] # This 'orphans' list is local to _build_documents

    for r in reads:
        if r.method == "excluded":
            continue
            
        curr, tot, pdf_page = r.curr, r.total, r.pdf_page
        is_inferred = r.method == "inferred"

        if curr == 1:
            if current is not None:
                documents.append(current)
            current = Document(
                index          = len(documents) + 1,
                start_pdf_page = pdf_page,
                declared_total = tot,
                pages          = [] if is_inferred else [pdf_page],
                inferred_pages = [pdf_page] if is_inferred else [],
            )

        elif curr is not None:
            if current is None:
                orphans.append(pdf_page)
                on_log(f"  → huérfana: curr={curr} sin doc activo", "warn")
                on_issue(pdf_page, "huérfana", f"curr={curr} sin doc activo")
            else:
                expected = current.found_total + 1
                if is_inferred:
                    current.inferred_pages.append(pdf_page)
                elif curr == expected and tot == current.declared_total:
                    current.pages.append(pdf_page)
                else:
                    current.sequence_ok = False
                    current.pages.append(pdf_page)
                    detail = f"secuencia rota: curr={curr}, expected={expected}"
                    on_log(f"  → {detail}", "error")
                    on_issue(pdf_page, "secuencia rota", detail)

    if current is not None:
        documents.append(current)

    if orphans:
        on_log(f"Páginas huérfanas: {orphans}", "warn")
    return documents

def re_infer_documents(
    reads: list[_PageRead],
    corrections: dict[int, tuple[int, int]],
    on_log: callable,
    on_issue: callable | None = None,
    exclusions: list[int] = None
) -> tuple[list[Document], list[_PageRead]]:
    """
    Applies manual user corrections and exclusions, resets other inferred pages,
    and runs the inference algorithm again to cascade probabilities.
    """
    def _issue(page: int, kind: str, detail: str):
        if on_issue is not None:
            on_issue(page, kind, detail, None)

    if exclusions is None:
        exclusions = []
        
    # 1. Apply corrections/exclusions and reset inferred pages to failed
    for r in reads:
        if r.pdf_page in exclusions:
            r.method = "excluded"
            r.curr = None
            r.total = None
            r.confidence = 1.0
        elif r.pdf_page in corrections:
            curr, tot = corrections[r.pdf_page]
            r.curr = curr
            r.total = tot
            r.method = "manual"
            r.confidence = 1.0
        elif r.method == "inferred":
             # Revoke inference to allow it to be re-evaluated
             r.method = "failed"
             r.curr = None
             r.total = None
             r.confidence = 0.0

    # 2. Re-run inference cascade
    reads = _infer_missing(reads)

    # 3. Report remaining issues (<= 0.60)
    for r in reads:
        if r.method == "inferred" and r.confidence <= 0.60:
            conf_label = "MEDIA" if r.confidence >= 0.50 else "BAJA"
            detail = (f"Pág {r.pdf_page}: inferida como {r.curr}/{r.total} "
                      f"(confianza {conf_label}: {r.confidence:.0%})")
            on_log(f"  → {detail}", "warn")
            _issue(r.pdf_page, f"inferida ({conf_label} {r.confidence:.0%})", detail)

    # 4. Rebuild document logic
    documents = _build_documents(reads, on_log, _issue)

    return documents, reads
