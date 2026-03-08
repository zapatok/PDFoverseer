"""
PDFoverseer  —  Supervisor de PDFs en carpeta
==============================================
Selecciona una carpeta (o un PDF individual) y analiza todos los PDFs
encontrados en orden, usando la lógica core de pdfcount.py (OCR + state
machine).  Permite pausar / reanudar el proceso y visualizar las páginas
problemáticas en una vista de detalle.
"""

from __future__ import annotations

import os
import subprocess
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Optional

from PIL import Image, ImageTk

from core.analyzer import Document, analyze_pdf

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
}


# ── Issue data ────────────────────────────────────────────────────────────────

@dataclass
class PageIssue:
    pdf_path:   Path
    pdf_page:   int
    issue_type: str       # "inferida", "huérfana", "secuencia rota"
    detail:     str
    pil_image:  Image.Image


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_pdfs(folder: str) -> list[Path]:
    """Busca PDFs recursivamente y los devuelve ordenados por nombre."""
    result = []
    for root, _dirs, files in os.walk(folder):
        for f in sorted(files):
            if f.lower().endswith(".pdf"):
                result.append(Path(root) / f)
    return result


def _open_in_explorer(path: Path):
    """Abre el explorador de archivos con el archivo seleccionado."""
    try:
        subprocess.Popen(f'explorer /select,"{path}"')
    except Exception:
        pass


# ── Aplicación ────────────────────────────────────────────────────────────────

class PDFoverseerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PDFoverseer")
        self.root.geometry("1060x720")
        self.root.minsize(820, 580)
        self.root.configure(bg=BG)

        # State
        self.pdf_list: list[Path] = []
        self.running = False
        self.pause_event = threading.Event()
        self.pause_event.set()

        # Global accumulators
        self.total_docs = 0
        self.total_complete = 0
        self.total_incomplete = 0
        self.total_inferred = 0

        # Issues store
        self.issues: list[PageIssue] = []
        self._current_preview_tk: Optional[ImageTk.PhotoImage] = None

        # Build both views
        self._build_shared_top()
        self._build_main_view()
        self._build_detail_view()

        # Start on main
        self._show_main()

    # ══════════════════════════════════════════════════════════════════════════
    # ── Shared top bar (always visible) ───────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════════════

    def _build_shared_top(self):
        # ── Buttons ───────────────────────────────────────────────────────────
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

        self.btn_pause = tk.Button(
            top, text="⏸  Pausar", command=self._toggle_pause,
            bg=SURFACE, fg=FG, font=("Segoe UI", 10, "bold"),
            activebackground="#45475a", activeforeground=FG,
            padx=14, pady=5, relief=tk.FLAT, cursor="hand2",
            state=tk.DISABLED,
        )
        self.btn_pause.pack(side=tk.LEFT, padx=10)

        self.btn_issues = tk.Button(
            top, text="⚠  Ver Problemas (0)", command=self._show_detail,
            bg=SURFACE, fg=DIM, font=("Segoe UI", 10, "bold"),
            activebackground="#45475a", activeforeground=FG,
            padx=14, pady=5, relief=tk.FLAT, cursor="hand2",
            state=tk.DISABLED,
        )
        self.btn_issues.pack(side=tk.LEFT)

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

        # Top bar with back button
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

        # Paned: issues list + preview
        paned = tk.PanedWindow(self.detail_frame, orient=tk.HORIZONTAL, bg=BG,
                                sashwidth=6, sashrelief=tk.FLAT)
        paned.pack(fill=tk.BOTH, expand=True, padx=14, pady=(2, 12))

        # LEFT: Issues list
        left = tk.Frame(paned, bg=BG_PANEL, highlightbackground=SURFACE,
                         highlightthickness=1)
        paned.add(left, width=380, minsize=280)

        tk.Label(left, text="Páginas con problemas", fg=ORANGE, bg=BG_PANEL,
                 font=("Segoe UI", 10, "bold"), anchor="w",
                 padx=8, pady=6).pack(fill=tk.X)

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

        # Button bar under issues list
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

        # RIGHT: Image preview
        right = tk.Frame(paned, bg=BG_PANEL, highlightbackground=SURFACE,
                          highlightthickness=1)
        paned.add(right, minsize=400)

        self.lbl_preview_title = tk.Label(
            right, text="Selecciona un problema para ver la página",
            fg=DIM, bg=BG_PANEL, font=("Segoe UI", 10, "bold"),
            anchor="w", padx=8, pady=6,
        )
        self.lbl_preview_title.pack(fill=tk.X)

        # Scrollable canvas for the image
        preview_outer = tk.Frame(right, bg=BG_LOG)
        preview_outer.pack(fill=tk.BOTH, expand=True)

        self.preview_canvas = tk.Canvas(
            preview_outer, bg=BG_LOG, highlightthickness=0,
        )

        sb_pv = tk.Scrollbar(preview_outer, orient=tk.VERTICAL,
                              command=self.preview_canvas.yview,
                              bg=SURFACE, troughcolor=BG_PANEL)
        sb_ph = tk.Scrollbar(preview_outer, orient=tk.HORIZONTAL,
                              command=self.preview_canvas.xview,
                              bg=SURFACE, troughcolor=BG_PANEL)

        self.preview_canvas.configure(yscrollcommand=sb_pv.set,
                                       xscrollcommand=sb_ph.set)

        sb_pv.pack(side=tk.RIGHT, fill=tk.Y)
        sb_ph.pack(side=tk.BOTTOM, fill=tk.X)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)

        self.preview_image_id = None

    # ── Frame switching ───────────────────────────────────────────────────────

    def _show_main(self):
        self.detail_frame.pack_forget()
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        self.btn_issues.config(
            text=f"⚠  Ver Problemas ({len(self.issues)})",
        )

    def _show_detail(self):
        self.main_frame.pack_forget()
        self.detail_frame.pack(fill=tk.BOTH, expand=True)
        self._refresh_issues_list()

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
        self._start_processing(None)

    def _start_processing(self, base_folder: str | None):
        # Ensure we're on main view
        self._show_main()

        # Populate listbox
        self.pdf_listbox.delete(0, tk.END)
        for p in self.pdf_list:
            if base_folder and p.is_relative_to(base_folder):
                rel = p.relative_to(base_folder)
            else:
                rel = p.name
            self.pdf_listbox.insert(tk.END, f"  ⏳  {rel}")
        self.pdf_listbox.config(fg=DIM)

        # Reset accumulators
        self.total_docs = 0
        self.total_complete = 0
        self.total_incomplete = 0
        self.total_inferred = 0
        self._update_summary()

        # Reset issues
        self.issues.clear()
        self._update_issues_button()

        self.lbl_pdfs_count.config(text=f"PDFs: 0 / {len(self.pdf_list)}")

        # Clear log
        self._clear_log()

        # Start processing
        self.btn_folder.config(state=tk.DISABLED)
        self.btn_file.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL)
        self.running = True
        self.pause_event.set()
        threading.Thread(target=self._process_all, daemon=True).start()

    def _toggle_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.btn_pause.config(text="▶  Reanudar", bg=YELLOW, fg="#11111b")
            self._log_msg("⏸  Proceso en pausa", "warn")
        else:
            self.pause_event.set()
            self.btn_pause.config(text="⏸  Pausar", bg=SURFACE, fg=FG)
            self._log_msg("▶  Proceso reanudado", "info")

    # ── Processing ────────────────────────────────────────────────────────────

    def _process_all(self):
        total_pdfs = len(self.pdf_list)

        for idx, pdf_path in enumerate(self.pdf_list):
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

            # Capture current pdf_path for the closure
            _current_path = pdf_path

            def on_issue(page, kind, detail, pil_img, _path=_current_path):
                issue = PageIssue(
                    pdf_path=_path,
                    pdf_page=page,
                    issue_type=kind,
                    detail=detail,
                    pil_image=pil_img,
                )
                self.root.after(0, self._add_issue, issue)

            try:
                docs = analyze_pdf(str(pdf_path), on_progress, on_log,
                                   pause_event=self.pause_event,
                                   on_issue=on_issue)
                complete = [d for d in docs if d.is_complete]
                incomplete = [d for d in docs if not d.is_complete]
                inferred = sum(len(d.inferred_pages) for d in docs)

                self.total_docs += len(docs)
                self.total_complete += len(complete)
                self.total_incomplete += len(incomplete)
                self.total_inferred += inferred

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
            self.root.after(0, lambda i=idx + 1, t=total_pdfs:
                            self.lbl_pdfs_count.config(text=f"PDFs: {i} / {t}"))

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
        self.root.after(0, lambda: self.btn_pause.config(state=tk.DISABLED))

    # ── Issues management ─────────────────────────────────────────────────────

    def _add_issue(self, issue: PageIssue):
        """Agrega un issue y actualiza el botón / lista si está visible."""
        self.issues.append(issue)
        self._update_issues_button()

        # If detail view is visible, update list live
        if self.detail_frame.winfo_ismapped():
            self._append_issue_to_listbox(len(self.issues) - 1, issue)

    def _update_issues_button(self):
        count = len(self.issues)
        self.btn_issues.config(
            text=f"⚠  Ver Problemas ({count})",
            state=tk.NORMAL if count > 0 else tk.DISABLED,
            fg=ORANGE if count > 0 else DIM,
        )

    def _refresh_issues_list(self):
        """Reconstruye la lista completa de issues."""
        self.issues_listbox.delete(0, tk.END)
        self.lbl_issues_count.config(
            text=f"{len(self.issues)} problemas encontrados",
            fg=ORANGE if self.issues else DIM,
        )

        current_file = None
        for i, issue in enumerate(self.issues):
            if issue.pdf_path != current_file:
                current_file = issue.pdf_path
                # File header
                self.issues_listbox.insert(tk.END, f"📁 {issue.pdf_path.name}")
                self.issues_listbox.itemconfig(tk.END, fg=ACCENT)
            self._append_issue_to_listbox(i, issue)

    def _append_issue_to_listbox(self, idx: int, issue: PageIssue):
        """Agrega un solo issue al listbox."""
        # Check if we need a file header
        if idx == 0 or self.issues[idx - 1].pdf_path != issue.pdf_path:
            if self.detail_frame.winfo_ismapped():
                self.issues_listbox.insert(tk.END, f"📁 {issue.pdf_path.name}")
                last = self.issues_listbox.size() - 1
                self.issues_listbox.itemconfig(last, fg=ACCENT)

        icon = "🔮" if issue.issue_type == "inferida" else "⚠"
        line = f"  {icon}  Pág {issue.pdf_page} — {issue.issue_type}"
        self.issues_listbox.insert(tk.END, line)
        last = self.issues_listbox.size() - 1
        self.issues_listbox.itemconfig(
            last, fg=YELLOW if issue.issue_type == "inferida" else ORANGE,
        )
        # Store index mapping for selection
        self.issues_listbox.see(last)

        self.lbl_issues_count.config(
            text=f"{len(self.issues)} problemas encontrados", fg=ORANGE,
        )

    def _on_issue_select(self, event):
        """Al seleccionar un issue, mostrar la imagen de la página."""
        sel = self.issues_listbox.curselection()
        if not sel:
            return

        text = self.issues_listbox.get(sel[0])
        # Skip file headers
        if text.startswith("📁"):
            return

        # Find the actual issue — count non-header items up to sel[0]
        issue_idx = 0
        for i in range(sel[0]):
            t = self.issues_listbox.get(i)
            if not t.startswith("📁"):
                issue_idx += 1

        if issue_idx >= len(self.issues):
            return

        issue = self.issues[issue_idx]

        # Update title
        self.lbl_preview_title.config(
            text=f"Pág {issue.pdf_page}  —  {issue.issue_type}  —  {issue.pdf_path.name}",
            fg=ORANGE,
        )

        # Enable open location button
        self.btn_open_loc.config(state=tk.NORMAL)

        # Show image
        self._display_preview(issue.pil_image)

    def _display_preview(self, pil_img: Image.Image):
        """Muestra la imagen en el canvas con scroll."""
        # Fit to canvas width if possible
        canvas_w = self.preview_canvas.winfo_width()
        if canvas_w < 100:
            canvas_w = 600  # fallback

        img_w, img_h = pil_img.size
        scale = min(canvas_w / img_w, 1.5)  # don't upscale too much
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)

        resized = pil_img.resize((new_w, new_h), Image.LANCZOS)
        self._current_preview_tk = ImageTk.PhotoImage(resized)

        self.preview_canvas.delete("all")
        self.preview_image_id = self.preview_canvas.create_image(
            0, 0, anchor=tk.NW, image=self._current_preview_tk,
        )
        self.preview_canvas.config(scrollregion=(0, 0, new_w, new_h))

    def _open_issue_location(self):
        """Abre el explorador en la ubicación del PDF del issue seleccionado."""
        sel = self.issues_listbox.curselection()
        if not sel:
            return

        # Find actual issue
        issue_idx = 0
        for i in range(sel[0]):
            t = self.issues_listbox.get(i)
            if not t.startswith("📁"):
                issue_idx += 1

        text = self.issues_listbox.get(sel[0])
        if text.startswith("📁"):
            return

        if issue_idx < len(self.issues):
            _open_in_explorer(self.issues[issue_idx].pdf_path)

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
        self.lbl_total.config(text=f"Documentos: {self.total_docs}")
        self.lbl_ok.config(text=f"Completos: {self.total_complete}")
        self.lbl_inc.config(
            text=f"Incompletos: {self.total_incomplete}",
            fg=RED if self.total_incomplete > 0 else GREEN,
        )
        self.lbl_inf.config(text=f"Inferidas: {self.total_inferred}")

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
