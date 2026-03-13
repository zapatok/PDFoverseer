"""
analyzer.py  —  V4 Pipeline Engine (parallel + EasyOCR GPU + SR)
=================================================================
Contador de documentos en PDFs de charlas (CRS).

Dependencias (venv-cuda):
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
    pip install PyMuPDF opencv-contrib-python fastapi uvicorn[standard] pydantic pytesseract easyocr
    + Tesseract OCR instalado en el sistema

Pipeline V4
-----------
Por cada pagina del PDF (procesamiento paralelo, PARALLEL_WORKERS paginas simultaneas):
  1. PyMuPDF clip rendering + Tesseract OCR — hasta PARALLEL_WORKERS threads en paralelo
  2. Tier 1: Tesseract directo con Otsu threshold
  3. Tier 1.5: EasyOCR GPU (si Tier 1 falla) — nativo PyTorch, sin subprocess overhead
  4. Tier 2: SR x4 + Tesseract (si Tier 1.5 falla)
Post-scan:
  5. Constraint Propagation + Bayesian inference para paginas fallidas
  6. Reportar paginas inferidas con confianza < 0.90 como issues

Compatibilidad V2/V3: todas las firmas publicas son identicas.
"""

from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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

MODELS_DIR      = Path(__file__).parent.parent / "models"
FSRCNN_PATH     = str(MODELS_DIR / "FSRCNN_x4.pb")
EDSR_PATH       = str(MODELS_DIR / "EDSR_x4.pb")

DPI              = 150
CROP_X_START     = 0.70   # rightmost 30%
CROP_Y_END       = 0.22   # top 22%
TESS_CONFIG      = "--psm 6 --oem 1"
PARALLEL_WORKERS = 4      # concurrent Tesseract subprocesses
BATCH_SIZE       = 8      # pages per batch (pause/cancel granularity)

# Regex: maneja variaciones del OCR en "Página X de N"
_PAGE_RE = re.compile(
    r"P.{0,2}[gq](?:ina?)?\.?\s*(\d{1,3})\s*\.?\s*de\s*(\d{1,3})",
    re.IGNORECASE,
)
_Z2 = re.compile(r"(?<!\d)Z(?!\d)")


# ── EasyOCR GPU (Tier 1.5) ───────────────────────────────────────────────────

_easyocr_reader = None        # singleton, lazy-loaded (not thread-safe — use via queue)
_easyocr_lock   = threading.Lock()


def _init_easyocr(on_log: callable) -> None:
    """Lazy-init EasyOCR Reader with GPU support."""
    global _easyocr_reader
    if _easyocr_reader is not None:
        return
    with _easyocr_lock:
        if _easyocr_reader is not None:
            return  # double-check after lock
        try:
            import easyocr
            gpu = False
            try:
                import torch
                gpu = torch.cuda.is_available()
            except ImportError:
                pass
            on_log(f"EasyOCR: inicializando ({'GPU' if gpu else 'CPU'})...", "info")
            _easyocr_reader = easyocr.Reader(
                ["es", "en"], gpu=gpu, verbose=False
            )
            on_log(f"EasyOCR: listo ({'GPU' if gpu else 'CPU'})", "ok")
        except Exception as e:
            on_log(f"EasyOCR: no disponible ({e})", "warn")


def _easyocr_read(gray: np.ndarray) -> str:
    """Run EasyOCR on a grayscale image. Returns concatenated text."""
    if _easyocr_reader is None:
        return ""
    with _easyocr_lock:
        results = _easyocr_reader.readtext(gray, detail=0, paragraph=True)
    return " ".join(results) if results else ""


# ── Super Resolution (GPU bicubic si disponible, FSRCNN CPU como fallback) ────

_sr_local      = threading.local()        # FSRCNN CPU: un modelo por thread
_gpu_sr_device = None                     # torch.device("cuda") si disponible
_sr_sem        = threading.Semaphore(2)   # max 2 FSRCNN simultáneos (OpenCV DNN ya es multithreaded)


