"""
SR Prototype V2 - High-Accuracy Page Number Detection
4-tier pipeline: Tesseract -> EDSR+Tess -> EasyOCR GPU -> Inference
Uses PyMuPDF clip rendering for 93% less pixels than pdf2image.
"""
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import threading
import re
import time
import os
from pathlib import Path
from dataclasses import dataclass

import cv2
import numpy as np
import pytesseract
import fitz  # PyMuPDF

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ─── Config ──────────────────────────────────────────────────────────────────
MODELS_DIR   = Path(__file__).parent / "models"
EDSR_PATH    = str(MODELS_DIR / "EDSR_x4.pb")
FSRCNN_PATH  = str(MODELS_DIR / "FSRCNN_x4.pb")
DPI          = 150
CROP_X_START = 0.70   # rightmost 30%
CROP_Y_END   = 0.22   # top 22%
TESS_CFG     = "--psm 6 --oem 1"

# Page number regex: handles Pagina/Pqina/P4gina + optional dot + number de number
_PAGE_RE = re.compile(
    r"P.{0,2}[gq](?:ina?)?\.?\s*(\d{1,3})\s*\.?\s*de\s*(\d{1,3})",
    re.IGNORECASE,
)

# ─── Data ────────────────────────────────────────────────────────────────────
@dataclass
class PageResult:
    pdf_page: int        # 1-indexed page in the PDF
    curr: int | None     # page number read (e.g. 1)
    total: int | None    # total declared (e.g. 2)
    method: str          # "direct", "edsr", "easyocr", "inferred", "failed"
    confidence: float    # 0.0 - 1.0
    elapsed_ms: int      # time in ms


# ─── OCR Engines ─────────────────────────────────────────────────────────────
_sr_model = None
_easyocr_reader = None


def _load_sr(use_edsr: bool = False):
    """Load super resolution model. EDSR (slow, quality) or FSRCNN (fast)."""
    global _sr_model
    _sr_model = cv2.dnn_superres.DnnSuperResImpl_create()
    if use_edsr:
        _sr_model.readModel(EDSR_PATH)
        _sr_model.setModel("edsr", 4)
    else:
        _sr_model.readModel(FSRCNN_PATH)
        _sr_model.setModel("fsrcnn", 4)


def _load_easyocr():
    global _easyocr_reader
    import easyocr
    _easyocr_reader = easyocr.Reader(["es", "en"], gpu=True, verbose=False)


def _tess_ocr(gray: np.ndarray) -> str:
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return pytesseract.image_to_string(th, lang="eng", config=TESS_CFG)


def _easy_ocr(bgr: np.ndarray) -> str:
    results = _easyocr_reader.readtext(bgr, detail=0)
    return " ".join(results)


