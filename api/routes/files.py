import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import fitz
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from api.database import has_reads
from api.state import SessionState, get_session
from api.worker import _recalculate_metrics

router = APIRouter()

PDF_ROOT = os.getenv("PDF_ROOT", "")


def _validate_path(path_str: str) -> Path:
    if not PDF_ROOT:
        raise HTTPException(400, "PDF_ROOT environment variable not set")
    p = Path(path_str).resolve()
    root = Path(PDF_ROOT).resolve()
    if not str(p).startswith(str(root)):
        raise HTTPException(400, "Path outside allowed root")
    return p


def _pdf_list_state(s: SessionState) -> list[dict]:
    result = []
    for p in s.pdf_list:
        p_str = str(p)
        st = (
            "done"
            if has_reads(s.session_id, p_str)
            else ("skipped" if p_str in s.skipped_pdfs else "pending")
        )
        result.append({"name": p.name, "path": p_str, "status": st})
    return result


class AddFolderRequest(BaseModel):
    path: str


class AddFilesRequest(BaseModel):
    paths: list[str]


def _open_file_dialog():
    """Opens a native tkinter file dialog for selecting PDFs."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    file_paths = filedialog.askopenfilenames(
        title="Seleccionar archivos PDF",
        filetypes=[("PDF", "*.pdf")],
    )
    root.destroy()
    return list(file_paths)


def _open_folder_dialog():
    """Opens a native tkinter folder dialog."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    folder = filedialog.askdirectory(title="Seleccionar carpeta con PDFs")
    root.destroy()
    return folder


def _add_pdfs_to_session(s: SessionState, paths: list[Path]):
    """Deduplicates paths and adds new PDFs to the session, counting pages."""
    existing = set(s.pdf_list)
    new_pdfs = [p for p in paths if p not in existing]
    s.pdf_list.extend(new_pdfs)
    for p in new_pdfs:
        p_str = str(p)
        if p_str not in s.page_counts:
            try:
                doc = fitz.open(p_str)
                s.page_counts[p_str] = len(doc)
                doc.close()
            except Exception:
                pass


@router.get("/browse")
def api_browse(s: SessionState = Depends(get_session)):
    """Opens native file dialog and adds selected PDFs to the session."""
    file_paths = _open_file_dialog()
    if not file_paths:
        return {"success": True, "pdfs": _pdf_list_state(s)}

    _add_pdfs_to_session(s, [Path(p) for p in file_paths])
    return {"success": True, "pdfs": _pdf_list_state(s)}


@router.get("/browse_folder")
def api_browse_folder(s: SessionState = Depends(get_session)):
    """Opens native folder dialog and adds all PDFs found recursively."""
    folder_path = _open_folder_dialog()
    if not folder_path:
        return {"success": True, "pdfs": _pdf_list_state(s)}

    folder = Path(folder_path)
    if not folder.is_dir():
        return {"success": True, "pdfs": _pdf_list_state(s)}

    pdfs = sorted(
        (p for p in folder.rglob("*.[pP][dD][fF]") if not p.name.startswith("~$")),
        key=lambda p: p.name,
    )
    _add_pdfs_to_session(s, pdfs)
    return {"success": True, "pdfs": _pdf_list_state(s)}


@router.post("/add_folder")
def api_add_folder(body: AddFolderRequest, s: SessionState = Depends(get_session)):
    """Appends all PDFs found recursively under the given folder path."""
    folder = _validate_path(body.path)
    if not folder.is_dir():
        raise HTTPException(400, "Path is not a directory")

    pdfs = [p for p in folder.rglob("*.[pP][dD][fF]") if not p.name.startswith("~$")]
    existing = set(s.pdf_list)
    new_pdfs = [p for p in pdfs if p not in existing]
    s.pdf_list.extend(new_pdfs)
    for p in new_pdfs:
        p_str = str(p)
        if p_str not in s.page_counts:
            try:
                doc = fitz.open(p_str)
                s.page_counts[p_str] = len(doc)
                doc.close()
            except Exception:
                pass

    return {
        "success": True,
        "pdfs": _pdf_list_state(s),
        "session_id": s.session_id,
    }


@router.post("/add_files")
def api_add_files(body: AddFilesRequest, s: SessionState = Depends(get_session)):
    """Appends specific PDF file paths to the list."""
    validated = [_validate_path(p) for p in body.paths]
    existing = set(s.pdf_list)
    new_pdfs = [p for p in validated if p not in existing]
    s.pdf_list.extend(new_pdfs)
    for p in new_pdfs:
        p_str = str(p)
        if p_str not in s.page_counts:
            try:
                doc = fitz.open(p_str)
                s.page_counts[p_str] = len(doc)
                doc.close()
            except Exception:
                pass

    return {
        "success": True,
        "pdfs": _pdf_list_state(s),
        "session_id": s.session_id,
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

    return {"success": True, "pdfs": _pdf_list_state(s)}


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

        if os.name == "nt":
            os.startfile(str(path))
        else:
            # SECURITY: subprocess.call uses list form, no shell injection; path validated against pdf_list
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