def _init_sr(on_log: callable) -> None:
    """Detect GPU SR capability; fall back to FSRCNN CPU."""
    global _gpu_sr_device
    try:
        import torch
        if torch.cuda.is_available():
            _gpu_sr_device = torch.device("cuda")
            on_log(f"SR Tier-2: PyTorch GPU bicubic 4x ({torch.cuda.get_device_name(0)})", "ok")
            return
    except ImportError:
        pass
    on_log("SR Tier-2: FSRCNN x4 CPU (GPU no disponible)", "info")


def _upsample_4x(bgr: np.ndarray) -> np.ndarray:
    """4x upscale for Tier-2 OCR.  GPU bilinear (~1ms) or FSRCNN CPU (~150ms)."""
    if _gpu_sr_device is not None:
        import torch
        import torch.nn.functional as F
        t = (torch.from_numpy(bgr)
               .permute(2, 0, 1).float().unsqueeze(0)
               .to(_gpu_sr_device) / 255.0)
        t_up = F.interpolate(t, scale_factor=4, mode="bicubic", align_corners=False)
        return (t_up.squeeze(0).permute(1, 2, 0)
                  .clamp(0, 1).mul(255).byte()
                  .cpu().numpy())
    # CPU fallback: FSRCNN (thread-local, max 2 concurrent via semaphore)
    if not getattr(_sr_local, "model", None):
        m = cv2.dnn_superres.DnnSuperResImpl_create()
        m.readModel(FSRCNN_PATH)
        m.setModel("fsrcnn", 4)
        _sr_local.model = m
    with _sr_sem:
        return _sr_local.model.upsample(bgr)


_sr_initialized = False


def _setup_sr(on_log: callable) -> None:
    """One-time SR initialization (called from analyze_pdf on first use)."""
    global _sr_initialized
    _init_sr(on_log)
    if _gpu_sr_device is None:
        on_log("Cargando FSRCNN x4 CPU...", "info")
        _upsample_4x(np.zeros((10, 10, 3), dtype=np.uint8))  # warmup
    _sr_initialized = True


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
    pdf_page:   int
    curr:       int | None
    total:      int | None
    method:     str
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

def _render_clip(page: fitz.Page, dpi: int = DPI) -> np.ndarray:
    """Render only the top-right corner of a PDF page. Returns BGR numpy array."""
    rect = page.rect
    clip = fitz.Rect(
        rect.width * CROP_X_START,
        0,
        rect.width,
        rect.height * CROP_Y_END,
    )
    pix = page.get_pixmap(dpi=dpi, clip=clip)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    if pix.n == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    elif pix.n == 3:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    else:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return img


# ── Tesseract-only page processor (runs in thread pool) ─────────────────────

EASYOCR_DPI = 300  # EasyOCR needs higher DPI for small text accuracy


def _process_page(pdf_path: str, page_idx: int) -> _PageRead:
    """
    Render one page clip and run Tesseract OCR (2 tiers).
    Designed to run inside ThreadPoolExecutor — opens its own fitz.Document.
    pytesseract launches tesseract.exe as subprocess → releases GIL → real parallelism.
    """
    pdf_page = page_idx + 1
    doc = fitz.open(pdf_path)
    try:
        bgr = _render_clip(doc[page_idx])
    finally:
        doc.close()

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # Tier 1: Tesseract direct
    text = _tess_ocr(gray)
    c, t = _parse(text)
    if c:
        return _PageRead(pdf_page, c, t, "direct", 1.0)

    # Tier 2: 4x upscale (GPU bicubic ~1ms or FSRCNN CPU ~150ms) + Tesseract
    bgr_sr = _upsample_4x(bgr)
    gray_sr = cv2.cvtColor(bgr_sr, cv2.COLOR_BGR2GRAY)
    text_sr = _tess_ocr(gray_sr)
    c, t = _parse(text_sr)
    if c:
        return _PageRead(pdf_page, c, t, "SR", 1.0)

    return _PageRead(pdf_page, None, None, "failed", 0.0)


# ── EasyOCR GPU batch for failed pages ──────────────────────────────────────

