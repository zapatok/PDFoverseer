import threading
from pathlib import Path
import uuid
import time
from fastapi import Header, Depends

class SessionState:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._lock = threading.Lock()
        self.running: bool = False
        self.stop_requested: bool = False
        self.skip_current: bool = False
        self.skipped_pdfs: set[str] = set()
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.cancel_event = threading.Event()

        self.pdf_list: list[Path] = []
        
        # Disk-buffered via database.py
        # self.pdf_reads is GONE
        
        self.global_total_pages: int = 0
        self.global_done_pages: int = 0
        self.total_docs: int = 0
        self.total_complete: int = 0
        self.total_incomplete: int = 0
        self.total_inferred: int = 0
        self.issues: list[dict] = []
        self.issue_counter: int = 0
        self.start_time: float = 0.0
        self.pause_start_time: float = 0.0
        self.total_paused_time: float = 0.0
        self.confidences: dict[str, float] = {}
        self.individual_metrics: dict[str, dict] = {}
        
        self.last_accessed = time.time()

class SessionManager:
    def __init__(self):
        self._sessions: dict[str, SessionState] = {}
        self._lock = threading.Lock()
        
    def get_or_create(self, session_id: str = None) -> SessionState:
        if not session_id:
            session_id = str(uuid.uuid4())
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionState(session_id)
            self._sessions[session_id].last_accessed = time.time()
            return self._sessions[session_id]

session_manager = SessionManager()

from fastapi import Header, Query

async def get_session(
    x_session_id: str = Header(None),
    session_id: str = Query(None)
) -> SessionState:
    return session_manager.get_or_create(x_session_id or session_id)
