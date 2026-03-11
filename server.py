import os
import time
import asyncio
import threading
from pathlib import Path
from tkinter import filedialog
import tkinter as tk

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import fitz  # For quick page counting

# Core logic
from core.analyzer import analyze_pdf, re_infer_documents

app = FastAPI(title="PDFoverseer V3 API")

# Allow CORS for local Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_path = Path(os.path.dirname(os.path.abspath(__file__))) / 'frontend' / 'dist'
if frontend_path.exists():
    app.mount("/ui", StaticFiles(directory=str(frontend_path), html=True), name="ui")
    assets_path = frontend_path / "assets"
    if assets_path.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_path)), name="assets")
else:
    print(f"Warning: UI directory {frontend_path} not found. Build the frontend first.")

from fastapi.responses import RedirectResponse
@app.get("/")
def read_root():
    return RedirectResponse(url="/ui/")

# --- Global State ---
class SummaryMetrics(BaseModel):
    docs: int = 0
    complete: int = 0
    incomplete: int = 0
    inferred: int = 0
    total_time: float = 0.0

class ServerState:
    def __init__(self):
        self.running: bool = False
        self.stop_requested: bool = False
        self.skip_current: bool = False
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.cancel_event = threading.Event()
        
        self.pdf_list: list[Path] = []
        self.pdf_reads: dict[str, list] = {}
        
        self.global_total_pages: int = 0
        self.global_done_pages: int = 0
        self.total_docs: int = 0
        self.total_complete: int = 0
        self.total_incomplete: int = 0
        self.total_inferred: int = 0
        self.issues: list[dict] = []
        self.start_time: float = 0.0
        self.pause_start_time: float = 0.0
        self.total_paused_time: float = 0.0
        self.loop = None

state = ServerState()

@app.on_event("startup")
def startup_event():
    # Capture the main asyncio loop so background threads can broadcast
    state.loop = asyncio.get_running_loop()

# --- WebSocket Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except RuntimeError:
                # Connection might be closed, gracefully handle
                pass

manager = ConnectionManager()

# --- Thread-Safe Broadcasters ---
def _emit(event_type: str, payload: dict):
    """Schedules a broadcast on the main asyncio event loop."""
    if state.loop and state.loop.is_running():
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": event_type, "payload": payload}), 
            state.loop
        )

# --- Endpoints ---

@app.get("/api/add_folder")
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
    
    return {
        "success": True, 
        "pdfs": [{"name": p.name, "path": str(p), "status": "pending"} for p in state.pdf_list]
    }

@app.get("/api/add_files")
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
    
    return {
        "success": True, 
        "pdfs": [{"name": p.name, "path": str(p), "status": "pending"} for p in state.pdf_list]
    }

import json
from datetime import datetime

@app.get("/api/debug_add")
def api_debug_add(path: str):
    p = Path(path)
    if p not in state.pdf_list:
        state.pdf_list.append(p)
    return {"success": True, "pdfs": [{"name": p.name, "path": str(p), "status": "pending"} for p in state.pdf_list]}

class StartProcessRequest(BaseModel):
    start_index: int = 0

class DeleteSessionRequest(BaseModel):
    timestamp: str

@app.get("/api/state")
def api_get_state():
    """Returns the current backend state so React can survive an F5 refresh."""
    return {
        "running": state.running,
        "pdf_list": [{"name": p.name, "path": str(p), "status": "pending"} for p in state.pdf_list],
        "issues": state.issues,
        "metrics": {
            "docs": state.total_docs,
            "complete": state.total_complete,
            "incomplete": state.total_incomplete,
            "inferred": state.total_inferred
        },
        "globalProg": {"done": state.global_done_pages, "total": state.global_total_pages}
    }

@app.post("/api/reset")
def api_reset():
    """Hard wipe of the backend state to start a new session."""
    state.pdf_list = []
    state.pdf_reads = {}
    state.issues = []
    state.total_docs = 0
    state.total_complete = 0
    state.total_incomplete = 0
    state.total_inferred = 0
    state.global_total_pages = 0
    state.global_done_pages = 0
    state.running = False
    state.start_time = 0.0
    return {"success": True}