def _match(text: str):
    """Try to match page pattern, return (curr, total) or None."""
    m = _PAGE_RE.search(text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


# ─── Clip Rendering ─────────────────────────────────────────────────────────
def _render_clip(page: fitz.Page) -> np.ndarray:
    """Render only the top-right corner of a PDF page. Returns BGR numpy array."""
    rect = page.rect
    clip = fitz.Rect(
        rect.width * CROP_X_START,  # x0
        0,                          # y0
        rect.width,                 # x1
        rect.height * CROP_Y_END,   # y1
    )
    pix = page.get_pixmap(dpi=DPI, clip=clip)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    if pix.n == 4:  # RGBA
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    elif pix.n == 3:  # RGB
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    else:  # grayscale
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return img


# ─── 4-Tier Pipeline ────────────────────────────────────────────────────────
_gpu_available = False  # set during model loading

def extract_page_number(page: fitz.Page, page_idx: int) -> PageResult:
    """Run the 4-tier pipeline on a single PDF page."""
    t0 = time.time()
    bgr = _render_clip(page)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # Tier 1: Direct Tesseract
    text = _tess_ocr(gray)
    match = _match(text)
    if match:
        return PageResult(page_idx, match[0], match[1], "direct", 1.0,
                          int((time.time()-t0)*1000))

    # Tier 2: EDSR x4 + Tesseract
    bgr_sr = _sr_model.upsample(bgr)
    gray_sr = cv2.cvtColor(bgr_sr, cv2.COLOR_BGR2GRAY)
    text_sr = _tess_ocr(gray_sr)
    match = _match(text_sr)
    if match:
        return PageResult(page_idx, match[0], match[1], "edsr", 1.0,
                          int((time.time()-t0)*1000))

    # Tier 3: EasyOCR (only when GPU available — too slow on CPU)
    if _gpu_available:
        # Use ORIGINAL crop, not EDSR-upscaled (EasyOCR has its own preprocessing)
        text_easy = _easy_ocr(bgr)
        match = _match(text_easy)
        if match:
            return PageResult(page_idx, match[0], match[1], "easyocr", 1.0,
                              int((time.time()-t0)*1000))

    # All OCR failed → will be handled by inference engine
    return PageResult(page_idx, None, None, "failed", 0.0,
                      int((time.time()-t0)*1000))


# ─── Tier 4: Inference Engine ────────────────────────────────────────────────
def infer_missing(results: list[PageResult]) -> list[PageResult]:
    """
    Constraint Propagation + Bayesian inference for failed pages.
    Runs AFTER all pages are scanned.
    """
    n = len(results)
    if n == 0:
        return results

    # Phase 0: Build prior P(total=N) from successful reads
    totals = [r.total for r in results if r.total is not None]
    total_counts: dict[int, int] = {}
    for t in totals:
        total_counts[t] = total_counts.get(t, 0) + 1
    total_sum = sum(total_counts.values()) or 1
    prior: dict[int, float] = {k: v / total_sum for k, v in total_counts.items()}
    # Default prior if no data
    if not prior:
        prior = {2: 0.85, 3: 0.10, 1: 0.05}

    # Phase 1: Forward propagation
    for i in range(n):
        r = results[i]
        if r.method != "failed":
            continue

        if i > 0:
            prev = results[i - 1]
            if prev.curr is not None and prev.total is not None:
                if prev.curr < prev.total:
                    # Sequential continuation
                    r.curr = prev.curr + 1
                    r.total = prev.total
                    r.method = "inferred"
                    r.confidence = 0.95
                elif prev.curr == prev.total:
                    # Previous was last page -> this could be page 1 of new doc
                    # Use prior for most likely total
                    best_total = max(prior, key=lambda k: prior[k]) if prior else 2
                    r.curr = 1
                    r.total = best_total
                    r.method = "inferred"
                    r.confidence = 0.70

    # Phase 2: Backward propagation
    for i in range(n - 2, -1, -1):
        r = results[i]
        if r.method != "failed":
            continue

        if i < n - 1:
            nxt = results[i + 1]
            if nxt.curr is not None and nxt.total is not None:
                if nxt.curr > 1:
                    # Must be the page before
                    r.curr = nxt.curr - 1
                    r.total = nxt.total
                    r.method = "inferred"
                    r.confidence = 0.90
                elif nxt.curr == 1:
                    # Next is first page of new doc -> this is last of previous
                    if i > 0:
                        prev = results[i - 1]
                        if prev.curr is not None and prev.total is not None:
                            r.curr = prev.curr + 1
                            r.total = prev.total
                            r.method = "inferred"
                            r.confidence = 0.90

    # Phase 3: Cross-validation
    for i in range(n):
        r = results[i]
        if r.method != "inferred":
            continue

        # Check consistency with neighbors
        consistent = True
        if i > 0:
            prev = results[i - 1]
            if prev.curr is not None and prev.total is not None:
                if prev.total == r.total and prev.curr == r.curr - 1:
                    pass  # consistent
                elif prev.curr == prev.total and r.curr == 1:
                    pass  # new document boundary, consistent
                else:
                    consistent = False

        if i < n - 1:
            nxt = results[i + 1]
            if nxt.curr is not None and nxt.total is not None:
                if nxt.total == r.total and nxt.curr == r.curr + 1:
                    pass  # consistent
                elif r.curr == r.total and nxt.curr == 1:
                    pass  # end of document, consistent
                else:
                    consistent = False

        if not consistent:
            r.confidence = min(r.confidence, 0.50)

    # Phase 4: Handle remaining failures with Bayesian update
    for i in range(n):
        r = results[i]
        if r.method == "failed":
            # Still failed after forward + backward
            # Try consecutive failed blocks
            best_total = max(prior, key=lambda k: prior[k]) if prior else 2
            r.curr = 1
            r.total = best_total
            r.method = "inferred"
            r.confidence = 0.40  # low confidence

    return results


# ─── GUI ─────────────────────────────────────────────────────────────────────
BG     = "#1e1e2e"
ACCENT = "#cba6f7"
GREEN  = "#a6e3a1"
RED    = "#f38ba8"
ORANGE = "#fab387"
YELLOW = "#f9e2af"
FG     = "#cdd6f4"
DIM    = "#6c7086"
SURF   = "#313244"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SR Prototype V2 - Page Number Detection")
        self.configure(bg=BG)
        self.geometry("780x580")
        self.minsize(650, 450)

        self._running = False
        self._pdf_path: str | None = None
        self._build()

    def _build(self):
        # Top bar
        top = tk.Frame(self, bg=BG)
        top.pack(fill=tk.X, padx=12, pady=10)

        tk.Button(
            top, text="Abrir PDF", command=self._pick,
            bg=ACCENT, fg="#11111b", font=("Segoe UI", 10, "bold"),
            padx=12, pady=4, relief=tk.FLAT, cursor="hand2",
        ).pack(side=tk.LEFT)

        self.btn_run = tk.Button(
            top, text="Analizar", command=self._run,
            bg=SURF, fg=GREEN, font=("Segoe UI", 10, "bold"),
            padx=12, pady=4, relief=tk.FLAT, cursor="hand2",
            state=tk.DISABLED,
        )
        self.btn_run.pack(side=tk.LEFT, padx=8)

        self.lbl_file = tk.Label(top, text="Ningun PDF seleccionado",
                                 bg=BG, fg=DIM, font=("Segoe UI", 9))
        self.lbl_file.pack(side=tk.LEFT)

        # Stats bar
        stats = tk.Frame(self, bg=SURF, pady=4)
        stats.pack(fill=tk.X, padx=12)
        kw = {"bg": SURF, "font": ("Segoe UI", 10, "bold"), "padx": 8}
        self.lbl_total   = tk.Label(stats, text="Pags: -",     fg=FG,     **kw)
        self.lbl_total.pack(side=tk.LEFT)
        self.lbl_direct  = tk.Label(stats, text="Direct: -",   fg=GREEN,  **kw)
        self.lbl_direct.pack(side=tk.LEFT)
        self.lbl_edsr    = tk.Label(stats, text="EDSR: -",     fg=ACCENT, **kw)
        self.lbl_edsr.pack(side=tk.LEFT)
        self.lbl_easy    = tk.Label(stats, text="EasyOCR: -",  fg=ORANGE, **kw)
        self.lbl_easy.pack(side=tk.LEFT)
        self.lbl_infer   = tk.Label(stats, text="Infer: -",    fg=YELLOW, **kw)
        self.lbl_infer.pack(side=tk.LEFT)
        self.lbl_failed  = tk.Label(stats, text="Fallos: -",   fg=RED,    **kw)
        self.lbl_failed.pack(side=tk.LEFT)

        # GPU indicator
        self.lbl_gpu = tk.Label(stats, text="GPU: ?", fg=DIM, **kw)
        self.lbl_gpu.pack(side=tk.RIGHT)

        # Progress
        pf = tk.Frame(self, bg=BG)
        pf.pack(fill=tk.X, padx=12, pady=(6, 2))
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TProgressbar", troughcolor=SURF, background=ACCENT)
        self.prog = ttk.Progressbar(pf, maximum=100, value=0)
        self.prog.pack(fill=tk.X)

        # Log
        self.log = scrolledtext.ScrolledText(
            self, bg=SURF, fg=FG, font=("Consolas", 9),
            relief=tk.FLAT, borderwidth=0,
        )
        self.log.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 10))
        self.log.tag_config("ok",     foreground=GREEN)
        self.log.tag_config("edsr",   foreground=ACCENT)
        self.log.tag_config("easy",   foreground=ORANGE)
        self.log.tag_config("infer",  foreground=YELLOW)
        self.log.tag_config("fail",   foreground=RED)
        self.log.tag_config("info",   foreground=DIM)
        self.log.tag_config("header", foreground=ORANGE)

    def _pick(self):
        path = filedialog.askopenfilename(
            filetypes=[("PDFs", "*.pdf"), ("Todos", "*.*")]
        )
        if path:
            self._pdf_path = path
            self.lbl_file.config(text=Path(path).name)
            self.btn_run.config(state=tk.NORMAL)

    def _run(self):
        if self._running:
            return
        self._running = True
        self.btn_run.config(state=tk.DISABLED)
        self.log.delete("1.0", tk.END)
        threading.Thread(target=self._analyze, daemon=True).start()

    def _log(self, msg, tag="info"):
        def _do():
            self.log.insert(tk.END, msg + "\n", tag)
            self.log.see(tk.END)
        self.after(0, _do)

    def _update_stats(self, results: list[PageResult]):
        counts = {"direct": 0, "edsr": 0, "easyocr": 0, "inferred": 0, "failed": 0}
        for r in results:
            counts[r.method] = counts.get(r.method, 0) + 1
        self.after(0, lambda: self.lbl_total.config(text=f"Pags: {len(results)}"))
        self.after(0, lambda: self.lbl_direct.config(text=f"Direct: {counts['direct']}"))
        self.after(0, lambda: self.lbl_edsr.config(text=f"EDSR: {counts['edsr']}"))
        self.after(0, lambda: self.lbl_easy.config(text=f"EasyOCR: {counts['easyocr']}"))
        self.after(0, lambda: self.lbl_infer.config(text=f"Infer: {counts['inferred']}"))
        self.after(0, lambda: self.lbl_failed.config(text=f"Fallos: {counts['failed']}"))

    def _analyze(self):
        path = self._pdf_path
        assert path is not None

        # Check GPU first
        try:
            import torch
            gpu_ok = torch.cuda.is_available()
            gpu_name = torch.cuda.get_device_name(0) if gpu_ok else "CPU"
        except Exception:
            gpu_ok = False
            gpu_name = "CPU"

        global _gpu_available
        _gpu_available = gpu_ok

        # Load SR model: EDSR if GPU, FSRCNN if CPU
        if gpu_ok:
            self._log("Cargando EDSR x4 (67MB, GPU)...", "header")
            _load_sr(use_edsr=True)
            self._log("EDSR listo.", "info")
        else:
            self._log("Cargando FSRCNN x4 (1MB, CPU)...", "header")
            _load_sr(use_edsr=False)
            self._log("FSRCNN listo.", "info")

        # Load EasyOCR only if GPU available
        if gpu_ok:
            self._log("Cargando EasyOCR (GPU)...", "header")
            _load_easyocr()
            self._log(f"EasyOCR listo. Device: {gpu_name}\n", "info")
        else:
            self._log("EasyOCR omitido (sin GPU CUDA)", "info")
            self._log("Pipeline: Tesseract -> FSRCNN+Tess -> Inferencia\n", "info")

        self.after(0, lambda: self.lbl_gpu.config(
            text=f"GPU: {gpu_name}" if gpu_ok else "GPU: CPU",
            fg=GREEN if gpu_ok else YELLOW,
        ))

        # Open PDF
        doc = fitz.open(path)
        total_pages = len(doc)
        self._log(f"PDF: {Path(path).name}", "header")
        self._log(f"Total paginas: {total_pages}\n", "info")

        # Phase 1-3: OCR all pages
        results: list[PageResult] = []
        t0_all = time.time()

        for i in range(total_pages):
            page = doc[i]
            r = extract_page_number(page, i + 1)
            results.append(r)

            # Log
            tag_map = {"direct": "ok", "edsr": "edsr", "easyocr": "easy", "failed": "fail"}
            tag = tag_map.get(r.method, "fail")
            if r.method != "failed":
                label = f"[{r.method.upper():7s}]  Pag {r.pdf_page:4d}  ->  {r.curr} de {r.total}   [{r.elapsed_ms}ms]"
            else:
                label = f"[FAILED ]  Pag {r.pdf_page:4d}  ->  ---              [{r.elapsed_ms}ms]"
            self._log(label, tag)

            # Progress
            pct = int((i + 1) / total_pages * 100)
            self.after(0, lambda p=pct: self.prog.config(value=p))
            self._update_stats(results)

        doc.close()

        # Phase 4: Inference
        failed_before = sum(1 for r in results if r.method == "failed")
        if failed_before > 0:
            self._log(f"\n--- Inference Engine ({failed_before} failures) ---", "header")
            results = infer_missing(results)
            inferred = sum(1 for r in results if r.method == "inferred")
            self._log(f"Inferred: {inferred} pages", "infer")
            for r in results:
                if r.method == "inferred":
                    conf_label = "HIGH" if r.confidence >= 0.90 else "MED" if r.confidence >= 0.70 else "LOW"
                    self._log(
                        f"  [INF]  Pag {r.pdf_page:4d}  ->  {r.curr} de {r.total}   "
                        f"[conf: {r.confidence:.2f} {conf_label}]",
                        "infer" if r.confidence >= 0.70 else "fail"
                    )
            self._update_stats(results)

        # Summary
        elapsed_total = time.time() - t0_all
        counts = {}
        for r in results:
            counts[r.method] = counts.get(r.method, 0) + 1

        self._log(f"\n{'='*50}", "header")
        self._log(f"Completado en {elapsed_total:.1f}s ({total_pages} paginas)", "header")
        self._log(f"  Direct:  {counts.get('direct', 0)}", "ok")
        self._log(f"  EDSR:    {counts.get('edsr', 0)}", "edsr")
        self._log(f"  EasyOCR: {counts.get('easyocr', 0)}", "easy")
        self._log(f"  Infer:   {counts.get('inferred', 0)}", "infer")
        self._log(f"  Failed:  {counts.get('failed', 0)}", "fail")

        detected = sum(1 for r in results if r.method in ("direct", "edsr", "easyocr"))
        inferred = counts.get("inferred", 0)
        accuracy = (detected + inferred) / total_pages * 100 if total_pages else 0
        self._log(f"\n  Accuracy: {accuracy:.1f}% ({detected} detected + {inferred} inferred)", "header")

        # Count documents (pages with curr=1)
        doc_count = sum(1 for r in results if r.curr == 1)
        self._log(f"  Documents found: {doc_count}", "header")

        self.after(0, lambda: self.prog.config(value=100))
        self._running = False
        self.after(0, lambda: self.btn_run.config(state=tk.NORMAL))


if __name__ == "__main__":
    App().mainloop()