def _easyocr_batch_recover(
    pdf_path: str,
    failed_indices: list[int],
    reads: list[_PageRead],
    on_log: callable,
) -> int:
    """
    Re-render failed pages at 300 DPI and batch-OCR them via EasyOCR GPU.
    Mutates `reads` in-place. Returns number of recovered pages.
    """
    if _easyocr_reader is None or not failed_indices:
        return 0

    on_log(
        f"EasyOCR GPU: procesando {len(failed_indices)} paginas fallidas"
        f" a {EASYOCR_DPI} DPI...",
        "info",
    )

    # Re-render at higher DPI for EasyOCR accuracy
    doc = fitz.open(pdf_path)
    clips = []
    for idx in failed_indices:
        bgr = _render_clip(doc[idx], dpi=EASYOCR_DPI)
        clips.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
    doc.close()

    # Batch OCR on GPU
    with _easyocr_lock:
        batch_results = _easyocr_reader.readtext_batched(
            clips, detail=0, paragraph=True
        )

    recovered = 0
    for i, (idx, result_texts) in enumerate(zip(failed_indices, batch_results)):
        text = " ".join(result_texts) if result_texts else ""
        c, t = _parse(text)
        if c:
            reads[idx] = _PageRead(idx + 1, c, t, "easyocr", 1.0)
            on_log(f"  Pag {idx + 1:>4}: {c}/{t}  [easyocr]", "page_ok")
            recovered += 1

    return recovered


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
    Procesa un PDF con pipeline V3 (paralelo):
      1. PARALLEL_WORKERS threads corren render+Tesseract simultáneamente
         (Tesseract libera el GIL → paralelismo real, ~4x throughput)
      2. FSRCNN+Tesseract como Tier 2 para páginas que fallan
      3. Inference engine post-scan para páginas fallidas
      4. Maquina de estados para construir documentos

    Pause/cancel se verifican entre batches (cada BATCH_SIZE páginas).
    Firma identica a V2 — compatible con server.py sin cambios.
    """
    if not _sr_initialized:
        _setup_sr(on_log)
    _init_easyocr(on_log)

    on_log("Leyendo metadatos...", "info")
    try:
        meta_doc    = fitz.open(pdf_path)
        total_pages = len(meta_doc)
        meta_doc.close()
    except Exception as e:
        on_log(f"Error leyendo PDF: {e}", "error")
        return [], []

    ocr_label = "EasyOCR GPU" if _easyocr_reader is not None else "Tesseract"
    on_log(f"Total paginas: {total_pages}", "info")
    on_log(
        f"Pipeline V4: {ocr_label} + Tesseract x{PARALLEL_WORKERS} threads"
        f" (batch={BATCH_SIZE})",
        "info",
    )

    def _issue(page: int, kind: str, detail: str):
        if on_issue is not None:
            on_issue(page, kind, detail, None)

    # ── Phase 1-2: Parallel render + OCR ──────────────────────────────────
    reads: list[_PageRead] = [None] * total_pages  # pre-allocated, filled in order
    method_tally: dict[str, int] = {}
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as pool:
        for batch_start in range(0, total_pages, BATCH_SIZE):
            # Cancel check between batches
            if cancel_event is not None and cancel_event.is_set():
                on_log("Analisis abortado a peticion del usuario.", "warn")
                return [], []

            # Pause check between batches
            if pause_event is not None:
                pause_event.wait()

            batch_end = min(batch_start + BATCH_SIZE, total_pages)

            # Submit batch to thread pool
            future_to_idx = {
                pool.submit(_process_page, pdf_path, i): i
                for i in range(batch_start, batch_end)
            }

            # Collect batch results in submission order (ordered by page index)
            batch_results: dict[int, _PageRead] = {}
            for future, i in future_to_idx.items():
                try:
                    batch_results[i] = future.result()
                except Exception as e:
                    pdf_page = i + 1
                    on_log(f"  Pag {pdf_page:>4}: error de procesamiento: {e}", "error")
                    batch_results[i] = _PageRead(pdf_page, None, None, "failed", 0.0)

            # Report results in page order and call progress
            for i in range(batch_start, batch_end):
                r = batch_results[i]
                reads[i] = r
                method_tally[r.method] = method_tally.get(r.method, 0) + 1

                pdf_page = i + 1
                if r.curr is not None:
                    on_log(f"  Pag {pdf_page:>4}: {r.curr}/{r.total}  [{r.method}]", "page_ok")
                else:
                    on_log(f"  Pag {pdf_page:>4}: ???  [{r.method}]", "page_warn")

                if on_progress:
                    try:
                        on_progress(pdf_page, total_pages, [x for x in reads[:pdf_page] if x])
                    except TypeError:
                        on_progress(pdf_page, total_pages)

    # ── Phase 2.5: EasyOCR GPU batch for failed pages ────────────────────
    failed_indices = [i for i, r in enumerate(reads) if r is not None and r.method == "failed"]
    if failed_indices:
        recovered = _easyocr_batch_recover(pdf_path, failed_indices, reads, on_log)
        if recovered > 0:
            # Update tallies
            method_tally["easyocr"] = recovered
            method_tally["failed"] = method_tally.get("failed", 0) - recovered

    # ── Phase 3: Inference ────────────────────────────────────────────────
    reads_clean: list[_PageRead] = [r for r in reads if r is not None]
    failed_count = sum(1 for r in reads_clean if r.method == "failed")
    if failed_count > 0:
        on_log(f"Inferencia: procesando {failed_count} paginas fallidas...", "info")
        reads_clean = _infer_missing(reads_clean)
        inferred = sum(1 for r in reads_clean if r.method == "inferred")
        on_log(f"Inferencia: {inferred} paginas recuperadas", "ok")

    # Report inferred pages with low/medium confidence as issues
    for r in reads_clean:
        if r.method == "inferred" and r.confidence <= 0.60:
            conf_label = "MEDIA" if r.confidence >= 0.50 else "BAJA"
            detail = (f"Pag {r.pdf_page}: inferida como {r.curr}/{r.total} "
                      f"(confianza {conf_label}: {r.confidence:.0%})")
            on_log(f"  -> {detail}", "warn")
            _issue(r.pdf_page, f"inferida ({conf_label} {r.confidence:.0%})", detail)

    # ── Phase 4: Build documents from reads ───────────────────────────────
    documents = _build_documents(reads_clean, on_log, _issue)

    # ── Summary ───────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    on_log(f"Metodos OCR: {method_tally}", "info")
    on_log(
        f"Tiempo: {elapsed:.1f}s ({total_pages} paginas, "
        f"{elapsed / total_pages * 1000:.0f}ms/pag promedio, "
        f"{PARALLEL_WORKERS} workers)",
        "info",
    )

    return documents, reads_clean


def _build_documents(
    reads: list[_PageRead],
    on_log: callable,
    on_issue: callable,
) -> list[Document]:
    documents: list[Document]    = []
    current:   Optional[Document] = None
    orphans:   list[int]         = []

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
                on_log(f"  -> huerfana: curr={curr} sin doc activo", "warn")
                on_issue(pdf_page, "huerfana", f"curr={curr} sin doc activo")
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
                    on_log(f"  -> {detail}", "error")
                    on_issue(pdf_page, "secuencia rota", detail)

    if current is not None:
        documents.append(current)

    if orphans:
        on_log(f"Paginas huerfanas: {orphans}", "warn")
    return documents


def re_infer_documents(
    reads: list[_PageRead],
    corrections: dict[int, tuple[int, int]],
    on_log: callable,
    on_issue: callable | None = None,
    exclusions: list[int] = None,
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
            detail = (f"Pag {r.pdf_page}: inferida como {r.curr}/{r.total} "
                      f"(confianza {conf_label}: {r.confidence:.0%})")
            on_log(f"  -> {detail}", "warn")
            _issue(r.pdf_page, f"inferida ({conf_label} {r.confidence:.0%})", detail)

    # 4. Rebuild document logic
    documents = _build_documents(reads, on_log, _issue)

    return documents, reads