@app.post("/api/save_session")
def api_save_session():
    """Saves the current final metrics and issues to a local JSON history file."""
    sessions_dir = Path(__file__).parent / "data" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = sessions_dir / f"session_{timestamp}.json"
    
    data = {
        "timestamp": timestamp,
        "metrics": {
            "docs": state.total_docs,
            "complete": state.total_complete,
            "incomplete": state.total_incomplete,
            "inferred": state.total_inferred,
            "total_time": time.time() - state.start_time if state.start_time > 0 else 0.0
        },
        "issues_count": len(state.issues),
        "files_processed": len(state.pdf_list)
    }
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return {"success": True, "path": str(filepath)}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/sessions")
def api_list_sessions():
    """Returns a list of saved historical sessions."""
    sessions_dir = Path(__file__).parent / "data" / "sessions"
    if not sessions_dir.exists():
        return {"sessions": []}
        
    sessions = []
    for f in sessions_dir.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as jf:
                sessions.append(json.load(jf))
        except:
            pass
            
    sessions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return {"sessions": sessions}

@app.post("/api/delete_session")
def api_delete_session(req: DeleteSessionRequest):
    """Deletes a saved session from the local history."""
    sessions_dir = Path(__file__).parent / "data" / "sessions"
    filepath = sessions_dir / f"session_{req.timestamp}.json"
    
    if filepath.exists():
        try:
            filepath.unlink()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    return {"success": False, "error": "File not found"}

@app.post("/api/start")
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
        state.pdf_reads = {}
    else:
        # Retain history of previously parsed files
        kept_pdfs = [str(p) for p in state.pdf_list[:req.start_index]]
        state.issues = [i for i in state.issues if i["pdf_path"] in kept_pdfs]
        state.pdf_reads = {k: v for k, v in state.pdf_reads.items() if k in kept_pdfs}
    
    state.global_total_pages = 0
    state.global_done_pages = 0
    state.total_paused_time = 0.0
    state.pause_start_time = 0.0
    
    # Start the worker thread
    threading.Thread(target=_process_pdfs, args=(req.start_index,), daemon=True).start()
    return {"success": True}

@app.post("/api/stop")
async def api_stop():
    if not state.running:
        return {"success": False}
    state.stop_requested = True
    state.cancel_event.set()
    _emit("log", {"msg": "🛑 Proceso detenido (abortando).", "level": "error"})
    return {"success": True}

@app.post("/api/skip")
async def api_skip():
    if not state.running:
        return {"success": False}
    state.skip_current = True
    state.cancel_event.set()
    _emit("log", {"msg": "⏭ Saltando archivo actual...", "level": "warn"})
    return {"success": True}

@app.post("/api/pause")
async def api_pause():
    if not state.running:
        return {"success": False}
    state.pause_event.clear()
    state.pause_start_time = time.time()
    _emit("log", {"msg": "⏸ Análisis en pausa.", "level": "warn"})
    _emit("global_progress", {"paused": True, "done": state.global_done_pages, "total": state.global_total_pages})
    return {"success": True}

@app.post("/api/resume")
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

