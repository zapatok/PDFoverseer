"""
PDFoverseer  —  Supervisor de PDFs en carpeta
==============================================
Selecciona una carpeta (o un PDF individual) y analiza todos los PDFs
encontrados en orden, usando la lógica core de pdfcount.py (OCR + state
machine).  Permite pausar / reanudar el proceso, visualizar las páginas
problemáticas y consultar un historial de ejecuciones anteriores.
"""

from __future__ import annotations

import os
import subprocess
import threading
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional, Any

from PIL import Image, ImageTk

from core.analyzer import Document, analyze_pdf, re_infer_documents
from history import HistoryEntry, PDFResult, add_entry, clear_history, load_history

# ── Colores y estilos ─────────────────────────────────────────────────────────

BG          = "#1e1e2e"
BG_PANEL    = "#282840"
BG_LOG      = "#1a1a2e"
FG          = "#cdd6f4"
ACCENT      = "#89b4fa"
ACCENT_DARK = "#5b8cd4"
GREEN       = "#a6e3a1"
RED         = "#f38ba8"
YELLOW      = "#f9e2af"
ORANGE      = "#fab387"
DIM         = "#6c7086"
SURFACE     = "#313244"

_LOG_COLORS = {
    "info":      ACCENT,
    "warn":      ORANGE,
    "error":     RED,
    "ok":        GREEN,
    "section":   FG,
    "page_ok":   DIM,
    "page_warn": YELLOW,
    "file_hdr":  ACCENT,
}

_STATUS = {
    "pending":    ("⏳", DIM),
    "processing": ("🔍", ACCENT),
    "done":       ("✅", GREEN),
    "error":      ("❌", RED),
    "paused":     ("⏸", YELLOW),
    "skipped":    ("⏭", YELLOW),
}


# ── Issue data ────────────────────────────────────────────────────────────────

@dataclass
class PageIssue:
    pdf_path:   Path
    pdf_page:   int
    issue_type: str
    detail:     str
    pil_image:  Image.Image | None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_pdfs(folder: str) -> list[Path]:
    result = []
    for root, _dirs, files in os.walk(folder):
        for f in sorted(files):
            if f.lower().endswith(".pdf"):
                result.append(Path(root) / f)
    return result


def _open_in_explorer(path: Path):
    try:
        subprocess.Popen(f'explorer /select,"{path}"')
    except Exception:
        pass


# ── Aplicación ────────────────────────────────────────────────────────────────

class PDFoverseerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PDFoverseer V2")
        self.root.geometry("1060x720")
        self.root.minsize(820, 580)
        self.root.configure(bg=BG)

        # State
        self.pdf_list: list[Path] = []
        self.issues: list[PageIssue] = []
        self._selected_issue_idx = -1

        self.running = False
        self.pause_event = threading.Event()
        self.pause_event.set()  # Initial state is unpaused
        self.cancel_event = threading.Event()
        self._skip_current = False
        self._stop_requested = False
        
        self._pdf_reads: dict[str, list[Any]] = {} 
        self._user_corrections: dict[str, dict[int, tuple[int, int]]] = {}
        # Source tracking (for history)
        self._current_source: str = ""
        self._current_source_name: str = ""
        self._current_is_folder: bool = False

        # Session state
        self._session_sources: list[str] = []
        self._session_pdf_count: int = 0
        # Global accumulators
        self.total_docs = 0
        self.total_complete = 0
        self.total_incomplete = 0
        self.total_inferred = 0

        # Per-PDF results (for history)
        self._pdf_results: list[PDFResult] = []

        # Issues store
        self._current_preview_tk: Optional[ImageTk.PhotoImage] = None
        self._current_preview_pil: Optional[Image.Image] = None
        self._adjustments: dict[int, int] = {}   # issue_idx → -1
        self._zoom_level: float = 1.0  # 1.0 = fit to canvas
        self._row_to_issue: dict[int, int] = {}  # listbox_row → issue_idx
        self._show_seq_issues: bool = False  # hide "secuencia rota" by default


        # Build all views
        self._build_shared_top()
        self._build_main_view()
        self._build_detail_view()
        self._build_history_view()

        self._show_main()

    # ══════════════════════════════════════════════════════════════════════════
    # ── Shared top bar (always visible) ───────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════════════

    def _build_shared_top(self):
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill=tk.X, padx=14, pady=(12, 4))

        self.btn_folder = tk.Button(
            top, text="📁  Seleccionar Carpeta", command=self._pick_folder,
            bg=ACCENT, fg="#11111b", font=("Segoe UI", 10, "bold"),
            activebackground=ACCENT_DARK, activeforeground="#11111b",
            padx=14, pady=5, relief=tk.FLAT, cursor="hand2",
        )
        self.btn_folder.pack(side=tk.LEFT)

        self.btn_file = tk.Button(
            top, text="📄  Seleccionar PDF", command=self._pick_file,
            bg=SURFACE, fg=FG, font=("Segoe UI", 10, "bold"),
            activebackground="#45475a", activeforeground=FG,
            padx=14, pady=5, relief=tk.FLAT, cursor="hand2",
        )
        self.btn_file.pack(side=tk.LEFT, padx=(6, 0))

        # Remove Mode combobox, Pause button. Keep Stop and Skip buttons.
        # We will build a new compact control bar.
        control_frame = tk.Frame(top, bg=SURFACE, padx=8, pady=4, highlightbackground="#45475a", highlightthickness=1)
        control_frame.pack(side=tk.LEFT, padx=(16, 0))

        self.btn_stop = tk.Button(
            control_frame, text="⏹  Detener", command=self._stop_processing,
            bg=SURFACE, fg=RED, font=("Segoe UI", 10, "bold"),
            activebackground="#45475a", activeforeground=RED,
            padx=10, pady=2, relief=tk.FLAT, cursor="hand2",
            state=tk.DISABLED,
        )
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_skip = tk.Button(
            control_frame, text="⏭  Saltar PDF", command=self._skip_file,
            bg=SURFACE, fg=ORANGE, font=("Segoe UI", 10, "bold"),
            activebackground="#45475a", activeforeground=ORANGE,
            padx=10, pady=2, relief=tk.FLAT, cursor="hand2",
            state=tk.DISABLED,
        )
        self.btn_skip.pack(side=tk.LEFT)

        self.btn_issues = tk.Button(
            top, text="⚠  Ver Problemas (0)", command=self._show_detail,
            bg=SURFACE, fg=DIM, font=("Segoe UI", 10, "bold"),
            activebackground="#45475a", activeforeground=FG,
            padx=14, pady=5, relief=tk.FLAT, cursor="hand2",
            state=tk.DISABLED,
        )
        self.btn_issues.pack(side=tk.LEFT, padx=(16, 0))

        # ---- Right side buttons ----
        self.btn_save_session = tk.Button(
            top, text="💾  Guardar", command=self._save_session,
            bg=SURFACE, fg=GREEN, font=("Segoe UI", 10, "bold"),
            activebackground="#45475a", activeforeground=GREEN,
            padx=10, pady=5, relief=tk.FLAT, cursor="hand2",
        )
        self.btn_save_session.pack(side=tk.RIGHT, padx=(4, 0))

        self.btn_load_session = tk.Button(
            top, text="📂  Cargar", command=self._load_session,
            bg=SURFACE, fg=FG, font=("Segoe UI", 10, "bold"),
            activebackground="#45475a", activeforeground=FG,
            padx=10, pady=5, relief=tk.FLAT, cursor="hand2",
        )
        self.btn_load_session.pack(side=tk.RIGHT, padx=(4, 0))

        self.btn_new_session = tk.Button(
            top, text="🔄  Nueva Sesión", command=self._new_session,
            bg=SURFACE, fg=RED, font=("Segoe UI", 10, "bold"),
            activebackground="#45475a", activeforeground=RED,
            padx=10, pady=5, relief=tk.FLAT, cursor="hand2",
        )
        self.btn_new_session.pack(side=tk.RIGHT)

        self.lbl_folder = tk.Label(
            top, text="Ningún origen seleccionado",
            fg=DIM, bg=BG, font=("Segoe UI", 9),
        )
        self.lbl_folder.pack(side=tk.LEFT, padx=12)

        # ── Summary bar ──────────────────────────────────────────────────────
        summary = tk.Frame(self.root, bg=BG_PANEL, highlightbackground=SURFACE,
                           highlightthickness=1)
        summary.pack(fill=tk.X, padx=14, pady=6)

        lbl_kw = dict(bg=BG_PANEL, font=("Segoe UI", 12, "bold"), pady=6, padx=14)
        self.lbl_total = tk.Label(summary, text="Documentos: –", fg=FG, **lbl_kw)
        self.lbl_total.pack(side=tk.LEFT)
        self.lbl_ok = tk.Label(summary, text="Completos: –", fg=GREEN, **lbl_kw)
        self.lbl_ok.pack(side=tk.LEFT)
        self.lbl_inc = tk.Label(summary, text="Incompletos: –", fg=RED, **lbl_kw)
        self.lbl_inc.pack(side=tk.LEFT)
        self.lbl_inf = tk.Label(summary, text="Inferidas: –", fg=ORANGE, **lbl_kw)
        self.lbl_inf.pack(side=tk.LEFT)

        # Separator + adjusted total
        tk.Frame(summary, bg=SURFACE, width=2).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=4)
        self.lbl_adjusted = tk.Label(summary, text="Ajustado: –", fg=ACCENT, **lbl_kw)
        self.lbl_adjusted.pack(side=tk.LEFT)

        self.lbl_pdfs_count = tk.Label(summary, text="PDFs: –", fg=DIM, **lbl_kw)
        self.lbl_pdfs_count.pack(side=tk.RIGHT)

        # ── Progress bars ────────────────────────────────────────────────────
        prog_frame = tk.Frame(self.root, bg=BG)
        prog_frame.pack(fill=tk.X, padx=14, pady=2)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Global.Horizontal.TProgressbar",
                         troughcolor=SURFACE, background=ACCENT,
                         bordercolor=SURFACE, lightcolor=ACCENT,
                         darkcolor=ACCENT)
        style.configure("File.Horizontal.TProgressbar",
                         troughcolor=SURFACE, background=GREEN,
                         bordercolor=SURFACE, lightcolor=GREEN,
                         darkcolor=GREEN)

        gf = tk.Frame(prog_frame, bg=BG)
        gf.pack(fill=tk.X, pady=1)
        self.lbl_gprog = tk.Label(gf, text="Global: –", fg=DIM, bg=BG,
                                   font=("Segoe UI", 8), anchor="w", width=30)
        self.lbl_gprog.pack(side=tk.LEFT)
        self.prog_global = ttk.Progressbar(gf, style="Global.Horizontal.TProgressbar",
                                            mode="determinate", maximum=100)
        self.prog_global.pack(fill=tk.X, expand=True, padx=(6, 0))

        ff = tk.Frame(prog_frame, bg=BG)
        ff.pack(fill=tk.X, pady=1)
        self.lbl_fprog = tk.Label(ff, text="Archivo: –", fg=DIM, bg=BG,
                                   font=("Segoe UI", 8), anchor="w", width=30)
        self.lbl_fprog.pack(side=tk.LEFT)
        self.prog_file = ttk.Progressbar(ff, style="File.Horizontal.TProgressbar",
                                          mode="determinate", maximum=100)
        self.prog_file.pack(fill=tk.X, expand=True, padx=(6, 0))

    # ══════════════════════════════════════════════════════════════════════════
    # ── Main view (PDF list + log) ────────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════════════

    def _build_main_view(self):
        self.main_frame = tk.Frame(self.root, bg=BG)

        paned = tk.PanedWindow(self.main_frame, orient=tk.HORIZONTAL, bg=BG,
                                sashwidth=6, sashrelief=tk.FLAT)
        paned.pack(fill=tk.BOTH, expand=True, padx=14, pady=(4, 12))

        # LEFT: PDF list
        left = tk.Frame(paned, bg=BG_PANEL, highlightbackground=SURFACE,
                         highlightthickness=1)
        paned.add(left, width=300, minsize=200)

        tk.Label(left, text="PDFs encontrados", fg=ACCENT, bg=BG_PANEL,
                 font=("Segoe UI", 10, "bold"), anchor="w",
                 padx=8, pady=6).pack(fill=tk.X)

        list_frame = tk.Frame(left, bg=BG_PANEL)
        list_frame.pack(fill=tk.BOTH, expand=True)

        sb_list = tk.Scrollbar(list_frame, bg=SURFACE, troughcolor=BG_PANEL)
        sb_list.pack(side=tk.RIGHT, fill=tk.Y)

        self.pdf_listbox = tk.Listbox(
            list_frame, bg=BG_LOG, fg=FG, font=("Consolas", 9),
            selectbackground=ACCENT, selectforeground="#11111b",
            highlightthickness=0, borderwidth=0,
            yscrollcommand=sb_list.set,
        )
        self.pdf_listbox.pack(fill=tk.BOTH, expand=True)
        sb_list.config(command=self.pdf_listbox.yview)

        # RIGHT: Log
        right = tk.Frame(paned, bg=BG_PANEL, highlightbackground=SURFACE,
                          highlightthickness=1)
        paned.add(right, minsize=400)

        tk.Label(right, text="Log de análisis", fg=ACCENT, bg=BG_PANEL,
                 font=("Segoe UI", 10, "bold"), anchor="w",
                 padx=8, pady=6).pack(fill=tk.X)

        log_frame = tk.Frame(right, bg=BG_PANEL)
        log_frame.pack(fill=tk.BOTH, expand=True)

        sb_log = tk.Scrollbar(log_frame, bg=SURFACE, troughcolor=BG_PANEL)
        sb_log.pack(side=tk.RIGHT, fill=tk.Y)

        self.log = tk.Text(
            log_frame, state=tk.DISABLED, bg=BG_LOG, fg=FG,
            font=("Consolas", 9), yscrollcommand=sb_log.set,
            wrap=tk.NONE, highlightthickness=0, borderwidth=0,
            insertbackground=FG, selectbackground=ACCENT,
        )
        self.log.pack(fill=tk.BOTH, expand=True)
        sb_log.config(command=self.log.yview)

        for tag, color in _LOG_COLORS.items():
            self.log.tag_configure(
                tag, foreground=color,
                font=("Consolas", 9, "bold") if tag in ("section", "file_hdr") else ("Consolas", 9),
            )

    # ══════════════════════════════════════════════════════════════════════════
    # ── Detail view (issues list + image preview) ─────────────────────────────
    # ══════════════════════════════════════════════════════════════════════════

    def _build_detail_view(self):
        self.detail_frame = tk.Frame(self.root, bg=BG)

        dtop = tk.Frame(self.detail_frame, bg=BG)
        dtop.pack(fill=tk.X, padx=14, pady=(4, 2))

        self.btn_back = tk.Button(
            dtop, text="←  Volver al inicio", command=self._show_main,
            bg=ACCENT, fg="#11111b", font=("Segoe UI", 10, "bold"),
            activebackground=ACCENT_DARK, activeforeground="#11111b",
            padx=14, pady=4, relief=tk.FLAT, cursor="hand2",
        )
        self.btn_back.pack(side=tk.LEFT)

        self.lbl_issues_count = tk.Label(
            dtop, text="0 problemas encontrados", fg=DIM, bg=BG,
            font=("Segoe UI", 9),
        )
        self.lbl_issues_count.pack(side=tk.LEFT, padx=12)

        paned = tk.PanedWindow(self.detail_frame, orient=tk.HORIZONTAL, bg=BG,
                                sashwidth=6, sashrelief=tk.FLAT)
        paned.pack(fill=tk.BOTH, expand=True, padx=14, pady=(2, 12))

        # LEFT: Issues list
        left = tk.Frame(paned, bg=BG_PANEL, highlightbackground=SURFACE,
                         highlightthickness=1)
        paned.add(left, width=380, minsize=280)

        lbl_hdr_frame = tk.Frame(left, bg=BG_PANEL)
        lbl_hdr_frame.pack(fill=tk.X)
        tk.Label(lbl_hdr_frame, text="Páginas con problemas", fg=ORANGE, bg=BG_PANEL,
                 font=("Segoe UI", 10, "bold"), anchor="w",
                 padx=8, pady=6).pack(side=tk.LEFT)
        self.btn_toggle_seq = tk.Button(
            lbl_hdr_frame, text="＋ Errores de secuencia",
            command=self._toggle_seq_visibility,
            bg=BG_PANEL, fg=DIM, font=("Segoe UI", 8),
            relief=tk.FLAT, cursor="hand2", padx=6,
        )
        self.btn_toggle_seq.pack(side=tk.RIGHT, padx=6)

        il_frame = tk.Frame(left, bg=BG_PANEL)
        il_frame.pack(fill=tk.BOTH, expand=True)

        sb_il = tk.Scrollbar(il_frame, bg=SURFACE, troughcolor=BG_PANEL)
        sb_il.pack(side=tk.RIGHT, fill=tk.Y)

        self.issues_listbox = tk.Listbox(
            il_frame, bg=BG_LOG, fg=FG, font=("Consolas", 9),
            selectbackground=ACCENT, selectforeground="#11111b",
            highlightthickness=0, borderwidth=0,
            yscrollcommand=sb_il.set,
        )
        self.issues_listbox.pack(fill=tk.BOTH, expand=True)
        sb_il.config(command=self.issues_listbox.yview)
        self.issues_listbox.bind("<<ListboxSelect>>", self._on_issue_select)

        ib = tk.Frame(left, bg=BG_PANEL)
        ib.pack(fill=tk.X, padx=6, pady=6)

        self.btn_open_loc = tk.Button(
            ib, text="📂  Abrir ubicación", command=self._open_issue_location,
            bg=SURFACE, fg=FG, font=("Segoe UI", 9),
            activebackground="#45475a", activeforeground=FG,
            padx=10, pady=3, relief=tk.FLAT, cursor="hand2",
            state=tk.DISABLED,
        )
        self.btn_open_loc.pack(side=tk.LEFT)

        self.btn_load_preview = tk.Button(
            ib, text="👁️ Cargar vista", command=self._load_preview_image,
            bg=SURFACE, fg=ACCENT, font=("Segoe UI", 9, "bold"),
            activebackground="#45475a", activeforeground=ACCENT,
            padx=10, pady=3, relief=tk.FLAT, cursor="hand2",
            state=tk.DISABLED,
        )
        self.btn_load_preview.pack(side=tk.LEFT, padx=(6, 0))

        # RIGHT: Image preview + adjustment
        self.preview_right = tk.Frame(paned, bg=BG_PANEL, highlightbackground=SURFACE,
                                      highlightthickness=1)
        paned.add(self.preview_right, minsize=400)

        # ── Status badge (TOP of preview, above image) ──────────────────
        self.lbl_adj_badge = tk.Label(
            self.preview_right, text="✅ INCLUIDA", fg="#11111b",
            bg=GREEN, font=("Segoe UI", 11, "bold"), pady=4,
        )
        self.lbl_adj_badge.pack(fill=tk.X)

        self.lbl_preview_title = tk.Label(
            self.preview_right, text="Selecciona un problema para ver la página",
            fg=DIM, bg=BG_PANEL, font=("Segoe UI", 10, "bold"),
            anchor="w", padx=8, pady=4,
        )
        self.lbl_preview_title.pack(fill=tk.X)

        # ── Canvas with scrollbars ───────────────────────────────────
        self.preview_outer = tk.Frame(self.preview_right, bg=BG_LOG)
        self.preview_outer.pack(fill=tk.BOTH, expand=True)

        self.preview_canvas = tk.Canvas(self.preview_outer, bg=BG_LOG, highlightthickness=0)

        sb_pv = tk.Scrollbar(self.preview_outer, orient=tk.VERTICAL,
                              command=self.preview_canvas.yview,
                              bg=SURFACE, troughcolor=BG_PANEL)
        sb_ph = tk.Scrollbar(self.preview_outer, orient=tk.HORIZONTAL,
                              command=self.preview_canvas.xview,
                              bg=SURFACE, troughcolor=BG_PANEL)

        self.preview_canvas.configure(yscrollcommand=sb_pv.set,
                                       xscrollcommand=sb_ph.set)

        sb_pv.pack(side=tk.RIGHT, fill=tk.Y)
        sb_ph.pack(side=tk.BOTTOM, fill=tk.X)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)

        self.preview_image_id = None

        # ── Bottom bar: toggle button + hints ─────────────────────────
        adj_frame = tk.Frame(self.preview_right, bg=BG_PANEL)
        adj_frame.pack(fill=tk.X, padx=8, pady=(4, 2))

        self.btn_adj_toggle = tk.Button(
            adj_frame, text="Excluir del conteo",
            command=self._toggle_adjustment,
            bg=SURFACE, fg=FG, font=("Segoe UI", 9),
            activebackground="#45475a", activeforeground=FG,
            padx=10, pady=4, relief=tk.FLAT, cursor="hand2",
            state=tk.DISABLED,
        )
        self.btn_adj_toggle.pack(side=tk.LEFT)

        self.lbl_adj_hint = tk.Label(
            adj_frame, text="Útil si el analizador cortó mal el documento",
            fg=DIM, bg=BG_PANEL, font=("Segoe UI", 8, "italic")
        )
        self.lbl_adj_hint.pack(side=tk.LEFT, padx=10)

        # ── Manual correction bar ─────────────────────────────────
        corr_frame = tk.Frame(self.preview_right, bg=SURFACE, padx=8, pady=8)
        corr_frame.pack(fill=tk.X, padx=8, pady=(0, 6))

        tk.Label(corr_frame, text="Corrección manual:", bg=SURFACE, fg=FG, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        
        self.txt_curr = tk.Entry(corr_frame, width=3, bg=BG_LOG, fg=FG, insertbackground=FG, borderwidth=1, relief=tk.FLAT, font=("Consolas", 10))
        self.txt_curr.pack(side=tk.LEFT, padx=(6, 2))
        
        tk.Label(corr_frame, text="de", bg=SURFACE, fg=DIM, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=2)
        
        self.txt_total = tk.Entry(corr_frame, width=3, bg=BG_LOG, fg=FG, insertbackground=FG, borderwidth=1, relief=tk.FLAT, font=("Consolas", 10))
        self.txt_total.pack(side=tk.LEFT, padx=(2, 8))
        
        self.btn_correct = tk.Button(
            corr_frame, text="✅ Validar e Inferir", command=self._apply_correction,
            bg=GREEN, fg="#11111b", font=("Segoe UI", 9, "bold"),
            activebackground="#82d17d", activeforeground="#11111b",
            padx=10, pady=2, relief=tk.FLAT, cursor="hand2",
            state=tk.DISABLED,
        )
        self.btn_correct.pack(side=tk.LEFT)

    # ══════════════════════════════════════════════════════════════════════════
    # ── History view (Treeview with expandable rows) ──────────────────────────
    # ══════════════════════════════════════════════════════════════════════════

    def _build_history_view(self):
        self.history_frame = tk.Frame(self.root, bg=BG)

        htop = tk.Frame(self.history_frame, bg=BG)
        htop.pack(fill=tk.X, padx=14, pady=(4, 2))

        self.btn_hist_back = tk.Button(
            htop, text="←  Volver al inicio", command=self._show_main,
            bg=ACCENT, fg="#11111b", font=("Segoe UI", 10, "bold"),
            activebackground=ACCENT_DARK, activeforeground="#11111b",
            padx=14, pady=4, relief=tk.FLAT, cursor="hand2",
        )
        self.btn_hist_back.pack(side=tk.LEFT)

        tk.Label(htop, text="Historial de análisis", fg=ACCENT, bg=BG,
                 font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT, padx=12)

        self.btn_hist_clear = tk.Button(
            htop, text="🗑  Limpiar historial", command=self._clear_history,
            bg=SURFACE, fg=RED, font=("Segoe UI", 9),
            activebackground="#45475a", activeforeground=RED,
            padx=10, pady=3, relief=tk.FLAT, cursor="hand2",
        )
        self.btn_hist_clear.pack(side=tk.RIGHT)

        self.btn_hist_open = tk.Button(
            htop, text="📂  Abrir ubicación", command=self._open_history_location,
            bg=SURFACE, fg=FG, font=("Segoe UI", 9),
            activebackground="#45475a", activeforeground=FG,
            padx=10, pady=3, relief=tk.FLAT, cursor="hand2",
        )
        self.btn_hist_open.pack(side=tk.RIGHT, padx=(0, 6))

        # Treeview
        tree_frame = tk.Frame(self.history_frame, bg=BG_PANEL,
                               highlightbackground=SURFACE, highlightthickness=1)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=(2, 12))

        cols = ("fecha", "documentos", "completos", "incompletos", "inferidas")
        self.history_tree = ttk.Treeview(
            tree_frame, columns=cols, show="tree headings",
            selectmode="browse",
        )

        # Style the treeview
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview",
                         background=BG_LOG, foreground=FG,
                         fieldbackground=BG_LOG,
                         font=("Consolas", 9),
                         rowheight=26)
        style.configure("Treeview.Heading",
                         background=SURFACE, foreground=FG,
                         font=("Segoe UI", 9, "bold"))
        style.map("Treeview",
                   background=[("selected", ACCENT)],
                   foreground=[("selected", "#11111b")])

        self.history_tree.heading("#0", text="Origen", anchor="w")
        self.history_tree.heading("fecha", text="Fecha", anchor="w")
        self.history_tree.heading("documentos", text="Docs", anchor="center")
        self.history_tree.heading("completos", text="✓", anchor="center")
        self.history_tree.heading("incompletos", text="⚠", anchor="center")
        self.history_tree.heading("inferidas", text="Inf.", anchor="center")

        self.history_tree.column("#0", width=350, minwidth=200)
        self.history_tree.column("fecha", width=140, minwidth=120)
        self.history_tree.column("documentos", width=60, minwidth=50, anchor="center")
        self.history_tree.column("completos", width=60, minwidth=50, anchor="center")
        self.history_tree.column("incompletos", width=60, minwidth=50, anchor="center")
        self.history_tree.column("inferidas", width=60, minwidth=50, anchor="center")

        sb_tree = tk.Scrollbar(tree_frame, command=self.history_tree.yview,
                                bg=SURFACE, troughcolor=BG_PANEL)
        self.history_tree.configure(yscrollcommand=sb_tree.set)
        sb_tree.pack(side=tk.RIGHT, fill=tk.Y)
        self.history_tree.pack(fill=tk.BOTH, expand=True)

    # ── Frame switching ───────────────────────────────────────────────────────

    def _hide_all_frames(self):
        self.main_frame.pack_forget()
        self.detail_frame.pack_forget()
        self.history_frame.pack_forget()

    def _show_main(self):
        self._hide_all_frames()
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        self.btn_issues.config(text=f"⚠  Ver Problemas ({len(self.issues)})")
        self._unbind_detail_keys()

    def _unbind_detail_keys(self):
        for key in ("<Left>", "<Right>", "<space>", "<plus>", "<minus>", "<KP_Add>", "<KP_Subtract>", "<Key-0>"):
            self.root.unbind(key)

    def _show_detail(self):
        self._hide_all_frames()
        self.detail_frame.pack(fill=tk.BOTH, expand=True)
        self._refresh_issues_list()
        # Bind keyboard navigation
        self.root.bind("<Left>", self._key_prev_issue)
        self.root.bind("<Right>", self._key_next_issue)
        self.root.bind("<space>", self._key_toggle_adj)
        self.root.bind("<plus>", self._key_zoom_in)
        self.root.bind("<minus>", self._key_zoom_out)
        self.root.bind("<KP_Add>", self._key_zoom_in)
        self.root.bind("<KP_Subtract>", self._key_zoom_out)
        self.root.bind("<Key-0>", self._key_zoom_reset)

    def _show_history(self):
        self._hide_all_frames()
        self.history_frame.pack(fill=tk.BOTH, expand=True)
        self._refresh_history_tree()
        self._unbind_detail_keys()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _pick_folder(self):
        folder = filedialog.askdirectory(title="Seleccionar carpeta con PDFs")
        if not folder:
            return

        self.pdf_list = _find_pdfs(folder)
        if not self.pdf_list:
            self.lbl_folder.config(text="No se encontraron PDFs", fg=RED)
            return

        display = Path(folder).name
        self.lbl_folder.config(text=f"📁 {display}  ({len(self.pdf_list)} PDFs)", fg=FG)
        self._current_source = folder
        self._current_source_name = display
        self._current_is_folder = True
        self._start_processing(folder)

    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="Seleccionar archivo PDF",
            filetypes=[("PDF", "*.pdf")],
        )
        if not path:
            return

        self.pdf_list = [Path(path)]
        self.lbl_folder.config(text=f"📄 {Path(path).name}", fg=FG)
        self._current_source = path
        self._current_source_name = Path(path).name
        self._current_is_folder = False
        self._start_processing(None)

    def _start_processing(self, base_folder: str | None):
        self._show_main()

        # Track session source
        src_name = self._current_source_name
        if src_name and src_name not in self._session_sources:
            self._session_sources.append(src_name)

        self.pdf_listbox.delete(0, tk.END)
        for p in self.pdf_list:
            if base_folder and p.is_relative_to(base_folder):
                rel = p.relative_to(base_folder)
            else:
                rel = p.name
            self.pdf_listbox.insert(tk.END, f"  ⏳  {rel}")
        self.pdf_listbox.config(fg=DIM)

        # NOTE: accumulators are NOT reset — session accumulates
        self._update_summary()

        self.lbl_pdfs_count.config(
            text=f"Sesión: {self._session_pdf_count + len(self.pdf_list)} PDFs"
        )
        self._update_session_label()

        self.btn_folder.config(state=tk.DISABLED)
        self.btn_file.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.btn_skip.config(state=tk.NORMAL)
        self.btn_new_session.config(state=tk.DISABLED)
        self.btn_load_session.config(state=tk.DISABLED)
        self._skip_current = False
        self.running = True
        self.pause_event.set()
        threading.Thread(target=self._process_all, daemon=True).start()

    def _stop_processing(self):
        """Detiene todo el proceso de análisis de la cola actual."""
        if not self.running:
            return
        self._stop_requested = True
        self.cancel_event.set()
        self.btn_stop.config(state=tk.DISABLED)
        self._log_msg("🛑  Deteniendo proceso (abortando OCR actual)...", "error")

    # ── Processing ────────────────────────────────────────────────────────────

    def _process_all(self):
        total_pdfs = len(self.pdf_list)

        for idx, pdf_path in enumerate(self.pdf_list):
            # Check skip flag
            if self._skip_current:
                self._skip_current = False
                self.root.after(0, self._set_list_status, idx, "skipped")
                self.root.after(0, self._log_msg,
                                f"⏭  Saltado: {pdf_path.name}", "warn")
                continue

            if self._stop_requested:
                self.root.after(0, self._log_msg, "🛑  Proceso detenido por el usuario.", "error")
                break

            self.root.after(0, self._set_list_status, idx, "processing")

            rel_name = pdf_path.name
            self.root.after(0, self._log_msg,
                            f"\n{'━' * 60}", "section")
            self.root.after(0, self._log_msg,
                            f"📄  [{idx + 1}/{total_pdfs}]  {rel_name}", "file_hdr")
            self.root.after(0, self._log_msg,
                            f"    {pdf_path}", "info")
            self.root.after(0, self._log_msg,
                            f"{'━' * 60}", "section")

            self.root.after(0, self._update_global_progress, idx, total_pdfs)
            self.root.after(0, lambda: self.prog_file.config(value=0))
            self.root.after(0, lambda n=rel_name: self.lbl_fprog.config(
                text=f"Archivo: {n}"))

            def on_progress(done, total, _idx=idx, _total=total_pdfs):
                pct = int(done / total * 100)
                self.root.after(0, lambda: self.prog_file.config(value=pct))
                self.root.after(0, lambda d=done, t=total: self.lbl_fprog.config(
                    text=f"Pág {d} / {t}"))

            def on_log(msg, level="info"):
                self.root.after(0, self._log_msg, msg, level)

            _current_path = pdf_path

            def on_issue(page, kind, detail, pil_img, _path=_current_path):
                issue = PageIssue(
                    pdf_path=_path, pdf_page=page,
                    issue_type=kind, detail=detail, pil_image=pil_img,
                )
                self.root.after(0, self._add_issue, issue)

            self.cancel_event.clear()

            try:
                # Mode is fixed to charla for now as per user request to declutter
                current_mode = "charla" 
                docs, reads = analyze_pdf(str(pdf_path), on_progress, on_log,
                                   pause_event=self.pause_event,
                                   cancel_event=self.cancel_event,
                                   on_issue=on_issue,
                                   doc_mode=current_mode)
                self._pdf_reads[str(pdf_path)] = reads

                if self._stop_requested:
                    self.root.after(0, self._set_list_status, idx, "error")
                    break

                # Check if file was skipped mid-processing
                if self._skip_current:
                    self._skip_current = False
                    self.root.after(0, self._set_list_status, idx, "skipped")
                    self.root.after(0, self._log_msg,
                                    f"⏭  Saltado: {rel_name}", "warn")
                    continue

                complete = [d for d in docs if d.is_complete]
                incomplete = [d for d in docs if not d.is_complete]
                inferred = sum(len(d.inferred_pages) for d in docs)

                self.total_docs += len(docs)
                self.total_complete += len(complete)
                self.total_incomplete += len(incomplete)
                self.total_inferred += inferred

                # Store per-PDF result
                self._pdf_results.append(PDFResult(
                    name=rel_name,
                    path=str(pdf_path),
                    total_docs=len(docs),
                    complete=len(complete),
                    incomplete=len(incomplete),
                    inferred=inferred,
                ))

                self._session_pdf_count += 1

                self.root.after(0, self._update_summary)
                self.root.after(0, self._show_file_summary, docs, rel_name)
                self.root.after(0, self._set_list_status, idx, "done")

            except Exception as e:
                import traceback
                self.root.after(0, self._log_msg,
                                f"Error procesando {rel_name}: {e}\n{traceback.format_exc()}",
                                "error")
                self.root.after(0, self._set_list_status, idx, "error")

            self.root.after(0, self._update_global_progress, idx + 1, total_pdfs)
            self.root.after(0, lambda c=self._session_pdf_count:
                            self.lbl_pdfs_count.config(text=f"Sesión: {c} PDFs"))

        # Done
        self.running = False
        self.root.after(0, self._log_msg,
                        f"\n{'═' * 60}", "section")
        self.root.after(0, self._log_msg,
                        "🏁  Proceso completado", "ok")
        self.root.after(0, self._log_msg,
                        f"{'═' * 60}", "section")
        self.root.after(0, lambda: self.btn_folder.config(state=tk.NORMAL))
        self.root.after(0, lambda: self.btn_file.config(state=tk.NORMAL))
        self.root.after(0, lambda: self.btn_stop.config(state=tk.DISABLED))
        self.root.after(0, lambda: self.btn_skip.config(state=tk.DISABLED))
        self.root.after(0, lambda: self.btn_new_session.config(state=tk.NORMAL))
        self.root.after(0, lambda: self.btn_load_session.config(state=tk.NORMAL))

    def _save_to_history(self):
        """Guarda los resultados del run actual en el historial (automático)."""
        entry = HistoryEntry(
            date=datetime.now().strftime("%Y-%m-%d %H:%M"),
            source=self._current_source,
            source_name=self._current_source_name,
            is_folder=self._current_is_folder,
            total_docs=self.total_docs,
            total_complete=self.total_complete,
            total_incomplete=self.total_incomplete,
            total_inferred=self.total_inferred,
            pdfs=list(self._pdf_results),
        )
        try:
            add_entry(entry)
        except Exception:
            pass  # silent for auto-save

    # ── Session management ────────────────────────────────────────────────────

    def _new_session(self):
        """Resetea todo para empezar una sesión nueva."""
        if self.running:
            return
        if self.total_docs > 0:
            if not messagebox.askyesno(
                "Nueva Sesión",
                f"Hay {self.total_docs} documentos contados en la sesión actual.\n"
                "¿Descartar y empezar de cero?",
            ):
                return

        self.total_docs = 0
        self.total_complete = 0
        self.total_incomplete = 0
        self.total_inferred = 0
        self._pdf_results.clear()
        self.issues.clear()
        self._adjustments.clear()
        self._selected_issue_idx = -1
        self._session_sources.clear()
        self._session_pdf_count = 0

        self._update_summary()
        self._update_issues_button()
        self._clear_log()
        self.pdf_listbox.delete(0, tk.END)
        self.lbl_pdfs_count.config(text="PDFs: –")
        self.lbl_folder.config(text="Sesión nueva", fg=GREEN)
        self._show_main()
        self._log_msg("🔄  Nueva sesión iniciada", "info")

    def _save_session(self):
        """Guarda la sesión actual al historial con nombre genérico."""
        if self.total_docs == 0:
            messagebox.showinfo("Guardar Sesión", "No hay datos para guardar.")
            return

        name = f"Sesión {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        sources = ", ".join(self._session_sources) if self._session_sources else self._current_source
        entry = HistoryEntry(
            date=datetime.now().strftime("%Y-%m-%d %H:%M"),
            source=sources,
            source_name=name,
            is_folder=True,
            total_docs=self._get_adjusted_total(),
            total_complete=self.total_complete,
            total_incomplete=self.total_incomplete,
            total_inferred=self.total_inferred,
            pdfs=list(self._pdf_results),
            is_session=True,
        )
        try:
            add_entry(entry)
            self._log_msg(f"💾  Sesión guardada como: {name}", "ok")
            messagebox.showinfo("Sesión Guardada", f"Guardada como:\n{name}")
        except Exception as e:
            self._log_msg(f"Error guardando sesión: {e}", "error")

    def _load_session(self):
        """Muestra un diálogo para cargar una sesión anterior."""
        if self.running:
            return

        history = load_history()
        if not history:
            messagebox.showinfo("Cargar Sesión", "No hay historial disponible.")
            return

        # Build a selection dialog
        dlg = tk.Toplevel(self.root)
        dlg.title("Cargar sesión anterior")
        dlg.geometry("520x400")
        dlg.config(bg=BG)
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(dlg, text="Seleccionar sesión para cargar:",
                 fg=FG, bg=BG, font=("Segoe UI", 11, "bold")).pack(pady=10)

        lb_frame = tk.Frame(dlg, bg=BG)
        lb_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=4)
        sb = tk.Scrollbar(lb_frame, bg=SURFACE)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        lb = tk.Listbox(lb_frame, bg=BG_LOG, fg=FG, font=("Consolas", 10),
                        selectbackground=ACCENT, selectforeground="#11111b",
                        yscrollcommand=sb.set)
        lb.pack(fill=tk.BOTH, expand=True)
        sb.config(command=lb.yview)

        for i, e in enumerate(history):
            icon = "📊" if e.is_session else "📄"
            lb.insert(tk.END, f"  {icon}  {e.date}  |  {e.source_name}  |  {e.total_docs} docs")

        def do_load():
            sel = lb.curselection()
            if not sel:
                return
            entry = history[sel[0]]
            # Load totals
            self.total_docs = entry.total_docs
            self.total_complete = entry.total_complete
            self.total_incomplete = entry.total_incomplete
            self.total_inferred = entry.total_inferred
            self._pdf_results = list(entry.pdfs)
            self._session_sources = [entry.source_name]
            self._session_pdf_count = len(entry.pdfs)
            self.issues.clear()
            self._adjustments.clear()
            self._selected_issue_idx = -1
            self._update_summary()
            self._update_issues_button()
            self._update_session_label()
            self.lbl_pdfs_count.config(
                text=f"Sesión: {self._session_pdf_count} PDFs"
            )
            self.pdf_listbox.delete(0, tk.END)
            for pr in entry.pdfs:
                self.pdf_listbox.insert(tk.END, f"  ✅  {pr.name}  ({pr.total_docs} docs)")
            self._clear_log()
            self._log_msg(f"📂  Sesión cargada: {entry.source_name}", "ok")
            self._log_msg(f"    Documentos: {entry.total_docs}  |  Completos: {entry.total_complete}  |  Incompletos: {entry.total_incomplete}", "info")
            dlg.destroy()

        btn_frame = tk.Frame(dlg, bg=BG)
        btn_frame.pack(fill=tk.X, padx=14, pady=10)
        tk.Button(btn_frame, text="Cargar", command=do_load,
                  bg=ACCENT, fg="#11111b", font=("Segoe UI", 10, "bold"),
                  padx=20, pady=4, relief=tk.FLAT, cursor="hand2",
                  ).pack(side=tk.LEFT)
        tk.Button(btn_frame, text="Cancelar", command=dlg.destroy,
                  bg=SURFACE, fg=FG, font=("Segoe UI", 10),
                  padx=20, pady=4, relief=tk.FLAT, cursor="hand2",
                  ).pack(side=tk.RIGHT)

    def _skip_file(self):
        """Salta el archivo que se está procesando actualmente."""
        if not self.running:
            return
        self._skip_current = True
        self.cancel_event.set()
        self._log_msg("⏭  Interrumpiendo PDF actual y saltando al siguiente...", "warn")

    def _update_session_label(self):
        """Actualiza el label de origen con contexto de sesión."""
        n = len(self._session_sources)
        if n == 0:
            self.lbl_folder.config(text="Ningún origen seleccionado", fg=DIM)
        elif n == 1:
            self.lbl_folder.config(text=f"📊 {self._session_sources[0]}", fg=FG)
        else:
            self.lbl_folder.config(
                text=f"📊 Sesión: {n} orígenes, {self._session_pdf_count} PDFs",
                fg=FG,
            )

    # ── Issues management ─────────────────────────────────────────────────────

    def _add_issue(self, issue: PageIssue):
        self.issues.append(issue)
        self._update_issues_button()
        if self.detail_frame.winfo_ismapped():
            self._append_issue_to_listbox(len(self.issues) - 1, issue)

    def _refresh_issue_listbox(self):
        """Reconstruye el listbox de problemas usando la lista actual internal (respeta _show_seq_issues)."""
        self.issues_listbox.delete(0, tk.END)
        self._row_to_issue.clear()
        
        row = 0
        for idx, iss in enumerate(self.issues):
            if iss.issue_type == "secuencia rota" and not self._show_seq_issues:
                continue
                
            badge = "⚠" if iss.issue_type == "incompleto" else "❌"
            self.issues_listbox.insert(tk.END, f"{badge} {iss.pdf_path.name} - {iss.detail}")
            
            if iss.issue_type == "incompleto":
                self.issues_listbox.itemconfig(row, {'fg': ORANGE})
            elif "inferida" in iss.issue_type:
                self.issues_listbox.itemconfig(row, {'fg': YELLOW})
            else:
                self.issues_listbox.itemconfig(row, {'fg': RED})
                
            self._row_to_issue[row] = idx
            row += 1

    def _update_issues_button(self):
        count = len(self.issues)
        self.btn_issues.config(
            text=f"⚠  Ver Problemas ({count})",
            state=tk.NORMAL if count > 0 else tk.DISABLED,
            fg=ORANGE if count > 0 else DIM,
        )

    def _refresh_issues_list(self):
        self.issues_listbox.delete(0, tk.END)
        self._row_to_issue.clear()

        # Filter: hide secuencia rota unless toggled on
        visible = [(i, iss) for i, iss in enumerate(self.issues)
                   if self._show_seq_issues or iss.issue_type != "secuencia rota"]

        # Count only actionable (non-sequence) issues for the label
        actionable = [iss for _, iss in visible if iss.issue_type != "secuencia rota"]
        excluded_count = sum(1 for i, _ in visible if i in self._adjustments)
        included_count = len(visible) - excluded_count
        seq_total = sum(1 for iss in self.issues if iss.issue_type == "secuencia rota")

        label_parts = [f"{len(actionable)} a verificar"]
        if excluded_count > 0:
            label_parts.append(f"{excluded_count} excluidas")
        if seq_total > 0:
            label_parts.append(f"{seq_total} sec. rota")
        self.lbl_issues_count.config(
            text="  |  ".join(label_parts),
            fg=ORANGE if actionable else DIM,
        )

        # Update toggle button text
        if seq_total > 0:
            self.btn_toggle_seq.config(
                text=f"{'－' if self._show_seq_issues else '＋'} Errores de secuencia ({seq_total})",
                fg=ORANGE if self._show_seq_issues else DIM,
            )
        else:
            self.btn_toggle_seq.config(text="Sin errores de secuencia", fg=DIM, state=tk.DISABLED)

        # Separate included vs excluded
        included = [(i, iss) for i, iss in visible if i not in self._adjustments]
        excluded = [(i, iss) for i, iss in visible if i in self._adjustments]

        # ── Included section ──
        if included:
            self.issues_listbox.insert(tk.END, f"── ✅ INCLUIDAS ({len(included)}) ──")
            self.issues_listbox.itemconfig(tk.END, fg=GREEN)
            current_file = None
            for i, issue in included:
                if issue.pdf_path != current_file:
                    current_file = issue.pdf_path
                    self.issues_listbox.insert(tk.END, f"  📁 {issue.pdf_path.name}")
                    self.issues_listbox.itemconfig(self.issues_listbox.size() - 1, fg=ACCENT)
                self._append_issue_entry(i, issue)

        # ── Excluded section ──
        if excluded:
            self.issues_listbox.insert(tk.END, f"── ❌ EXCLUIDAS ({len(excluded)}) ──")
            self.issues_listbox.itemconfig(tk.END, fg=RED)
            current_file = None
            for i, issue in excluded:
                if issue.pdf_path != current_file:
                    current_file = issue.pdf_path
                    self.issues_listbox.insert(tk.END, f"  📁 {issue.pdf_path.name}")
                    self.issues_listbox.itemconfig(self.issues_listbox.size() - 1, fg=ACCENT)
                self._append_issue_entry(i, issue)

    def _toggle_seq_visibility(self):
        """Toggle visibility of 'secuencia rota' issues."""
        self._show_seq_issues = not self._show_seq_issues
        self._refresh_issues_list()


    def _append_issue_entry(self, idx: int, issue: PageIssue):
        """Agrega una entrada de issue al listbox (sin header de archivo)."""
        adj = self._adjustments.get(idx, 0)
        icon = self._adj_icon(idx, issue)
        suffix = self._adj_suffix(adj)
        line = f"    {icon}  Pág {issue.pdf_page} — {issue.issue_type}{suffix}"
        self.issues_listbox.insert(tk.END, line)
        last = self.issues_listbox.size() - 1
        self.issues_listbox.itemconfig(last, fg=self._adj_color(idx, issue))
        self._row_to_issue[last] = idx

    def _append_issue_to_listbox(self, idx: int, issue: PageIssue):
        """Agrega issue al listbox durante el streaming (con header de archivo si es nuevo)."""
        if idx == 0 or self.issues[idx - 1].pdf_path != issue.pdf_path:
            if self.detail_frame.winfo_ismapped():
                self.issues_listbox.insert(tk.END, f"📁 {issue.pdf_path.name}")
                last = self.issues_listbox.size() - 1
                self.issues_listbox.itemconfig(last, fg=ACCENT)

        adj = self._adjustments.get(idx, 0)
        icon = self._adj_icon(idx, issue)
        suffix = self._adj_suffix(adj)
        line = f"  {icon}  Pág {issue.pdf_page} — {issue.issue_type}{suffix}"
        self.issues_listbox.insert(tk.END, line)
        last = self.issues_listbox.size() - 1
        self.issues_listbox.itemconfig(last, fg=self._adj_color(idx, issue))
        self.issues_listbox.see(last)
        self.lbl_issues_count.config(
            text=f"{len(self.issues)} problemas encontrados", fg=ORANGE,
        )

    def _is_header_row(self, text: str) -> bool:
        """True si la fila es un header (sección o archivo)."""
        return text.strip().startswith(("📁", "──"))

    def _on_issue_select(self, event):
        sel = self.issues_listbox.curselection()
        if not sel:
            return
        row = sel[0]
        issue_idx = self._row_to_issue.get(row)
        if issue_idx is None:
            return  # clicked a header row
        self._select_issue_by_idx(issue_idx)

    def _display_preview(self, pil_img: Image.Image | None, keep_zoom: bool = False):
        if not keep_zoom:
            self._zoom_level = 1.0
        self._current_preview_pil = pil_img
        self._render_preview()

    def _load_preview_image(self):
        idx = self._selected_issue_idx
        if idx < 0: return
        issue = self.issues[idx]

        import fitz
        from PIL import Image

        try:
            self._log_msg(f"Cargando vista previa para {issue.pdf_path.name} (Pág {issue.pdf_page})...", "info")
            doc = fitz.open(str(issue.pdf_path))
            page = doc[issue.pdf_page - 1]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            issue.pil_image = img  # cache it
            self._display_preview(img)
            self.btn_load_preview.config(state=tk.DISABLED)
            doc.close()
            self._log_msg("Vista previa cargada.", "ok")
        except Exception as e:
            self._log_msg(f"Error cargando preview: {e}", "error")

    def _apply_correction(self):
        idx = self._selected_issue_idx
        if idx < 0: return
        issue = self.issues[idx]

        try:
            curr = int(self.txt_curr.get())
            total = int(self.txt_total.get())
        except ValueError:
            return

        pdf_str = str(issue.pdf_path)
        reads = self._pdf_reads.get(pdf_str)
        if not reads:
            self._log_msg(f"No se pudieron cargar las lecturas anteriores de {pdf_str}.", "error")
            return

        # Store correction
        pdf_corrections = self._user_corrections.setdefault(pdf_str, {})
        pdf_corrections[issue.pdf_page] = (curr, total)

        # Clear existing issues for this PDF to let re-infer recreate them
        self.issues = [i for i in self.issues if str(i.pdf_path) != pdf_str]

        def on_issue(page, kind, detail, pil_img, _path=issue.pdf_path):
            new_issue = PageIssue(
                pdf_path=_path, pdf_page=page,
                issue_type=kind, detail=detail, pil_image=pil_img,
            )
            self.issues.append(new_issue)

        self._log_msg(f"Recalculando inferencia para {issue.pdf_path.name}...", "info")
        docs, new_reads = re_infer_documents(
            reads=reads,
            corrections=pdf_corrections,
            on_log=self._log_msg,
            on_issue=on_issue
        )
        self._pdf_reads[pdf_str] = new_reads

        # Update metrics globally so they are correct in history and summary
        old_res = next((r for r in self._pdf_results if r.path == pdf_str), None)
        if old_res:
            self.total_docs -= old_res.total_docs
            self.total_complete -= old_res.complete
            self.total_incomplete -= old_res.incomplete
            self.total_inferred -= old_res.inferred
            
            complete = [d for d in docs if d.is_complete]
            incomplete = [d for d in docs if not d.is_complete]
            inferred = sum(len(d.inferred_pages) for d in docs)
            
            old_res.total_docs = len(docs)
            old_res.complete = len(complete)
            old_res.incomplete = len(incomplete)
            old_res.inferred = inferred
            
            self.total_docs += len(docs)
            self.total_complete += len(complete)
            self.total_incomplete += len(incomplete)
            self.total_inferred += inferred
            
            for doc in incomplete:
                missing = doc.missing_pages
                if not missing: continue
                page_ref = doc.pages[-1] if doc.pages else doc.start_pdf_page
                detail = f"Doc {doc.index} incompleto. Detectadas {doc.found_total}/{doc.declared_total}. Faltan: {missing}"
                self.issues.append(PageIssue(
                    pdf_path=issue.pdf_path,
                    pdf_page=page_ref,
                    issue_type="incompleto",
                    detail=detail,
                    pil_image=None
                ))
            
            self._update_summary()

        # Refresh UI
        self._refresh_issue_listbox()
        self._update_issues_button()
        self.lbl_issues_count.config(text=f"{len(self.issues)} problemas encontrados")
        
        # Deselect logic
        self.issues_listbox.selection_clear(0, tk.END)
        self._selected_issue_idx = -1
        self._display_preview(None)
        self.txt_curr.delete(0, tk.END)
        self.txt_total.delete(0, tk.END)
        self.btn_correct.config(state=tk.DISABLED)
        self.btn_load_preview.config(state=tk.DISABLED)
        self.lbl_preview_title.config(text="Selecciona un problema para ver la página", fg=DIM)

    def _render_preview(self):
        """Renderiza la imagen actual con el zoom actual."""
        pil_img = self._current_preview_pil
        self.preview_canvas.delete("all")
        if pil_img is None:
            self.preview_canvas.create_text(
                10, 10, anchor=tk.NW, text="Sin vista previa disponible para predicciones/errores v2.",
                fill=DIM, font=("Segoe UI", 10)
            )
            return

        canvas_w = self.preview_canvas.winfo_width()
        if canvas_w < 100:
            canvas_w = 600

        img_w, img_h = pil_img.size
        base_scale = min(canvas_w / img_w, 1.5)
        scale = base_scale * self._zoom_level
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)

        resized = pil_img.resize((new_w, new_h), Image.LANCZOS)
        self._current_preview_tk = ImageTk.PhotoImage(resized)

        self.preview_image_id = self.preview_canvas.create_image(
            0, 0, anchor=tk.NW, image=self._current_preview_tk,
        )
        self.preview_canvas.config(scrollregion=(0, 0, new_w, new_h))

    def _open_issue_location(self):
        """Abre la ubicación del issue seleccionado."""
        idx = self._selected_issue_idx
        if 0 <= idx < len(self.issues):
            _open_in_explorer(self.issues[idx].pdf_path)

    # ── Adjustment helpers ────────────────────────────────────────────────

    def _toggle_adjustment(self):
        """Alterna incluir/excluir la página del conteo."""
        idx = self._selected_issue_idx
        if idx < 0 or idx >= len(self.issues):
            return

        # No permitir ajustar "secuencia rota", no afectan el conteo total de documentos
        if self.issues[idx].issue_type == "secuencia rota":
            return

        if idx in self._adjustments:  # currently excluded → re-include
            self._adjustments.pop(idx)
        else:                         # currently included → exclude
            self._adjustments[idx] = -1

        self._update_adj_ui()
        self._refresh_issues_list()
        self._update_summary()

    def _update_adj_ui(self):
        """Actualiza badge, fondo del panel derecho, y botón."""
        idx = self._selected_issue_idx
        if idx < 0:
            return

        issue = self.issues[idx]

        if issue.issue_type == "secuencia rota":
            # Estos problemas no suman +1, así que no se pueden excluir/incluir
            self.lbl_adj_badge.config(
                text="ℹ NO AFECTA EL CONTEO (Es error de secuencia)",
                fg="gray", bg=BG_LOG,
            )
            self.btn_adj_toggle.config(
                text="No aplicable", fg="gray", state=tk.DISABLED
            )
            self.preview_outer.config(bg=BG_LOG)
            self.preview_canvas.config(bg=BG_LOG)
            return

        excluded = idx in self._adjustments

        # Subtle tint colors for background
        BG_INCLUDED = "#1a3a2a"   # dark green tint
        BG_EXCLUDED = "#3a1a1a"   # dark red tint

        if excluded:
            self.lbl_adj_badge.config(text="❌ EXCLUIDA", fg="#11111b", bg=RED)
            self.btn_adj_toggle.config(
                text="Incluir en el conteo", fg=GREEN,
                activeforeground=GREEN, state=tk.NORMAL,
            )
            self.preview_outer.config(bg=BG_EXCLUDED)
            self.preview_canvas.config(bg=BG_EXCLUDED)
        else:
            self.lbl_adj_badge.config(text="✅ INCLUIDA", fg="#11111b", bg=GREEN)
            self.btn_adj_toggle.config(
                text="Excluir del conteo", fg=RED,
                activeforeground=RED,
                state=tk.NORMAL if idx >= 0 else tk.DISABLED,
            )
            self.preview_outer.config(bg=BG_LOG)
            self.preview_canvas.config(bg=BG_LOG)

    def _adj_icon(self, idx: int, issue: PageIssue) -> str:
        if idx in self._adjustments:
            return "❌"
        return "🔮" if issue.issue_type == "inferida" else "⚠"

    def _adj_suffix(self, adj: int) -> str:
        if adj == -1:
            return "  [excluida]"
        return ""

    def _adj_color(self, idx: int, issue: PageIssue) -> str:
        if idx in self._adjustments:
            return DIM  # grayed out when excluded
        return YELLOW if issue.issue_type == "inferida" else ORANGE

    def _get_adjusted_total(self) -> int:
        """Calcula el total de documentos con los ajustes del usuario."""
        return self.total_docs + sum(self._adjustments.values())

    # ── Keyboard navigation ─────────────────────────────────────────────

    def _key_prev_issue(self, event=None):
        """Tecla ← : ir al issue anterior."""
        if not self.issues:
            return
        new_idx = max(0, self._selected_issue_idx - 1)
        self._select_issue_by_idx(new_idx)

    def _key_next_issue(self, event=None):
        """Tecla → : ir al issue siguiente."""
        if not self.issues:
            return
        new_idx = min(len(self.issues) - 1, self._selected_issue_idx + 1)
        self._select_issue_by_idx(new_idx)

    def _key_toggle_adj(self, event=None):
        """Tecla Espacio: alternar incluir/excluir."""
        self._toggle_adjustment()

    def _key_zoom_in(self, event=None):
        """Tecla + : acercar."""
        self._zoom_level = min(self._zoom_level * 1.25, 5.0)
        self._render_preview()

    def _key_zoom_out(self, event=None):
        """Tecla - : alejar."""
        self._zoom_level = max(self._zoom_level / 1.25, 0.2)
        self._render_preview()

    def _key_zoom_reset(self, event=None):
        """Tecla 0 : restablecer zoom a 100%."""
        self._zoom_level = 1.0
        self._render_preview()

    def _select_issue_by_idx(self, issue_idx: int):
        """Selecciona un issue programáticamente y actualiza la UI."""
        if issue_idx < 0 or issue_idx >= len(self.issues):
            return

        self._selected_issue_idx = issue_idx
        issue = self.issues[issue_idx]

        # Find the corresponding listbox row via reverse map
        target_row = -1
        for row, idx in self._row_to_issue.items():
            if idx == issue_idx:
                target_row = row
                break

        if target_row >= 0:
            self.issues_listbox.selection_clear(0, tk.END)
            self.issues_listbox.selection_set(target_row)
            self.issues_listbox.see(target_row)

        self.lbl_preview_title.config(
            text=f"Pág {issue.pdf_page}  —  {issue.issue_type}  —  {issue.pdf_path.name}"
                 f"  ({issue_idx + 1}/{len(self.issues)})",
            fg=ORANGE,
        )
        self.btn_open_loc.config(state=tk.NORMAL)
        self.btn_load_preview.config(state=tk.NORMAL if issue.pil_image is None else tk.DISABLED)
        
        # Enforce correction button state based on issue type
        if "inferida" in issue.issue_type or "rota" in issue.issue_type or "huérfana" in issue.issue_type:
            self.btn_correct.config(state=tk.NORMAL)
            # Pre-fill inputs where logical
            self.txt_curr.delete(0, tk.END)
            self.txt_total.delete(0, tk.END)
            
            import re
            match = re.search(r"curr=(\d+), expected=\d+", issue.detail)
            if match:
                 self.txt_curr.insert(0, match.group(1))

            match_inf = re.search(r"inferida como (\d+)/(\d+)", issue.detail)
            if match_inf:
                 self.txt_curr.insert(0, match_inf.group(1))
                 self.txt_total.insert(0, match_inf.group(2))
        else:
            self.btn_correct.config(state=tk.DISABLED)
            self.txt_curr.delete(0, tk.END)
            self.txt_total.delete(0, tk.END)
            
        self._display_preview(issue.pil_image)
        self._update_adj_ui()

    # ── History management ────────────────────────────────────────────────────

    def _refresh_history_tree(self):
        """Carga el historial desde disco y rellena el Treeview."""
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        entries = load_history()
        if not entries:
            self.history_tree.insert("", tk.END, text="  (sin historial)",
                                      values=("", "", "", "", ""))
            return

        for entry in entries:
            icon = "📁" if entry.is_folder else "📄"
            parent = self.history_tree.insert(
                "", tk.END,
                text=f"  {icon}  {entry.source_name}",
                values=(
                    entry.date,
                    entry.total_docs,
                    entry.total_complete,
                    entry.total_incomplete,
                    entry.total_inferred,
                ),
                open=False,
                tags=("folder" if entry.is_folder else "file",),
            )

            # Insert child rows for each PDF
            for pdf in entry.pdfs:
                self.history_tree.insert(
                    parent, tk.END,
                    text=f"      📄  {pdf.name}",
                    values=(
                        "",
                        pdf.total_docs,
                        pdf.complete,
                        pdf.incomplete,
                        pdf.inferred,
                    ),
                    tags=("pdf_child",),
                )

        # Tag colors
        self.history_tree.tag_configure("folder", foreground=FG)
        self.history_tree.tag_configure("file", foreground=FG)
        self.history_tree.tag_configure("pdf_child", foreground=DIM)

    def _clear_history(self):
        """Borra todo el historial después de confirmación."""
        if messagebox.askyesno("Limpiar historial",
                                "¿Estás seguro de que quieres borrar todo el historial?",
                                parent=self.root):
            clear_history()
            self._refresh_history_tree()

    def _open_history_location(self):
        """Abre la ubicación del item seleccionado en el historial."""
        sel = self.history_tree.selection()
        if not sel:
            return

        item = sel[0]
        # Try to get the source path from the item's text
        # For parent items, find the entry; for children, find the PDF path
        parent = self.history_tree.parent(item)

        entries = load_history()
        if parent:
            # It's a child (PDF) — find its entry
            parent_idx = self.history_tree.index(parent)
            if parent_idx < len(entries):
                child_idx = self.history_tree.index(item)
                entry = entries[parent_idx]
                if child_idx < len(entry.pdfs):
                    _open_in_explorer(Path(entry.pdfs[child_idx].path))
        else:
            # It's a parent (folder/file)
            idx = self.history_tree.index(item)
            if idx < len(entries):
                _open_in_explorer(Path(entries[idx].source))

    # ── Main view UI helpers ──────────────────────────────────────────────────

    def _set_list_status(self, idx: int, status: str):
        current_text = self.pdf_listbox.get(idx)
        name_part = current_text[5:] if len(current_text) > 5 else current_text.strip()
        icon, color = _STATUS.get(status, ("?", FG))
        self.pdf_listbox.delete(idx)
        self.pdf_listbox.insert(idx, f"  {icon}  {name_part}")
        self.pdf_listbox.itemconfig(idx, fg=color)
        if status == "processing":
            self.pdf_listbox.see(idx)

    def _update_global_progress(self, done: int, total: int):
        pct = int(done / total * 100) if total > 0 else 0
        self.prog_global.config(value=pct)
        self.lbl_gprog.config(text=f"Global: PDF {done} / {total}")

    def _update_summary(self):
        adj_total = self._get_adjusted_total()
        self.lbl_total.config(text=f"Documentos: {self.total_docs}")
        self.lbl_ok.config(text=f"Completos: {self.total_complete}")
        self.lbl_inc.config(
            text=f"Incompletos: {self.total_incomplete}",
            fg=RED if self.total_incomplete > 0 else GREEN,
        )
        self.lbl_inf.config(text=f"Inferidas: {self.total_inferred}")
        delta = adj_total - self.total_docs
        if delta == 0:
            self.lbl_adjusted.config(text=f"Ajustado: {adj_total}", fg=ACCENT)
        elif delta > 0:
            self.lbl_adjusted.config(text=f"Ajustado: {adj_total} (+{delta})", fg=GREEN)
        else:
            self.lbl_adjusted.config(text=f"Ajustado: {adj_total} ({delta})", fg=RED)

    def _show_file_summary(self, docs: list[Document], filename: str):
        complete = [d for d in docs if d.is_complete]
        incomplete = [d for d in docs if not d.is_complete]
        total_inf = sum(len(d.inferred_pages) for d in docs)

        self._log_msg(f"\n── Resumen: {filename} ──", "section")
        self._log_msg(f"  Documentos: {len(docs)}  |  "
                       f"Completos: {len(complete)}  |  "
                       f"Incompletos: {len(incomplete)}  |  "
                       f"Inferidas: {total_inf}", "ok" if not incomplete else "warn")

        if incomplete:
            for d in incomplete:
                issues = []
                if not d.sequence_ok:
                    issues.append("secuencia rota")
                if d.found_total != d.declared_total:
                    issues.append(f"{d.found_total}/{d.declared_total} págs")
                if d.inferred_pages:
                    issues.append(f"{len(d.inferred_pages)} inferidas")
                self._log_msg(
                    f"    ⚠ Doc {d.index:>3} | pág PDF {d.start_pdf_page:>4} | "
                    + " | ".join(issues),
                    "warn",
                )

    def _log_msg(self, msg: str, level: str = "info"):
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n", level)
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    def _clear_log(self):
        self.log.config(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.config(state=tk.DISABLED)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        root = tk.Tk()
        PDFoverseerApp(root)
        root.mainloop()
    except Exception as e:
        import traceback
        traceback.print_exc()
        input("Presiona Enter para salir...")
