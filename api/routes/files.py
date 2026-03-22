import os
import sys
import subprocess
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
from fastapi import APIRouter, Response
import fitz

from api.state import state
from api.worker import _recalculate_metrics

router = APIRouter()

@router.get("/add_folder")
def api_add_folder():
    """Opens a native Tkinter folder dialog and appends PDFs to the list."""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    folder = filedialog.askdirectory(title="Seleccionar carpeta de PDFs")
    root.destroy()
    
    if not folder:
        return {"success": False, "pdfs": []}
    
    path = Path(folder)
    pdfs = [p for p in path.rglob("*.[pP][dD][fF]") if not p.name.startswith("~$")]
    
    existing = set(state.pdf_list)
    new_pdfs = [p for p in pdfs if p not in existing]
    state.pdf_list.extend(new_pdfs)
    
    pdf_list_state = []
    for p in state.pdf_list:
        p_str = str(p)
        st = "done" if p_str in state.pdf_reads else ("skipped" if p_str in state.skipped_pdfs else "pending")
        pdf_list_state.append({"name": p.name, "path": p_str, "status": st})
    
    return {
        "success": True, 
        "pdfs": pdf_list_state
    }

@router.get("/add_files")
def api_add_files():
    """Opens a native Tkinter file dialog and appends paths."""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    file_paths = filedialog.askopenfilenames(
        title="Seleccionar archivos PDF",
        filetypes=[("PDF", "*.pdf")]
    )
    root.destroy()
    
    if not file_paths:
        return {"success": False, "pdfs": []}
    
    existing = set(state.pdf_list)
    new_pdfs = [Path(p) for p in file_paths if Path(p) not in existing]
    state.pdf_list.extend(new_pdfs)
    
    pdf_list_state = []
    for p in state.pdf_list:
        p_str = str(p)
        st = "done" if p_str in state.pdf_reads else ("skipped" if p_str in state.skipped_pdfs else "pending")
        pdf_list_state.append({"name": p.name, "path": p_str, "status": st})
        
    return {
        "success": True, 
        "pdfs": pdf_list_state
    }

@router.post("/remove_pdf")
def api_remove_pdf(pdf_path: str):
    new_list = []
    removed_path = None
    for p in state.pdf_list:
        if str(p) == pdf_path:
            removed_path = str(p)
        else:
            new_list.append(p)
            
    if removed_path:
        state.pdf_list = new_list
        state.skipped_pdfs.discard(removed_path)
        state.pdf_reads.pop(removed_path, None)
        state.confidences.pop(removed_path, None)
        with state._lock:
            state.issues = [i for i in state.issues if i["pdf_path"] != removed_path]
        _recalculate_metrics()
        
    pdf_list_state = []
    for p in state.pdf_list:
        p_str = str(p)
        st = "done" if p_str in state.pdf_reads else ("skipped" if p_str in state.skipped_pdfs else "pending")
        pdf_list_state.append({"name": p.name, "path": p_str, "status": st})
        
    return {"success": True, "pdfs": pdf_list_state}

@router.get("/debug_add")
def api_debug_add(path: str):
    p = Path(path)
    if p.suffix.lower() != ".pdf":
        return {"success": False, "msg": "Not a PDF file"}
    if p not in state.pdf_list:
        state.pdf_list.append(p)
    return {"success": True, "pdfs": [{"name": p.name, "path": str(p), "status": "pending"} for p in state.pdf_list]}

@router.get("/open_pdf")
def api_open_pdf(pdf_path: str, page: int = 1):
    """Opens the PDF file in the user's default native OS viewer."""
    try:
        allowed_paths = {str(p) for p in state.pdf_list}
        if pdf_path not in allowed_paths:
            return {"success": False, "error": "PDF not in list"}

        path = Path(pdf_path)
        if not path.exists():
            return {"success": False, "error": "File not found"}
        if path.suffix.lower() != ".pdf":
            return {"success": False, "error": "Not a PDF file"}

        if os.name == 'nt': # Windows
            os.startfile(str(path))
        else: # macOS / Linux
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.call([opener, str(path)])

        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/preview")
def api_preview(pdf_path: str, page: int):
    allowed_paths = {str(p) for p in state.pdf_list}
    if pdf_path not in allowed_paths:
        return {"success": False, "msg": "PDF not in list"}

    doc = None
    try:
        doc = fitz.open(pdf_path)
        if not (1 <= page <= len(doc)):
            return {"success": False, "msg": "Page out of range"}

        pdf_page = doc[page - 1]

        # Render top 25%
        rect = pdf_page.rect
        crop = fitz.Rect(0, 0, rect.width, rect.height * 0.25)
        pix = pdf_page.get_pixmap(matrix=fitz.Matrix(3.0, 3.0), clip=crop)

        return Response(content=pix.tobytes("png"), media_type="image/png")
    except Exception as e:
        return {"success": False, "msg": str(e)}
    finally:
        if doc is not None:
            doc.close()