# --- Background Worker ---
def _process_pdfs(start_index: int = 0):
    _emit("log", {"msg": "Pre-calculando páginas del lote...", "level": "info"})
    try:
        total_pages = 0
        done_pages = 0
        for i, pdf_path in enumerate(state.pdf_list):
            doc = fitz.open(str(pdf_path))
            num_pages = len(doc)
            total_pages += num_pages
            if i < start_index:
                done_pages += num_pages
            doc.close()
            
        state.global_total_pages = total_pages
        state.global_done_pages = done_pages
        _emit("global_progress", {"done": done_pages, "total": total_pages, "elapsed": 0.0, "eta": 0.0})
        _emit("log", {"msg": f"Total a procesar: {total_pages} páginas.", "level": "success"})
    except Exception as e:
        _emit("log", {"msg": f"Error calculando páginas: {e}", "level": "error"})
        return

    _emit("log", {"msg": "Iniciando análisis profundo...", "level": "section"})
    
    state.start_time = time.time()
    last_metrics_refresh = 0

    for idx in range(start_index, len(state.pdf_list)):
        pdf_path = state.pdf_list[idx]
        if state.skip_current:
            state.skip_current = False
            _emit("status_update", {"idx": idx, "status": "skipped"})
            continue
            
        if state.stop_requested:
            _emit("status_update", {"idx": idx, "status": "error"})
            break
            
        _emit("status_update", {"idx": idx, "status": "processing"})
        _emit("log", {"msg": f"\n📄 [{idx+1}/{len(state.pdf_list)}] {pdf_path.name}", "level": "file_hdr"})
        
        def on_progress(done, total):
            state.global_done_pages += 1
            
            elapsed_raw = time.time() - state.start_time if state.start_time > 0 else 0
            active_pause = (time.time() - state.pause_start_time) if state.pause_start_time > 0 else 0
            elapsed = max(0.0, elapsed_raw - state.total_paused_time - active_pause)
            
            eta = 0
            if elapsed > 0 and (state.global_done_pages - done_pages) > 0:
                pages_per_seg = (state.global_done_pages - done_pages) / elapsed
                missing_pages = state.global_total_pages - state.global_done_pages
                eta = missing_pages / pages_per_seg if pages_per_seg > 0 else 0
                
            _emit("file_progress", {"done": done, "total": total, "filename": pdf_path.name})
            _emit("global_progress", {
                "done": state.global_done_pages, 
                "total": state.global_total_pages,
                "elapsed": elapsed,
                "eta": eta,
                "paused": not state.pause_event.is_set()
            })
            
            # Periodically recalculate metrics live (every 5 pages approx to avoid UI lag)
            nonlocal last_metrics_refresh
            now = time.time()
            if now - last_metrics_refresh > 1.0:
                _recalculate_metrics()
                last_metrics_refresh = now
            
        def on_log(msg, level="info"):
            _emit("log", {"msg": msg, "level": level})
            
        def on_issue(page, kind, detail, pil_img):
            issue = {
                "id": len(state.issues),
                "pdf_path": str(pdf_path),
                "filename": pdf_path.name,
                "page": page,
                "type": kind,
                "detail": detail,
            }
            state.issues.append(issue)
            _emit("new_issue", issue)

        state.cancel_event.clear()
        
        try:
            docs, reads = analyze_pdf(
                str(pdf_path), 
                on_progress, 
                on_log,
                pause_event=state.pause_event,
                cancel_event=state.cancel_event,
                on_issue=on_issue,
                doc_mode="charla"
            )
            
            if state.stop_requested:
                on_log(f"Análisis abortado a petición del usuario. Extrayendo datos parciales...", "warn")
                break
            
            state.pdf_reads[str(pdf_path)] = reads
            
            _recalculate_metrics()
            
            if state.stop_requested:
                _emit("status_update", {"idx": idx, "status": "error"})
                break
                
            if state.skip_current:
                state.skip_current = False
                _emit("status_update", {"idx": idx, "status": "skipped"})
                continue
                
            _emit("status_update", {"idx": idx, "status": "done"})
            
        except Exception as e:
            _emit("log", {"msg": f"Error procesando {pdf_path.name}: {e}", "level": "error"})
            _emit("status_update", {"idx": idx, "status": "error"})
            
        _emit("global_progress", {"done": idx + 1, "total": len(state.pdf_list), "elapsed": time.time() - state.start_time, "eta": 0})
        
    state.running = False
    
    elapsed_total = time.time() - state.start_time if state.start_time > 0 else 0
    
    _emit("process_finished", {
        "metrics": {
            "docs": state.total_docs,
            "complete": state.total_complete,
            "incomplete": state.total_incomplete,
            "inferred": state.total_inferred,
            "total_time": elapsed_total
        }
    })
    _emit("log", {"msg": f"\n🏁 Proceso completado en {elapsed_total:.1f}s", "level": "ok"})

# --- Human-in-the-Loop ---
from fastapi.responses import Response

class CorrectRequest(BaseModel):
    pdf_path: str
    page: int
    correct_curr: int
    correct_tot: int

@app.post("/api/correct")
def api_correct(req: CorrectRequest):
    pdf_str = req.pdf_path
    if pdf_str not in state.pdf_reads:
        return {"success": False, "msg": "PDF reads no encontrados en memoria"}
        
    reads = state.pdf_reads[pdf_str]
    corrections = {req.page: (req.correct_curr, req.correct_tot)}
    
    def on_issue(page, kind, detail, pil_img, _path=pdf_str):
        issue = {
            "id": len(state.issues),
            "pdf_path": _path,
            "filename": Path(_path).name,
            "page": page,
            "type": kind,
            "detail": detail,
        }
        state.issues.append(issue)

    _emit("log", {"msg": f"Recalculando inferencia para {Path(pdf_str).name}...", "level": "info"})
    
    # Remove old issues for this PDF from state
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
    
    # Send event to trigger issue refresh on frontend, scoped to this PDF
    surviving = [i for i in state.issues if i["pdf_path"] == pdf_str]
    _emit("issues_refresh", {
        "pdf_path": pdf_str,
        "issues": surviving
    })
    return {"success": True}

