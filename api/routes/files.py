import os
import sys
import subprocess
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
from fastapi import APIRouter, Response, Depends
import fitz

from api.state import get_session, SessionState
from api.worker import _recalculate_metrics
from api.database import get_reads

router = APIRouter()

@router.get("/add_folder")
def api_add_folder(s: SessionState = Depends(get_session)):
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
    
    existing = set(s.pdf_list)
    new_pdfs = [p for p in pdfs if p not in existing]
    s.pdf_list.extend(new_pdfs)
    
    pdf_list_state = []
    for p in s.pdf_list:
        p_str = str(p)
        st = "done" if len(get_reads(s.session_id, p_str)) > 0 else ("skipped" if p_str in s.skipped_pdfs else "pending")
        pdf_list_state.append({"name": p.name, "path": p_str, "status": st})
    
    return {
        "success": True, 
        "pdfs": pdf_list_state,
        "session_id": s.session_id
    }

@router.get("/add_files")
def api_add_files(s: SessionState = Depends(get_session)):
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
    
    existing = set(s.pdf_list)
    new_pdfs = [Path(p) for p in file_paths if Path(p) not in existing]
    s.pdf_list.extend(new_pdfs)
    
    pdf_list_state = []
    for p in s.pdf_list:
        p_str = str(p)
        st = "done" if len(get_reads(s.session_id, p_str)) > 0 else ("skipped" if p_str in s.skipped_pdfs else "pending")
        pdf_list_state.append({"name": p.name, "path": p_str, "status": st})
        
    return {
        "success": True, 
        "pdfs": pdf_list_state,
        "session_id": s.session_id
    }

@router.post("/remove_pdf")
def api_remove_pdf(pdf_path: str, s: SessionState = Depends(get_session)):
    new_list = []
    removed_path = None
    for p in s.pdf_list:
        if str(p) == pdf_path:
            removed_path = str(p)
        else:
            new_list.append(p)
            
    if removed_path:
        s.pdf_list = new_list
        s.skipped_pdfs.discard(removed_path)
        s.confidences.pop(removed_path, None)
        s.individual_metrics.pop(removed_path, None)
        with s._lock:
            s.issues = [i for i in s.issues if i["pdf_path"] != removed_path]
        
        # NOTE: If we want to fully clean the database we should do it here, but no big deal.
        _recalculate_metrics(s.session_id)
        
    pdf_list_state = []
    for p in s.pdf_list:
        p_str = str(p)
        st = "done" if len(get_reads(s.session_id, p_str)) > 0 else ("skipped" if p_str in s.skipped_pdfs else "pending")
        pdf_list_state.append({"name": p.name, "path": p_str, "status": st})
        
    return {"success": True, "pdfs": pdf_list_state}

@router.get("/debug_add")
def api_debug_add(path: str, s: SessionState = Depends(get_session)):
    p = Path(path)
    if p.suffix.lower() != ".pdf":
        return {"success": False, "msg": "Not a PDF file"}
    if p not in s.pdf_list:
        s.pdf_list.append(p)
    return {"success": True, "pdfs": [{"name": p.name, "path": str(p), "status": "pending"} for p in s.pdf_list]}

@router.get("/open_pdf")
def api_open_pdf(pdf_path: str, page: int = 1, s: SessionState = Depends(get_session)):
    """Opens the PDF file in the user's default native OS viewer."""
    try:
        allowed_paths = {str(p) for p in s.pdf_list}
        if pdf_path not in allowed_paths:
            return {"success": False, "error": "PDF not in list"}

        path = Path(pdf_path)
        if not path.exists():
            return {"success": False, "error": "File not found"}
        if path.suffix.lower() != ".pdf":
            return {"success": False, "error": "Not a PDF file"}

        if os.name == 'nt':
            os.startfile(str(path))
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.call([opener, str(path)])

        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/preview")
def api_preview(pdf_path: str, page: int, s: SessionState = Depends(get_session)):
    allowed_paths = {str(p) for p in s.pdf_list}
    if pdf_path not in allowed_paths:
        return {"success": False, "msg": "PDF not in list"}

    doc = None
    try:
        doc = fitz.open(pdf_path)
        if not (1 <= page <= len(doc)):
            return {"success": False, "msg": "Page out of range"}

        pdf_page = doc[page - 1]

        rect = pdf_page.rect
        crop = fitz.Rect(0, 0, rect.width, rect.height * 0.25)
        pix = pdf_page.get_pixmap(matrix=fitz.Matrix(3.0, 3.0), clip=crop)

        return Response(content=pix.tobytes("png"), media_type="image/png")
    except Exception as e:
        return {"success": False, "msg": str(e)}
    finally:
        if doc is not None:
            doc.close()
