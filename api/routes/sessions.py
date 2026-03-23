import json
import time
import re
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.state import get_session, SessionState
from api.database import get_reads, clear_session, has_reads

router = APIRouter()

class DeleteSessionRequest(BaseModel):
    timestamp: str

@router.get("/state")
def api_get_state(s: SessionState = Depends(get_session)):
    """Returns the current backend state so React can survive an F5 refresh."""
    pdf_list_state = []
    for p in s.pdf_list:
        p_str = str(p)
        st = "done" if has_reads(s.session_id, p_str) else ("skipped" if p_str in s.skipped_pdfs else "pending")
        pdf_list_state.append({"name": p.name, "path": p_str, "status": st})

    return {
        "running": s.running,
        "pdf_list": pdf_list_state,
        "issues": s.issues,
        "metrics": {
            "docs": s.total_docs,
            "complete": s.total_complete,
            "incomplete": s.total_incomplete,
            "inferred": s.total_inferred,
            "confidences": s.confidences,
            "individual": s.individual_metrics
        },
        "globalProg": {"done": s.global_done_pages, "total": s.global_total_pages}
    }

@router.post("/reset")
def api_reset(s: SessionState = Depends(get_session)):
    """Hard wipe of the backend state to start a new session."""
    s.pdf_list = []
    s.skipped_pdfs.clear()
    clear_session(s.session_id)
    s.issues = []
    s.total_docs = 0
    s.total_complete = 0
    s.total_incomplete = 0
    s.total_inferred = 0
    s.global_total_pages = 0
    s.global_done_pages = 0
    s.running = False
    s.start_time = 0.0
    s.confidences = {}
    s.individual_metrics = {}
    return {"success": True}

@router.post("/save_session")
def api_save_session(s: SessionState = Depends(get_session)):
    """Saves the current final metrics and issues to a local JSON history file."""
    sessions_dir = Path(__file__).parent.parent.parent / "data" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = sessions_dir / f"session_{timestamp}.json"
    
    data = {
        "timestamp": timestamp,
        "metrics": {
            "docs": s.total_docs,
            "complete": s.total_complete,
            "incomplete": s.total_incomplete,
            "inferred": s.total_inferred,
            "total_time": time.time() - s.start_time if s.start_time > 0 else 0.0
        },
        "issues_count": len(s.issues),
        "files_processed": len(s.pdf_list)
    }
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return {"success": True, "path": str(filepath)}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/sessions")
def api_list_sessions():
    """Returns a list of saved historical sessions."""
    sessions_dir = Path(__file__).parent.parent.parent / "data" / "sessions"
    if not sessions_dir.exists():
        return {"sessions": []}
        
    sessions = []
    for f in sessions_dir.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as jf:
                sessions.append(json.load(jf))
        except (json.JSONDecodeError, OSError):
            pass

    sessions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return {"sessions": sessions}

@router.post("/delete_session")
def api_delete_session(req: DeleteSessionRequest):
    """Deletes a saved session from the local history."""
    if not re.match(r'^\d{8}_\d{6}$', req.timestamp):
        return {"success": False, "error": "Invalid timestamp format"}
    sessions_dir = Path(__file__).parent.parent.parent / "data" / "sessions"
    filepath = sessions_dir / f"session_{req.timestamp}.json"
    
    if filepath.exists():
        try:
            filepath.unlink()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    return {"success": False, "error": "File not found"}