class ExcludeRequest(BaseModel):
    pdf_path: str
    page: int

import subprocess
import os
import sys

@app.get("/api/open_pdf")
def api_open_pdf(pdf_path: str, page: int = 1):
    """Opens the PDF file in the user's default native OS viewer."""
    try:
        path = Path(pdf_path)
        if not path.exists():
            return {"success": False, "error": "File not found"}
            
        if os.name == 'nt': # Windows
            os.startfile(str(path))
        else: # macOS / Linux
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.call([opener, str(path)])
            
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/exclude")
def api_exclude(req: ExcludeRequest):
    pdf_str = req.pdf_path
    if pdf_str not in state.pdf_reads:
        return {"success": False, "msg": "PDF reads no encontrados en memoria"}
        
    reads = state.pdf_reads[pdf_str]
    exclusions = [req.page]
    
    def on_issue(page, kind, detail, pil_img, _path=pdf_str):
        issue = {
            "id": len(state.issues),
            "pdf_path": _path,
            "filename": Path(_path).name,
            "page": page,
            "type": kind,
            "detail": detail,
        }
        state.issues.append(issue)

    _emit("log", {"msg": f"Excluyendo página {req.page} y recalculando {Path(pdf_str).name}...", "level": "info"})
    
    # Remove old issues for this PDF from state
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
    surviving = [i for i in state.issues if i["pdf_path"] == pdf_str]
    _emit("issues_refresh", {
        "pdf_path": pdf_str,
        "issues": surviving
    })
    return {"success": True}

def _recalculate_metrics():
    # Recalculate the global metrics across all processed PDFs
    total_docs = 0
    total_complete = 0
    total_incomplete = 0
    total_inferred = 0
    from core.analyzer import _build_documents
    for path, reads in state.pdf_reads.items():
        # Rebuild docs purely to count them
        docs = _build_documents(reads, lambda m, l: None, lambda p, k, d: None)
        complete = [d for d in docs if d.is_complete]
        incomplete = [d for d in docs if not d.is_complete]
        inferred = sum(len(d.inferred_pages) for d in docs)
        
        total_docs += len(docs)
        total_complete += len(complete)
        total_incomplete += len(incomplete)
        total_inferred += inferred
        
    state.total_docs = total_docs
    state.total_complete = total_complete
    state.total_incomplete = total_incomplete
    state.total_inferred = total_inferred
    
    # Calculate PDF confidences and individual metrics
    pdf_confidences = {}
    pdf_metrics = {}
    for path, reads in state.pdf_reads.items():
        valid_reads = [r for r in reads if r.method != "excluded"]
        if not valid_reads:
            pdf_confidences[path] = 1.0
        else:
            pdf_confidences[path] = sum(r.confidence for r in valid_reads) / len(valid_reads)
            
        # Also rebuild docs to calculate individual stats per file
        docs = _build_documents(reads, lambda m, l: None, lambda p, k, d: None)
        complete = [d for d in docs if d.is_complete]
        incomplete = [d for d in docs if not d.is_complete]
        inferred = sum(len(d.inferred_pages) for d in docs)
        pdf_metrics[path] = {
            "docs": len(docs),
            "complete": len(complete),
            "incomplete": len(incomplete),
            "inferred": inferred
        }
            
    _emit("metrics", {
        "docs": state.total_docs,
        "complete": state.total_complete,
        "incomplete": state.total_incomplete,
        "inferred": state.total_inferred,
        "confidences": pdf_confidences,
        "individual": pdf_metrics
    })

@app.get("/api/preview")
def api_preview(pdf_path: str, page: int):
    import fitz
    try:
        doc = fitz.open(pdf_path)
        pdf_page = doc[page - 1]
        
        # Render top 20%
        rect = pdf_page.rect
        crop = fitz.Rect(0, 0, rect.width, rect.height * 0.25)
        pix = pdf_page.get_pixmap(matrix=fitz.Matrix(3.0, 3.0), clip=crop)
        
        doc.close()
        # Return as image/png
        return Response(content=pix.tobytes("png"), media_type="image/png")
    except Exception as e:
        return {"success": False, "msg": str(e)}

# --- WebSocket ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming WS messages if necessary (ping/pong)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
