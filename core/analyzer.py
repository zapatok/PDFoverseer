"""
analyzer.py  —  V4 Pipeline Engine (producer-consumer + EasyOCR GPU + SR)
==========================================================================
Contador de documentos en PDFs de charlas (CRS).

Dependencias (venv-cuda):
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
    pip install PyMuPDF opencv-contrib-python fastapi uvicorn[standard] pydantic pytesseract easyocr
    + Tesseract OCR instalado en el sistema

Pipeline V4 — Phase 3 (producer-consumer)
------------------------------------------
  Producers (PARALLEL_WORKERS threads):
    1. PyMuPDF clip rendering + Tesseract OCR en paralelo
    2. Tier 1: Tesseract directo con Otsu threshold
    3. Tier 2: SR x4 + Tesseract (si Tier 1 falla)
    4. Si ambos tiers fallan → push page index a GPU queue

  Consumer (1 dedicated GPU thread):
    5. Recibe page indices en tiempo real via queue.Queue
    6. Re-render a 300 DPI + EasyOCR GPU
    7. Corre concurrentemente mientras Tesseract sigue procesando

  Post-scan:
    8. Constraint Propagation + Bayesian inference para paginas fallidas
    9. Reportar paginas inferidas con confianza < 0.90 como issues

Compatibilidad V2/V3: todas las firmas publicas son identicas.
"""

from __future__ import annotations

import hashlib
import queue
import re
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

# Auto-hash: changes every time this file is modified
_CORE_HASH = hashlib.md5(Path(__file__).read_bytes()).hexdigest()[:8]

import cv2
import numpy as np
import pytesseract
import fitz  # PyMuPDF

# ── Configuración ─────────────────────────────────────────────────────────────

import os as _os

