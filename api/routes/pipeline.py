import time
import threading
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel

from core import re_infer_documents
from api.state import state
from api.websocket import _emit
from api.worker import _process_pdfs, _recalculate_metrics

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
async def api_start(req: StartProcessRequest):
    if state.running or not state.pdf_list:
        return {"success": False, "msg": "Already running or no PDFs loaded"}
    
    state.running = True
    state.stop_requested = False
    state.skip_current = False
    state.cancel_event.clear()
    state.pause_event.set()
    
    if req.start_index == 0:
        state.total_docs = 0
        state.total_complete = 0
        state.total_incomplete = 0
        state.total_inferred = 0
        state.issues = []
        state.skipped_pdfs.clear()
        state.pdf_reads = {}
        state.confidences = {}
        
        # Broadcast visual reset to the UI instantly
        _emit("metrics", {
            "docs": 0, "complete": 0, "incomplete": 0, "inferred": 0,
            "confidences": {}, "individual": {}
        })
        for i in range(len(state.pdf_list)):
            _emit("status_update", {"idx": i, "status": "pending"})
            
    else:
        pass
    
    state.global_total_pages = 0
    state.global_done_pages = 0
    state.total_paused_time = 0.0
    state.pause_start_time = 0.0
    
    # Start the worker thread
    threading.Thread(target=_process_pdfs, args=(req.start_index,), daemon=True).start()
    return {"success": True}

@router.post("/stop")
async def api_stop():
    if not state.running:
        return {"success": False}
    state.stop_requested = True
    state.cancel_event.set()
    state.pause_event.set()
    _emit("log", {"msg": "🛑 Proceso detenido (abortando).", "level": "error"})
    return {"success": True}

@router.post("/skip")
async def api_skip():
    if not state.running:
        return {"success": False}
    state.skip_current = True
    state.cancel_event.set()
    state.pause_event.set()
    _emit("log", {"msg": "⏭ Saltando archivo actual...", "level": "warn"})
    return {"success": True}

@router.post("/pause")
async def api_pause():
    if not state.running:
        return {"success": False}
    state.pause_event.clear()
    state.pause_start_time = time.time()
    _emit("log", {"msg": "⏸ Análisis en pausa.", "level": "warn"})
    _emit("global_progress", {"paused": True, "done": state.global_done_pages, "total": state.global_total_pages})
    return {"success": True}

@router.post("/resume")
async def api_resume():
    if not state.running:
        return {"success": False}
    state.pause_event.set()
    if state.pause_start_time > 0:
        state.total_paused_time += time.time() - state.pause_start_time
        state.pause_start_time = 0.0
    _emit("log", {"msg": "▶ Reanudando análisis...", "level": "ok"})
    _emit("global_progress", {"paused": False, "done": state.global_done_pages, "total": state.global_total_pages})
    return {"success": True}

@router.post("/correct")
def api_correct(req: CorrectRequest):
    pdf_str = req.pdf_path
    if pdf_str not in state.pdf_reads:
        return {"success": False, "msg": "PDF reads no encontrados en memoria"}
        
    reads = state.pdf_reads[pdf_str]
    corrections = {req.page: (req.correct_curr, req.correct_tot)}
    
    def on_issue(page, kind, detail, pil_img, _path=pdf_str):
        with state._lock:
            issue = {
                "id": state.issue_counter,
                "pdf_path": _path,
                "filename": Path(_path).name,
                "page": page,
                "type": kind,
                "detail": detail,
                "impact": "sequence",
            }
            state.issue_counter += 1
            state.issues.append(issue)

    _emit("log", {"msg": f"Recalculando inferencia para {Path(pdf_str).name}...", "level": "info"})

    with state._lock:
        state.issues = [i for i in state.issues if i["pdf_path"] != pdf_str]

    # Re-infer
    docs, new_reads = re_infer_documents(
        reads=reads,
        corrections=corrections,
        on_log=lambda msg, lvl="info": _emit("log", {"msg": msg, "level": lvl}),
        on_issue=on_issue
    )
    state.pdf_reads[pdf_str] = new_reads

    # Recalculate globals entirely
    _recalculate_metrics()
    _emit("log", {"msg": "Inferencia completada, actualizando lista de problemas...", "level": "ok"})

    with state._lock:
        surviving = [i for i in state.issues if i["pdf_path"] == pdf_str]
    _emit("issues_refresh", {
        "pdf_path": pdf_str,
        "issues": surviving
    })
    return {"success": True}

@router.post("/exclude")
def api_exclude(req: ExcludeRequest):
    pdf_str = req.pdf_path
    if pdf_str not in state.pdf_reads:
        return {"success": False, "msg": "PDF reads no encontrados en memoria"}
        
    reads = state.pdf_reads[pdf_str]
    exclusions = [req.page]
    
    def on_issue(page, kind, detail, pil_img, _path=pdf_str):
        with state._lock:
            issue = {
                "id": state.issue_counter,
                "pdf_path": _path,
                "filename": Path(_path).name,
                "page": page,
                "type": kind,
                "detail": detail,
                "impact": "sequence",
            }
            state.issue_counter += 1
            state.issues.append(issue)

    _emit("log", {"msg": f"Excluyendo página {req.page} y recalculando {Path(pdf_str).name}...", "level": "info"})

    with state._lock:
        state.issues = [i for i in state.issues if i["pdf_path"] != pdf_str]

    # Re-infer
    docs, new_reads = re_infer_documents(
        reads=reads,
        corrections={},
        on_log=lambda msg, lvl="info": _emit("log", {"msg": msg, "level": lvl}),
        on_issue=on_issue,
        exclusions=exclusions
    )
    state.pdf_reads[pdf_str] = new_reads

    _recalculate_metrics()
    _emit("log", {"msg": "Página excluida, actualizando métricas...", "level": "ok"})
    with state._lock:
        surviving = [i for i in state.issues if i["pdf_path"] == pdf_str]
    _emit("issues_refresh", {
        "pdf_path": pdf_str,
        "issues": surviving
    })
    return {"success": True}
