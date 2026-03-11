"""
SR OCR Tester - GUI simple para probar Super Resolution + Tesseract
en un PDF completo. Muestra el resultado pagina a pagina con conteo de
numeros detectados vs inferidos.
"""
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import threading
import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ─── Configuracion ───────────────────────────────────────────────────────────
MODEL_PATH   = str(Path(__file__).parent / "models" / "FSRCNN_x4.pb")
DPI          = 150
CROP_X_START = 0.70   # 30% derecho de la pagina
CROP_Y_END   = 0.22   # 22% superior
TESS_CFG     = "--psm 6 --oem 1"

# ─── Regex ─────────────────────────────────────────────────────────────────
# Handles: 'Pagina 1 de 2', 'Pagina 1de 2', 'Pagina 1.de 2', 'Pqina 1 de 2'
_PAGE_RE = re.compile(
    r"P.{0,2}[gq](?:ina?)?\.?\s*(\d{1,3})\s*\.?\s*de\s*(\d{1,3})",
    re.IGNORECASE,
)

# ─── Cargar SR una sola vez ──────────────────────────────────────────────────
_sr = None

def load_model():
    global _sr
    _sr = cv2.dnn_superres.DnnSuperResImpl_create()
    _sr.readModel(MODEL_PATH)
    _sr.setModel("fsrcnn", 4)


def ocr_gray(gray: np.ndarray) -> str:
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return pytesseract.image_to_string(th, lang="eng", config=TESS_CFG)


def extract_number(pil_img: Image.Image):
    """Retorna (curr, total, method) usando SR->Tesseract."""
    w, h = pil_img.size
    bgr  = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    crp  = bgr[0:int(h * CROP_Y_END), int(w * CROP_X_START):w]

    # Paso 1: Tesseract directo (rapido, sin SR)
    gray  = cv2.cvtColor(crp, cv2.COLOR_BGR2GRAY)
    text  = ocr_gray(gray)
    m = _PAGE_RE.search(text)
    if m:
        return int(m.group(1)), int(m.group(2)), "direct"

    # Paso 2: FSRCNN x4 + Tesseract
    bgr_sr = _sr.upsample(crp)
    gray_sr = cv2.cvtColor(bgr_sr, cv2.COLOR_BGR2GRAY)
    text_sr = ocr_gray(gray_sr)
    m = _PAGE_RE.search(text_sr)
    if m:
        return int(m.group(1)), int(m.group(2)), "fsrcnn"

    return None, None, "failed"


# ─── GUI ─────────────────────────────────────────────────────────────────────
BG     = "#1e1e2e"
ACCENT = "#cba6f7"
GREEN  = "#a6e3a1"
RED    = "#f38ba8"
ORANGE = "#fab387"
FG     = "#cdd6f4"
DIM    = "#6c7086"
SURF   = "#313244"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SR OCR Tester")
        self.configure(bg=BG)
        self.geometry("720x520")
        self.minsize(600, 400)

        self._running = False
        self._pdf_path: str | None = None

        self._build()

    def _build(self):
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
        kw = {"bg": SURF, "font": ("Segoe UI", 11, "bold"), "padx": 10}
        self.lbl_total   = tk.Label(stats, text="Paginas: -",   fg=FG,     **kw)
        self.lbl_total.pack(side=tk.LEFT)
        self.lbl_direct  = tk.Label(stats, text="Directo: -",   fg=GREEN,  **kw)
        self.lbl_direct.pack(side=tk.LEFT)
        self.lbl_sr      = tk.Label(stats, text="Con SR: -",    fg=ACCENT, **kw)
        self.lbl_sr.pack(side=tk.LEFT)
        self.lbl_failed  = tk.Label(stats, text="Fallados: -",  fg=RED,    **kw)
        self.lbl_failed.pack(side=tk.LEFT)

        # Progress
        prog = tk.Frame(self, bg=BG)
        prog.pack(fill=tk.X, padx=12, pady=(6, 2))
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TProgressbar", troughcolor=SURF, background=ACCENT)
        self.prog = ttk.Progressbar(prog, maximum=100, value=0, style="TProgressbar")
        self.prog.pack(fill=tk.X)

        # Log
        self.log = scrolledtext.ScrolledText(
            self, bg=SURF, fg=FG, font=("Consolas", 9),
            relief=tk.FLAT, borderwidth=0,
        )
        self.log.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 10))
        self.log.tag_config("ok",     foreground=GREEN)
        self.log.tag_config("sr",     foreground=ACCENT)
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

    def _analyze(self):
        path = self._pdf_path
        assert path is not None
        self._log("Cargando modelo FSRCNN...", "header")
        load_model()
        self._log("Modelo listo.\n", "info")

        try:
            info  = pdfinfo_from_path(path)
            total_pages = int(info["Pages"])
        except Exception:
            total_pages = None

        self._log(f"PDF: {Path(path).name}", "header")
        if total_pages:
            self._log(f"Total paginas: {total_pages}\n", "info")

        direct_n = 0
        sr_n     = 0
        failed_n = 0
        page_idx = 0
        t0_all   = time.time()

        CHUNK = 20
        chunk_start = 1
        while True:
            chunk_end = chunk_start + CHUNK - 1
            if total_pages and chunk_end > total_pages:
                chunk_end = total_pages

            try:
                pages = convert_from_path(
                    path, dpi=DPI,
                    first_page=chunk_start, last_page=chunk_end,
                )
            except Exception as e:
                self._log(f"Error convirtiendo paginas {chunk_start}-{chunk_end}: {e}", "fail")
                break

            if not pages:
                break

            for img in pages:
                page_idx += 1
                t0 = time.time()
                curr, tot, method = extract_number(img)
                elapsed = int((time.time()-t0)*1000)

                if method == "direct":
                    direct_n += 1
                    tag   = "ok"
                    label = f"[OK]  Pag {page_idx:4d}  ->  {curr} de {tot}   [directo  {elapsed}ms]"
                elif method == "fsrcnn":
                    sr_n += 1
                    tag   = "sr"
                    label = f"[SR]  Pag {page_idx:4d}  ->  {curr} de {tot}   [SR+Tess  {elapsed}ms]"
                else:
                    failed_n += 1
                    tag   = "fail"
                    label = f"[XX]  Pag {page_idx:4d}  ->  fallo              [{elapsed}ms]"

                self._log(label, tag)

                if total_pages:
                    pct = int(page_idx / total_pages * 100)
                    self.after(0, lambda p=pct: self.prog.config(value=p))

                self.after(0, lambda v=f"Paginas: {page_idx}":   self.lbl_total.config(text=v))
                self.after(0, lambda v=f"Directo: {direct_n}":  self.lbl_direct.config(text=v))
                self.after(0, lambda v=f"Con SR: {sr_n}":       self.lbl_sr.config(text=v))
                self.after(0, lambda v=f"Fallados: {failed_n}": self.lbl_failed.config(text=v))

            if total_pages and chunk_end >= total_pages:
                break
            if len(pages) < CHUNK:
                break
            chunk_start = chunk_end + 1

        elapsed_total = time.time() - t0_all
        self._log(f"\n-----------------------------------", "header")
        self._log(
            f"Completado en {elapsed_total:.1f}s -- "
            f"Directo: {direct_n} | SR: {sr_n} | Fallados: {failed_n}", "header"
        )
        self.after(0, lambda: self.prog.config(value=100))
        self._running = False
        self.after(0, lambda: self.btn_run.config(state=tk.NORMAL))


if __name__ == "__main__":
    App().mainloop()
