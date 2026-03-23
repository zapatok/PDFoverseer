import time
import threading
from pathlib import Path
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core import re_infer_documents
from api.state import get_session, SessionState
from api.websocket import _emit
from api.worker import _process_pdfs, _recalculate_metrics
from api.database import get_reads, save_reads

router = APIRouter()

class StartProcessRequest(BaseModel):
    start_index: int = 0

class CorrectRequest(BaseModel):
    pdf_path: str
    page: int
    correct_curr: int
    correct_tot: int

class ExcludeRequest(BaseModel):
    pdf_path: str
    page: int

@router.post("/start")
async def api_start(req: StartProcessRequest, s: SessionState = Depends(get_session)):
    if s.running or not s.pdf_list:
        return {"success": False, "msg": "Already running or no PDFs loaded"}
    
    s.running = True
    s.stop_requested = False
    s.skip_current = False
    s.cancel_event.clear()
    s.pause_event.set()
    
    if req.start_index == 0:
        s.total_docs = 0
        s.total_complete = 0
        s.total_incomplete = 0
        s.total_inferred = 0
        s.issues = []
        s.skipped_pdfs.clear()
        s.confidences = {}
        s.individual_metrics = {}
        
        # Wait until Session tracking is passed inside _emit before broadcasting
        _emit(s.session_id, "metrics", {
            "docs": 0, "complete": 0, "incomplete": 0, "inferred": 0,
            "confidences": {}, "individual": {}
        })
        for i in range(len(s.pdf_list)):
            _emit(s.session_id, "status_update", {"idx": i, "status": "pending"})
            
    s.global_total_pages = 0
    s.global_done_pages = 0
    s.total_paused_time = 0.0
    s.pause_start_time = 0.0
    
    threading.Thread(target=_process_pdfs, args=(s.session_id, req.start_index), daemon=True).start()
    return {"success": True}

@router.post("/stop")
async def api_stop(s: SessionState = Depends(get_session)):
    if not s.running:
        return {"success": False}
    s.stop_requested = True
    s.cancel_event.set()
    s.pause_event.set()
    _emit(s.session_id, "log", {"msg": "🛑 Proceso detenido (abortando).", "level": "error"})
    return {"success": True}

@router.post("/skip")
async def api_skip(s: SessionState = Depends(get_session)):
    if not s.running:
        return {"success": False}
    s.skip_current = True
    s.cancel_event.set()
    s.pause_event.set()
    _emit(s.session_id, "log", {"msg": "⏭ Saltando archivo actual...", "level": "warn"})
    return {"success": True}

@router.post("/pause")
async def api_pause(s: SessionState = Depends(get_session)):
    if not s.running:
        return {"success": False}
    s.pause_event.clear()
    s.pause_start_time = time.time()
    _emit(s.session_id, "log", {"msg": "⏸ Análisis en pausa.", "level": "warn"})
    _emit(s.session_id, "global_progress", {"paused": True, "done": s.global_done_pages, "total": s.global_total_pages})
    return {"success": True}

@router.post("/resume")
async def api_resume(s: SessionState = Depends(get_session)):
    if not s.running:
        return {"success": False}
    s.pause_event.set()
    if s.pause_start_time > 0:
        s.total_paused_time += time.time() - s.pause_start_time
        s.pause_start_time = 0.0
    _emit(s.session_id, "log", {"msg": "▶ Reanudando análisis...", "level": "ok"})
    _emit(s.session_id, "global_progress", {"paused": False, "done": s.global_done_pages, "total": s.global_total_pages})
    return {"success": True}

@router.post("/correct")
def api_correct(req: CorrectRequest, s: SessionState = Depends(get_session)):
    pdf_str = req.pdf_path
    reads = get_reads(s.session_id, pdf_str)
    if not reads:
        return {"success": False, "msg": "PDF reads no encontrados en base de datos"}
        
    corrections = {req.page: (req.correct_curr, req.correct_tot)}
    
    def on_issue(page, kind, detail, pil_img, _path=pdf_str):
        with s._lock:
            issue = {
                "id": s.issue_counter,
                "pdf_path": _path,
                "filename": Path(_path).name,
                "page": page,
                "type": kind,
                "detail": detail,
                "impact": "sequence",
            }
            s.issue_counter += 1
            s.issues.append(issue)

    _emit(s.session_id, "log", {"msg": f"Recalculando inferencia para {Path(pdf_str).name}...", "level": "info"})

    with s._lock:
        s.issues = [i for i in s.issues if i["pdf_path"] != pdf_str]

    docs, new_reads = re_infer_documents(
        reads=reads,
        corrections=corrections,
        on_log=lambda msg, lvl="info": _emit(s.session_id, "log", {"msg": msg, "level": lvl}),
        on_issue=on_issue
    )
    
    save_reads(s.session_id, pdf_str, new_reads)
    _recalculate_metrics(s.session_id)
    _emit(s.session_id, "log", {"msg": "Inferencia completada, actualizando lista de problemas...", "level": "ok"})

    with s._lock:
        surviving = [i for i in s.issues if i["pdf_path"] == pdf_str]
    _emit(s.session_id, "issues_refresh", {
        "pdf_path": pdf_str,
        "issues": surviving
    })
    return {"success": True}

@router.post("/exclude")
def api_exclude(req: ExcludeRequest, s: SessionState = Depends(get_session)):
    pdf_str = req.pdf_path
    reads = get_reads(s.session_id, pdf_str)
    if not reads:
        return {"success": False, "msg": "PDF reads no encontrados en base de datos"}
        
    exclusions = [req.page]
    
    def on_issue(page, kind, detail, pil_img, _path=pdf_str):
        with s._lock:
            issue = {
                "id": s.issue_counter,
                "pdf_path": _path,
                "filename": Path(_path).name,
                "page": page,
                "type": kind,
                "detail": detail,
                "impact": "sequence",
            }
            s.issue_counter += 1
            s.issues.append(issue)

    _emit(s.session_id, "log", {"msg": f"Excluyendo página {req.page} y recalculando {Path(pdf_str).name}...", "level": "info"})

    with s._lock:
        s.issues = [i for i in s.issues if i["pdf_path"] != pdf_str]

    docs, new_reads = re_infer_documents(
        reads=reads,
        corrections={},
        on_log=lambda msg, lvl="info": _emit(s.session_id, "log", {"msg": msg, "level": lvl}),
        on_issue=on_issue,
        exclusions=exclusions
    )
    
    save_reads(s.session_id, pdf_str, new_reads)
    _recalculate_metrics(s.session_id)
    
    _emit(s.session_id, "log", {"msg": "Página excluida, actualizando métricas...", "level": "ok"})
    with s._lock:
        surviving = [i for i in s.issues if i["pdf_path"] == pdf_str]
    _emit(s.session_id, "issues_refresh", {
        "pdf_path": pdf_str,
        "issues": surviving
    })
    return {"success": True}