pytesseract.pytesseract.tesseract_cmd = _os.getenv(
    "TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

MODELS_DIR  = Path(__file__).parent.parent / "models"
FSRCNN_PATH = str(MODELS_DIR / "FSRCNN_x4.pb")

DPI              = 150
CROP_X_START     = 0.70   # rightmost 30%
CROP_Y_END       = 0.22   # top 22%
TESS_CONFIG      = "--psm 6 --oem 1"
PARALLEL_WORKERS = 6      # concurrent Tesseract subprocesses
BATCH_SIZE       = 12     # pages per batch (pause/cancel granularity)

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

def _parse(text: str) -> tuple[int | None, int | None]:
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


def _process_page(doc: fitz.Document, page_idx: int) -> _PageRead:
    """
    Render one page clip and run Tesseract OCR (2 tiers).
    Receives a pre-opened fitz.Document from the caller's doc pool (one per thread).
    pytesseract launches tesseract.exe as subprocess → releases GIL → real parallelism.
    """
    pdf_page = page_idx + 1
    bgr = _render_clip(doc[page_idx])

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
    total_counts = Counter(r.total for r in reads if r.total is not None)
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
                    best_total = max(prior, key=prior.get) if prior else 2
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
            best_total = max(prior, key=prior.get) if prior else 2
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
    Procesa un PDF con pipeline V4 (producer-consumer):
      Producers: PARALLEL_WORKERS threads corren render+Tesseract simultáneamente
      Consumer:  1 thread GPU dedicado recibe páginas fallidas via queue en tiempo real
      Post-scan: Inference engine para páginas que ni Tesseract ni EasyOCR resolvieron

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

    has_gpu = _easyocr_reader is not None
    on_log(f"Total paginas: {total_pages}", "info")
    on_log(
        f"Pipeline V4: Tesseract x{PARALLEL_WORKERS} producers"
        f" + {'EasyOCR GPU consumer' if has_gpu else 'no GPU consumer'}"
        f" (batch={BATCH_SIZE})",
        "info",
    )

    def _issue(page: int, kind: str, detail: str):
        if on_issue is not None:
            on_issue(page, kind, detail, None)

    # ── Setup producer-consumer pipeline ──────────────────────────────────
    reads: list[_PageRead] = [None] * total_pages
    method_tally: dict[str, int] = {}
    t0 = time.time()

    # GPU consumer queue + recovery counter
    gpu_queue: queue.Queue[int | None] = queue.Queue()
    gpu_recovered = [0]  # mutable int for thread access

    def _gpu_consumer():
        """Dedicated GPU thread: picks up failed page indices, re-renders
        at 300 DPI, and runs EasyOCR. Runs concurrently with Tesseract producers."""
        if not has_gpu:
            while gpu_queue.get() is not None:
                pass  # drain queue
            return

        doc = fitz.open(pdf_path)
        try:
            while True:
                item = gpu_queue.get()
                if item is None:  # sentinel → stop
                    break
                idx = item
                bgr = _render_clip(doc[idx], dpi=EASYOCR_DPI)
                gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
                with _easyocr_lock:
                    results = _easyocr_reader.readtext(gray, detail=0, paragraph=True)
                text = " ".join(results) if results else ""
                c, t = _parse(text)
                if c:
                    reads[idx] = _PageRead(idx + 1, c, t, "easyocr", 1.0)
                    on_log(f"  Pag {idx + 1:>4}: {c}/{t}  [easyocr-gpu]", "page_ok")
                    gpu_recovered[0] += 1
        finally:
            doc.close()

    gpu_thread = threading.Thread(target=_gpu_consumer, daemon=True, name="gpu-consumer")
    gpu_thread.start()

    # ── Doc pool: one fitz.Document per worker thread ──────────────────────
    # Opening the PDF once per thread (not once per page) avoids 2719 redundant
    # fitz.open() calls for large files. Queue enforces exclusive per-thread access.
    _doc_pool: queue.Queue[fitz.Document] = queue.Queue()
    for _ in range(PARALLEL_WORKERS):
        _doc_pool.put(fitz.open(pdf_path))

    def _submit_page(page_idx: int) -> _PageRead:
        doc = _doc_pool.get()
        try:
            return _process_page(doc, page_idx)
        finally:
            _doc_pool.put(doc)

    # ── Producers: Parallel Tesseract OCR ─────────────────────────────────
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as pool:
        for batch_start in range(0, total_pages, BATCH_SIZE):
            if cancel_event is not None and cancel_event.is_set():
                on_log("Analisis abortado a peticion del usuario.", "warn")
                gpu_queue.put(None)
                gpu_thread.join(timeout=5)
                while not _doc_pool.empty():
                    _doc_pool.get_nowait().close()
                return [], []

            if pause_event is not None:
                pause_event.wait()

            batch_end = min(batch_start + BATCH_SIZE, total_pages)

            future_to_idx = {
                pool.submit(_submit_page, i): i
                for i in range(batch_start, batch_end)
            }

            batch_results: dict[int, _PageRead] = {}
            for future, i in future_to_idx.items():
                try:
                    batch_results[i] = future.result()
                except Exception as e:
                    pdf_page = i + 1
                    on_log(f"  Pag {pdf_page:>4}: error de procesamiento: {e}", "error")
                    batch_results[i] = _PageRead(pdf_page, None, None, "failed", 0.0)

            for i in range(batch_start, batch_end):
                r = batch_results[i]
                reads[i] = r
                method_tally[r.method] = method_tally.get(r.method, 0) + 1

                pdf_page = i + 1
                if r.curr is not None:
                    on_log(f"  Pag {pdf_page:>4}: {r.curr}/{r.total}  [{r.method}]", "page_ok")
                elif r.method == "failed":
                    on_log(f"  Pag {pdf_page:>4}: ???  → GPU queue", "page_warn")
                    gpu_queue.put(i)  # send to GPU consumer immediately
                else:
                    on_log(f"  Pag {pdf_page:>4}: ???  [{r.method}]", "page_warn")

                if on_progress:
                    on_progress(pdf_page, total_pages)

    # ── Close worker doc pool ─────────────────────────────────────────────
    while not _doc_pool.empty():
        _doc_pool.get_nowait().close()

    # ── Signal GPU consumer to stop and wait ──────────────────────────────
    gpu_queue.put(None)
    gpu_thread.join()

    if gpu_recovered[0] > 0:
        method_tally["easyocr"] = gpu_recovered[0]
        method_tally["failed"] = method_tally.get("failed", 0) - gpu_recovered[0]
        on_log(f"EasyOCR GPU consumer: {gpu_recovered[0]} paginas recuperadas en paralelo", "ok")

    # ── Inference for remaining failures ──────────────────────────────────
    reads_clean: list[_PageRead] = [r for r in reads if r is not None]
    failed_count = sum(1 for r in reads_clean if r.method == "failed")
    if failed_count > 0:
        on_log(f"Inferencia: procesando {failed_count} paginas fallidas...", "info")
        reads_clean = _infer_missing(reads_clean)
        inferred = sum(1 for r in reads_clean if r.method == "inferred")
        on_log(f"Inferencia: {inferred} paginas recuperadas", "ok")

    # Report inferred pages with low/medium confidence as issues — grouped by pattern
    from collections import defaultdict as _dd
    inf_groups: dict = _dd(list)
    for r in reads_clean:
        if r.method == "inferred" and r.confidence <= 0.60:
            conf_label = "MEDIA" if r.confidence >= 0.50 else "BAJA"
            key = (r.curr, r.total, conf_label, f"{r.confidence:.0%}")
            inf_groups[key].append(r.pdf_page)
            detail = (f"Pag {r.pdf_page}: inferida como {r.curr}/{r.total} "
                      f"(confianza {conf_label}: {r.confidence:.0%})")
            _issue(r.pdf_page, f"inferida ({conf_label} {r.confidence:.0%})", detail)
    for (curr, total, conf_label, conf_pct), pages in inf_groups.items():
        pages_str = ", ".join(map(str, pages))
        on_log(f"  -> inferida {curr}/{total} {conf_label}({conf_pct}): pags {pages_str}", "warn")

    # ── Phase 4: Build documents from reads ───────────────────────────────
    documents = _build_documents(reads_clean, on_log, _issue)

    # ── Summary ───────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    on_log(f"Metodos OCR: {method_tally}", "info")
    on_log(
        f"Tiempo: {elapsed:.1f}s ({total_pages} paginas, "
        f"{elapsed / total_pages * 1000:.0f}ms/pag promedio, "
        f"{PARALLEL_WORKERS}+1gpu workers)",
        "info",
    )

    # AI-compact summary — scales to any PDF size
    fname = Path(pdf_path).name
    mstr = ",".join(f"{k}:{v}" for k, v in method_tally.items() if v)

    # Document size distribution: {declared_total: count}
    from collections import Counter
    size_dist = Counter(d.declared_total for d in documents)
    dist_str = " ".join(f"{s}p×{c}" for s, c in sorted(size_dist.items()))

    # Bad doc breakdown: seq-broken vs under-count
    docs_ok  = sum(1 for d in documents if d.is_complete)
    docs_bad = len(documents) - docs_ok
    seq_broken  = sum(1 for d in documents if not d.sequence_ok)
    undercount  = sum(1 for d in documents if d.sequence_ok and not d.is_complete)
    bad_str = f"{docs_bad}bad(seq:{seq_broken} under:{undercount})" if docs_bad else "0bad"

    # Inferred confidence buckets
    inf_reads = [r for r in reads_clean if r.method == "inferred"]
    inf_low  = [r for r in inf_reads if r.confidence < 0.50]
    inf_mid  = [r for r in inf_reads if 0.50 <= r.confidence <= 0.60]
    inf_high = [r for r in inf_reads if r.confidence > 0.60]
    # Show first 8 low-conf pages explicitly, rest as count
    low_pages = [f"p{r.pdf_page}={r.curr}/{r.total}({r.confidence:.0%})" for r in inf_low[:8]]
    if len(inf_low) > 8:
        low_pages.append(f"...+{len(inf_low)-8}more")
    low_str = " ".join(low_pages) if low_pages else "none"

    # Failed pages still unresolved
    failed_pp = [r.pdf_page for r in reads_clean if r.method == "failed"]
    fail_str = f"{len(failed_pp)}pp:{','.join(map(str,failed_pp[:10]))}{'...' if len(failed_pp)>10 else ''}" if failed_pp else "none"

    on_log(
        f"[AI:{_CORE_HASH}] {fname} | {total_pages}p {elapsed:.1f}s {elapsed/total_pages*1000:.0f}ms/p | W{PARALLEL_WORKERS}+GPU\n"
        f"OCR: {mstr}\n"
        f"DOCS: {len(documents)}total → {docs_ok}ok+{bad_str} | dist: {dist_str}\n"
        f"INF: {len(inf_reads)}total(low:{len(inf_low)} mid:{len(inf_mid)} hi:{len(inf_high)}) | LOW: {low_str}\n"
        f"FAIL: {fail_str}",
        "ai",
    )

    return documents, reads_clean


def _build_documents(
    reads: list[_PageRead],
    on_log: callable,
    on_issue: callable,
) -> list[Document]:
    documents:  list[Document]        = []
    current:    Document | None       = None
    orphans:    list[int]             = []
    seq_breaks: list[tuple[int,int,int]] = []  # (pdf_page, curr, expected)

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
                on_log(f"  -> pag {pdf_page}: huerfana curr={curr} sin doc activo", "warn")
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
                    detail = f"Pag {pdf_page}: secuencia rota curr={curr}/expected={expected}"
                    on_issue(pdf_page, "secuencia rota", detail)
                    seq_breaks.append((pdf_page, curr, expected))

    if current is not None:
        documents.append(current)

    # Emit sequence breaks grouped by (curr, expected)
    if seq_breaks:
        from collections import defaultdict as _dd
        grp: dict = _dd(list)
        for pp, c, e in seq_breaks:
            grp[(c, e)].append(pp)
        for (c, e), pages in grp.items():
            pages_str = ", ".join(map(str, pages))
            on_log(f"  -> secuencia rota curr={c}/expected={e}: pags {pages_str}", "error")

    if orphans:
        on_log(f"Paginas huerfanas: {orphans}", "warn")
    return documents


def re_infer_documents(
    reads: list[_PageRead],
    corrections: dict[int, tuple[int, int]],
    on_log: callable,
    on_issue: callable | None = None,
    exclusions: list[int] | None = None,
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
